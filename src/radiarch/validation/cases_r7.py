"""The R7 validation cases: Monte Carlo comparison, Dij consistency per engine,
proton Bragg-peak shape, TG-119 planning, the lung end-to-end case.

Registered into ``run.KINDS`` by ``run.py``. Everything here goes through the
same services the API uses, on an artifact directory inside the run's work
directory, so a case exercises the pipeline a user gets.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from loguru import logger

from . import phantoms as ph
from .common import CaseResult, Context, Skip, _ccc_engine, _open_field_plan, _within, data_root, load_reference

RADIARCH_ROOT = Path(__file__).resolve().parents[3]
MC_DIR = Path(__file__).resolve().parent / "references" / "mc"
SIMPLEFANTOM = RADIARCH_ROOT / "tests" / "data" / "SimpleFantomWithStruct"
OAR_WEIGHT = 200.0        # an OAR goal term against the target's uniform term at weight 100


# ---------------------------------------------------------------------------
# Services on the run's work directory
# ---------------------------------------------------------------------------

def _services(ctx: Context, data_root_dir: Optional[Path] = None) -> None:
    """Point the services at an artifact directory inside the work directory."""
    from ..config import get_settings

    art = ctx.workdir / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    os.environ["RADIARCH_ARTIFACT_DIR"] = str(art)
    os.environ.setdefault("RADIARCH_ORTHANC_USE_MOCK", "true")
    os.environ.setdefault("RADIARCH_DATABASE_URL", "")
    os.environ.setdefault("RADIARCH_BROKER_URL", "memory://")
    os.environ.setdefault("RADIARCH_RESULT_BACKEND", "cache+memory://")
    os.environ.setdefault("RADIARCH_DICOMWEB_URL", "")
    if data_root_dir is not None:
        os.environ["RADIARCH_DATA_ROOT"] = str(data_root_dir)
    get_settings.cache_clear()


def _read_volume(uri: str) -> np.ndarray:
    import SimpleITK as sitk
    path = uri[len("file://"):] if uri.startswith("file://") else uri
    return sitk.GetArrayFromImage(sitk.ReadImage(path)).astype(np.float32)


def _dose_at(doses: np.ndarray, pct: float) -> float:
    from ..services.dvh import dose_at_volume
    return float(dose_at_volume(doses, pct))


def _agreement(direct: np.ndarray, via: np.ndarray, lit_frac: float = 0.01, high_frac: float = 0.5) -> Dict[str, float]:
    """Integral ratio, correlation and the high-dose p95 relative error of two dose volumes
    (the gate of the nightly MCsquare Dij test, tests/test_mcsquare_dij_consistency.py)."""
    d = direct.astype(np.float64).ravel(); v = via.astype(np.float64).ravel()
    mx = float(d.max())
    lit = d > lit_frac * mx
    dl, vl = d[lit], v[lit]
    high = d > high_frac * mx
    rel_high = np.abs(d[high] - v[high]) / np.maximum(d[high], 1e-12)
    return {"integral_ratio": float(vl.sum() / dl.sum()) if dl.sum() > 0 else float("nan"),
            "correlation": float(np.corrcoef(dl, vl)[0, 1]) if dl.std() > 0 and vl.std() > 0 else float("nan"),
            "highdose_p95": float(np.percentile(rel_high, 95)) if rel_high.size else float("nan"),
            "highdose_count": int(high.sum())}


# ---------------------------------------------------------------------------
# photon_vs_mc — CCC against the OpenGATE references
# ---------------------------------------------------------------------------

def _mc_reference(name: str):
    npz, meta = MC_DIR / f"{name}.npz", MC_DIR / f"{name}.json"
    if not npz.is_file():
        return None
    from .mc_reference import load_reference_arrays
    dose, unc, spacing, origin, primaries = load_reference_arrays(npz)
    prov = json.loads(meta.read_text(encoding="utf-8")) if meta.is_file() else {}
    return {"dose": dose, "uncertainty": unc, "spacing_mm": spacing, "origin_mm": origin, "primaries": primaries, "provenance": prov}


def _resample_to(dose: np.ndarray, spacing_from: Sequence[float], origin_from: Sequence[float], phantom: ph.Phantom) -> np.ndarray:
    """Trilinear resampling of a (z, y, x) volume onto a phantom's grid."""
    from scipy.ndimage import map_coordinates
    nz, ny, nx = phantom.shape
    z = (phantom.axis_mm("z") - origin_from[2]) / spacing_from[2]
    y = (phantom.axis_mm("y") - origin_from[1]) / spacing_from[1]
    x = (phantom.axis_mm("x") - origin_from[0]) / spacing_from[0]
    zz, yy, xx = np.meshgrid(z, y, x, indexing="ij")
    return map_coordinates(dose, [zz.ravel(), yy.ravel(), xx.ravel()], order=1, mode="nearest").reshape(nz, ny, nx).astype(np.float32)


def _phantom_for(case: str, s: float) -> ph.Phantom:
    return {"water_10x10": lambda: ph.water_box(150.0, 300.0, s), "water_4x4": lambda: ph.water_box(150.0, 300.0, s),
            "water_20x20": lambda: ph.water_box(150.0, 300.0, s), "lung_slab": lambda: ph.lung_slab(s), "lung_slab_2x2": lambda: ph.lung_slab(s), "bone_slab": lambda: ph.bone_slab(s)}[case]()


def _cax3(dose: np.ndarray, phantom: ph.Phantom) -> np.ndarray:
    """Central-axis dose as the mean of the 3 x 3 voxels around the axis (against Monte Carlo noise)."""
    cz, cx = phantom.centre_index("z"), phantom.centre_index("x")
    return dose[cz - 1:cz + 2, :, cx - 1:cx + 2].mean(axis=(0, 2))


CCC_CACHE = Path(os.environ.get("RADIARCH_VALIDATION_CACHE", str(RADIARCH_ROOT / "validation" / "cache"))) / "ccc"


def _cached_ccc_dose(eng, phantom: ph.Phantom, plan, params: dict, key: str) -> np.ndarray:
    """CCC dose of a phantom, cached by the case, the setting and the engine build (binary and kernel digests),
    so iterating on the comparison does not recompute 5-minute full-scatter runs. ``RADIARCH_VALIDATION_CACHE``
    moves the cache; deleting it is always safe."""
    import hashlib
    drv = eng.driver(params)
    binary = drv.binary
    ident = hashlib.sha256()
    ident.update(key.encode()); ident.update(json.dumps(params, sort_keys=True, default=str).encode())
    ident.update(drv.kernel_fingerprint().encode() if drv.kernel_dir.is_dir() else b"")
    if binary.is_file():
        ident.update(binary.read_bytes())
    ident.update(str(phantom.shape).encode()); ident.update(str(phantom.origin_mm).encode())
    path = CCC_CACHE / f"{ident.hexdigest()[:24]}.npy"
    if path.is_file():
        return np.load(path)
    dose = eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params=params)
    try:
        CCC_CACHE.mkdir(parents=True, exist_ok=True)
        np.save(path, np.asarray(dose, dtype=np.float32))
    except OSError as exc:  # pragma: no cover — a read-only checkout still runs
        logger.warning("validation cache not writable ({}): {}", CCC_CACHE, exc)
    return dose


