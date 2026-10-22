"""Offline photon pencil-beam cross-check with pyRadPlan (roadmap R7).

A standalone script for pyRadPlan's own environment (it pins numpy below
radiarch's and pulls heavy optional dependencies; BSD-3, never a runtime
dependency, decision 1 of the roadmap report)::

    uv run --no-project --python 3.12 --with pyRadPlan==0.5.0 --with "pydantic>=2.11.2,<2.12" \\
        python -m radiarch.validation.pyradplan_crosscheck --case water_10x10 --out validation/references/pyradplan

(pyRadPlan 0.5.0's beam serializer breaks on pydantic 2.12, hence the pin.)

It builds the harness phantom as a pyRadPlan CT, a 10 × 10 × 10 cm target
box whose beam's-eye-view projection is the field, one beam at gantry 0 with
10 mm bixels, computes the dose-influence matrix with pyRadPlan's photon
pencil-beam (SVD kernel) engine on its generic 6 MV machine, and writes the
unit-fluence dose on radiarch's ``(z, y, x)`` grid convention with the beam
along ``+y``. The harness case ``photon_vs_pyradplan`` compares central-axis
depth doses and heterogeneity ratios with the CCC engine; the field edges
differ by construction (pyRadPlan places bixels over the target projection),
so profiles are not compared.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PHANTOM_MM = 300.0
SLABS = {"water_10x10": [], "lung_slab": [(30.0, 110.0, 0.26)], "bone_slab": [(30.0, 60.0, 1.85)]}
FIELD_MM = 100.0
TARGET_DEPTH_MM = (50.0, 150.0)


def density_to_hu(rho: float) -> float:
    """pyRadPlan's generic HLUT is close to linear around water; -1000 HU is air, 0 water."""
    return float((rho - 1.0) * 1000.0)


