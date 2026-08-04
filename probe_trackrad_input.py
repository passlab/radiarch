#!/usr/bin/env python3
"""probe_trackrad_input.py — TrackRAD → RadiArch model input-compatibility probe.

PURPOSE (input-path check only)
-------------------------------
Answer ONE question with evidence: can the RadiArch dose model *accept* a
TrackRAD2025 case as input far enough to run a smoke test? This exercises the
input / loading / adaptation path. It does NOT validate that any dose output is
correct — TrackRAD ships no dose ground truth, so correctness is out of scope.

WHAT THE MODEL REQUIRES (from code — see TRACKRAD_COMPAT_REPORT.md for path:line)
  * GeometryBundle.density : 3D (nz,ny,nx) float32 MASS DENSITY g/cm³   [hard]
  * GeometryBundle.masks   : 3D (nz,ny,nx) uint16, same shape as density [hard]
  * GeometryBundle.spacing_mm : (sx,sy,sz)                               [hard]
  * BeamModelBundle.result.fluence_elements.total_count >= 1  (BEAMS)    [hard]
  * weights : np.ndarray shape (total_count,)                            [hard]
  * GeometryBundle.ct_hu / ct_image : optional for analytic engine   [has-default]

WHAT TRACKRAD PROVIDES
  * <patient>_frames.mha : 2D+t sagittal cine-MRI (3D array, 3rd axis = TIME)
  * tumor mask .mha
  * JSON sidecars (field strength, frame rate, scanned region)
  * NO CT, NO HU, NO beam parameters, NO dose.

Therefore TrackRAD is missing BOTH hard-required non-image inputs (density-from-CT
and beam parameters). This probe fabricates those with OBVIOUS placeholders — every
synthetic value is prefixed with a SYNTHETIC_/PLACEHOLDER_ marker and echoed in the
output so it can NEVER be mistaken for a real evaluation input.

Run:  python probe_trackrad_input.py
"""

from __future__ import annotations

import glob
import json
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import SimpleITK as sitk

# ---------------------------------------------------------------------------
# Loud markers for every fabricated value (honesty requirement).
# ---------------------------------------------------------------------------
SYNTHETIC_TRACKRAD_STANDIN = "SYNTHETIC_TRACKRAD_FORMAT_STANDIN (no real case on disk)"
PLACEHOLDER_DENSITY = "PLACEHOLDER_DENSITY_FROM_MRI_INTENSITY (NOT g/cm3 — fabricated)"
PLACEHOLDER_BEAM = "PLACEHOLDER_BEAM_SINGLE_TRIVIAL (TrackRAD has no beams — fabricated)"
PLACEHOLDER_ZSPACING = "PLACEHOLDER_Z_SPACING (single 2D frame has no real depth spacing)"


def banner(msg: str) -> None:
    print("\n" + "=" * 78 + f"\n{msg}\n" + "=" * 78)


# ---------------------------------------------------------------------------
# Phase 2 — obtain a TrackRAD case (real if present, else a format stand-in)
# ---------------------------------------------------------------------------
def find_real_trackrad_case() -> Path | None:
    """Search common locations for a real <patient>_frames.mha."""
    roots = [
        Path.home() / "Desktop", Path.home() / "Downloads",
        Path.home() / "Documents", Path.cwd(), Path("/data"), Path("/tmp"),
    ]
    for root in roots:
        if not root.exists():
            continue
        hits = glob.glob(str(root / "**" / "*_frames.mha"), recursive=True)
        hits += glob.glob(str(root / "**" / "*frames*.mha"), recursive=True)
        if hits:
            return Path(sorted(hits)[0])
    return None


def make_standin_case(dstdir: Path) -> tuple[Path, Path, Path]:
    """Write a *format-faithful* TrackRAD stand-in: 2D+t cine .mha + mask + JSON.

    Shapes/spacing mirror the documented TrackRAD layout so the loading and
    adaptation code paths are identical to a real case. Content is synthetic.
    ITK 3rd axis = time  =>  GetArrayFromImage() returns (T, H, W).
    """
    T, H, W = 50, 256, 256                    # 50 cine frames, 256x256 sagittal
    rng = np.random.default_rng(0)
    frames = (rng.random((T, H, W)) * 400).astype(np.float32)   # MRI-like intensities
    img = sitk.GetImageFromArray(frames)      # size = (W, H, T)
    img.SetSpacing((1.5, 1.5, 0.25))          # (x_mm, y_mm, t_seconds-as-"spacing")
    frames_p = dstdir / "STANDIN_patient_frames.mha"
    sitk.WriteImage(img, str(frames_p))

    mask = np.zeros((T, H, W), dtype=np.uint8)
    mask[:, 100:150, 100:150] = 1             # a blocky "tumor" that moves not-at-all
    m = sitk.GetImageFromArray(mask)
    m.CopyInformation(img)
    mask_p = dstdir / "STANDIN_patient_mask.mha"
    sitk.WriteImage(m, str(mask_p))

    meta = {"field_strength_T": 0.35, "frame_rate_Hz": 4.0, "scanned_region": "abdomen",
            "_note": SYNTHETIC_TRACKRAD_STANDIN}
    json_p = dstdir / "STANDIN_patient.json"
    json_p.write_text(json.dumps(meta, indent=2))
    return frames_p, mask_p, json_p