def run_photon_vs_mc(spec: dict, ctx: Context) -> CaseResult:
    """CCC against the OpenGATE references, per scatter setting of the engine. Water: depth dose and profile
    normalised at 10 cm, gamma. Slabs: the heterogeneity correction factor, slab dose over water dose at the
    same depth for the same field, of CCC against that of Monte Carlo; the factor cancels both engines' water
    depth dose and absolute calibration, so it isolates how each handles the heterogeneity."""
    res = CaseResult(spec["name"], spec["kind"])
    from ..services.gamma import gamma_index

    eng = _ccc_engine()
    tol = spec.get("tolerances", {})
    settings = {"shipped": list(spec["cases"])} if ctx.fast else dict(spec.get("settings") or {spec.get("scatter", "full"): list(spec["cases"])})
    missing = sorted({c for cs in settings.values() for c in cs if _mc_reference(c) is None})
    crit = spec.get("gamma", {"dose_percent": 3.0, "dta_mm": 3.0, "threshold_percent": 10.0, "pass_percent": 95.0})
    for scatter, cases in settings.items():
        cases = [c for c in cases if c not in missing]
        if not cases:
            continue
        params = {"scatter": scatter, "n_jobs": int(spec.get("n_jobs", 8))}
        if ctx.fast:
            params["calibration_spacing_mm"] = 5.0
        water: Dict[str, np.ndarray] = {}           # CAX of the water case: "ccc", "mc"
        for case in sorted(cases, key=lambda c: not c.startswith("water")):    # water first: the slabs need it
            ref = _mc_reference(case)
            s = ctx.spacing(ref["spacing_mm"][0])
            phantom = _phantom_for(case, s)
            field = float(ref["provenance"].get("field_mm", 100.0))
            plan = _open_field_plan(field, spec.get("leaf_width_mm", 10.0), spec.get("beamlet_mm", 10.0))
            ccc = _cached_ccc_dose(eng, phantom, plan, params, key=f"{case}-{s:g}mm-{scatter}-{field:g}-{spec.get('beamlet_mm', 10.0)}")
            # the references put a voxel boundary on the axis (an even count), the phantoms a voxel centre (odd):
            # the reference is always interpolated onto the phantom grid
            mc = _resample_to(ref["dose"], ref["spacing_mm"], ref["origin_mm"], phantom)
            unc = _resample_to(ref["uncertainty"], ref["spacing_mm"], ref["origin_mm"], phantom)
            tag = f"[{scatter}] {case}"
            cz, cx = phantom.centre_index("z"), phantom.centre_index("x")
            y = phantom.axis_mm("y")
            j10 = phantom.depth_index(100.0)
            cax_c, cax_m = _cax3(ccc, phantom), _cax3(mc, phantom)
            res.metrics[f"{scatter}_{case}_cax"] = {"depth_mm": y.tolist(), "ccc_gy_per_mu": cax_c.tolist(), "mc_gy_per_primary": cax_m.tolist()}
            res.metrics[f"{case}_mc_rel_uncertainty_cax_10cm"] = float(unc[cz, j10, cx])
            if case.startswith("water"):
                if case == "water_10x10":
                    water = {"ccc": cax_c, "mc": cax_m}
                t = float(tol.get("in_field_percent", 2.0))
                n_c, n_m = cax_c / cax_c[j10], cax_m / cax_m[j10]
                km, kc = int(np.argmax(n_m)), int(np.argmax(n_c))
                pdd10_m, pdd10_c = 100.0 / n_m[km], 100.0 / n_c[kc]
                res.add(f"{tag}: PDD10 CCC vs MC (%)", pdd10_c, f"{pdd10_m:.1f} ± {t} (MC)", abs(pdd10_c - pdd10_m) <= t, "MPPG 5.a basic photon, in field")
                res.add(f"{tag}: d_max CCC vs MC (mm)", float(y[kc]), f"{y[km]:.1f} (MC)", None,
                        "informative: both transport photons only, no contamination electrons; CCC's build-up depends on its grid")
                for depth in (50.0, 150.0, 200.0, 250.0):
                    j = phantom.depth_index(depth)
                    ratio = float(n_c[j] / n_m[j])
                    res.add(f"{tag}: CAX dose at {depth:g} mm, CCC / MC", ratio, f"1 ± {t / 100:.2f}", _within(ratio, 1.0, t / 100), "normalised at 10 cm")
                x = phantom.axis_mm("x")
                pc = ccc[cz, j10, :] / ccc[cz, j10, cx]; pm = mc[cz - 1:cz + 2, j10 - 1:j10 + 2, :].mean(axis=(0, 1)); pm = pm / pm[cx]
                pens = {}
                for name, prof in (("ccc", pc), ("mc", pm)):
                    right = x >= 0; order = np.argsort(prof[right])
                    pens[name] = float(np.interp(0.2, prof[right][order], x[right][order]) - np.interp(0.8, prof[right][order], x[right][order]))
                res.add(f"{tag}: penumbra 80-20 % at 10 cm, CCC (mm)", pens["ccc"], f"{pens['mc']:.1f} ± {max(2.0, s):g} (MC)", abs(pens["ccc"] - pens["mc"]) <= max(2.0, s),
                        "MPPG 5.a penumbra; the CCC penumbra also reflects its 10 mm beamlet grid")
                oar = 0.4 * field
                oc, om = float(np.interp(oar, x, pc)), float(np.interp(oar, x, pm))
                res.add(f"{tag}: off-axis ratio at {oar:g} mm, 10 cm depth", oc, f"{om:.3f} ± 0.03 (MC)", abs(oc - om) <= 0.03, "in-field profile")
                g = gamma_index(ccc / ccc[cz, j10, cx], mc / float(cax_m[j10]), spacing_mm=phantom.spacing_mm[::-1], dose_percent=crit["dose_percent"],
                                distance_mm=crit["dta_mm"], threshold_pct=crit["threshold_percent"], local=False)
                res.add(f"{tag}: gamma {crit['dose_percent']:g} %/{crit['dta_mm']:g} mm pass rate (%)", float(g.pass_rate_pct), f"≥ {crit['pass_percent']}",
                        float(g.pass_rate_pct) >= float(crit["pass_percent"]), "MPPG 5.b / TG-218 criteria, normalised at 10 cm depth on the axis")
            else:
                if not water:
                    res.notes.append(f"{tag}: no water case under this setting; correction factors skipped"); continue
                t = float(tol.get("heterogeneity_percent", 3.0))
                depths = spec.get("probe_depths_mm", [20, 50, 80, 150, 200, 250])
                for depth in (depths.get(case, [20, 50, 80, 150, 200, 250]) if isinstance(depths, dict) else depths):
                    j = phantom.depth_index(depth)
                    cf_c = float(cax_c[j] / water["ccc"][j]); cf_m = float(cax_m[j] / water["mc"][j])
                    res.metrics[f"{scatter}_{case}_cf_{depth:g}mm"] = {"ccc": cf_c, "mc": cf_m}
                    res.add(f"{tag}: correction factor at {depth:g} mm, CCC vs MC", round(cf_c, 4), f"{cf_m:.3f} ± {t / 100 * cf_m:.3f} (MC)",
                            abs(cf_c - cf_m) <= t / 100 * cf_m, "slab dose / water dose at the same depth; MPPG 5.a / TECDOC-1583 heterogeneity 3 %")
            res.notes.append(f"{tag}: MC {ref['primaries']:.2e} primaries, relative uncertainty {float(unc[cz, j10, cx]) * 100:.1f} % on the axis at 10 cm")
    res.notes.append("the Monte Carlo beam carries the spectrum of the CCC kernels (Mohan 6 MV, mean 1.90 MeV; kernel fluence mean 1.89 MeV), so the comparison is transport in the phantom")
    if missing:
        msg = f"no Monte Carlo reference for {missing}: run `python -m radiarch.validation.mc_reference --case <name>` (see the module docstring)"
        if len(missing) == len({c for cs in settings.values() for c in cs}):
            raise Skip(msg)
        res.notes.append(msg)
    return res


