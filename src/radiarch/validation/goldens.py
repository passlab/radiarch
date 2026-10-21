"""Regression goldens (roadmap R7a).

While the vendored OpenTPS code paths still produce radiarch's outputs, this
module freezes them under ``tests/golden/`` so that the replacements of R14
(MCsquare driver), R2 (DICOM readers) and R15 (own loaders, rasterization,
spot placement) can be checked against today's behaviour:

* ``ccc_water_10x10.npz`` — the CCC beamlet matrix (raw engine units) for a
  small water box and a 6 × 6 cm² field: exact, deterministic.
* ``geometry_simplefantom.json`` — structure index, voxel counts, density
  statistics and content hashes of the geometry built from the OpenTPS
  SimpleFantom (CT + structure set).
* ``proton_spots_simplefantom.json`` — energy layers and spot positions of
  the proton beam model built on that geometry.
* ``mcsquare_inputs_simplefantom/`` — the files OpenTPS writes for MCsquare
  (``config.txt``, ``PlanPencil.txt``, the CT header, the SHA-256 of the CT
  raw block) with absolute paths normalised. R14's driver must write the same.

Capture with ``python -m radiarch.validation.goldens --capture``; the test
``tests/test_goldens.py`` regenerates everything and compares.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
RADIARCH_ROOT = HERE.parents[2]
GOLDEN_DIR = RADIARCH_ROOT / "tests" / "golden"
SIMPLEFANTOM = RADIARCH_ROOT / "tests" / "opentps" / "core" / "opentps-testData" / "SimpleFantomWithStruct"


def _sha256(arr_or_bytes) -> str:
    h = hashlib.sha256()
    h.update(arr_or_bytes.tobytes() if isinstance(arr_or_bytes, np.ndarray) else arr_or_bytes)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. CCC beamlet matrix
# ---------------------------------------------------------------------------

CCC_SPEC = {"half_width_mm": 60.0, "depth_mm": 120.0, "spacing_mm": 10.0, "field_mm": 60.0, "leaf_mm": 10.0, "beamlet_mm": 10.0}


def compute_ccc_golden() -> Dict[str, Any]:
    from ..services.dose_engines.ccc import CCCEngine
    from ..services.photon_beamlets import build_photon_plan
    from . import phantoms as ph

    eng = CCCEngine()
    ok, reason = eng.driver().availability()
    if not ok:
        raise RuntimeError(reason)
    s = CCC_SPEC
    phantom = ph.water_box(s["half_width_mm"], s["depth_mm"], s["spacing_mm"])
    h = s["field_mm"] / 2.0
    plan = build_photon_plan([(0.0, 0.0)], (-h, h), (-h, h), s["leaf_mm"], 1.0, (s["beamlet_mm"], s["beamlet_mm"]), name="golden")
    dij = eng.influence_matrix(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan,
                               params={"output_factor_gy_per_unit": 1.0, "n_jobs": 1}).tocsr()
    return {
        "data": dij.data.astype(np.float32), "indices": dij.indices.astype(np.int32), "indptr": dij.indptr.astype(np.int64),
        "shape": np.array(dij.shape, dtype=np.int64),
        "meta": {"spec": s, "engine_version": eng.version, "kernel_fingerprint": eng.driver().kernel_fingerprint(),
                 "n_beamlets": plan.n_beamlets},
    }


# ---------------------------------------------------------------------------
# 2–4. SimpleFantom geometry, proton spots, MCsquare inputs
# ---------------------------------------------------------------------------

def build_simplefantom(workdir: Path):
    """Geometry + proton beam model on the SimpleFantom through the services."""
    import SimpleITK as sitk
    from ..models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from ..models.geometry import GeometryBuildRequest, PatientRef
    from ..services.beam_model import BeamModelService
    from ..services.geometry import GeometryService

    if not SIMPLEFANTOM.is_dir():
        raise RuntimeError(f"SimpleFantom test data not found at {SIMPLEFANTOM}")
    geo_svc = GeometryService(base_dir=workdir / "geometry")
    geo = geo_svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="golden-simplefantom"),
                                             data_root_override=str(SIMPLEFANTOM)))
    bm_svc = BeamModelService(base_dir=workdir / "beam_models")
    # The beam model service resolves the geometry through GeometryService() on the
    # configured artifact directory; point that at our work directory while building.
    from ..config import get_settings
    settings = get_settings()
    previous = settings.artifact_dir
    settings.artifact_dir = str(workdir)
    try:
        bm = bm_svc.build(BeamModelBuildRequest(
            geometry_id=geo.geometry_id, modality=Modality.proton_pbs,
            beam_set=BeamSetSpec(isocenter_mm=(0.0, 0.0, 0.0), beams=[BeamSpec(beam_id="B1", gantry_deg=0.0)]),
            delivery_params=DeliveryParams(),
        ))
    finally:
        settings.artifact_dir = previous
    return geo, geo_svc, bm, bm_svc


def compute_geometry_golden(geo, geo_svc) -> Dict[str, Any]:
    import SimpleITK as sitk
    density = sitk.GetArrayFromImage(sitk.ReadImage(geo.density_grid_uri)).astype(np.float32)
    masks = sitk.GetArrayFromImage(sitk.ReadImage(geo.structure_masks_uri)).astype(np.uint16)
    counts = {name: int((masks == label).sum()) for name, label in geo.structure_index.items()}
    return {
        "structure_index": dict(geo.structure_index),
        "voxel_counts": counts,
        "shape_zyx": list(density.shape),
        "spacing_mm": [float(v) for v in geo.grid_spec.spacing_mm],
        "origin_mm": [float(v) for v in (geo.grid_spec.origin_mm or (0, 0, 0))],
        "density": {"mean": float(density.mean()), "min": float(density.min()), "max": float(density.max()),
                    "sha256": _sha256(density)},
        "masks_sha256": _sha256(masks),
        "hu_to_density_model": str(getattr(geo, "hu_to_density_model", "")),
    }


def compute_spots_golden(bm, bm_svc) -> Dict[str, Any]:
    plan = bm_svc.store.load_plan(bm.beam_model_id)
    layers = []
    for beam in plan.beams:
        for layer in beam.layers:
            xy = np.asarray(list(layer.spotXY), dtype=float).reshape(-1, 2)
            layers.append({"energy_mev": round(float(layer.nominalEnergy), 3),
                           "spots_xy_mm": np.round(xy, 3).tolist()})
    return {"beams": len(plan.beams), "layers": layers,
            "total_spots": int(sum(len(l["spots_xy_mm"]) for l in layers)),
            "fluence_total_count": int(bm.fluence_elements.total_count)}


def _normalise_paths(text: str, roots: Tuple[str, ...]) -> str:
    for i, r in enumerate(roots):
        if r:
            text = text.replace(r, f"<ROOT{i}>")
    return text


def compute_mcsquare_inputs_golden(geo, bm, geo_svc, bm_svc, workdir: Path) -> Dict[str, str]:
    """Run one MCsquare dose (few primaries) and collect the input files OpenTPS wrote."""
    from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import MCsquareDoseCalculator
    from ..services.dose import DoseService
    from ..services.dose_engines.registry import get_engine, engine_health

    if not engine_health("mcsquare").get("available"):
        raise RuntimeError("MCsquare engine not available")
    ds = DoseService(dose_dir=workdir / "doses", influence_dir=workdir / "influence")
    # Build the bundles the way the service does, from our stores.
    from ..services.dose_engines.protocol import BeamModelBundle, GeometryBundle
    import SimpleITK as sitk
    from ..services.geometry_bundle import load_ct_hu, wrap_ct_image
    density = sitk.GetArrayFromImage(sitk.ReadImage(geo.density_grid_uri)).astype(np.float32)
    masks = sitk.GetArrayFromImage(sitk.ReadImage(geo.structure_masks_uri)).astype(np.uint16)
    ct_hu = load_ct_hu(geo)
    geometry = GeometryBundle(result=geo, density=density, masks=masks, spacing_mm=tuple(geo.grid_spec.spacing_mm),
                              ct_hu=ct_hu, ct_image=wrap_ct_image(ct_hu, geo),
                              origin_mm=tuple(float(o) for o in (geo.grid_spec.origin_mm or (0, 0, 0))))
    beam_model = BeamModelBundle(result=bm, plan=bm_svc.store.load_plan(bm.beam_model_id))
    engine = get_engine("mcsquare")
    weights = np.ones(bm.fluence_elements.total_count, dtype=np.float32)
    engine.compute_dose(geometry, beam_model, weights, params={"nb_primaries": 1000})
    sim_dir = Path(MCsquareDoseCalculator()._mcsquareSimuDir)
    out: Dict[str, str] = {}
    roots = (str(sim_dir), str(sim_dir.parent), str(Path.home()))
    for name in ("config.txt", "PlanPencil.txt"):
        p = sim_dir / name
        if p.is_file():
            out[name] = _normalise_paths(p.read_text(), roots)
    mhd = [p for p in sim_dir.rglob("*.mhd")]
    if mhd:
        out[mhd[0].name] = _normalise_paths(mhd[0].read_text(), roots)
        raw = mhd[0].with_suffix(".raw")
        if raw.is_file():
            out[raw.name + ".sha256"] = _sha256(raw.read_bytes())
    if not out:
        raise RuntimeError(f"no MCsquare input files found under {sim_dir}")
    return out


# ---------------------------------------------------------------------------
# Capture / compare
# ---------------------------------------------------------------------------

def capture(golden_dir: Path = GOLDEN_DIR, which: Tuple[str, ...] = ("ccc", "simplefantom")) -> None:
    golden_dir.mkdir(parents=True, exist_ok=True)
    if "ccc" in which:
        g = compute_ccc_golden()
        np.savez_compressed(golden_dir / "ccc_water_10x10.npz", data=g["data"], indices=g["indices"], indptr=g["indptr"], shape=g["shape"])
        (golden_dir / "ccc_water_10x10.json").write_text(json.dumps(g["meta"], indent=2))
        print("captured ccc_water_10x10 (nnz", int(g["data"].size), ")")
    if "simplefantom" in which:
        with tempfile.TemporaryDirectory(prefix="radiarch-golden-") as tmp:
            work = Path(tmp)
            geo, geo_svc, bm, bm_svc = build_simplefantom(work)
            (golden_dir / "geometry_simplefantom.json").write_text(json.dumps(compute_geometry_golden(geo, geo_svc), indent=2))
            (golden_dir / "proton_spots_simplefantom.json").write_text(json.dumps(compute_spots_golden(bm, bm_svc), indent=2))
            print("captured geometry and spots for SimpleFantom")
            inputs = compute_mcsquare_inputs_golden(geo, bm, geo_svc, bm_svc, work)
            d = golden_dir / "mcsquare_inputs_simplefantom"
            d.mkdir(exist_ok=True)
            for name, text in inputs.items():
                (d / name).write_text(text)
            print("captured MCsquare inputs:", sorted(inputs))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="capture regression goldens")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--only", nargs="*", default=["ccc", "simplefantom"])
    ap.add_argument("--dir", type=Path, default=GOLDEN_DIR)
    args = ap.parse_args(argv)
    if not args.capture:
        ap.print_help(); return 2
    capture(args.dir, tuple(args.only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
