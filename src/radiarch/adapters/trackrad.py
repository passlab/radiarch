"""TrackRAD2025 dataset adapter — real MRI-linac cine loading (input-path only).

Charter §3 governs this module. TrackRAD2025 (LMUK-RADONC-PHYS-RES/TrackRAD2025)
is a *cine-MRI tumour-tracking* dataset. It contains **no dose and no beam
parameters**, so it **cannot validate dose accuracy** and must never be reported
as a dose benchmark. Its only sanctioned role here is a **smoke-test asset for
the input/loading path on real MRI-linac data**.

This module therefore does exactly three things, and refuses to do more:

1. **Loads only what TrackRAD really contains** — the sagittal cine frames, the
   tumour mask, and the JSON sidecars (field strength, frame rate, scanned
   region) — into an immutable :class:`TrackRADCase`. It fabricates nothing. The
   frames are raw MR signal intensity: **not** Hounsfield Units, **not** mass
   density.
2. **Provides a deterministic case checksum** so the Phase 0 reproducibility gate
   ("the same command twice gives the same number", Charter §5) can be
   demonstrated on real data once it lands.
3. **Quarantines the only path that invents TrackRAD's missing hard inputs**
   (a density volume, which normally comes from a CT, and beam parameters) behind
   an explicit, loudly-named barrier — :func:`to_smoke_test_bundles` — so a
   fabricated value can never *silently* reach an evaluation path (Charter §2.2).

Dataset layout consumed (verified against real cases A_001 / C_001, 2026-07-30 —
the card's documented names/axis-order do NOT match the release, so this follows
the bytes on disk, not the card)::

    <patient>/
      *field-strength.json     -> bare scalar, e.g. 0.35   (real file: "b-field-strength.json")
      *frame-rate.json         -> bare scalar, e.g. 8.0
      *scanned-region.json     -> bare string, e.g. "abdomen"
      images/<patient>_frames.mha        ITK size (T,H,W); numpy (H,W,T) — TIME is the LAST axis
      targets/<patient>_labels.mha       same layout, tumour mask       [labeled only]
      targets/<patient>_first_label.mha  ITK size (1,H,W)               [labeled only]

On load, frames/masks are canonicalised to **(T, H, W)** in memory (time first),
so downstream code can index ``frames[t]`` for a real 2D image.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

# The single sentence every caller (and reader) must internalise. Used verbatim
# in the guard exception so the reason travels with the failure.
TRACKRAD_IS_NOT_A_DOSE_BENCHMARK = (
    "TrackRAD2025 contains no dose and no beam parameters (Charter §3): it is an "
    "input/loading SMOKE-TEST asset only and must never be used to report, "
    "validate, or train against dose accuracy."
)

# Marker stamped into any geometry fabricated for a smoke test, so a placeholder
# is identifiable downstream (see :func:`is_placeholder_geometry`).
PLACEHOLDER_GEOMETRY_PREFIX = "PLACEHOLDER_TRACKRAD_"


# ---------------------------------------------------------------------------
# The real case — only fields TrackRAD actually contains
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TrackRADCase:
    """One TrackRAD patient's real data. Immutable; fabricates nothing.

    ``frames`` is canonicalised to **(T, H, W)** — axis 0 is TIME (a 2D+t cine),
    not spatial depth. The intensities are raw MR signal — not HU, not g/cm³ —
    which is precisely why this case cannot be turned into a real dose input
    without inventing data.
    """

    patient_id: str
    frames: np.ndarray                 # (T, H, W) — raw MR intensity, axis0 = time
    in_plane_spacing_mm: tuple         # (row_mm, col_mm) in-plane pixel spacing
    frame_thickness_mm: float          # slice thickness carried on the time axis (mm)
    mask: Optional[np.ndarray]         # (T, H, W) tumour mask (T may be 1 for first_label), or None
    field_strength_t: Optional[float]  # e.g. 0.35 or 1.5
    frame_rate_hz: Optional[float]     # e.g. 8.0
    scanned_region: Optional[str]      # "thorax" | "abdomen" | "pelvis"
    source_dir: str
    labeled: bool

    @property
    def n_frames(self) -> int:
        return int(self.frames.shape[0])


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _read_json_scalar_glob(patient_dir: Path, suffix: str) -> Optional[Any]:
    """Read a bare-scalar sidecar, tolerating the real ``b-`` prefix.

    The card documents ``field-strength.json`` but the release ships
    ``b-field-strength.json`` (confirmed on A_001 and C_001), so match by suffix.
    """
    hits = sorted(patient_dir.glob(f"*{suffix}"))
    if not hits:
        return None
    return json.loads(hits[0].read_text())


def _read_cine_mha(path: Path) -> tuple[np.ndarray, tuple, float]:
    """Read a cine/mask ``.mha`` and canonicalise to (T, H, W).

    On disk, ITK stores the time axis first (ITK axis 0), so
    ``GetArrayFromImage`` returns it *last* (numpy ``(H, W, T)``). We move it to
    the front. Returns ``(frames_thw, in_plane_spacing_mm, frame_thickness_mm)``.
    Imported lazily so importing this adapter never hard-requires SimpleITK.
    """
    import SimpleITK as sitk  # lazy

    img = sitk.ReadImage(str(path))
    arr = sitk.GetArrayFromImage(img)          # (H, W, T) — time last
    if arr.ndim != 3:
        raise ValueError(f"{path.name}: expected a 3D cine/mask, got shape {arr.shape}")
    frames = np.moveaxis(arr, -1, 0)           # -> (T, H, W)
    sx, sy, sz = (float(s) for s in img.GetSpacing())   # ITK (time, in-plane, in-plane)
    in_plane = (sy, sz)                         # the two 1×1 mm in-plane axes
    thickness = sx                              # slice thickness carried on the time axis
    return frames, in_plane, thickness


def load_case(patient_dir: str | Path) -> TrackRADCase:
    """Load one TrackRAD patient directory into a :class:`TrackRADCase`.

    Loads the *primary* scan (``<id>_frames.mha`` — additional ``_frames2/3``
    scans are ignored by design; the labeled set has a single scan per patient).
    Frames/masks are canonicalised to (T, H, W). Raises ``FileNotFoundError`` if
    the primary cine is missing.
    """
    patient_dir = Path(patient_dir)
    patient_id = patient_dir.name

    frames_path = patient_dir / "images" / f"{patient_id}_frames.mha"
    if not frames_path.is_file():
        # Fall back to any single primary cine (defensive against odd naming).
        candidates = sorted(
            p for p in (patient_dir / "images").glob("*_frames.mha")
            if p.stem.endswith("_frames")  # excludes *_frames2, *_frames3
        )
        if not candidates:
            raise FileNotFoundError(f"no primary <id>_frames.mha under {patient_dir/'images'}")
        frames_path = candidates[0]

    frames, in_plane, thickness = _read_cine_mha(frames_path)

    # Mask: prefer the full per-frame labels, else the first-frame label. Absent
    # for unlabeled patients — that's legal (labeled=False).
    targets = patient_dir / "targets"
    mask: Optional[np.ndarray] = None
    labeled = False
    for name in (f"{patient_id}_labels.mha", f"{patient_id}_first_label.mha"):
        mp = targets / name
        if mp.is_file():
            mask, _, _ = _read_cine_mha(mp)     # canonicalised to (T, H, W); T=1 for first_label
            labeled = True
            break

    return TrackRADCase(
        patient_id=patient_id,
        frames=frames,
        in_plane_spacing_mm=in_plane,
        frame_thickness_mm=thickness,
        mask=mask,
        field_strength_t=_read_json_scalar_glob(patient_dir, "field-strength.json"),
        frame_rate_hz=_read_json_scalar_glob(patient_dir, "frame-rate.json"),
        scanned_region=_read_json_scalar_glob(patient_dir, "scanned-region.json"),
        source_dir=str(patient_dir),
        labeled=labeled,
    )


def list_patient_dirs(root: str | Path) -> list[Path]:
    """Deterministically enumerate TrackRAD patient dirs under ``root``.

    Patient-LEVEL (Charter §2.4): each returned dir is one patient. Sorted so
    enumeration is reproducible across machines. A dir counts as a patient iff it
    has an ``images/`` subfolder with a primary cine.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and any((d / "images").glob("*_frames.mha")):
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Reproducibility — deterministic checksum over the REAL fields only
# ---------------------------------------------------------------------------
def case_checksum(case: TrackRADCase) -> str:
    """SHA-256 over a case's real content. Same case on disk → same checksum.

    This is the Phase 0 gate applied to data loading: it proves the loader is
    deterministic and that a case's bytes round-trip identically. It is an
    infrastructure check, not a scientific result.
    """
    h = hashlib.sha256()
    h.update(case.patient_id.encode("utf-8"))
    h.update(np.ascontiguousarray(case.frames).tobytes())
    h.update(str(case.frames.dtype).encode("utf-8"))
    h.update(repr(tuple(round(float(s), 6) for s in case.in_plane_spacing_mm)).encode("utf-8"))
    h.update(repr(round(float(case.frame_thickness_mm), 6)).encode("utf-8"))
    if case.mask is not None:
        h.update(b"MASK")
        h.update(np.ascontiguousarray(case.mask).tobytes())
        h.update(str(case.mask.dtype).encode("utf-8"))
    else:
        h.update(b"NOMASK")
    h.update(
        json.dumps(
            [case.field_strength_t, case.frame_rate_hz, case.scanned_region],
            sort_keys=True,
        ).encode("utf-8")
    )
    return h.hexdigest()