# ---------------------------------------------------------------------------
# dij_consistency — Dij · w against the forward dose, per engine, through the services
# ---------------------------------------------------------------------------

def run_dij_consistency(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    if not SIMPLEFANTOM.is_dir():
        raise Skip(f"SimpleFantom test data not found at {SIMPLEFANTOM}")
    _services(ctx, SIMPLEFANTOM)
    from ..models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from ..models.dose import DoseComputeRequest, EngineSpec, InfluenceBuildRequest, WeightVector
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from ..services.beam_model import BeamModelService
    from ..services.dose import DoseService
    from ..services.dose_engines.registry import engine_health
    from ..services.geometry import GeometryService

    s = ctx.spacing(spec.get("spacing_mm", 2.0))
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="simplefantom"), grid_spec=GridSpec(spacing_mm=(s, s, s))))
    rng = np.random.default_rng(20261021)
    dose_service = DoseService()
    for eng in spec.get("engines", ["ccc", "mcsquare"]):
        h = engine_health(eng)
        if not h.get("available"):
            res.notes.append(f"{eng}: unavailable ({h.get('reason', '')}); skipped"); continue
        e = spec.get(eng, {})
        if eng in ("ccc", "pb"):
            bm = BeamModelService().build(BeamModelBuildRequest(
                geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id="synthetic-120",
                beam_set=BeamSetSpec(beams=[BeamSpec(beam_id="B1", gantry_deg=0.0), BeamSpec(beam_id="B2", gantry_deg=90.0)]),
                delivery_params=DeliveryParams(jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))))
            params = {"n_jobs": int(e.get("n_jobs", 8))}
        else:   # mcsquare
            bm = BeamModelService().build(BeamModelBuildRequest(
                geometry_id=geo.geometry_id, modality=Modality.proton_pbs,
                beam_set=BeamSetSpec(isocenter_mm=(0.0, 0.0, 0.0), beams=[BeamSpec(beam_id="B1", gantry_deg=0.0)]),
                delivery_params=DeliveryParams(spot_spacing_mm=float(e.get("spot_spacing_mm", 7.0)), layer_spacing_mm=float(e.get("layer_spacing_mm", 7.0)))))
            params = {"nb_primaries": float(e.get("nb_primaries", 1e6)) / (5 if ctx.fast else 1), "seed": 20261021}
        n = bm.fluence_elements.total_count
        w = rng.uniform(0.5, 2.0, size=n).astype(np.float32)
        engine = EngineSpec(name=eng, params=params)
        direct = _read_volume(dose_service.compute_dose(DoseComputeRequest(
            geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, engine=engine, weights=WeightVector(length=n, values=w.tolist()), rbe=1.0)).dose_grid_uri)
        inf = dose_service.build_influence(InfluenceBuildRequest(geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, engine=engine, rbe=1.0))
        data = dose_service.influence_store.load_influence(inf.influence_id)
        from scipy.sparse import csr_matrix
        dij = csr_matrix((data.data, data.indices, data.indptr), shape=(data.n_voxels, data.n_elements))
        via = np.asarray(dij @ w.astype(np.float64)).reshape(direct.shape).astype(np.float32)
        rep = _agreement(direct, via)
        res.metrics[eng] = {**rep, "n_elements": int(n), "params": params}
        default_tols = {"mcsquare": {"integral_ratio": 0.05, "correlation": 0.95, "highdose_p95": 0.15},
                        # pb: the forward dose convolves the full 200 mm kernel; the Dij stops 80 mm from each beamlet and
                        # thins entries below 0.3 % of a column's maximum (unbiased), R8
                        "pb": {"integral_ratio": 0.03, "correlation": 0.999, "highdose_p95": 0.02}}
        tols = dict(e.get("tolerances", default_tols.get(eng, {"integral_ratio": 1e-4, "correlation": 0.9999, "highdose_p95": 1e-3})))
        if ctx.fast and eng == "mcsquare":       # a fifth of the primaries: the per-voxel noise is sqrt(5) larger
            tols = {k: (v * 2.2 if k != "correlation" else 1 - (1 - v) * 2.2) for k, v in tols.items()}
        res.add(f"{eng}: integral ratio Dij·w / forward", rep["integral_ratio"], f"1 ± {tols['integral_ratio']:g}", _within(rep["integral_ratio"], 1.0, tols["integral_ratio"]),
                {"mcsquare": "two independent Monte Carlo runs", "pb": "forward: full kernel; Dij: 80 mm cutoff, sampled tail"}.get(
                    eng, "deterministic engine: the forward dose is the same beamlets"))
        res.add(f"{eng}: correlation above 1 % of max", rep["correlation"], f"≥ {tols['correlation']}", rep["correlation"] >= tols["correlation"])
        res.add(f"{eng}: high-dose (≥ 50 % of max) p95 relative error", rep["highdose_p95"], f"≤ {tols['highdose_p95']:g}", rep["highdose_p95"] <= tols["highdose_p95"],
                {"mcsquare": "two independent Monte Carlo runs: the p95 of the relative difference in the well-sampled region is the counting noise of both",
                 "pb": "the Dij's sampled tail and cutoff: per-voxel spread of the unbiased roulette"}.get(
                    eng, "deterministic engine: rounding only"))
    return res


# ---------------------------------------------------------------------------
# proton_bragg_peak — shape of single spots in water against the analytic expectations
# ---------------------------------------------------------------------------

