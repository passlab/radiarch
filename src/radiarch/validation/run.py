"""Validation runner: ``python -m radiarch.validation.run --list | --cases NAME... | --all``.

Each case file under ``cases/`` names a ``kind``; the matching ``run_<kind>``
function below builds the inputs, calls radiarch, computes the metrics and
compares them with the reference tables under ``references/``. A run writes
``<out>/<timestamp>-<commit>/results.json`` and ``summary.md``.

Statuses: ``pass`` (every pass/fail check met), ``fail``, ``info`` (only
informative checks), ``skip`` (prerequisite missing: binary, data, tool) and
``error`` (exception; traceback kept). Results are research targets against
the commissioning literature; they are not a clinical commissioning.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..services.masks import structure_mask

from . import phantoms as ph

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "cases"
REF_DIR = HERE / "references"
RADIARCH_ROOT = HERE.parents[2]
SMIS_ROOT = RADIARCH_ROOT.parent


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    value: Any
    target: str
    passed: Optional[bool]          # None = informative
    note: str = ""


@dataclass
class CaseResult:
    name: str
    kind: str
    status: str = "pending"
    seconds: float = 0.0
    checks: List[Check] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def add(self, name: str, value: Any, target: str, passed: Optional[bool], note: str = "") -> None:
        self.checks.append(Check(name, _jsonable(value), target, passed, note))

    def finish(self) -> None:
        if self.status in ("skip", "error"):
            return
        graded = [c.passed for c in self.checks if c.passed is not None]
        if any(p is False for p in graded):
            self.status = "fail"
        elif graded:
            self.status = "pass"
        else:
            self.status = "info"


class Skip(Exception):
    """Raised by a case when a prerequisite is missing."""


def _jsonable(v):
    if isinstance(v, (np.floating, np.integer)):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def load_reference(name: str) -> dict:
    return json.loads((REF_DIR / f"{name}.json").read_text())


def data_root() -> Path:
    env = os.environ.get("RADIARCH_VALIDATION_DATA")
    return Path(env) if env else SMIS_ROOT / "data" / "public"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@dataclass
class Context:
    fast: bool = False
    spacing_scale: float = 1.0
    workdir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="radiarch-validation-")))

    def spacing(self, mm: float) -> float:
        return float(mm) * (2.0 if self.fast else 1.0) * self.spacing_scale


def _phantom(spec: dict, ctx: Context) -> ph.Phantom:
    kind = spec.get("type", "water_box")
    s = ctx.spacing(spec.get("spacing_mm", 2.5))
    if kind == "water_box":
        return ph.water_box(spec.get("half_width_mm", 150.0), spec.get("depth_mm", 300.0), s)
    if kind == "lung_slab":
        return ph.lung_slab(s)
    if kind == "bone_slab":
        return ph.bone_slab(s)
    if kind == "thorax_like":
        return ph.thorax_like(s)
    raise ValueError(f"unknown phantom type {kind!r}")


def _open_field_plan(field_mm: float, leaf_mm: float, beamlet_mm: float, gantry_deg: float = 0.0, mu: float = 1.0):
    from ..services.photon_beamlets import build_photon_plan
    h = field_mm / 2.0
    return build_photon_plan([(gantry_deg, 0.0)], (-h, h), (-h, h), leaf_mm, mu, (beamlet_mm, beamlet_mm),
                             name=f"validation-{field_mm:g}mm")


def _ccc_engine():
    from ..services.dose_engines.ccc import CCCEngine
    eng = CCCEngine()
    ok, reason = eng.driver().availability()
    if not ok:
        raise Skip(reason)
    return eng


def _ccc_dose(eng, phantom: ph.Phantom, plan, ctx: Context) -> np.ndarray:
    params = {"calibration_spacing_mm": 5.0} if ctx.fast else None
    return eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params=params)


def _cax(dose: np.ndarray, phantom: ph.Phantom) -> np.ndarray:
    return dose[phantom.centre_index("z"), :, phantom.centre_index("x")]


def _within(value: float, target: float, tol: float) -> bool:
    return abs(value - target) <= tol


# ---------------------------------------------------------------------------
# Photon cases
# ---------------------------------------------------------------------------

def _pdd_metrics(dose: np.ndarray, phantom: ph.Phantom) -> Dict[str, float]:
    cax = _cax(dose, phantom)
    y = phantom.axis_mm("y")
    k = int(np.argmax(cax))
    dmax = float(cax[k])
    return {
        "dmax_mm": float(y[k]),
        "dmax_gy_per_mu": dmax,
        "pdd10": float(np.interp(100.0, y, cax) / dmax * 100.0),
        "pdd20": float(np.interp(200.0, y, cax) / dmax * 100.0),
        "cax_depth_mm": y.tolist(),
        "cax_dose": cax.tolist(),
    }


def run_photon_pdd(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    ref = load_reference(spec.get("references", "photon_6mv"))
    eng = _ccc_engine()
    phantom = _phantom(spec["phantom"], ctx)
    f = spec["field"]
    plan = _open_field_plan(f["jaw_mm"], f["leaf_width_mm"], f["beamlet_mm"], f.get("gantry_deg", 0.0), f.get("mu", 1.0))
    dose = _ccc_dose(eng, phantom, plan, ctx)
    m = _pdd_metrics(dose, phantom)
    res.metrics.update({k: v for k, v in m.items() if not k.startswith("cax_")})
    res.metrics["cax"] = {"depth_mm": m["cax_depth_mm"], "dose_gy_per_mu": m["cax_dose"]}

    r = ref["pdd10_percent"]
    res.add("PDD10 (%)", m["pdd10"], f"{r['value']} ± {r['tolerance_abs']}",
            _within(m["pdd10"], r["value"], r["tolerance_abs"]) if r.get("pass_fail", True) else None, r["source"])
    r = ref["dmax_mm"]
    res.add("d_max (mm)", m["dmax_mm"], f"{r['min']}–{r['max']}", r["min"] <= m["dmax_mm"] <= r["max"], r["source"])
    r = ref["pdd20_over_pdd10"]
    ratio = m["pdd20"] / m["pdd10"]
    res.add("PDD20/PDD10", ratio, f"{r['value']} ± {r['tolerance_abs']}",
            _within(ratio, r["value"], r["tolerance_abs"]) if r.get("pass_fail") else None, r["source"])
    # 1 cGy per MU at d_max for 10 x 10 at SSD 100 is the calibration definition; on a phantom
    # of the same size it must hold to within the grid.
    res.add("dose at d_max per MU (Gy)", m["dmax_gy_per_mu"], "0.010 ± 0.0005 (calibration definition)",
            _within(m["dmax_gy_per_mu"], 0.010, 0.0005))
    return res


def _profile_metrics(dose: np.ndarray, phantom: ph.Phantom, depth_mm: float, field_mm: float) -> Dict[str, float]:
    iy = phantom.depth_index(depth_mm)
    prof = dose[phantom.centre_index("z"), iy, :].astype(float)
    x = phantom.axis_mm("x")
    d0 = float(np.interp(0.0, x, prof))
    core = np.abs(x) <= 0.4 * field_mm
    p = prof[core]
    flatness = float((p.max() - p.min()) / (p.max() + p.min()) * 100.0)
    xs = x[core & (x > 0)]
    sym = float(max(abs(np.interp(xx, x, prof) - np.interp(-xx, x, prof)) / d0 * 100.0 for xx in xs)) if xs.size else 0.0
    # 80-20 % penumbra on the +x side, relative to the central-axis value
    rel = prof / d0
    right = x >= 0
    xr, pr = x[right], rel[right]
    order = np.argsort(pr)   # pr decreases with x; interp needs increasing
    x80 = float(np.interp(0.8, pr[order], xr[order]))
    x20 = float(np.interp(0.2, pr[order], xr[order]))
    return {"depth_mm": float(phantom.axis_mm("y")[iy]), "flatness_pct": flatness, "symmetry_pct": sym,
            "penumbra_80_20_mm": x20 - x80, "x_mm": x.tolist(), "profile": prof.tolist()}


def run_photon_profile(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    ref = load_reference(spec.get("references", "photon_6mv"))
    eng = _ccc_engine()
    phantom = _phantom(spec["phantom"], ctx)
    f = spec["field"]
    plan = _open_field_plan(f["jaw_mm"], f["leaf_width_mm"], f["beamlet_mm"], f.get("gantry_deg", 0.0), f.get("mu", 1.0))
    dose = _ccc_dose(eng, phantom, plan, ctx)
    m = _profile_metrics(dose, phantom, spec.get("depth_mm", 100.0), f["jaw_mm"])
    res.metrics.update({k: v for k, v in m.items() if k not in ("x_mm", "profile")})
    res.metrics["profile"] = {"x_mm": m["x_mm"], "dose_gy_per_mu": m["profile"]}
    r = ref["flatness_percent_at_10cm"]
    res.add("flatness (%)", m["flatness_pct"], f"≤ {r['max']}", m["flatness_pct"] <= r["max"], r["source"])
    r = ref["symmetry_percent_at_10cm"]
    res.add("symmetry (%)", m["symmetry_pct"], f"≤ {r['max']}", m["symmetry_pct"] <= r["max"], r["source"])
    r = ref["penumbra_80_20_mm_at_10cm"]
    res.add("penumbra 80–20 % (mm)", m["penumbra_80_20_mm"], f"{r['value']} ± {r['tolerance_abs']}",
            _within(m["penumbra_80_20_mm"], r["value"], r["tolerance_abs"]) if r.get("pass_fail") else None, r["source"])
    return res


def run_photon_slab(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    eng = _ccc_engine()
    s = ctx.spacing(spec.get("spacing_mm", 2.5))
    f = spec["field"]
    plan = _open_field_plan(f["jaw_mm"], f["leaf_width_mm"], f["beamlet_mm"], f.get("gantry_deg", 0.0), f.get("mu", 1.0))
    water = ph.water_box(150.0, 300.0, s)
    cax_w = _cax(_ccc_dose(eng, water, plan, ctx), water)
    y = water.axis_mm("y")
    tol = float(spec.get("tolerance_percent", 5.0))
    graded = bool(spec.get("pass_fail", False))
    for slab in (ph.lung_slab(s), ph.bone_slab(s)):
        dose = _ccc_dose(eng, slab, plan, ctx)
        cax = _cax(dose, slab)
        rho = slab.density[slab.centre_index("z"), :, slab.centre_index("x")]
        # radiological depth at each voxel centre: density integrated to the centre
        y_rad = (np.cumsum(rho) - rho / 2.0) * s
        ssd = 1000.0
        for d in spec.get("probe_depths_mm", [150, 200, 250]):
            k = slab.depth_index(d)
            expected = np.interp(y_rad[k], y, cax_w) * ((ssd + y_rad[k]) / (ssd + y[k])) ** 2
            ratio = float(cax[k] / expected)
            res.metrics[f"{slab.name}_ratio_at_{d:g}mm"] = ratio
            res.add(f"{slab.name}: dose / water-equivalent expectation at {d:g} mm", ratio,
                    f"1 ± {tol / 100:.2f} (effective path length + inverse square)",
                    _within(ratio, 1.0, tol / 100.0) if graded else None,
                    "informative until the Monte Carlo references of R7; lateral scatter in lung is not captured by the path-length estimate")
        res.metrics[f"{slab.name}_cax"] = {"depth_mm": slab.axis_mm("y").tolist(), "dose_gy_per_mu": cax.tolist()}
    res.metrics["water_cax"] = {"depth_mm": y.tolist(), "dose_gy_per_mu": cax_w.tolist()}
    return res


def run_photon_output_vs_field(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    ref = load_reference(spec.get("references", "photon_6mv"))["output_factor_vs_10x10"]
    eng = _ccc_engine()
    phantom = _phantom(spec["phantom"], ctx)
    dmax_dose = {}
    for fmm in spec["fields_mm"]:
        plan = _open_field_plan(fmm, spec.get("leaf_width_mm", 10.0), spec.get("beamlet_mm", 5.0))
        cax = _cax(_ccc_dose(eng, phantom, plan, ctx), phantom)
        dmax_dose[fmm] = float(cax.max())
    base = dmax_dose[100]
    for fmm, d in dmax_dose.items():
        key = f"{fmm // 10}x{fmm // 10}"
        factor = d / base
        res.metrics[f"output_factor_{key}"] = factor
        if key in ref["values"]:
            res.add(f"output factor {key} vs 10x10", factor, f"{ref['values'][key]} measured (phantom scatter only here)", None, ref["source"])
    return res


# ---------------------------------------------------------------------------
# Proton range (through the vendored OpenTPS path until R14)
# ---------------------------------------------------------------------------

def run_proton_range(spec: dict, ctx: Context) -> CaseResult:
    """Single spots in water through radiarch's MCsquare driver (R14), with the water-only
    calibration: the clinical Schneider tables map HU 0 to an adipose/soft-tissue blend
    whose stopping power is 1-3 % above water, which shortens ranges; a water range test
    must see water (material 17 at 1.000 g/cm³)."""
    res = CaseResult(spec["name"], spec["kind"])
    ref = load_reference(spec.get("references", "proton_water"))
    from ..models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot
    from ..services.dose_engines.mcsquare_driver import CalibrationTables, MCsquareDriver

    drv = MCsquareDriver(work_root=ctx.workdir / "mcsquare", n_threads=0, seed=20261021)
    ok, reason = drv.availability()
    if not ok:
        raise Skip(f"MCsquare engine not available on this machine: {reason}")
    p = spec["phantom"]
    s = ctx.spacing(p.get("spacing_mm", 2.0))
    phantom = ph.water_box(p.get("half_width_mm", 40.0), p.get("depth_mm", 350.0), s)
    hu = np.zeros(phantom.shape, dtype=np.float32)               # water = 0 HU, (z, y, x)
    water = CalibrationTables.water()
    n_prim = int(spec.get("nb_primaries", 200000) / (4 if ctx.fast else 1))
    tol = ref["tolerance"]
    y = phantom.axis_mm("y")
    for energy in spec["energies_mev"]:
        plan = ProtonPlan(beams=[ProtonBeam(isocenter_mm=(0.0, 0.0, 0.0), gantry_deg=0.0,
                                            layers=[ProtonLayer(energy_mev=float(energy), spots=[ProtonSpot(x_mm=0.0, y_mm=0.0, mu=1.0)])])])
        dose = drv.compute_dose(hu, phantom.spacing_mm, phantom.origin_mm, plan, nb_primaries=n_prim, calibration=water)   # (z, y, x)
        # A single spot spreads laterally with depth, so its central-axis dose is not a
        # Bragg curve; the laterally integrated depth dose (IDD) is what commissioning uses.
        idd = np.asarray(dose, dtype=float).sum(axis=(0, 2))
        k = int(np.argmax(idd))
        beyond = np.where(idd[k:] <= 0.8 * idd[k])[0]
        if beyond.size == 0:
            res.add(f"R80 at {energy} MeV", None, "distal 80 % found", False, "no distal fall-off inside the phantom"); continue
        j = k + beyond[0]
        r80 = float(np.interp(0.8 * idd[k], [idd[j], idd[j - 1]], [y[j], y[j - 1]]))
        edge = float(np.asarray(dose)[[0, -1], :, :].sum() + np.asarray(dose)[:, :, [0, -1]].sum()) / max(float(np.asarray(dose).sum()), 1e-12)
        res.metrics[f"lateral_edge_fraction_{energy}"] = edge
        pstar = ref.get("pstar_values_mm", {}).get(str(energy))
        expected = pstar or ref["csda_range_mm"].get(str(energy))
        if expected is None:
            expected = ref["fit"]["alpha_cm_per_mev_p"] * energy ** ref["fit"]["p"] * 10.0
        tol_mm = tol["abs_mm"] + tol["percent"] / 100.0 * expected
        res.metrics[f"r80_mm_{energy}"] = r80
        res.add(f"R80 at {energy} MeV (mm)", r80, f"{expected:.1f} ± {tol_mm:.1f}", abs(r80 - expected) <= tol_mm,
                "reference: NIST PSTAR CSDA range" if pstar else "reference: Bragg–Kleeman fit (no PSTAR entry for this energy)")
        res.metrics[f"idd_{energy}"] = {"depth_mm": y.tolist(), "dose": idd.tolist()}
    res.notes.append("radiarch's MCsquare driver (R14) with the water-only calibration; seed fixed, all threads")
    return res


# ---------------------------------------------------------------------------
# Geometry volumes against contour polygons (LCTSC)
# ---------------------------------------------------------------------------

def _contour_volumes_cc(rtstruct_path: Path) -> Dict[str, float]:
    """Volume per ROI from the contour polygons: shoelace area × slice spacing."""
    import pydicom
    ds = pydicom.dcmread(rtstruct_path)
    names = {r.ROINumber: r.ROIName for r in ds.StructureSetROISequence}
    out: Dict[str, float] = {}
    for roi in ds.ROIContourSequence:
        name = names.get(roi.ReferencedROINumber, str(roi.ReferencedROINumber))
        areas_by_z: Dict[float, float] = {}
        for c in getattr(roi, "ContourSequence", []):
            if getattr(c, "ContourGeometricType", "CLOSED_PLANAR") != "CLOSED_PLANAR":
                continue
            pts = np.asarray(c.ContourData, dtype=float).reshape(-1, 3)
            x, yv = pts[:, 0], pts[:, 1]
            area = 0.5 * abs(np.dot(x, np.roll(yv, -1)) - np.dot(yv, np.roll(x, -1)))
            z = round(float(pts[:, 2].mean()), 2)
            areas_by_z[z] = areas_by_z.get(z, 0.0) + area
        if len(areas_by_z) < 2:
            continue
        zs = np.array(sorted(areas_by_z))
        gaps = np.diff(zs)
        # thickness of each contoured slice: half the distance to each neighbour (the
        # end slices get the nominal spacing), so a missing slice is shared by its
        # neighbours as a rasterizer that fills gaps would do
        nominal = float(np.median(gaps))
        thick = np.empty(zs.size)
        thick[0] = nominal / 2 + gaps[0] / 2
        thick[-1] = nominal / 2 + gaps[-1] / 2
        thick[1:-1] = (gaps[:-1] + gaps[1:]) / 2
        out[name] = float(sum(areas_by_z[z] * th for z, th in zip(zs, thick)) / 1000.0)
    return out


def _norm(name: str) -> str:
    return name.lower().replace("_", "").replace(" ", "").replace("-", "")


def run_geometry_volumes(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    import SimpleITK as sitk
    from ..models.geometry import GeometryBuildRequest, PatientRef
    from ..services.geometry import GeometryService
    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (run `make public-lctsc-validation` in smis/data)")
    tol = float(spec.get("tolerance_percent", 5.0))
    svc = GeometryService(base_dir=ctx.workdir / "geometry")
    patients = spec["patients"][:1] if ctx.fast else spec["patients"]
    for pid in patients:
        pdir = root / pid
        rs = list(pdir.glob("RTSTRUCT_*/*.dcm"))
        if not pdir.is_dir() or not rs:
            res.notes.append(f"{pid}: missing"); continue
        polygon = _contour_volumes_cc(rs[0])
        geom = svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"validation-{pid}"),
                                              data_root_override=str(pdir)))
        masks = sitk.GetArrayFromImage(sitk.ReadImage(geom.structure_masks_uri))
        vox_cc = float(np.prod(geom.grid_spec.spacing_mm)) / 1000.0
        for name, label in geom.structure_index.items():
            ours = float(structure_mask(masks, label, getattr(geom, "mask_encoding", "labels")).sum()) * vox_cc
            match = next((v for k, v in polygon.items() if _norm(k) == _norm(name)), None)
            if match is None:
                res.notes.append(f"{pid}/{name}: no contour match"); continue
            dev = (ours - match) / match * 100.0
            res.metrics[f"{pid}/{name}"] = {"rasterized_cc": ours, "polygon_cc": match, "deviation_pct": dev}
            res.add(f"{pid} {name} volume", round(ours, 1), f"{match:.1f} cc ± {tol} %", abs(dev) <= tol)
    return res


# ---------------------------------------------------------------------------
# DVH cross-check against dicompyler-core (Pancreatic-CT-CBCT-SEG)
# ---------------------------------------------------------------------------

def _read_rtdose(path: Path):
    import pydicom
    ds = pydicom.dcmread(path)
    arr = ds.pixel_array.astype(np.float32) * float(ds.DoseGridScaling)   # (frames, rows, cols)
    offsets = np.asarray(ds.GridFrameOffsetVector, dtype=float)
    dz = float(np.median(np.diff(offsets))) if offsets.size > 1 else 1.0
    if dz < 0:
        arr = arr[::-1]; dz = -dz; offsets = offsets[::-1]
    ipp = [float(v) for v in ds.ImagePositionPatient]
    origin = (ipp[0], ipp[1], ipp[2] + float(offsets.min()))
    spacing = (float(ds.PixelSpacing[1]), float(ds.PixelSpacing[0]), dz)
    return arr, spacing, origin, ds


def run_dvh_crosscheck(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    try:
        from dicompylercore import dicomparser, dvhcalc
    except ImportError:
        raise Skip("dicompyler-core not installed (pip install -e ./src[validation])")
    from ..dicom.rtstruct import read_rtstruct
    from ..services.dvh import dose_at_volume
    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (run `make public-pancreatic-validation` in smis/data)")
    tol = spec.get("tolerance_percent", {"mean": 3.0, "d95": 5.0, "max": 3.0})
    graded_keys = set(spec.get("graded", ["mean", "max"]))
    patients = spec["patients"][:1] if ctx.fast else spec["patients"]
    for pid in patients:
        pdir = root / pid
        doses = list(pdir.glob("RTDOSE_*/*.dcm"))
        if not doses:
            res.notes.append(f"{pid}: no RTDOSE"); continue
        dose, spacing, origin, dds = _read_rtdose(doses[0])
        # the planning-CT structure set: same frame of reference, most ROIs
        best = None
        for rs in pdir.glob("RTSTRUCT_*/*.dcm"):
            rp = dicomparser.DicomParser(str(rs))
            structs = rp.GetStructures()
            same_for = rp.ds.ReferencedFrameOfReferenceSequence[0].FrameOfReferenceUID == dds.FrameOfReferenceUID
            if same_for and (best is None or len(structs) > len(best[1])):
                best = (rs, structs)
        if best is None:
            res.notes.append(f"{pid}: no RTSTRUCT in the dose frame of reference"); continue
        rs_path, structs = best
        try:
            contours = {c.name: c for c in read_rtstruct(rs_path).contours}
        except Exception as exc:
            res.notes.append(f"{pid}: could not read {rs_path.name}: {exc}"); continue
        grid_xyz = (dose.shape[2], dose.shape[1], dose.shape[0])
        for roi_number, info in structs.items():
            name = info["name"]
            if name not in contours or info.get("empty"):
                continue
            print(f"   {pid}/{name}", flush=True)
            ref_dvh = dvhcalc.get_dvh(str(rs_path), str(doses[0]), roi_number)
            if ref_dvh.volume <= 0:
                continue
            mask_xyz = contours[name].getBinaryMask(np.array(origin), np.array(grid_xyz), np.array(spacing)).imageArray.astype(bool)
            mask = np.ascontiguousarray(mask_xyz.transpose(2, 1, 0))
            vals = dose[mask]
            if vals.size == 0:
                res.notes.append(f"{pid}/{name}: empty mask on the dose grid"); continue
            ours = {"mean": float(vals.mean()), "max": float(vals.max()), "d95": float(dose_at_volume(vals, 95.0))}
            theirs = {"mean": float(ref_dvh.mean), "max": float(ref_dvh.max), "d95": float(ref_dvh.statistic("D95").value)}
            for key in ("mean", "max", "d95"):
                if theirs[key] <= 0:
                    continue
                dev = (ours[key] - theirs[key]) / theirs[key] * 100.0
                res.metrics[f"{pid}/{name}/{key}"] = {"radiarch": ours[key], "dicompyler": theirs[key], "deviation_pct": dev}
                res.add(f"{pid} {name} {key} (Gy)", round(ours[key], 3), f"{theirs[key]:.3f} ± {tol[key]} % (dicompyler-core)",
                        abs(dev) <= tol[key] if key in graded_keys else None,
                        "" if key in graded_keys else "D95 of low-dose structures sits on the DVH tail, where the two rasterizers' voxel-level differences dominate; informative")
    return res


# ---------------------------------------------------------------------------
# Gamma cross-check against pymedphys (uv, Python 3.12)
# ---------------------------------------------------------------------------

_PYMEDPHYS_SCRIPT = r'''
import json, sys, numpy as np, pymedphys
d = np.load(sys.argv[1])
axes = (d["z"], d["y"], d["x"])
g = pymedphys.gamma(axes, d["reference"], axes, d["evaluated"],
                    dose_percent_threshold=float(d["dose_percent"]), distance_mm_threshold=float(d["dta_mm"]),
                    lower_percent_dose_cutoff=float(d["threshold_percent"]), interp_fraction=5, max_gamma=1.5,
                    local_gamma=False, quiet=True)
valid = ~np.isnan(g)
print(json.dumps({"pass_rate_pct": float((g[valid] <= 1).mean() * 100.0), "evaluated": int(valid.sum())}))
'''


def _radiarch_gamma_pass_rate(evaluated, reference, spacing_zyx, crit) -> float:
    from ..services.gamma import gamma_index
    g = gamma_index(evaluated, reference, spacing_mm=spacing_zyx, dose_percent=crit["dose_percent"],
                    distance_mm=crit["dta_mm"], threshold_pct=crit["threshold_percent"], local=False)
    return float(g.pass_rate_pct)


def run_gamma_crosscheck(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    if shutil.which("uv") is None:
        raise Skip("uv not installed; pymedphys needs Python < 3.13 and is run through `uv run --python 3.12`")
    shape = tuple(spec["grid"]["shape"]); s = float(spec["grid"]["spacing_mm"])
    z, y, x = (np.arange(n) * s for n in shape)
    zz, yy, xx = np.meshgrid(z - z.mean(), y - y.mean(), x - x.mean(), indexing="ij")
    reference = (60.0 * np.exp(-(xx ** 2 + yy ** 2) / (2 * 15.0 ** 2) - zz ** 2 / (2 * 20.0 ** 2))).astype(np.float32)
    crit = spec["criteria"]
    tol = float(spec.get("tolerance_pass_rate_points", 2.0))
    for pert in spec["perturbations"]:
        shift_vox = [int(round(v / s)) for v in pert["shift_mm"]]
        evaluated = np.roll(reference, shift_vox, axis=(0, 1, 2)) * float(pert["scale"])
        ours = _radiarch_gamma_pass_rate(evaluated, reference, (s, s, s), crit)
        npz = ctx.workdir / f"gamma_{pert['name']}.npz"
        np.savez(npz, z=z, y=y, x=x, reference=reference, evaluated=evaluated,
                 dose_percent=crit["dose_percent"], dta_mm=crit["dta_mm"], threshold_percent=crit["threshold_percent"])
        script = ctx.workdir / "pymedphys_gamma.py"; script.write_text(_PYMEDPHYS_SCRIPT)
        cmd = ["uv", "run", "--quiet", "--no-project", "--python", "3.12", "--with", "pymedphys==0.41.0", "--with", "numba",
               "python", str(script), str(npz)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(ctx.workdir))
        if proc.returncode != 0:
            raise Skip(f"pymedphys run failed: {proc.stderr[-400:]}")
        theirs = json.loads(proc.stdout.strip().splitlines()[-1])["pass_rate_pct"]
        res.metrics[pert["name"]] = {"radiarch_pass_pct": ours, "pymedphys_pass_pct": theirs}
        res.add(f"gamma pass rate, {pert['name']}", round(ours, 2), f"{theirs:.2f} % ± {tol} points (pymedphys)", abs(ours - theirs) <= tol,
                "radiarch's gamma searches voxel centres only (no sub-voxel interpolation; TG-218 asks for <= 1/3 of the DTA), "
                "so borderline plans score lower than pymedphys — scheduled for R5")
    return res


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

KINDS: Dict[str, Callable[[dict, Context], CaseResult]] = {
    "photon_pdd": run_photon_pdd,
    "photon_profile": run_photon_profile,
    "photon_slab": run_photon_slab,
    "photon_output_vs_field": run_photon_output_vs_field,
    "proton_range": run_proton_range,
    "geometry_volumes": run_geometry_volumes,
    "dvh_crosscheck": run_dvh_crosscheck,
    "gamma_crosscheck": run_gamma_crosscheck,
}


def load_cases() -> Dict[str, dict]:
    import yaml
    cases = {}
    for f in sorted(CASES_DIR.glob("*.yaml")):
        spec = yaml.safe_load(f.read_text())
        cases[spec["name"]] = spec
    return cases


def run_case(spec: dict, ctx: Context) -> CaseResult:
    t0 = time.time()
    try:
        res = KINDS[spec["kind"]](spec, ctx)
        res.finish()
    except Skip as exc:
        res = CaseResult(spec["name"], spec["kind"], status="skip", notes=[str(exc)])
    except Exception:
        res = CaseResult(spec["name"], spec["kind"], status="error", error=traceback.format_exc())
    res.seconds = round(time.time() - t0, 1)
    return res


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RADIARCH_ROOT, capture_output=True, text=True).stdout.strip() or "unknown"
    except Exception:  # pragma: no cover
        return "unknown"


def write_results(results: List[CaseResult], out_dir: Path, ctx: Context) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = out_dir / f"{stamp}-{_git_commit()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    from ..models.common import RESEARCH_USE_ONLY
    payload = {
        "intended_use": RESEARCH_USE_ONLY,
        "radiarch_commit": _git_commit(), "timestamp": stamp, "fast": ctx.fast, "host": platform.node(),
        "python": sys.version.split()[0],
        "results": [asdict(r) for r in results],
    }
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2))
    lines = [f"# Radiarch validation run {stamp} ({_git_commit()})", "", RESEARCH_USE_ONLY, ""]
    lines.append("| Case | Status | Time (s) | Checks |")
    lines.append("|---|---|---|---|")
    for r in results:
        n_pass = sum(1 for c in r.checks if c.passed is True); n_fail = sum(1 for c in r.checks if c.passed is False)
        n_info = sum(1 for c in r.checks if c.passed is None)
        lines.append(f"| {r.name} | **{r.status}** | {r.seconds} | {n_pass} pass, {n_fail} fail, {n_info} informative |")
    for r in results:
        lines += ["", f"## {r.name} — {r.status}", ""]
        if r.error:
            lines += ["```", r.error.strip()[-1500:], "```"]
        for n in r.notes:
            lines.append(f"- note: {n}")
        if r.checks:
            lines += ["", "| Check | Value | Target | Result |", "|---|---|---|---|"]
            for c in r.checks:
                flag = "informative" if c.passed is None else ("pass" if c.passed else "FAIL")
                val = c.value if not isinstance(c.value, float) else f"{c.value:.4g}"
                lines.append(f"| {c.name} | {val} | {c.target} | {flag} |")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n")
    return run_dir


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="radiarch validation harness")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--cases", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", type=Path, default=RADIARCH_ROOT / "validation" / "results")
    ap.add_argument("--fast", action="store_true", help="coarser grids and fewer primaries (smoke run)")
    ap.add_argument("--spacing-scale", type=float, default=1.0)
    args = ap.parse_args(argv)
    cases = load_cases()
    if args.list:
        for name, spec in cases.items():
            print(f"{name:32s} {spec['kind']:22s} {spec.get('description', '')[:90]}")
        return 0
    names = list(cases) if args.all else args.cases
    unknown = [n for n in names if n not in cases]
    if unknown or not names:
        print("unknown or no cases:", unknown or "(none given; use --all or --cases)", file=sys.stderr)
        return 2
    ctx = Context(fast=args.fast, spacing_scale=args.spacing_scale)
    results = []
    for n in names:
        print(f"== {n}", flush=True)
        r = run_case(cases[n], ctx)
        print(f"   {r.status} in {r.seconds}s" + (f": {r.notes[0]}" if r.status == 'skip' and r.notes else ""), flush=True)
        results.append(r)
    run_dir = write_results(results, args.out, ctx)
    shutil.rmtree(ctx.workdir, ignore_errors=True)
    print("results:", run_dir / "summary.md")
    return 0 if all(r.status in ("pass", "info", "skip") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