def assert_case_integrity(case: TrackRADCase) -> None:
    """Cheap data-integrity checks (a preview of the Phase 1 gate).

    Raises ``ValueError`` on anything that would make a case unusable even as a
    smoke input: wrong rank, empty, non-finite, or a mask whose spatial shape
    disagrees with the frames.
    """
    if case.frames.ndim != 3:
        raise ValueError(f"{case.patient_id}: frames must be 3D (T,H,W), got {case.frames.shape}")
    if case.frames.size == 0:
        raise ValueError(f"{case.patient_id}: frames are empty")
    if not np.all(np.isfinite(case.frames)):
        raise ValueError(f"{case.patient_id}: frames contain NaN/Inf")
    if case.mask is not None:
        # Mask is (T,H,W) or (H,W); its trailing 2 dims must match the frames'.
        if case.mask.shape[-2:] != case.frames.shape[-2:]:
            raise ValueError(
                f"{case.patient_id}: mask HxW {case.mask.shape[-2:]} "
                f"!= frames HxW {case.frames.shape[-2:]}"
            )


# ---------------------------------------------------------------------------
# Quarantined smoke-test bundle builder (Charter §2.2)
# ---------------------------------------------------------------------------
def is_placeholder_geometry(geometry_id: str) -> bool:
    """True if a geometry id was minted by the smoke-test path below."""
    return geometry_id.startswith(PLACEHOLDER_GEOMETRY_PREFIX)