def _bdl_row(bdl_path: Path, energy: float) -> Optional[Dict[str, float]]:
    lines = [l for l in bdl_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    header = None
    for l in lines:
        if l.startswith("NominalEnergy"):
            header = l.split(); continue
        if header and not l.startswith("#"):
            vals = l.split()
            if len(vals) >= len(header) and abs(float(vals[0]) - energy) < 1e-6:
                return dict(zip(header, map(float, vals[:len(header)])))
    return None


def _sigma_mm(values: np.ndarray, axis_mm: np.ndarray) -> float:
    w = np.clip(values.astype(float), 0.0, None)
    if w.sum() <= 0:
        return float("nan")
    m = float((w * axis_mm).sum() / w.sum())
    return float(np.sqrt((w * (axis_mm - m) ** 2).sum() / w.sum()))


def _bdl_nozzle_to_isocenter_mm(bdl_path: Path) -> float:
    lines = [l.strip() for l in bdl_path.read_text(encoding="utf-8").splitlines()]
    for i, l in enumerate(lines):
        if l.lower().startswith("nozzle exit to isocenter distance") and i + 1 < len(lines):
            return float(lines[i + 1].split()[0])
    return 0.0


def _propagated_sigma_mm(row: Dict[str, float], axis: str, d_mm: float) -> float:
    """The primary Gaussian of a BDL row carried from the nozzle exit to the isocenter in vacuum
    (the Fermi-Eyges moments: sigma^2 + 2 rho sigma theta d + theta^2 d^2)."""
    s0 = float(row[f"SpotSize1{axis}"]); th = float(row.get(f"Divergence1{axis}", 0.0)); rho = float(row.get(f"Correlation1{axis}", 0.0))
    return math.sqrt(max(s0 ** 2 + 2.0 * rho * s0 * th * d_mm + (th * d_mm) ** 2, 0.0))


def _fwhm_sigma_mm(values: np.ndarray, axis_mm: np.ndarray) -> float:
    """Sigma of the core from the full width at half maximum (Gaussian: FWHM = 2.355 sigma)."""
    v = np.clip(values.astype(float), 0.0, None)
    if v.max() <= 0:
        return float("nan")
    half = v.max() / 2.0
    above = np.flatnonzero(v >= half)
    lo, hi = int(above[0]), int(above[-1])
    x_lo = float(np.interp(half, [v[lo - 1], v[lo]], [axis_mm[lo - 1], axis_mm[lo]])) if lo > 0 else float(axis_mm[lo])
    x_hi = float(np.interp(half, [v[hi + 1], v[hi]], [axis_mm[hi + 1], axis_mm[hi]])) if hi < v.size - 1 else float(axis_mm[hi])
    return (x_hi - x_lo) / 2.355


def run_proton_bragg_peak(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    ref = load_reference(spec.get("references", "proton_water"))
    from ..models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot
    from ..services.dose_engines.mcsquare_driver import CalibrationTables, MCsquareDriver

    drv = MCsquareDriver(work_root=ctx.workdir / "mcsquare", n_threads=0, seed=20261021)
    ok, reason = drv.availability()
    if not ok:
        raise Skip(f"MCsquare engine not available: {reason}")
    p = spec["phantom"]
    s = ctx.spacing(p.get("spacing_mm", 1.0))
    phantom = ph.water_box(p.get("half_width_mm", 40.0), p.get("depth_mm", 350.0), s)
    hu = np.zeros(phantom.shape, dtype=np.float32)
    water = CalibrationTables.water()
    n_prim = int(spec.get("nb_primaries", 400000) / (4 if ctx.fast else 1))
    y = phantom.axis_mm("y"); x = phantom.axis_mm("x"); z = phantom.axis_mm("z")
    fit = ref["fit"]
    bdl_path = Path(drv.assets.bdl_path(drv.bdl_name))          # the library the driver runs with
    for energy in spec["energies_mev"]:
        plan = ProtonPlan(beams=[ProtonBeam(isocenter_mm=(0.0, 0.0, 0.0), gantry_deg=0.0,
                                            layers=[ProtonLayer(energy_mev=float(energy), spots=[ProtonSpot(x_mm=0.0, y_mm=0.0, mu=1.0)])])])
        dose = np.asarray(drv.compute_dose(hu, phantom.spacing_mm, phantom.origin_mm, plan, nb_primaries=n_prim, calibration=water), dtype=float)
        idd = dose.sum(axis=(0, 2))
        k = int(np.argmax(idd))
        # distal 80 % and 20 % depths of the IDD
        def depth_at(frac: float) -> float:
            beyond = np.where(idd[k:] <= frac * idd[k])[0]
            if beyond.size == 0:
                return float("nan")
            j = k + beyond[0]
            return float(np.interp(frac * idd[k], [idd[j], idd[j - 1]], [y[j], y[j - 1]]))
        r80, r20 = depth_at(0.8), depth_at(0.2)
        width = r20 - r80
        # Bortfeld 1997: range straggling sigma = 0.012 R^0.935 (cm); the beam's energy spread adds p R sigma_E/E
        R_cm = r80 / 10.0
        sig_strag = 0.012 * R_cm ** 0.935 * 10.0
        row = _bdl_row(bdl_path, float(energy)) if bdl_path and bdl_path.is_file() else None
        sig_e = None
        if row is not None and "EnergySpread" in row and "MeanEnergy" in row and row["MeanEnergy"] > 0:
            # MCsquare's BDL gives the spread as a percentage of the mean energy
            sig_e = fit["p"] * r80 * (row["EnergySpread"] / 100.0)
        sig_total = math.hypot(sig_strag, sig_e or 0.0)
        expected = 1.683 * sig_total          # 80-20 % of a Gaussian fall-off
        res.metrics[f"distal_80_20_mm_{energy}"] = width
        res.metrics[f"expected_80_20_mm_{energy}"] = expected
        tol = max(1.0, 0.3 * expected)
        res.add(f"distal 80-20 % fall-off at {energy} MeV (mm)", width, f"{expected:.1f} ± {tol:.1f} (Bortfeld straggling"
                + (f" + BDL energy spread {row['EnergySpread']:.2f} %" if sig_e is not None else "") + ")",
                _within(width, expected, tol), "Bortfeld, Med Phys 24:2024, 1997: sigma_straggling = 0.012 R^0.935 (cm); Gaussian 80-20 = 1.683 sigma")
        # peak-to-entrance ratio of the IDD (informative: the literature quotes 3-5 for mono-energetic beams)
        pe = float(idd[k] / idd[max(1, int(5.0 / s))])
        res.add(f"IDD peak-to-entrance at {energy} MeV", pe, "3-5 (informative)", None, "entrance at 5 mm depth")
        # lateral sigma at the entrance against the BDL spot size (the second Gaussian carries a few % of the weight)
        entry = dose[:, max(1, int(5.0 / s)), :]
        sx, sz = _sigma_mm(entry.sum(axis=0), x), _sigma_mm(entry.sum(axis=1), z)
        res.metrics[f"entrance_sigma_mm_{energy}"] = {"x": sx, "z": sz}
        # the core of the spot: sigma from the FWHM of the entrance profile (the library's second, wide Gaussian
        # carries a few per cent of the weight and does not move the half maximum) against SpotSize1 of the BDL
        core_x, core_y = _fwhm_sigma_mm(entry.sum(axis=0), x), _fwhm_sigma_mm(entry.sum(axis=1), z)
        res.metrics[f"entrance_core_sigma_mm_{energy}"] = {"x": core_x, "y": core_y}
        if row is not None and "SpotSize1x" in row:
            d_nozzle = _bdl_nozzle_to_isocenter_mm(bdl_path)
            for label, meas in (("x", core_x), ("y", core_y)):
                exp = _propagated_sigma_mm(row, label, d_nozzle)
                tol_s = max(0.5, 0.10 * exp)
                res.add(f"entrance core sigma {label} at {energy} MeV (mm)", meas,
                        f"{exp:.2f} ± {tol_s:.2f} (BDL SpotSize1{label} propagated {d_nozzle:g} mm to the isocenter)", _within(meas, exp, tol_s),
                        "the beam data library gives the primary Gaussian at the nozzle exit: sigma^2 = s0^2 + 2 rho s0 theta d + theta^2 d^2 "
                        f"(divergence theta, correlation rho); the isocenter is at the phantom surface, read at 5 mm depth; rms with the halo {sx:.2f} / {sz:.2f} mm")
        # lateral growth: sigma at 80 % of the range against Highland (Gottschalk 2010, water)
        j80 = phantom.depth_index(0.8 * r80)
        mid = dose[:, j80, :]
        smx = _sigma_mm(mid.sum(axis=0), x)
        res.metrics[f"sigma_x_at_0.8R_mm_{energy}"] = smx
        res.add(f"lateral sigma x at 0.8 R80 ({0.8 * r80:.0f} mm) for {energy} MeV (mm)", smx, "informative (multiple Coulomb scattering grows it to several mm)", None,
                "Gottschalk 2010 / Highland; a transport check, no tolerance set")
        res.metrics[f"idd_{energy}"] = {"depth_mm": y.tolist(), "dose": idd.tolist()}
    res.notes.append(f"MCsquare through radiarch's driver, water-only calibration, {n_prim} primaries per spot, seed fixed")
    return res


# ---------------------------------------------------------------------------
# tg119_planning — the four TG-119 structure sets planned by radiarch, scored against the goals
# ---------------------------------------------------------------------------

def _structure_extent_mm(mask_zyx: np.ndarray, origin: Sequence[float], spacing: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    idx = np.argwhere(mask_zyx)
    lo = origin[::-1] + idx.min(axis=0) * np.asarray(spacing[::-1]); hi = origin[::-1] + idx.max(axis=0) * np.asarray(spacing[::-1])
    return lo[::-1], hi[::-1]       # (x, y, z)


def _goal_value(doses: np.ndarray, metric: str) -> float:
    m = metric.strip()
    if m.lower() == "dmax":
        return float(doses.max())
    if m.lower() == "dmean":
        return float(doses.mean())
    if m.upper().startswith("D"):
        return _dose_at(doses, float(m[1:]))
    raise ValueError(f"unsupported goal metric {metric}")


NORMALISATION_HEADROOM = 1.002   # plans are normalised 0.2 % above the coverage goal, so percentile rounding cannot fail it


def _goal_met(doses: np.ndarray, goal: dict) -> bool:
    value = _goal_value(doses, goal["metric"])
    return value >= float(goal["gy"]) - 1e-6 if goal["op"].startswith(">") else value <= float(goal["gy"]) + 1e-6


def _target_names(target: str, goals: List[dict]) -> List[str]:
    """The case's targets: the named one and every structure with a coverage (>=) goal."""
    return list(dict.fromkeys([target] + [g["structure"] for g in goals if g["op"].startswith(">")]))


def _objectives(arrays, target: str, rx_gy: float, goals: List[dict], scale: Dict[int, float], level: Dict[int, float]):
    """The objective set for a goal list. Every target (a structure with a coverage goal) gets a uniform term
    between its coverage goal and its hot-spot limit (the prescription for the main target without a limit),
    a DVH-minimum term for coverage and a DVH-maximum term for its hot spot; organs get a DVH-maximum and a
    maximum-dose term. ``scale`` multiplies a goal's weight and ``level`` an organ limit's dose (the rounds)."""
    from ..models.optimization import ObjectiveSpec

    targets = set(_target_names(target, goals))
    objectives = []
    for t in _target_names(target, goals):
        if t not in arrays.structure_index:
            continue
        cover = [float(g["gy"]) for g in goals if g["structure"] == t and g["op"].startswith(">")]
        hot = [float(g["gy"]) for g in goals if g["structure"] == t and g["op"].startswith("<")]
        if cover and hot and min(hot) > max(cover):
            uniform = (max(cover) + min(hot)) / 2.0
        elif t == target:
            uniform = rx_gy
        else:
            uniform = max(cover) * 1.05 if cover else rx_gy
        objectives.append(ObjectiveSpec(type="DUniform", structure_name=t, dose_gy=uniform, weight=100.0 if t == target else 60.0))
    for i, g in enumerate(goals):
        st, metric, op, val = g["structure"], g["metric"].strip(), g["op"], float(g["gy"])
        if st not in arrays.structure_index:
            continue
        w, lv = scale.get(i, 1.0), level.get(i, 1.0)
        on_target = st in targets
        if op.startswith(">"):
            frac = float(metric[1:]) / 100.0 if metric.upper().startswith("D") and metric[1:].replace(".", "", 1).isdigit() else 0.99
            objectives.append(ObjectiveSpec(type="DVHMin", structure_name=st, dose_gy=val, weight=100.0 * w, volume_fraction=frac))
        elif metric.lower() == "dmax":
            objectives.append(ObjectiveSpec(type="DMax", structure_name=st, dose_gy=val * lv, weight=(30.0 if on_target else OAR_WEIGHT) * w))
        elif metric.lower() == "dmean":
            objectives.append(ObjectiveSpec(type="DVHMax", structure_name=st, dose_gy=val * lv, weight=OAR_WEIGHT * w, volume_fraction=0.5))
        elif metric.upper().startswith("D"):
            frac = float(metric[1:]) / 100.0
            if on_target:
                objectives.append(ObjectiveSpec(type="DVHMax", structure_name=st, dose_gy=val, weight=30.0 * w, volume_fraction=frac))
            else:
                objectives.append(ObjectiveSpec(type="DVHMax", structure_name=st, dose_gy=val * lv, weight=OAR_WEIGHT * w, volume_fraction=frac))
                if g.get("dmax_term", True):     # parallel organs around the target (the lungs) opt out: their maximum is the target's
                    objectives.append(ObjectiveSpec(type="DMax", structure_name=st, dose_gy=min(val * 1.25, rx_gy) * lv, weight=OAR_WEIGHT * w / 4))
    return objectives


def _plan_case(ctx: Context, geo, target: str, rx_gy: float, goals: List[dict], beams: dict, beamlet_mm: float, iterations: int,
               jaw_margin_mm: float = 20.0, engine_name: str = "ccc", n_jobs: int = 8, rounds: int = 4):
    """Beam model → CCC Dij → optimization, then goal-driven reweighting rounds (the rule-based auto-planning a
    planner does by hand: a goal that fails gets three times the weight and, for an organ's limit, a 10 % lower dose
    level, and the optimizer restarts from the previous weights). Every round's plan is normalised to the target's first
    coverage goal. Returns (bm, opt, normalised dose_zyx, arrays, history)."""
    from ..models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from ..models.dose import EngineSpec
    from ..models.optimization import OptimizationRunRequest, SolverConfig
    from ..services.beam_model import BeamModelService
    from ..services.geometry_bundle import load_geometry_arrays
    from ..services.optimization import OptimizationService

    arrays = load_geometry_arrays(geo)
    # the field covers every target: the multi-target case has three
    targets = [t for t in _target_names(target, goals) if t in arrays.structure_index]
    union = np.zeros(arrays.shape_zyx, dtype=bool)
    for t in targets:
        union |= arrays.mask_zyx(arrays.structure_index[t])
    lo, hi = _structure_extent_mm(union, arrays.origin_mm, arrays.spacing_mm)
    jaw_x = float(max(hi[0] - lo[0], hi[1] - lo[1]) + 2 * jaw_margin_mm)
    jaw_y = float(hi[2] - lo[2] + 2 * jaw_margin_mm)
    centre = tuple(float(v) for v in (lo + hi) / 2.0)
    n_beams = int(beams.get("count", 7)); spacing = float(beams.get("spacing_deg", 360.0 / n_beams)); start = float(beams.get("start_deg", 0.0))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id="synthetic-120",
        beam_set=BeamSetSpec(isocenter_mm=centre, beams=[BeamSpec(beam_id=f"G{(start + i * spacing) % 360:g}", gantry_deg=(start + i * spacing) % 360.0) for i in range(n_beams)]),
        delivery_params=DeliveryParams(jaw_opening_mm=(jaw_x, jaw_y), beamlet_size_mm=(beamlet_mm, beamlet_mm))))
    cover = next((g for g in goals if g["structure"] == target and g["op"].startswith(">")), None)
    masks = {g["structure"]: arrays.mask_zyx(arrays.structure_index[g["structure"]]) for g in goals if g["structure"] in arrays.structure_index}
    scale: Dict[int, float] = {}
    level: Dict[int, float] = {}
    history: List[dict] = []
    init = None
    opt = dose = None
    for r in range(max(1, int(rounds))):
        opt = OptimizationService().run(OptimizationRunRequest(
            geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=EngineSpec(name=engine_name, params={"n_jobs": n_jobs}),
            objectives=_objectives(arrays, target, rx_gy, goals, scale, level), solver=SolverConfig(method="L-BFGS-B", max_iterations=iterations),
            init_weights_uri=init))
        dose = _read_volume(opt.dose_ref_uri)
        k = 1.0
        if cover is not None:
            dose, k = _normalise_to_goal(dose, dose[masks[cover["structure"]]], cover["metric"], float(cover["gy"]) * NORMALISATION_HEADROOM)
        failed = [i for i, g in enumerate(goals) if g["structure"] in masks and not _goal_met(dose[masks[g["structure"]]], g)]
        history.append({"round": r + 1, "optimization_id": opt.optimization_id, "normalisation": k,
                        "failed": [f"{goals[i]['structure']} {goals[i]['metric']}" for i in failed]})
        if not failed:
            break
        target_names = set(targets)
        for i in failed:
            scale[i] = scale.get(i, 1.0) * 3.0
            # an organ's limit also moves 10 % lower; a target's hot-spot limit only gains weight (lowering it
            # pushes the plan cold, and the normalisation then raises everything, the hot spot included)
            if not goals[i]["op"].startswith(">") and goals[i]["structure"] not in target_names:
                level[i] = level.get(i, 1.0) * 0.9
        init = opt.weights_ref_uri
    return bm, opt, dose, arrays, history


def _normalise_to_goal(dose: np.ndarray, target_doses: np.ndarray, metric: str, goal_gy: float) -> Tuple[np.ndarray, float]:
    """Scale the plan so the target's coverage metric meets its goal exactly (plan normalisation,
    as TG-119 and clinical practice do); returns the scaled dose and the factor."""
    value = _goal_value(target_doses, metric)
    if value <= 0:
        return dose, 1.0
    k = float(goal_gy / value)
    return dose * k, k


def _write_volume(ctx: Context, name: str, dose: np.ndarray, arrays) -> str:
    import SimpleITK as sitk
    img = sitk.GetImageFromArray(np.ascontiguousarray(dose, dtype=np.float32))
    img.SetSpacing([float(v) for v in arrays.spacing_mm]); img.SetOrigin([float(v) for v in arrays.origin_mm])
    path = ctx.workdir / f"{name}.nii.gz"
    sitk.WriteImage(img, str(path))
    return str(path)


def run_tg119_planning(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    import pydicom
    from ..models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from ..services.geometry import GeometryService

    ref = load_reference("tg119_goals")
    root = data_root() / Path(spec["data"]).name / ref["phantom"]["package"].split("/")[-1]
    if not root.is_dir():
        raise Skip(f"TG-119 package not found at {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    _services(ctx)
    cases = spec["cases"][:1] if ctx.fast else spec["cases"]
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    beamlet = float(spec.get("beamlet_mm", 5.0)) * (2.0 if ctx.fast else 1.0)
    iterations = int(spec.get("iterations", 200) / (2 if ctx.fast else 1))
    rounds = int(spec.get("rounds", 4)) if not ctx.fast else min(2, int(spec.get("rounds", 4)))
    published = ref.get("published", {})
    for name in cases:
        case = ref["cases"][name]
        rs_path = root / case["rtstruct"]
        rs = pydicom.dcmread(rs_path, stop_before_pixels=True)
        geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"tg119-{case['rtstruct']}", rtstruct_uid=str(rs.SOPInstanceUID)),
                                                           data_root_override=str(root), grid_spec=GridSpec(spacing_mm=(s, s, s))))
        bm, opt, dose, arrays, history = _plan_case(ctx, geo, case["target"], float(case["prescription_gy"]), case["goals"], case["beams"], beamlet, iterations,
                                                     n_jobs=int(spec.get("n_jobs", 8)), rounds=rounds)
        res.metrics[name] = {"geometry_id": geo.geometry_id, "beamlets": bm.fluence_elements.total_count, "rounds": history,
                             "grid_mm": s, "beamlet_mm": beamlet}
        pub = published.get(name, {})
        for g in case["goals"]:
            st = g["structure"]
            if st not in arrays.structure_index:
                res.notes.append(f"{name}: structure {st} not in the geometry"); continue
            doses = dose[arrays.mask_zyx(arrays.structure_index[st])]
            value = _goal_value(doses, g["metric"])
            op, limit = g["op"], float(g["gy"])
            met = value >= limit - 1e-6 if op.startswith(">") else value <= limit + 1e-6
            key = f"{st} {g['metric']}"
            mean_sd = pub.get(key)
            note = "TG-119 planning goal (instructions, Zenodo 8037934)"
            passed, target_text = met, f"{op} {limit}"
            if mean_sd:
                # TG-119 compares an institution with the multi-institution results: a goal the participants
                # did not meet on average is passed when the plan is no worse than their mean ± 2 SD
                mean, sd = mean_sd
                bound = max(limit, mean + 2 * sd) if not op.startswith(">") else min(limit, mean - 2 * sd)
                passed = met or (value <= bound + 1e-6 if not op.startswith(">") else value >= bound - 1e-6)
                if bound != limit:
                    target_text = f"{op} {limit} (or {op} {bound:.2f}: institutional mean {mean} ± 2 SD)"
                note += f"; institutional mean {mean} (SD {sd})" + ("" if met else ("; goal not met, within the institutional spread" if passed else "; outside the institutional spread"))
                res.metrics[name][key] = {"value": value, "goal": f"{op} {limit}", "mean": mean, "sd": sd, "met": met, "passed": passed}
            res.add(f"{name}: {key} (Gy)", round(value, 2), target_text, passed, note)
        res.metrics[name]["beam_model_id"] = bm.beam_model_id; res.metrics[name]["optimization_id"] = opt.optimization_id
    res.notes.append("fluence-level plans (open-field beamlets, CCC shipped-scatter Dij, L-BFGS-B); TG-119 institutional results are deliverable plans, "
                     "so the comparison with their means is informative; the goals are graded")
    return res


