"""VMAT (roadmap R8): arcs from the fluence of sector beams.

The method is arc sequencing of sector fluence maps (Craft, McQuaid, Wala,
Chen, Salari and Bortfeld, Med Phys 39:686, 2012) with the unidirectional
sliding-window decomposition R4 already uses (Bortfeld, Boyer et al. 1994):

1. **Fluence.** An ordinary fluence optimization of static beams at the
   centres of each arc's sectors (:func:`radiarch.models.vmat.sector_beams`).
2. **Sweeps.** Each sector's fluence map is decomposed into at most as many
   apertures as the sector has control-point intervals; the leaves sweep the
   field once per sector, left to right in even sectors and right to left in
   odd ones, so one sweep ends where the next begins. The apertures are the
   control points' leaf positions; the jaws stay fixed for the arc around
   everything a control point opens.
3. **Limits.** An interval takes the longest of its gantry time (its angle at
   the machine's top gantry speed), its leaf time (the largest leaf move at
   the top leaf speed) and its beam-on time (its meterset at the top dose
   rate). The machine cannot lower the dose rate below its minimum, so an
   interval's meterset is at least that minimum times its gantry-and-leaf time.
4. **Dose.** Each interval's dose per MU is recomputed by the dose engine at
   the interval's mid-angle with the mean of its two control points' leaves
   (:meth:`radiarch.services.dose_engines.pb.PencilBeamEngine.segment_dose_matrix`).
5. **Metersets.** Re-optimized against the plan's objectives, every interval
   at or above its minimum.
6. **Result.** The arc plan's dose with the full kernel, and the
   deliverability of each arc.

Not done: progressive sampling or direct optimization of the leaf positions
(the leaf trajectories are the sweeps'); tongue-and-groove, leaf
transmission. Interval doses are static mid-angle approximations, accurate for
2-4 degree intervals.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from loguru import logger

from ..config import get_settings
from ..models.machine import MLCSpec, PhotonMachineSpec
from ..models.photon_plan import ArcControlPoint, MLCRow, PhotonArc, PhotonBeam, PhotonPlan, arc_step_deg
from ..models.vmat import ArcDeliverabilityReport, ArcRequest, ArcResult, ArcSpec
from .sequencing import Aperture, FluenceMap, apply_machine_limits, fluence_maps, sequence_row

CostTerms = Callable[[np.ndarray], Tuple[float, np.ndarray]]


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------

def _levels_for(values: np.ndarray, n: int) -> int:
    """The most fluence levels (at most ``n``) whose decomposition needs no more than ``n`` apertures in any row
    (a row needs as many as its profile rises in total)."""
    top = float(values.max())
    for levels in range(n, 0, -1):
        q = np.rint(values / (top / levels)).astype(int)
        q = np.pad(q, ((0, 0), (1, 1)))
        if int(np.maximum(np.diff(q, axis=1), 0).sum(axis=1).max()) <= n:
            return levels
    return 1


def sweep(fmap: FluenceMap, n: int, reverse: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """``n`` leaf states (``(n, rows, 2)``: left and right tip per leaf pair) sweeping the map left to right
    (``reverse``: right to left), and the meterset each delivers (``(n,)``, in the map's weight units).

    The map is quantized to as many levels as fit in ``n`` apertures; segment ``i`` of a row opens from its
    ``i``-th rising to its ``i``-th falling edge (in sweep order), a row that has finished stays closed where it
    ended, a row without fluence stays closed at the field's centre. When the decomposition has fewer apertures
    than ``n``, each is held over consecutive control points and its meterset shared among them."""
    values = np.asarray(fmap.values, float)
    x = np.asarray(fmap.x_edges_mm, float)
    rows = values.shape[0]
    centre = 0.5 * (x[0] + x[-1])
    top = float(values.max()) if values.size else 0.0
    if top <= 0:
        return np.full((n, rows, 2), centre), np.zeros(n)
    levels = _levels_for(values, n)
    delta = top / levels
    q = np.rint(values / delta).astype(int)
    per_row: List[List[Tuple[float, float]]] = []
    for r in range(rows):
        prof, xe = (q[r][::-1], x[::-1]) if reverse else (q[r], x)
        per_row.append([(min(a, b), max(a, b)) for a, b in sequence_row(prof, xe)])
    n_seg = max(1, max(len(s) for s in per_row))
    states = np.zeros((n_seg, rows, 2))
    for r, segs in enumerate(per_row):
        for i in range(n_seg):
            if not segs:
                states[i, r] = (centre, centre)
            elif i < len(segs):
                states[i, r] = segs[i]
            else:
                end = segs[-1][0] if reverse else segs[-1][1]
                states[i, r] = (end, end)
    idx = (np.arange(n) * n_seg) // n
    reps = np.bincount(idx, minlength=n_seg)
    return states[idx], delta / reps[idx]


# ---------------------------------------------------------------------------
# Arcs from sector maps
# ---------------------------------------------------------------------------

def _rows(state: np.ndarray, pairs: Sequence[int], bounds: np.ndarray) -> List[MLCRow]:
    return [MLCRow(y_min_mm=float(bounds[p]), y_max_mm=float(bounds[p + 1]), x_left_mm=float(state[r, 0]),
                   x_right_mm=float(max(state[r, 1], state[r, 0]))) for r, p in enumerate(pairs)]


def build_arc(spec: ArcSpec, maps: List[FluenceMap], mlc: MLCSpec, machine: PhotonMachineSpec, *,
              isocenter_mm: Tuple[float, float, float], sad_mm: float, energy_mv: Optional[float],
              beamlet_spacing_mm: Tuple[float, float]) -> Tuple[PhotonBeam, np.ndarray, List[str]]:
    """The arc for ``spec`` from its sectors' maps (in sector order): the beam (control points with the sweeps'
    leaves and the initial metersets), the initial meterset per interval, and the machine-limit issues."""
    if len(maps) != spec.sectors:
        raise ValueError(f"arc {spec.arc_id}: {len(maps)} sector maps for {spec.sectors} sectors")
    pairs = list(maps[0].pair_indices)
    if any(list(m.pair_indices) != pairs or len(m.x_edges_mm) != len(maps[0].x_edges_mm) for m in maps):
        raise ValueError(f"arc {spec.arc_id}: the sector beams must share one field (the same leaf pairs and columns)")
    k = spec.intervals_per_sector
    states: List[np.ndarray] = []
    mus: List[float] = []
    issues: List[str] = []
    for s, fmap in enumerate(maps):
        st, mu = sweep(fmap, k, reverse=bool(s % 2))
        for i in range(k):
            ap = apply_machine_limits(Aperture(fmap.beam_index, st[i, :, 0].copy(), st[i, :, 1].copy(), float(mu[i])), mlc, pairs)
            issues += [f"sector {s + 1}: {msg}" for msg in ap.issues]
            states.append(np.stack([ap.left_mm, ap.right_mm], axis=1))
        mus += [float(m) for m in mu]
    states.append(states[-1].copy())                      # the arc's last control point closes the last interval
    bounds = np.asarray(mlc.leaf_boundaries_mm, float)
    opened = [(st, st[:, 1] > st[:, 0]) for st in states]
    xs = [v for st, o in opened if o.any() for v in (st[o, 0].min(), st[o, 1].max())]
    ys = [v for st, o in opened if o.any() for r in np.flatnonzero(o) for v in (bounds[pairs[r]], bounds[pairs[r] + 1])]
    if not xs:
        raise ValueError(f"arc {spec.arc_id}: no control point opens the leaves; the sector fluence is empty")
    jx, jy = machine.jaws.x_range_mm, machine.jaws.y_range_mm
    x_jaw = (max(min(xs), jx[0]), min(max(xs), jx[1]))
    y_jaw = (max(min(ys), jy[0]), min(max(ys), jy[1]))
    angles = spec.control_point_angles_deg()
    cum = np.concatenate([[0.0], np.cumsum(mus)])
    cps = [ArcControlPoint(gantry_deg=angles[j], cumulative_mu=float(cum[j]), x_jaw_mm=x_jaw, y_jaw_mm=y_jaw,
                           mlc_rows=_rows(states[j], pairs, bounds)) for j in range(len(states))]
    arc = PhotonArc(direction=spec.direction, collimator_deg=spec.collimator_deg, control_points=cps)
    beam = PhotonBeam.from_arc(spec.arc_id, arc, couch_deg=spec.couch_deg, isocenter_mm=isocenter_mm, sad_mm=sad_mm,
                               energy_mv=energy_mv, beamlet_spacing_mm=beamlet_spacing_mm)
    return beam, np.asarray(mus), issues


def with_metersets(beam: PhotonBeam, mu: np.ndarray) -> PhotonBeam:
    """The arc beam with interval metersets ``mu``."""
    arc = beam.arc
    cum = np.concatenate([[0.0], np.cumsum(np.asarray(mu, float))])
    cps = [cp.model_copy(update={"cumulative_mu": float(c)}) for cp, c in zip(arc.control_points, cum)]
    new_arc = PhotonArc(direction=arc.direction, collimator_deg=arc.collimator_deg, control_points=cps)
    return PhotonBeam.from_arc(beam.beam_id, new_arc, couch_deg=beam.couch_deg, isocenter_mm=beam.isocenter_mm,
                               sad_mm=beam.sad_mm, energy_mv=beam.energy_mv, beamlet_spacing_mm=beam.segments[0].beamlet_spacing_mm)


# ---------------------------------------------------------------------------
# Machine limits in time
# ---------------------------------------------------------------------------

@dataclass
class IntervalTiming:
    angle_deg: np.ndarray        # gantry turn per interval
    leaf_travel_mm: np.ndarray   # largest leaf move per interval
    min_time_s: np.ndarray       # gantry and leaf limits
    min_mu: np.ndarray           # the minimum dose rate over min_time_s


def interval_timing(beam: PhotonBeam, machine: PhotonMachineSpec, energy_mv: Optional[float] = None, fractions: int = 1) -> IntervalTiming:
    """Per interval, the gantry turn, the largest leaf move, the gantry-and-leaf time and the minimum meterset
    (for the whole course of ``fractions``: the machine's floor applies to each fraction's meterset)."""
    arc = beam.arc
    if arc is None:
        raise ValueError(f"beam {beam.beam_id} is not an arc")
    rate_min, _ = machine.energy(energy_mv).dose_rate_mu_min
    tips = [np.asarray([[r.x_left_mm, r.x_right_mm] for r in cp.mlc_rows]).reshape(-1, 2) for cp in arc.control_points]
    travel = np.asarray([float(np.max(np.abs(b - a))) if a.size else 0.0 for a, b in zip(tips, tips[1:])])
    cps = arc.control_points
    turn = np.asarray([abs(arc_step_deg(a.gantry_deg, b.gantry_deg, arc.direction)) for a, b in zip(cps, cps[1:])])
    t = np.maximum(turn / machine.max_gantry_speed_deg_s, travel / machine.mlc.max_leaf_speed_mm_s)
    return IntervalTiming(turn, travel, t, rate_min / 60.0 * t * int(fractions))


def arc_report(beam: PhotonBeam, machine: PhotonMachineSpec, energy_mv: Optional[float] = None,
               extra_issues: Sequence[str] = (), fractions: int = 1) -> ArcDeliverabilityReport:
    """The arc's delivery per fraction (the beam's metersets are for ``fractions``)."""
    timing = interval_timing(beam, machine, energy_mv, fractions=1)
    _, rate_max = machine.energy(energy_mv).dose_rate_mu_min
    mu = np.asarray([s.mu for s in beam.segments], float) / int(fractions)
    t = np.maximum(timing.min_time_s, mu * 60.0 / rate_max)
    issues = list(extra_issues)
    below = np.flatnonzero(mu < timing.min_mu * (1 - 1e-6) - 1e-9)
    if below.size:
        issues.append(f"{below.size} intervals deliver less than the minimum dose rate allows (first: interval {below[0]})")
    speed = timing.angle_deg / np.maximum(t, 1e-9)
    arc = beam.arc
    return ArcDeliverabilityReport(
        arc_id=beam.beam_id, direction=arc.direction, start_deg=arc.start_deg, stop_deg=arc.stop_deg,
        n_control_points=len(arc.control_points), control_point_spacing_deg=float(np.mean(timing.angle_deg)),
        fractions=int(fractions), total_mu=float(mu.sum()), delivery_time_s=float(t.sum()),
        gantry_speed_deg_s=(float(speed.min()), float(speed.max())),
        mean_dose_rate_mu_min=float(mu.sum() / max(t.sum(), 1e-9) * 60.0),
        max_leaf_travel_mm=float(timing.leaf_travel_mm.max()) if timing.leaf_travel_mm.size else 0.0,
        intervals_at_dose_rate_floor=int(np.sum(np.isclose(mu, timing.min_mu, rtol=1e-3, atol=1e-6))),
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Metersets
# ---------------------------------------------------------------------------

def optimize_interval_mu(S: sp.csr_matrix, grid_shape: Tuple[int, int, int], cost_terms: CostTerms, mu0: np.ndarray,
                         mu_min: np.ndarray, method: str = "L-BFGS-B", max_iterations: int = 200, tol: float = 1e-9):
    """Minimize the objectives over interval metersets ``mu >= mu_min`` with ``dose = S @ mu`` (the solvers keep
    variables non-negative, so they run on ``mu - mu_min``)."""
    from .optimization_solvers import get_solver

    S = S.tocsr()
    ST = S.T.tocsr()
    base = np.asarray(S @ mu_min, dtype=np.float64)

    def cost_and_grad(z: np.ndarray) -> Tuple[float, np.ndarray]:
        dose = (base + np.asarray(S @ np.asarray(z, dtype=np.float64))).reshape(grid_shape)
        loss, g = cost_terms(dose)
        return float(loss), np.asarray(ST @ g.ravel(order="C"), dtype=np.float64)

    z0 = np.maximum(np.asarray(mu0, float) - mu_min, 0.0)
    z, conv = get_solver(method).run(cost_and_grad, z0, max_iterations, tol)
    return mu_min + np.clip(np.asarray(z, float), 0.0, None), conv


# ---------------------------------------------------------------------------
# The whole step
# ---------------------------------------------------------------------------

@dataclass
class VMATPlanResult:
    plan: PhotonPlan
    interval_mu: np.ndarray
    segment_dose: sp.csr_matrix
    dose: np.ndarray
    convergence: object
    reports: List[ArcDeliverabilityReport]
    initial_mu: np.ndarray = field(default_factory=lambda: np.zeros(0))


def plan_arcs(sector_plan: PhotonPlan, weights: np.ndarray, arcs: List[ArcSpec], density_zyx: np.ndarray,
              spacing_mm: Sequence[float], origin_mm: Sequence[float], cost_terms: CostTerms, machine: PhotonMachineSpec,
              engine, engine_params: Optional[dict] = None, *, energy_mv: Optional[float] = None, method: str = "L-BFGS-B",
              max_iterations: int = 200, name: Optional[str] = None, fractions: int = 1) -> VMATPlanResult:
    """Sector fluence (``weights`` on ``sector_plan``, whose beams are the arcs' sector beams in order) → arcs."""
    expected = [(bid, g, a) for a in arcs for bid, g in zip(a.sector_beam_ids(), a.sector_centres_deg())]
    if len(sector_plan.beams) != len(expected):
        raise ValueError(f"the optimization has {len(sector_plan.beams)} beams; the arcs have {len(expected)} sectors")
    for beam, (bid, g, a) in zip(sector_plan.beams, expected):
        if abs(((beam.gantry_deg - g + 180.0) % 360.0) - 180.0) > 0.05:
            raise ValueError(f"beam {beam.beam_id} at {beam.gantry_deg:g} deg is not sector {bid} at {g:g} deg")
        col = beam.segments[0].collimator_deg
        if abs(((col - a.collimator_deg + 180.0) % 360.0) - 180.0) > 0.05 or abs(beam.couch_deg - a.couch_deg) > 0.05:
            raise ValueError(f"beam {beam.beam_id}: collimator {col:g} and couch {beam.couch_deg:g} deg differ from arc {a.arc_id}'s "
                             f"({a.collimator_deg:g}, {a.couch_deg:g}); the sector fluence must be in the arc's beam's-eye view")
    if not hasattr(engine, "segment_dose_matrix"):
        raise ValueError(f"engine {getattr(engine, 'name', engine)!r} cannot recompute control-point doses (use 'pb')")
    mlc = machine.mlc
    maps = fluence_maps(sector_plan, weights, mlc)
    if len(maps) != len(sector_plan.beams):
        raise ValueError("every sector beam needs beamlets")
    beams: List[PhotonBeam] = []
    mu0: List[np.ndarray] = []
    issues: Dict[str, List[str]] = {}
    first = 0
    for spec in arcs:
        smaps = maps[first:first + spec.sectors]
        first += spec.sectors
        ref = sector_plan.beams[smaps[0].beam_index]
        beam, mu, iss = build_arc(spec, smaps, mlc, machine, isocenter_mm=ref.isocenter_mm, sad_mm=ref.sad_mm,
                                  energy_mv=ref.energy_mv or machine.energy(energy_mv).nominal_mv,
                                  beamlet_spacing_mm=ref.segments[0].beamlet_spacing_mm)
        beams.append(beam); mu0.append(mu); issues[spec.arc_id] = iss
    plan0 = PhotonPlan(name=name or f"{sector_plan.name}-vmat", beams=beams)
    mu_init = np.concatenate(mu0)
    mu_min = np.concatenate([interval_timing(b, machine, energy_mv, fractions).min_mu for b in beams])
    logger.info("VMAT: {} arcs, {} control-point intervals; recomputing their doses", len(beams), mu_init.size)
    S = engine.segment_dose_matrix(density_zyx, spacing_mm, origin_mm, plan0, params=engine_params)
    grid_shape = tuple(np.asarray(density_zyx).shape)
    mu, conv = optimize_interval_mu(S, grid_shape, cost_terms, np.maximum(mu_init, mu_min), mu_min, method, max_iterations)
    out_beams, offset = [], 0
    for b in beams:
        n = len(b.segments)
        out_beams.append(with_metersets(b, mu[offset:offset + n]))
        offset += n
    plan = PhotonPlan(name=plan0.name, beams=out_beams)
    p = dict(engine_params or {}); p["fluence"] = "apertures"
    dose = engine.compute_plan_dose(density_zyx, spacing_mm, origin_mm, plan, params=p)
    reports = [arc_report(b, machine, energy_mv, issues.get(b.beam_id, ()), fractions) for b in out_beams]
    return VMATPlanResult(plan, mu, S, dose, conv, reports, mu_init)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class VMATStore:
    """``{artifact_dir}/vmat/{vmat_id}/meta.json`` with a cache index, like the other stores."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _index(self) -> Path:
        return self.base_dir / "_index.json"

    def _load_index(self) -> Dict[str, str]:
        try:
            return json.loads(self._index.read_text()) if self._index.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def lookup_by_cache_key(self, key: str) -> Optional[ArcResult]:
        vid = self._load_index().get(key)
        return self.get_by_id(vid) if vid else None

    def get_by_id(self, vmat_id: str) -> Optional[ArcResult]:
        meta = self.base_dir / vmat_id / "meta.json"
        if not meta.is_file():
            return None
        try:
            return ArcResult.model_validate_json(meta.read_text())
        except Exception:
            return None

    def save(self, result: ArcResult, interval_mu: np.ndarray) -> None:
        root = self.base_dir / result.vmat_id
        root.mkdir(parents=True, exist_ok=True)
        np.save(root / "interval_mu.npy", np.asarray(interval_mu, dtype=np.float64))
        tmp = root / "meta.json.tmp"
        tmp.write_text(result.model_dump_json(indent=2))
        os.replace(tmp, root / "meta.json")
        index = self._load_index()
        index[result.cache_key] = result.vmat_id
        tmp_i = self._index.with_suffix(".json.tmp")
        tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True))
        os.replace(tmp_i, self._index)


class VMATService:
    """An optimization of sector beams → an arc plan (beam model) with its dose (dose result)."""

    def __init__(self, base_dir: Optional[Path] = None, dose_service=None, optimization_service=None, beam_model_service=None) -> None:
        from .beam_model import BeamModelService
        from .dose import DoseService
        from .optimization import OptimizationService
        settings = get_settings()
        self.store = VMATStore(Path(base_dir) if base_dir else Path(settings.artifact_dir) / "vmat")
        self.dose_service = dose_service or DoseService()
        self.optimization_service = optimization_service or OptimizationService(dose_service=self.dose_service)
        self.beam_model_service = beam_model_service or BeamModelService()

    def arcs(self, optimization_id: str, request: ArcRequest) -> ArcResult:
        from ..models.beam_model import BeamModelResult, FluenceElementSet, Modality, PerBeamElements
        from ..models.dose import DoseResult, dose_units_for
        from .beam_persistence import BeamModelPaths
        from .dose import _summary_stats
        from .dose_engines.registry import get_engine
        from .dose_persistence import DOSE_FILENAME
        from .machine_model import PhotonMachineModel

        cache_key = request.compute_cache_key(optimization_id)
        cached = self.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            return cached
        opt = self.optimization_service.store.get_by_id(optimization_id)
        if opt is None:
            raise ValueError(f"optimization {optimization_id!r} not found")
        weights = self.optimization_service.store.load_weights(optimization_id)
        geometry = self.dose_service._load_geometry(opt.geometry_id)
        beam_model = self.dose_service._load_beam_model(opt.beam_model_id)
        if beam_model.result.modality is not Modality.photon_imrt:
            raise ValueError("arcs apply to photon beam models")
        plan = beam_model.plan
        if not isinstance(plan, PhotonPlan):
            raise ValueError("the beam model holds no PhotonPlan")
        machine_id = request.machine_model_id or beam_model.result.machine_model_id or "default"
        machine = PhotonMachineModel.from_id(machine_id).spec
        engine = get_engine(request.dose_engine.name)
        origin = getattr(geometry, "origin_mm", None) or geometry.result.grid_spec.origin_mm
        grid_shape = tuple(geometry.density.shape)
        obj_terms = self.optimization_service._build_objective_terms(request.objectives, geometry, grid_shape)
        con_terms = self.optimization_service._build_constraint_terms(request.constraints, geometry, grid_shape)

        def cost_terms(dose: np.ndarray) -> Tuple[float, np.ndarray]:
            total = 0.0
            grad = np.zeros(grid_shape, dtype=np.float64)
            for term, mask in obj_terms + con_terms:
                loss, g = term(dose, mask)
                total += loss
                grad += g
            return total, grad

        res = plan_arcs(plan, weights, request.arcs, geometry.density, geometry.spacing_mm, origin, cost_terms, machine, engine,
                        request.dose_engine.params, energy_mv=request.energy_mv, method=request.solver_method,
                        max_iterations=request.max_iterations, name=f"{plan.name}-vmat-{machine.machine_id}", fractions=request.fractions)
        vmat_id = str(uuid.uuid4())
        bm_id = str(uuid.uuid4())
        bm_paths = BeamModelPaths.for_id(self.beam_model_service.store.base_dir, bm_id)
        per_beam = [PerBeamElements(beam_id=b.beam_id, element_count=b.n_beamlets, active_beamlets=b.n_beamlets) for b in res.plan.beams]
        bm_result = BeamModelResult(
            beam_model_id=bm_id, geometry_id=opt.geometry_id, modality=Modality.photon_imrt,
            fluence_elements=FluenceElementSet(total_count=res.plan.n_beamlets, per_beam=per_beam),
            beam_model_ref_uri=str(bm_paths.plan), machine_model_id=machine.machine_id, cache_key=f"vmat:{vmat_id}",
        )
        self.beam_model_service.store.save(beam_model_id=bm_id, cache_key=bm_result.cache_key, plan=res.plan, result=bm_result)
        dose_id = str(uuid.uuid4())
        dose_root = self.dose_service.dose_store.base_dir / dose_id
        dose_result = DoseResult(
            dose_id=dose_id, plan_id=request.plan_id, geometry_id=opt.geometry_id, beam_model_id=bm_id,
            modality=Modality.photon_imrt, engine_name=f"{engine.name}+arcs", engine_version=engine.version,
            dose_grid_uri=str(dose_root / DOSE_FILENAME), statistics=_summary_stats(res.dose),
            rbe_factor=opt.rbe_factor, dose_units=dose_units_for(opt.rbe_factor), cache_key=f"vmat:{vmat_id}",
        )
        self.dose_service.dose_store.save(dose_id=dose_id, cache_key=dose_result.cache_key, nominal_dose=res.dose,
                                          spacing_mm=geometry.spacing_mm, scenario_doses=None, result=dose_result)
        result = ArcResult(
            vmat_id=vmat_id, cache_key=cache_key, optimization_id=optimization_id, geometry_id=opt.geometry_id,
            source_beam_model_id=opt.beam_model_id, beam_model_id=bm_id, dose_id=dose_id, machine_model_id=machine.machine_id,
            engine_name=engine.name, engine_version=engine.version,
            n_control_points=sum(len(b.arc.control_points) for b in res.plan.beams), total_mu=float(res.interval_mu.sum()),
            fractions=request.fractions,
            arcs=res.reports, convergence=res.convergence, deliverable=not any(r.issues for r in res.reports),
            dose_units=dose_units_for(opt.rbe_factor), plan_id=request.plan_id,
        )
        self.store.save(result, res.interval_mu)
        logger.info("VMAT for optimization {}: {} arcs, {} control points, {:.1f} MU, deliverable={}",
                    optimization_id, len(res.plan.beams), result.n_control_points, result.total_mu, result.deliverable)
        return result


__all__ = ["sweep", "build_arc", "with_metersets", "IntervalTiming", "interval_timing", "arc_report", "optimize_interval_mu",
           "VMATPlanResult", "plan_arcs", "VMATStore", "VMATService"]