def build_ct(case: str, spacing_mm: float):
    import SimpleITK as sitk
    n = int(round(PHANTOM_MM / spacing_mm))
    hu = np.zeros((n, n, n), dtype=np.float32)             # (z, y, x) for sitk's array order; y is depth (beam along +y)
    y = (np.arange(n) + 0.5) * spacing_mm                   # depth of voxel centres below the surface at y = 0
    for d0, d1, rho in SLABS[case]:
        hu[:, (y >= d0) & (y < d1), :] = density_to_hu(rho)
    img = sitk.GetImageFromArray(hu)
    img.SetSpacing([spacing_mm] * 3)
    half = (n - 1) / 2.0 * spacing_mm
    img.SetOrigin([-half, spacing_mm / 2.0, -half])          # x and z centred on the axis, surface at y = 0
    return img, n, y


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="pyRadPlan photon pencil-beam cross-check for the radiarch harness")
    ap.add_argument("--case", required=True, choices=sorted(SLABS))
    ap.add_argument("--spacing-mm", type=float, default=2.5)
    ap.add_argument("--bixel-mm", type=float, default=10.0)
    ap.add_argument("--target-mm", type=float, default=90.0, help="lateral size of the target box; the generator covers it with ceil(size/bixel)+1 bixels per axis, so 90 mm gives a 10 x 10 cm field at 10 mm bixels")
    ap.add_argument("--out", type=Path, default=HERE / "references" / "pyradplan")
    args = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    import SimpleITK as sitk
    import pyRadPlan
    from pyRadPlan import PhotonPlan, calc_dose_influence, generate_stf
    from pyRadPlan.cst import ExternalVOI, Target, create_cst
    from pyRadPlan.ct import create_ct

    t0 = time.time()
    img, n, y = build_ct(args.case, args.spacing_mm)
    ct = create_ct({"cubeHU": img})
    mask = np.zeros((n, n, n), dtype=np.uint8)
    half_f = float(args.target_mm) / 2.0
    x = img.GetOrigin()[0] + np.arange(n) * args.spacing_mm
    z = img.GetOrigin()[2] + np.arange(n) * args.spacing_mm
    mask[np.ix_(np.abs(z) < half_f, (y >= TARGET_DEPTH_MM[0]) & (y < TARGET_DEPTH_MM[1]), np.abs(x) < half_f)] = 1
    m_img = sitk.GetImageFromArray(mask); m_img.CopyInformation(img)
    target = Target(name="Target", mask=m_img, grid=ct.grid)
    # pyRadPlan computes dose only inside the structure set's voxels: an external VOI over the whole cube
    body = sitk.GetImageFromArray(np.ones((n, n, n), dtype=np.uint8)); body.CopyInformation(img)
    external = ExternalVOI(name="BODY", mask=body, grid=ct.grid)
    cst = create_cst({"vois": [target, external]}, ct=ct)
    # isocenter on the surface (SSD = SAD = 100 cm), as the CCC harness phantoms are set up
    pln = PhotonPlan(propStf={"gantryAngles": [0.0], "couchAngles": [0.0], "bixelWidth": float(args.bixel_mm), "addMargin": False,
                              "isoCenter": [[0.0, 0.0, 0.0]]},
                     propDoseCalc={"doseGrid": {"resolution": {"x": args.spacing_mm, "y": args.spacing_mm, "z": args.spacing_mm}}},
                     machine="Generic", numOfFractions=1, prescribedDose=1.0)
    stf = generate_stf(ct, cst, pln)
    dij = calc_dose_influence(ct, cst, stf, pln)
    n_bixels = int(dij.total_num_of_bixels) if hasattr(dij, "total_num_of_bixels") else None
    fluence = np.ones(n_bixels if n_bixels else dij.physical_dose.shape[1] if hasattr(dij, "physical_dose") else 1, dtype=float)
    result = dij.compute_result_ct_grid(fluence)
    dose_img = result["physical_dose"] if isinstance(result, dict) else getattr(result, "physical_dose", result)
    if not isinstance(dose_img, sitk.Image):
        dose_img = sitk.GetImageFromArray(np.asarray(dose_img, dtype=np.float32))
    dose = sitk.GetArrayFromImage(dose_img).astype(np.float32)          # (z, y, x) on the CT grid
    if dose.shape != (n, n, n):
        raise SystemExit(f"dose grid {dose.shape} is not the CT grid {(n, n, n)}; set the dose grid resolution")
    # find the beam axis: the target is centred laterally, so the two lateral axes have symmetric
    # mean profiles and the beam axis is the asymmetric one (entrance side higher); put it on y
    # with the entrance first (radiarch's convention: beam along +y, surface at y = 0)
    scores = []
    for axis in range(3):
        prof = dose.mean(axis=tuple(a for a in range(3) if a != axis))
        scores.append((abs(float(prof[: n // 4].mean() - prof[-n // 4:].mean())) / max(float(prof.max()), 1e-30), float(prof[: n // 4].mean() - prof[-n // 4:].mean())))
    beam_axis = int(np.argmax([sc[0] for sc in scores]))
    dose = np.moveaxis(dose, beam_axis, 1)
    if scores[beam_axis][1] < 0:
        dose = dose[:, ::-1, :]
    axis_note = {"beam_axis_in_sitk_zyx": beam_axis, "entrance_reversed": bool(scores[beam_axis][1] < 0), "asymmetry": [sc[0] for sc in scores]}
    flipped = axis_note
    elapsed = time.time() - t0
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"{args.case}.npz"
    s = float(args.spacing_mm); half = (n - 1) / 2.0 * s
    np.savez_compressed(out, dose=dose, spacing_mm=np.array([s, s, s]), origin_mm=np.array([-half, s / 2.0, -half]))
    (args.out / f"{args.case}.json").write_text(json.dumps({
        "case": args.case, "field_mm": FIELD_MM, "target_mm": args.target_mm, "bixel_mm": args.bixel_mm, "spacing_mm": s, "n_bixels": n_bixels,
        "engine": "pyRadPlan photon pencil beam (SVD kernels), machine Generic", "pyradplan_version": getattr(pyRadPlan, "__version__", "0.5.0"),
        "target_depth_mm": list(TARGET_DEPTH_MM), "isocenter_mm": [0.0, 0.0, 0.0], "ssd_mm": 1000.0, "beam_axis": flipped, "slabs": SLABS[args.case], "elapsed_s": round(elapsed, 1),
        "date": _dt.datetime.now().isoformat(timespec="seconds"), "python": sys.version.split()[0],
        "units": "dose per unit fluence on every bixel; compare after normalisation"}, indent=2))
    c = n // 2
    cax = dose[c, :, c]
    k = int(np.argmax(cax))
    print(f"wrote {out}: bixels {n_bixels}, d_max {y[k]:.1f} mm, PDD10 {np.interp(100.0, y, cax) / cax[k] * 100:.1f} %, elapsed {elapsed:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