# ---------------------------------------------------------------------------
# lung_e2e — an LCTSC thorax with a synthetic GTV: contour → plan → dose → goals
# ---------------------------------------------------------------------------

def _sphere_polygons(centre: Sequence[float], radius_mm: float, z_positions: Sequence[float], n_pts: int = 48) -> List[np.ndarray]:
    polys = []
    for z in z_positions:
        dz = float(z) - centre[2]
        if abs(dz) >= radius_mm:
            continue
        r = math.sqrt(radius_mm ** 2 - dz ** 2)
        t = np.linspace(0, 2 * math.pi, n_pts, endpoint=False)
        pts = np.stack([centre[0] + r * np.cos(t), centre[1] + r * np.sin(t), np.full(n_pts, float(z))], axis=1)
        polys.append(pts.reshape(-1))
    return polys


def _case_dir_with_gtv(ctx: Context, tag: str, ct_files, rs_files, centre: Sequence[float], radius_mm: float, description: str) -> Path:
    """A case directory beside the CT: the CT slices linked, and one RT Structure Set written by radiarch with the
    original contours and a synthetic GTV sphere. One structure set, because the geometry service reads one: before
    R8 the GTV went into a second file and the organs were lost, so the organ goals were never evaluated."""
    from ..dicom.ct import read_ct_series
    from ..dicom.rtstruct import read_rtstruct
    from ..dicom.writers import CaseContext, Structure, write_rtstruct

    case_dir = ctx.workdir / tag
    case_dir.mkdir(parents=True, exist_ok=True)
    for f in ct_files:
        dst = case_dir / f.name
        if not dst.exists():
            os.symlink(f, dst)
    ct = read_ct_series(ct_files)
    structures = []
    for rs in rs_files:
        for c in read_rtstruct(rs).contours:
            if c.name != "GTV" and c.polygonMesh:
                structures.append(Structure(name=c.name, polygons=[np.asarray(p, float) for p in c.polygonMesh],
                                            color=tuple(c.displayColor) if c.displayColor else None, generation="MANUAL"))
    structures.append(Structure(name="GTV", polygons=_sphere_polygons(centre, radius_mm, ct.sliceLocation)))
    write_rtstruct(CaseContext.from_ct(ct), structures, case_dir / "RS_with_synthetic_gtv.dcm", label="SYN-GTV", description=description)
    return case_dir