def inspect_case(frames_p: Path, mask_p: Path, json_p: Path) -> dict:
    banner("PHASE 2 — TRACKRAD PROVIDES (SimpleITK load of the case)")
    fr = sitk.ReadImage(str(frames_p))
    arr = sitk.GetArrayFromImage(fr)          # (T, H, W)
    mk = sitk.GetArrayFromImage(sitk.ReadImage(str(mask_p)))
    meta = json.loads(json_p.read_text())
    info = {
        "frames_path": str(frames_p),
        "frames_shape_zyx": arr.shape,        # axis0 = TIME for TrackRAD
        "frames_ndim": arr.ndim,
        "time_axis": 0,
        "spacing_xyz": fr.GetSpacing(),
        "direction": fr.GetDirection(),
        "dtype": str(arr.dtype),
        "intensity_min": float(arr.min()),
        "intensity_max": float(arr.max()),
        "mask_shape_zyx": mk.shape,
        "mask_aligned": mk.shape == arr.shape,
        "sidecar": meta,
        "_arr": arr, "_mask": mk, "_spacing": fr.GetSpacing(),
    }
    for k, v in info.items():
        if not k.startswith("_"):
            print(f"  {k:20s}: {v}")
    return info


# ---------------------------------------------------------------------------
# Phase 4 — adapt into the model's input object and call the engine
# ---------------------------------------------------------------------------
def build_bundles(arr: np.ndarray, mask: np.ndarray, spacing_xyz, *, interpretation: str):
    """Adapt a TrackRAD case into (GeometryBundle, BeamModelBundle, weights).

    interpretation:
      'single_frame' : one cine frame as a degenerate 3D volume (nz=1, ny, nx)
                       — the reading the model's 3D contract most nearly fits.
      'time_stack'   : the whole (T,H,W) stack fed as (nz=T, ny, nx)
                       — dimensionally 3D, but stacks TIME as depth (semantically wrong).
    """
    from radiarch.services.dose_engines.protocol import BeamModelBundle, GeometryBundle
    from radiarch.models.beam_model import (
        BeamModelResult, FluenceElementSet, Modality, PerBeamElements,
    )
    from radiarch.models.geometry import CTMetadata, GeometryResult, GridSpec

    if interpretation == "single_frame":
        frame = arr[0]                                  # (H, W)
        vol = frame[None, :, :]                         # (nz=1, ny=H, nx=W)
        mvol = (mask[0][None, :, :] > 0).astype(np.uint16)
    elif interpretation == "time_stack":
        vol = arr                                       # (nz=T, ny=H, nx=W)
        mvol = (mask > 0).astype(np.uint16)
    else:
        raise ValueError(interpretation)

    nz, ny, nx = vol.shape

    # --- PLACEHOLDER density: MRI intensity is NOT mass density. Map intensity
    #     into a narrow band around 1.0 g/cm3 purely to exercise the path. ------
    lo, hi = float(vol.min()), float(vol.max())
    norm = (vol - lo) / (hi - lo + 1e-9)
    density = (0.9 + 0.2 * norm).astype(np.float32)     # fabricated "g/cm3"

    sx, sy = float(spacing_xyz[0]), float(spacing_xyz[1])
    sz = 1.0                                             # PLACEHOLDER_Z_SPACING

    geom = GeometryBundle(
        result=GeometryResult(
            geometry_id="TRACKRAD-STANDIN",
            density_grid_uri="memory://placeholder",
            structure_masks_uri="memory://placeholder",
            structure_index={"TUMOR": 1},
            grid_spec=GridSpec(spacing_mm=(sx, sy, sz),
                               origin_mm=(0.0, 0.0, 0.0), size=(nx, ny, nz)),
            frame_of_reference_uid="0.0.0.trackrad.standin",
            ct_metadata=CTMetadata(num_slices=nz),
            cache_key="trackrad-standin",
        ),
        density=density,
        masks=mvol,
        spacing_mm=(sx, sy, sz),
        # ct_hu / ct_image left None — TrackRAD has no CT (analytic engine tolerates).
    )

    # --- PLACEHOLDER beam model: a single trivial fluence element. -------------
    bm = BeamModelBundle(
        result=BeamModelResult(
            beam_model_id="PLACEHOLDER-BEAM", geometry_id="TRACKRAD-STANDIN",
            modality=Modality.proton_pbs,
            fluence_elements=FluenceElementSet(
                total_count=1,
                per_beam=[PerBeamElements(beam_id="PLACEHOLDER_B1", element_count=1,
                                          energy_layers=[100.0], spots_per_layer=[1])],
            ),
            beam_model_ref_uri="memory://placeholder",
            machine_model_id="PLACEHOLDER", cache_key="placeholder-bm",
        ),
        plan=object(),                                   # PLACEHOLDER test double
    )
    weights = np.ones((1,), dtype=np.float32)            # PLACEHOLDER single weight
    return geom, bm, weights