def to_smoke_test_bundles(
    case: TrackRADCase,
    *,
    acknowledge_synthetic: bool,
    frame_index: int = 0,
):
    """Adapt a real TrackRAD frame into engine bundles **for a smoke test only**.

    TrackRAD lacks the two hard inputs a dose engine requires — a mass-density
    volume (normally CT-derived) and beam parameters. To exercise the
    input→engine path at all, those must be **fabricated**. This function makes
    that fabrication impossible to do by accident:

    * it refuses to run unless ``acknowledge_synthetic=True`` is passed
      explicitly;
    * every fabricated field is stamped with a ``PLACEHOLDER_``/``SYNTHETIC_``
      marker (``geometry_id`` starts with :data:`PLACEHOLDER_GEOMETRY_PREFIX`),
      so :func:`is_placeholder_geometry` and any eval guard can reject it.

    Returns ``(GeometryBundle, BeamModelBundle, weights)``. The **only** valid
    downstream use is the analytic engine's ``validate()``/``compute_dose()`` in
    a smoke test that asserts *shape*, never dose values. The real physics engine
    (MCsquare) will reject these bundles anyway — they carry no CT.
    """
    if acknowledge_synthetic is not True:
        raise RuntimeError(
            TRACKRAD_IS_NOT_A_DOSE_BENCHMARK
            + " to_smoke_test_bundles() fabricates the density and beam parameters "
            "TrackRAD lacks; call it with acknowledge_synthetic=True only from a "
            "smoke test that never asserts on dose values."
        )

    # Imported lazily: these pull in the full radiarch model layer, which the
    # loader/guard above deliberately do not require.
    from radiarch.models.beam_model import (
        BeamModelResult,
        FluenceElementSet,
        Modality,
        PerBeamElements,
    )
    from radiarch.models.geometry import CTMetadata, GeometryResult, GridSpec
    from radiarch.services.dose_engines.protocol import BeamModelBundle, GeometryBundle

    frame = case.frames[frame_index]                    # (H, W) real MR intensity
    vol = frame[None, :, :]                             # (nz=1, ny=H, nx=W)
    if case.mask is not None:
        mslice = case.mask[frame_index] if case.mask.ndim == 3 else case.mask
        mvol = (mslice[None, :, :] > 0).astype(np.uint16)
    else:
        mvol = np.zeros_like(vol, dtype=np.uint16)

    nz, ny, nx = vol.shape

    # PLACEHOLDER density: MR intensity is NOT mass density. Map it into a narrow
    # band around 1.0 g/cm³ purely to give the engine a well-formed array.
    lo, hi = float(vol.min()), float(vol.max())
    norm = (vol - lo) / (hi - lo + 1e-9)
    density = (0.9 + 0.2 * norm).astype(np.float32)     # FABRICATED "g/cm³"

    sx, sy = float(case.in_plane_spacing_mm[0]), float(case.in_plane_spacing_mm[1])
    sz = 1.0                                             # PLACEHOLDER z-spacing (no depth)

    geom = GeometryBundle(
        result=GeometryResult(
            geometry_id=f"{PLACEHOLDER_GEOMETRY_PREFIX}{case.patient_id}",
            density_grid_uri="memory://placeholder-trackrad",
            structure_masks_uri="memory://placeholder-trackrad",
            structure_index={"TUMOR": 1},
            grid_spec=GridSpec(
                spacing_mm=(sx, sy, sz),
                origin_mm=(0.0, 0.0, 0.0),
                size=(nx, ny, nz),
            ),
            frame_of_reference_uid=f"0.0.0.trackrad.placeholder.{case.patient_id}",
            ct_metadata=CTMetadata(num_slices=nz, patient_name="SYNTHETIC_TRACKRAD"),
            cache_key=f"{PLACEHOLDER_GEOMETRY_PREFIX}{case.patient_id}",
        ),
        density=density,
        masks=mvol,
        spacing_mm=(sx, sy, sz),
        # ct_hu / ct_image intentionally None: TrackRAD has no CT. MCsquare rejects.
    )

    bm = BeamModelBundle(
        result=BeamModelResult(
            beam_model_id=f"{PLACEHOLDER_GEOMETRY_PREFIX}BEAM",
            geometry_id=f"{PLACEHOLDER_GEOMETRY_PREFIX}{case.patient_id}",
            modality=Modality.proton_pbs,
            fluence_elements=FluenceElementSet(
                total_count=1,
                per_beam=[
                    PerBeamElements(
                        beam_id="PLACEHOLDER_B1",
                        element_count=1,
                        energy_layers=[100.0],
                        spots_per_layer=[1],
                    )
                ],
            ),
            beam_model_ref_uri="memory://placeholder-trackrad",
            machine_model_id="PLACEHOLDER",
            cache_key=f"{PLACEHOLDER_GEOMETRY_PREFIX}bm",
        ),
        plan=object(),                                  # PLACEHOLDER test double
    )
    weights = np.ones((1,), dtype=np.float32)           # PLACEHOLDER single weight
    return geom, bm, weights
