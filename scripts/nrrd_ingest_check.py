#!/usr/bin/env python3
"""Run a real CT ``.nrrd`` (+ optional Slicer ``.seg.nrrd``) through the full
GeometryService and log a reproducible report.

This is the "on real 3D data" evidence for the NRRD ingest path (the unit test
in ``tests/test_nrrd_ingest.py`` covers the synthetic case). It reports what it
finds honestly; it does not assert dose or clinical correctness — only that the
geometry pipeline ingests real anatomy end-to-end.

Usage:
    python scripts/nrrd_ingest_check.py
    python scripts/nrrd_ingest_check.py --ct path/to/ct.nrrd --seg path/to/seg.nrrd
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from radiarch.models.geometry import GeometryBuildRequest, HUDensityModel, PatientRef
from radiarch.services.geometry import GeometryService

try:  # optional: run-provenance logging is a bonus, not a hard dependency
    from radiarch import repro
except ImportError:  # pragma: no cover
    repro = None

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CT = _ROOT / "data" / "dicom3DCTdata" / "3 3D BRACHY FB100.nrrd"
_DEFAULT_SEG = _ROOT / "data" / "dicom3DCTdata" / "Segmentation.seg.nrrd"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ct", default=str(_DEFAULT_CT))
    p.add_argument("--seg", default=str(_DEFAULT_SEG))
    p.add_argument("--hu-model", default="LINEAR",
                   choices=[m.value for m in HUDensityModel])
    p.add_argument("--out", default=str(_ROOT / "data" / "artifacts" / "nrrd_geom"))
    p.add_argument("--runs-dir", default="runs")
    args = p.parse_args(argv)

    ct_path = Path(args.ct)
    seg_path = Path(args.seg) if args.seg and Path(args.seg).is_file() else None
    if not ct_path.is_file():
        print(f"CT not found: {ct_path}")
        return 1

    print(f"CT  : {ct_path.name}")
    print(f"Seg : {seg_path.name if seg_path else '(none)'}")
    print(f"HU→density model: {args.hu_model}\n")

    svc = GeometryService(base_dir=args.out)
    req = GeometryBuildRequest(
        patient_ref=PatientRef(
            nrrd_ct_path=str(ct_path),
            nrrd_seg_path=str(seg_path) if seg_path else None,
        ),
        hu_to_density_model=HUDensityModel(args.hu_model),
    )

    t0 = time.time()
    result = svc.build(req)
    runtime_s = time.time() - t0

    # --- report -----------------------------------------------------------
    import SimpleITK as sitk

    def _load(pathstr):
        return np.transpose(sitk.GetArrayFromImage(sitk.ReadImage(pathstr)))

    density = _load(result.density_grid_uri)
    masks = _load(result.structure_masks_uri)
    ct = _load(result.ct_grid_uri) if result.ct_grid_uri else None

    print(f"geometry_id : {result.geometry_id}")
    print(f"grid size   : {result.grid_spec.size}")
    print(f"spacing (mm): {result.grid_spec.spacing_mm}")
    print(f"origin  (mm): {result.grid_spec.origin_mm}")
    print(f"runtime     : {runtime_s:.2f}s\n")

    if ct is not None:
        print(f"CT HU     : min={ct.min():.0f} max={ct.max():.0f} "
              f"finite={bool(np.all(np.isfinite(ct)))}")
    print(f"density   : min={density.min():.4f} max={density.max():.4f} "
          f"finite={bool(np.all(np.isfinite(density)))}")

    print("\nstructures (label : name : voxel count):")
    counts = {}
    for name, label in sorted(result.structure_index.items(), key=lambda kv: kv[1]):
        n = int((masks == label).sum())
        counts[name] = n
        print(f"  {label:>3d} : {name:<24s} : {n:,} voxels")
    if not result.structure_index:
        print("  (no structures — CT only)")

    # --- reproducible logged record (§6, when repro is available) ----------
    if repro is not None:
        rec = repro.new_run(
            "nrrd_ingest_check",
            config={"ct": ct_path.name, "seg": seg_path.name if seg_path else None,
                    "hu_model": args.hu_model},
            dataset_version="local NRRD (dicom3DCTdata) — real 3D CT, NO dose",
            split="dev_smoke",
        )
        rec.runtime_s = runtime_s
        rec.metrics = {
            "geometry_id": result.geometry_id,
            "grid_size": list(result.grid_spec.size),
            "spacing_mm": list(result.grid_spec.spacing_mm),
            "density_min": float(density.min()), "density_max": float(density.max()),
            "density_finite": bool(np.all(np.isfinite(density))),
            "structures": counts,
        }
        path = rec.write(args.runs_dir)
        print(f"\nlogged -> {path}")
    else:
        print("\n(repro module not available on this branch — skipping run log)")
    print("Note: this verifies INGESTION only — it says nothing about dose "
          "(no beams/plan here).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