def run_lung_e2e(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    from ..models.evaluation import EvaluationRequest, GoalSetSpec
    from ..models.geometry import GeometryBuildRequest, GeometryDeriveRequest, GridSpec, PatientRef, StructureOperation
    from ..services.evaluation import EvaluationService
    from ..services.geometry import GeometryService
    from ..services.geometry_bundle import load_geometry_arrays

    root = data_root() / Path(spec["data"]).name
    if not root.is_dir():
        raise Skip(f"data not found: {root} (set RADIARCH_VALIDATION_DATA to the directory holding it)")
    _services(ctx)
    patients = spec["patients"][:1] if ctx.fast else spec["patients"]
    s = ctx.spacing(spec.get("spacing_mm", 3.0))
    beamlet = float(spec.get("beamlet_mm", 5.0)) * (2.0 if ctx.fast else 1.0)
    iterations = int(spec.get("iterations", 200) / (2 if ctx.fast else 1))
    rx = float(spec.get("prescription_gy", 60.0)); fractions = int(spec.get("fractions", 30))
    for pid in patients:
        pdir = root / pid
        ct_files = sorted(next(pdir.glob("CT_*")).glob("*.dcm"))
        rs_files = list(pdir.glob("RTSTRUCT_*/*.dcm"))
        if not ct_files or not rs_files:
            res.notes.append(f"{pid}: CT or RTSTRUCT missing"); continue
        # 1. the lungs from the original structure set, to place the GTV inside the right lung
        geo0 = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"lung-{pid}-base"), data_root_override=str(pdir),
                                                            grid_spec=GridSpec(spacing_mm=(s, s, s))))
        arr0 = load_geometry_arrays(geo0)
        lung_name = next((n for n in arr0.structure_index if n.lower() in ("lung_r", "lung_right")), None)
        if lung_name is None:
            res.notes.append(f"{pid}: no right lung"); continue
        lung = arr0.mask_zyx(arr0.structure_index[lung_name])
        idx = np.argwhere(lung)
        com = idx.mean(axis=0)                      # (z, y, x) voxel
        centre = (arr0.origin_mm[0] + com[2] * s, arr0.origin_mm[1] + com[1] * s, arr0.origin_mm[2] + com[0] * s)
        radius = float(spec.get("gtv_radius_mm", 20.0))
        # 2. the original contours and a synthetic GTV sphere in one RT Structure Set beside the CT (radiarch's own writer)
        case_dir = _case_dir_with_gtv(ctx, f"lung-{pid}", ct_files, rs_files, centre, radius, "synthetic GTV sphere for the validation harness")
        geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=f"lung-{pid}"), data_root_override=str(case_dir),
                                                           grid_spec=GridSpec(spacing_mm=(s, s, s))))
        geo = GeometryService().derive(geo.geometry_id, GeometryDeriveRequest(operations=[
            StructureOperation(op="expand", name="CTV", source="GTV", margin_mm=5.0),
            StructureOperation(op="expand", name="PTV", source="CTV", margin_mm=5.0),
            StructureOperation(op="union", name="Lungs", sources=["Lung_L", "Lung_R"]),
            StructureOperation(op="subtract", name="Lungs-GTV", source="Lungs", sources=["GTV"]),     # the template's
            StructureOperation(op="subtract", name="Lungs-PTV", source="Lungs", sources=["PTV"])]))   # the optimizer's
        # 3. plan: 7 coplanar fields, RTOG 0617-style objectives
        goals = [{"structure": "SpinalCord", "metric": "Dmax", "op": "<=", "gy": 50.5},
                 {"structure": "Esophagus", "metric": "Dmean", "op": "<=", "gy": 34.0},
                 {"structure": "Heart", "metric": "D33", "op": "<=", "gy": 60.0},
                 # RTOG 0617 limits the lungs minus the GTV (V20 <= 37 %, mean <= 20 Gy); the optimizer gets the lungs
                 # minus the PTV, so its maximum-dose terms do not cool the PTV margin that lies in lung
                 {"structure": "Lungs-PTV", "metric": "D37", "op": "<=", "gy": 20.0, "dmax_term": False},
                 {"structure": "Lungs-PTV", "metric": "Dmean", "op": "<=", "gy": 20.0}]
        beams = {"count": int(spec.get("beams", 7)), "spacing_deg": 360.0 / int(spec.get("beams", 7)), "start_deg": 0.0}
        plan_goals = [{"structure": "PTV", "metric": "D95", "op": ">=", "gy": rx}] + goals
        rounds = int(spec.get("rounds", 4)) if not ctx.fast else min(2, int(spec.get("rounds", 4)))
        bm, opt, dose, arrays, history = _plan_case(ctx, geo, "PTV", rx, plan_goals, beams, beamlet, iterations,
                                                     n_jobs=int(spec.get("n_jobs", 8)), rounds=rounds)
        # 4. the plan comes normalised (PTV D95 at the prescription + 0.2 %); evaluate it with the RTOG 0617 goal template (R5)
        ptv_mask = arrays.mask_zyx(arrays.structure_index["PTV"])
        k = history[-1]["normalisation"]
        dose_uri = _write_volume(ctx, f"lung-{pid}-dose", dose, arrays)
        ev = EvaluationService().run(EvaluationRequest(dose_ref_uri=dose_uri, geometry_id=geo.geometry_id, prescription_gy=rx, target_structure="PTV",
                                                       fractions=fractions, goals=GoalSetSpec(template_id=spec.get("goal_template", "rtog-0617"))))
        n_pass = n_fail = 0
        for g in (ev.goals.results if ev.goals else []):
            passed = g.passed
            if passed is None:
                continue
            n_pass += int(bool(passed)); n_fail += int(not passed)
            res.add(f"{pid}: {g.structure} {g.metric} {g.op} {g.value} Gy", round(float(g.achieved), 2) if g.achieved is not None else None,
                    f"{g.op} {g.value}", bool(passed) if int(g.priority) == 1 else None,
                    f"{spec.get('goal_template', 'rtog-0617')} priority {g.priority}" + ("" if int(g.priority) == 1 else " (informative)"))
        ptv = dose[ptv_mask]
        res.add(f"{pid}: PTV D5 / D95 after normalisation (homogeneity)", round(_dose_at(ptv, 5.0) / _dose_at(ptv, 95.0), 3), "≤ 1.15 (informative)", None,
                f"plan normalised by {k:.3f} so that PTV D95 = {rx * NORMALISATION_HEADROOM:.2f} Gy; {len(history)} reweighting round(s)")
        res.metrics[pid] = {"normalisation_factor": k, "rounds": history, "gtv_centre_mm": [round(float(v), 1) for v in centre], "gtv_radius_mm": radius, "beamlets": bm.fluence_elements.total_count,
                            "goals_pass": n_pass, "goals_fail": n_fail,
                            "geometry_id": geo.geometry_id, "optimization_id": opt.optimization_id, "evaluation_id": ev.evaluation_id,
                            "indices": ev.indices.model_dump() if ev.indices else None}
    res.notes.append("synthetic 2 cm GTV at the right lung's centroid, CTV +5 mm, PTV +5 mm; 7 coplanar open-field beam models, CCC shipped-scatter Dij, "
                     "L-BFGS-B; goals from the RTOG 0617 template; a research pipeline check, not a plan quality statement")
    return res