def probe_interpretation(info: dict, interpretation: str) -> dict:
    banner(f"PHASE 4 — PROBE model input path  [interpretation = {interpretation}]")
    print(f"  placeholders in play:\n    - {PLACEHOLDER_DENSITY}"
          f"\n    - {PLACEHOLDER_BEAM}\n    - {PLACEHOLDER_ZSPACING}")
    from radiarch.services.dose_engines.analytic import AnalyticEngine
    engine = AnalyticEngine()
    result = {"interpretation": interpretation, "accepted": False,
              "validate_issues": None, "output_shape": None, "output_dtype": None,
              "break_point": None, "traceback": None}
    try:
        geom, bm, weights = build_bundles(
            info["_arr"], info["_mask"], info["_spacing"], interpretation=interpretation)
        print(f"  adapted density shape : {geom.density.shape} dtype={geom.density.dtype} "
              f"[{geom.density.min():.3f},{geom.density.max():.3f}] g/cm3 (FABRICATED)")
        print(f"  adapted masks shape   : {geom.masks.shape} dtype={geom.masks.dtype}")
        print(f"  spacing_mm            : {geom.spacing_mm}")
        print(f"  beam total_count      : {bm.result.fluence_elements.total_count} (PLACEHOLDER)")

        issues = engine.validate(geom, bm, params={})
        result["validate_issues"] = issues
        print(f"  engine.validate()     : {issues if issues else 'PASS (no issues)'}")
        if issues:
            result["break_point"] = "AnalyticEngine.validate() returned issues"
            return result

        dose = engine.compute_dose(geom, bm, weights, params={}).dose
        result["accepted"] = True
        result["output_shape"] = tuple(dose.shape)
        result["output_dtype"] = str(dose.dtype)
        print(f"  engine.compute_dose() : ACCEPTED — output dose {dose.shape} {dose.dtype}, "
              f"sum={float(dose.sum()):.4g}")
    except Exception as e:                               # noqa: BLE001 — we want the exact break
        result["break_point"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()
        print(f"  BROKE AT: {result['break_point']}")
        print(result["traceback"])
    return result


# ---------------------------------------------------------------------------
def main() -> int:
    banner("PHASE 2 SETUP — locate a TrackRAD case")
    real = find_real_trackrad_case()
    with tempfile.TemporaryDirectory() as td:
        if real is not None:
            print(f"  REAL TrackRAD case found: {real}")
            frames_p = real
            # best-effort sibling mask / json
            mask_p = next(iter(glob.glob(str(real.parent / "*mask*.mha"))), None)
            json_p = next(iter(glob.glob(str(real.parent / "*.json"))), None)
            if mask_p is None or json_p is None:
                print("  (no sibling mask/json found — falling back to stand-in for those)")
                fr, mk, js = make_standin_case(Path(td))
                mask_p = mask_p or str(mk)
                json_p = json_p or str(js)
            frames_p, mask_p, json_p = Path(frames_p), Path(mask_p), Path(json_p)
        else:
            print(f"  NO real TrackRAD case on disk. Using: {SYNTHETIC_TRACKRAD_STANDIN}")
            frames_p, mask_p, json_p = make_standin_case(Path(td))

        info = inspect_case(frames_p, mask_p, json_p)
        results = [probe_interpretation(info, "single_frame"),
                   probe_interpretation(info, "time_stack")]

    banner("VERDICT")
    print(f"  Data source: {'REAL' if real else SYNTHETIC_TRACKRAD_STANDIN}")
    for r in results:
        status = "ACCEPTED input" if r["accepted"] else f"REJECTED ({r['break_point']})"
        print(f"  [{r['interpretation']:12s}] {status}"
              + (f" → dose {r['output_shape']} {r['output_dtype']}" if r["accepted"] else ""))
    print("\n  NOTE: 'ACCEPTED' means the model consumed the input and emitted a dose array.")
    print("  It required TWO fabricated hard-inputs TrackRAD lacks: density (from MRI")
    print("  intensity, NOT g/cm3) and a placeholder beam. This probe does NOT validate")
    print("  dose correctness — TrackRAD contains no dose ground truth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
