"""TrackRAD2025 data-integrity checks — the Phase 1 gate applied to real data.

Charter §5, Phase 1 ("Data integrity"): *every case loads; image/mask geometry
identical; no NaN/Inf; splits patient-level and asserted.* This module turns that
gate into concrete, per-case checks over the real TrackRAD sample, plus a
patient-level manifest so leakage is impossible by construction (Charter §2.4).

It reports; it never fabricates. A case that fails a check is recorded as a
failure with the reason — not silently repaired. Nothing here touches dose
(TrackRAD has none, Charter §3): the checks are about *ingestion correctness*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from radiarch.adapters import trackrad


@dataclass
class CaseIntegrity:
    """Per-patient integrity outcome. ``ok`` is the AND of every check."""

    patient_id: str
    ok: bool
    center: str                          # leading token of the id, e.g. "A"
    field_strength_t: Optional[float]
    frame_rate_hz: Optional[float]
    scanned_region: Optional[str]
    n_frames: int = 0
    height: int = 0
    width: int = 0
    in_plane_spacing_mm: tuple = ()
    frame_thickness_mm: float = 0.0
    dtype: str = ""
    intensity_min: float = 0.0
    intensity_max: float = 0.0
    labeled: bool = False
    mask_frames_labeled: int = 0         # frames whose mask has >0 tumour voxels
    mask_px_min: int = 0
    mask_px_max: int = 0
    checksum: str = ""
    checks: dict = field(default_factory=dict)   # check_name -> passed?
    failures: list = field(default_factory=list)  # human-readable reasons


def check_case(patient_dir: str | Path) -> CaseIntegrity:
    """Run every ingestion-integrity check on one patient directory."""
    patient_dir = Path(patient_dir)
    pid = patient_dir.name
    center = pid.split("_")[0]
    checks: dict[str, bool] = {}
    failures: list[str] = []

    def record(name: str, passed: bool, reason: str = "") -> None:
        checks[name] = bool(passed)
        if not passed:
            failures.append(reason or name)

    # --- loads at all -------------------------------------------------------
    try:
        case = trackrad.load_case(patient_dir)
        record("loads", True)
    except Exception as e:  # noqa: BLE001 — a load failure is a first-class result
        record("loads", False, f"load raised {type(e).__name__}: {e}")
        return CaseIntegrity(
            patient_id=pid, ok=False, center=center, field_strength_t=None,
            frame_rate_hz=None, scanned_region=None, checks=checks, failures=failures,
        )

    T, H, W = case.frames.shape
    record("frames_3d", case.frames.ndim == 3, f"frames not 3D: {case.frames.shape}")
    record("frames_nonempty", case.frames.size > 0, "frames empty")
    record("frames_finite", bool(np.all(np.isfinite(case.frames))), "frames contain NaN/Inf")
    # In-plane geometry: what actually matters is (a) the two axes are isotropic
    # and (b) the grid is ~1mm (the preprocessing claim). Real MHA headers store
    # 1mm as e.g. 0.998901, so use realistic tolerances, not exact equality — a
    # sub-percent deviation is header rounding, not corrupt data.
    sx, sy = case.in_plane_spacing_mm
    mean = (sx + sy) / 2 or 1.0
    record("inplane_isotropic", abs(sx - sy) / mean < 0.01,
           f"in-plane not isotropic: {case.in_plane_spacing_mm}")
    record("inplane_near_1mm", all(0.98 <= s <= 1.02 for s in case.in_plane_spacing_mm),
           f"in-plane spacing not ~1mm (preprocessing claim): {case.in_plane_spacing_mm}")
    record("sidecars_present",
           None not in (case.field_strength_t, case.frame_rate_hz, case.scanned_region),
           f"missing sidecar(s): B={case.field_strength_t} rate={case.frame_rate_hz} "
           f"region={case.scanned_region}")
    record("field_strength_known", case.field_strength_t in (0.35, 1.5),
           f"unexpected field strength {case.field_strength_t}")

    # --- mask geometry matches the frames ----------------------------------
    mask_frames_labeled = mask_px_min = mask_px_max = 0
    if case.mask is not None:
        record("mask_hw_matches_frames", case.mask.shape[-2:] == (H, W),
               f"mask HxW {case.mask.shape[-2:]} != frames HxW {(H, W)}")
        # mask time dim is either T (per-frame labels) or 1 (first_label only)
        record("mask_time_dim_valid", case.mask.shape[0] in (T, 1),
               f"mask T {case.mask.shape[0]} not in {{{T}, 1}}")
        per = [int((case.mask[i] > 0).sum()) for i in range(case.mask.shape[0])]
        mask_frames_labeled = sum(1 for v in per if v > 0)
        mask_px_min, mask_px_max = min(per), max(per)
        record("mask_nonempty", mask_frames_labeled > 0, "mask has no tumour voxels")
    else:
        # unlabeled is legal; just record it, don't fail
        checks["mask_present"] = False

    ok = all(checks.values())
    return CaseIntegrity(
        patient_id=pid, ok=ok, center=center,
        field_strength_t=case.field_strength_t, frame_rate_hz=case.frame_rate_hz,
        scanned_region=case.scanned_region, n_frames=T, height=H, width=W,
        in_plane_spacing_mm=case.in_plane_spacing_mm,
        frame_thickness_mm=case.frame_thickness_mm, dtype=str(case.frames.dtype),
        intensity_min=float(case.frames.min()), intensity_max=float(case.frames.max()),
        labeled=case.labeled, mask_frames_labeled=mask_frames_labeled,
        mask_px_min=mask_px_min, mask_px_max=mask_px_max,
        checksum=trackrad.case_checksum(case), checks=checks, failures=failures,
    )


def assert_patient_level_unique(results: list[CaseIntegrity]) -> None:
    """Charter §2.4: patient ids must be unique across the sample (no leakage).

    Asserted in code, not a comment. Raises ``ValueError`` on any duplicate.
    """
    ids = [r.patient_id for r in results]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"patient-level uniqueness violated — duplicate ids: {sorted(dupes)}")


def sweep(root: str | Path) -> list[CaseIntegrity]:
    """Check every patient under ``root`` (deterministic, patient-level order)."""
    return [check_case(d) for d in trackrad.list_patient_dirs(root)]