# ---------------------------------------------------------------------------
# photon_vs_pyradplan — CCC against pyRadPlan's photon pencil beam (offline cross-check)
# ---------------------------------------------------------------------------

PYRADPLAN_DIR = Path(__file__).resolve().parent / "references" / "pyradplan"


def run_photon_vs_pyradplan(spec: dict, ctx: Context) -> CaseResult:
    res = CaseResult(spec["name"], spec["kind"])
    eng = _ccc_engine()
    scatter = "shipped" if ctx.fast else spec.get("scatter", "shipped")
    tol = float(spec.get("tolerance_percent", 3.0))
    graded = bool(spec.get("pass_fail", False))      # pyRadPlan's generic machine is not the reference beam: informative
    missing = []
    for case in spec["cases"]:
        npz, meta = PYRADPLAN_DIR / f"{case}.npz", PYRADPLAN_DIR / f"{case}.json"
        if not npz.is_file():
            missing.append(case); continue
        d = np.load(npz); prov = json.loads(meta.read_text(encoding="utf-8")) if meta.is_file() else {}
        s = ctx.spacing(float(d["spacing_mm"][0]))
        phantom = {"water_10x10": lambda: ph.water_box(150.0, 300.0, s), "lung_slab": lambda: ph.lung_slab(s), "bone_slab": lambda: ph.bone_slab(s)}[case]()
        plan = _open_field_plan(float(prov.get("field_mm", 100.0)), 10.0, 10.0)
        params = {"scatter": scatter, "n_jobs": int(spec.get("n_jobs", 8))}
        if ctx.fast:
            params["calibration_spacing_mm"] = 5.0
        ccc = _cached_ccc_dose(eng, phantom, plan, params, key=f"{case}-{s:g}mm-{scatter}-{float(prov.get('field_mm', 100.0)):g}-10.0")
        other = _resample_to(d["dose"].astype(np.float32), tuple(float(v) for v in d["spacing_mm"]), tuple(float(v) for v in d["origin_mm"]), phantom)
        cz, cx = phantom.centre_index("z"), phantom.centre_index("x"); j10 = phantom.depth_index(100.0)
        y = phantom.axis_mm("y")
        cax_c = ccc[cz, :, cx] / ccc[cz, j10, cx]; cax_p = other[cz, :, cx] / other[cz, j10, cx]
        res.metrics[f"{case}_cax"] = {"depth_mm": y.tolist(), "ccc": cax_c.tolist(), "pyradplan": cax_p.tolist()}
        if case.startswith("water"):
            kc, kp = int(np.argmax(cax_c)), int(np.argmax(cax_p))
            p10c = float(np.interp(100.0, y, cax_c) / cax_c[kc] * 100); p10p = float(np.interp(100.0, y, cax_p) / cax_p[kp] * 100)
            res.add(f"{case}: PDD10 CCC vs pyRadPlan (%)", p10c, f"{p10p:.1f} ± {tol} (pyRadPlan pencil beam)", (abs(p10c - p10p) <= tol) if graded else None,
                    "two pencil-beam-class engines with generic 6 MV data; the Monte Carlo case is the reference, this is the second opinion")
        for depth in spec.get("probe_depths_mm", [50, 150, 200, 250]):
            j = phantom.depth_index(depth)
            ratio = float(cax_c[j] / cax_p[j]) if cax_p[j] > 0 else float("nan")
            res.add(f"{case}: CAX dose at {depth:g} mm, CCC / pyRadPlan", ratio, f"1 ± {tol / 100:.2f}", _within(ratio, 1.0, tol / 100) if graded else None,
                    "normalised at 10 cm depth; MPPG 5.a 2 % in field, 3 % heterogeneity")
        res.notes.append(f"{case}: pyRadPlan {prov.get('pyradplan_version', '?')}, {prov.get('engine', '')}, {prov.get('n_bixels')} bixels of {prov.get('bixel_mm')} mm "
                         f"(its bixels are centred on the axis, so the field is 9 x 9 cm at the isocenter and 10 x 10 cm at the 10 cm normalisation depth; "
                         f"the ~1 % scatter difference is inside the tolerance); CCC scatter '{scatter}'")
    res.notes.append("informative: pyRadPlan's generic photon machine is a different beam from the kernels' spectrum (its water PDD10 is "
                     "about 3.5 points below the Monte Carlo reference's), so the Monte Carlo case, not this one, judges the CCC engine")
    if missing:
        msg = f"no pyRadPlan reference for {missing}: run `python -m radiarch.validation.pyradplan_crosscheck --case <name>` in its environment"
        if len(missing) == len(spec["cases"]):
            raise Skip(msg)
        res.notes.append(msg)
    return res


KINDS_R7 = {
    "photon_vs_pyradplan": run_photon_vs_pyradplan,
    "photon_vs_mc": run_photon_vs_mc,
    "dij_consistency": run_dij_consistency,
    "proton_bragg_peak": run_proton_bragg_peak,
    "tg119_planning": run_tg119_planning,
    "lung_e2e": run_lung_e2e,
}

__all__ = ["KINDS_R7"]
