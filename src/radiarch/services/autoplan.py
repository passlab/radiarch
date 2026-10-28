"""Goal-driven auto-planning (roadmap R10): the loop a planner runs by hand, as a service.

From a list of clinical goals the loop builds an objective set (a uniform term per target between its coverage and
hot-spot goals, DVH terms for coverage, maximum and DVH-maximum terms for organs), optimizes, normalises the plan to
the main target's coverage goal, and grades every goal. A goal that fails gets three times its weight and, for an
organ's limit, a 10 % lower dose level; the optimizer restarts from the previous weights. Static fields stop at the
fluence (optionally sequenced into apertures); VMAT turns the sector fluence into arcs, whose metersets get the same
rounds (an organ level 5 % lower per round).

These functions were the validation harness's planning (R7, R8); they moved here unchanged, and the harness calls
them, so its recorded plans are this service's. :class:`AutoplanService` adds what the harness did not keep: the
plan normalised in its metersets (not only in its dose array), stored as a deliverable beam model with its dose.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from loguru import logger

OAR_WEIGHT = 200.0                 # an OAR goal term against the target's uniform term at weight 100
NORMALISATION_HEADROOM = 1.002     # plans are normalised 0.2 % above the coverage goal, so percentile rounding cannot fail it
AUTOPLAN_VERSION = "1"
SCALED_PREFIX = "scaled:"          # a normalised plan's beam model: scaled:{source beam model}:{factor}:{key} (lineage reads it)


def read_volume(uri: str) -> np.ndarray:
    import SimpleITK as sitk
    path = uri[len("file://"):] if uri.startswith("file://") else uri
    return sitk.GetArrayFromImage(sitk.ReadImage(path)).astype(np.float32)


def dose_at(doses: np.ndarray, pct: float) -> float:
    from .dvh import dose_at_volume
    return float(dose_at_volume(doses, pct))


def structure_extent_mm(mask_zyx: np.ndarray, origin: Sequence[float], spacing: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    idx = np.argwhere(mask_zyx)
    lo = origin[::-1] + idx.min(axis=0) * np.asarray(spacing[::-1]); hi = origin[::-1] + idx.max(axis=0) * np.asarray(spacing[::-1])
    return lo[::-1], hi[::-1]       # (x, y, z)


def goal_value(doses: np.ndarray, metric: str) -> float:
    m = metric.strip()
    if m.lower() == "dmax":
        return float(doses.max())
    if m.lower() == "dmean":
        return float(doses.mean())
    if m.upper().startswith("D"):
        return dose_at(doses, float(m[1:]))
    raise ValueError(f"unsupported goal metric {metric}")


def goal_met(doses: np.ndarray, goal: dict) -> bool:
    value = goal_value(doses, goal["metric"])
    return value >= float(goal["gy"]) - 1e-6 if goal["op"].startswith(">") else value <= float(goal["gy"]) + 1e-6


def target_names(target: str, goals: List[dict]) -> List[str]:
    """The case's targets: the named one and every structure with a coverage (>=) goal."""
    return list(dict.fromkeys([target] + [g["structure"] for g in goals if g["op"].startswith(">")]))


def objectives_for(arrays, target: str, rx_gy: float, goals: List[dict], scale: Dict[int, float], level: Dict[int, float]):
    """The objective set for a goal list. Every target (a structure with a coverage goal) gets a uniform term
    between its coverage goal and its hot-spot limit (the prescription for the main target without a limit),
    a DVH-minimum term for coverage and a DVH-maximum term for its hot spot; organs get a DVH-maximum and a
    maximum-dose term. ``scale`` multiplies a goal's weight and ``level`` an organ limit's dose (the rounds)."""
    from ..models.optimization import ObjectiveSpec

    targets = set(target_names(target, goals))
    objectives = []
    for t in target_names(target, goals):
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


def normalise_to_goal(dose: np.ndarray, target_doses: np.ndarray, metric: str, goal_gy: float) -> Tuple[np.ndarray, float]:
    """Scale the plan so the target's coverage metric meets its goal exactly (plan normalisation,
    as TG-119 and clinical practice do); returns the scaled dose and the factor."""
    value = goal_value(target_doses, metric)
    if value <= 0:
        return dose, 1.0
    k = float(goal_gy / value)
    return dose * k, k


# ---------------------------------------------------------------------------
# The two loops (moved from the validation harness unchanged)
# ---------------------------------------------------------------------------

def plan_static(geo, target: str, rx_gy: float, goals: List[dict], beams: dict, beamlet_mm: float, iterations: int,
                jaw_margin_mm: float = 20.0, engine_name: str = "ccc", n_jobs: int = 8, rounds: int = 4, machine: str = "synthetic-120",
                extra: Sequence = (), engine_params: Optional[dict] = None, on_round: Optional[Callable[[int, int], None]] = None):
    """Beam model → Dij → optimization, then goal-driven reweighting rounds (the rule-based auto-planning a
    planner does by hand: a goal that fails gets three times the weight and, for an organ's limit, a 10 % lower dose
    level, and the optimizer restarts from the previous weights). Every round's plan is normalised to the target's first
    coverage goal. Returns (bm, opt, normalised dose_zyx, arrays, history)."""
    from ..models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from ..models.dose import EngineSpec
    from ..models.optimization import OptimizationRunRequest, SolverConfig
    from .beam_model import BeamModelService
    from .geometry_bundle import load_geometry_arrays
    from .optimization import OptimizationService

    arrays = load_geometry_arrays(geo)
    # the field covers every target: the multi-target case has three
    targets = [t for t in target_names(target, goals) if t in arrays.structure_index]
    union = np.zeros(arrays.shape_zyx, dtype=bool)
    for t in targets:
        union |= arrays.mask_zyx(arrays.structure_index[t])
    lo, hi = structure_extent_mm(union, arrays.origin_mm, arrays.spacing_mm)
    jaw_x = float(max(hi[0] - lo[0], hi[1] - lo[1]) + 2 * jaw_margin_mm)
    jaw_y = float(hi[2] - lo[2] + 2 * jaw_margin_mm)
    centre = tuple(float(v) for v in (lo + hi) / 2.0)
    n_beams = int(beams.get("count", 7)); spacing = float(beams.get("spacing_deg", 360.0 / n_beams)); start = float(beams.get("start_deg", 0.0))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id=machine,
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
        if on_round is not None:
            on_round(r + 1, max(1, int(rounds)))
        opt = OptimizationService().run(OptimizationRunRequest(
            geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id,
            dose_engine=EngineSpec(name=engine_name, params={"n_jobs": n_jobs} if engine_params is None else dict(engine_params)),
            objectives=objectives_for(arrays, target, rx_gy, goals, scale, level) + list(extra),
            solver=SolverConfig(method="L-BFGS-B", max_iterations=iterations),
            init_weights_uri=init))
        dose = read_volume(opt.dose_ref_uri)
        k = 1.0
        if cover is not None:
            dose, k = normalise_to_goal(dose, dose[masks[cover["structure"]]], cover["metric"], float(cover["gy"]) * NORMALISATION_HEADROOM)
        failed = [i for i, g in enumerate(goals) if g["structure"] in masks and not goal_met(dose[masks[g["structure"]]], g)]
        history.append({"round": r + 1, "optimization_id": opt.optimization_id, "normalisation": k,
                        "failed": [f"{goals[i]['structure']} {goals[i]['metric']}" for i in failed]})
        if not failed:
            break
        target_set = set(targets)
        for i in failed:
            scale[i] = scale.get(i, 1.0) * 3.0
            # an organ's limit also moves 10 % lower; a target's hot-spot limit only gains weight (lowering it
            # pushes the plan cold, and the normalisation then raises everything, the hot spot included)
            if not goals[i]["op"].startswith(">") and goals[i]["structure"] not in target_set:
                level[i] = level.get(i, 1.0) * 0.9
        init = opt.weights_ref_uri
    return bm, opt, dose, arrays, history


def plan_vmat(geo, arrays, target: str, rx: float, goals: List[dict], extra: list, arcs, beamlet: float, iterations: int, rounds: int,
              fractions: int, spec: dict, on_round: Optional[Callable[[int, int], None]] = None) -> dict:
    """Sector beams around every target (the field covers them from every angle of the arcs), fluence optimization
    with the pb Dij and goal-driven reweighting rounds, then arcs (VMAT service); the arc dose normalised so the
    main target's D95 meets its prescription. Returns bm, opt, vm, dose, k, history, objectives."""
    from ..models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from ..models.dose import EngineSpec
    from ..models.optimization import OptimizationRunRequest, SolverConfig
    from ..models.vmat import ArcRequest, sector_beams
    from .beam_model import BeamModelService
    from .dose import DoseService
    from .optimization import OptimizationService
    from .vmat import VMATService

    target_mask = arrays.mask_zyx(arrays.structure_index[target])
    union = np.zeros(arrays.shape_zyx, bool)
    for t in {target} | {g["structure"] for g in goals if g["op"].startswith(">")}:
        union |= arrays.mask_zyx(arrays.structure_index[t])
    lo, hi = structure_extent_mm(union, arrays.origin_mm, arrays.spacing_mm)
    iso = tuple(float(v) for v in (lo + hi) / 2.0)
    margin = float(spec.get("jaw_margin_mm", 10.0))
    jaw_x = float(np.hypot(hi[0] - lo[0], hi[1] - lo[1]) + 2 * margin)
    jaw_y = float(hi[2] - lo[2] + 2 * margin)
    machine = spec.get("machine", "synthetic-120")
    engine = EngineSpec(name="pb", params=dict(spec.get("pb_params", {})))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id=machine,
        beam_set=BeamSetSpec(isocenter_mm=iso, beams=[BeamSpec(beam_id=b, gantry_deg=g, couch_deg=c, collimator_deg=col)
                                                      for b, g, c, col in sector_beams(arcs)]),
        delivery_params=DeliveryParams(jaw_opening_mm=(jaw_x, jaw_y), beamlet_size_mm=(beamlet, beamlet))))
    masks = {g["structure"]: arrays.mask_zyx(arrays.structure_index[g["structure"]]) for g in goals if g["structure"] in arrays.structure_index}
    targets = {g["structure"] for g in goals if g["op"].startswith(">")}
    scale: Dict[int, float] = {}
    level: Dict[int, float] = {}
    init = None
    history: List[dict] = []
    objectives: list = []
    opt = None
    for r in range(max(1, rounds)):
        if on_round is not None:
            on_round(r + 1, max(1, rounds))
        objectives = objectives_for(arrays, target, rx, goals, scale, level) + list(extra)
        opt = OptimizationService().run(OptimizationRunRequest(
            geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=engine,
            objectives=objectives, solver=SolverConfig(method="L-BFGS-B", max_iterations=iterations), init_weights_uri=init))
        fmo = read_volume(opt.dose_ref_uri)
        dose, k = normalise_to_goal(fmo, fmo[target_mask], "D95", rx * NORMALISATION_HEADROOM)
        failed = [i for i, g in enumerate(goals) if g["structure"] in masks and not goal_met(dose[masks[g["structure"]]], g)]
        history.append({"round": r + 1, "normalisation": k, "failed": [f"{goals[i]['structure']} {goals[i]['metric']}" for i in failed]})
        if not failed:
            break
        for i in failed:
            scale[i] = scale.get(i, 1.0) * 3.0
            if goals[i]["structure"] not in targets:
                level[i] = level.get(i, 1.0) * 0.9
        init = opt.weights_ref_uri
    # arcs: the sector fluence swept by the leaves, control-point doses recomputed, metersets re-optimized; the arcs
    # reproduce the sector fluence only approximately, so the same goal-driven rounds run on the arc metersets
    vm = arc_dose = None
    k = 1.0
    for r in range(max(1, int(spec.get("arc_rounds", 3)))):
        vm = VMATService().arcs(opt.optimization_id, ArcRequest(objectives=objectives, arcs=arcs, max_iterations=iterations, fractions=fractions,
                                                                machine_model_id=machine, dose_engine=engine))
        raw = read_volume(DoseService().dose_store.get_by_id(vm.dose_id).dose_grid_uri)
        arc_dose, k = normalise_to_goal(raw, raw[target_mask], "D95", rx * NORMALISATION_HEADROOM)
        failed = [i for i, g in enumerate(goals) if g["structure"] in masks and not goal_met(arc_dose[masks[g["structure"]]], g)]
        history.append({"arc_round": r + 1, "normalisation": k, "failed": [f"{goals[i]['structure']} {goals[i]['metric']}" for i in failed]})
        if not failed:
            break
        for i in failed:
            scale[i] = scale.get(i, 1.0) * 3.0
            if goals[i]["structure"] not in targets:
                level[i] = level.get(i, 1.0) * 0.95
        objectives = objectives_for(arrays, target, rx, goals, scale, level) + list(extra)
    return {"bm": bm, "opt": opt, "vm": vm, "dose": arc_dose, "k": k, "history": history, "objectives": objectives}


# ---------------------------------------------------------------------------
# Protocols and the service
# ---------------------------------------------------------------------------

PROTOCOLS_DIR = Path(__file__).resolve().parents[1] / "protocols"


class AutoplanError(ValueError):
    pass


def builtin_protocols() -> List[str]:
    return sorted(p.stem for p in PROTOCOLS_DIR.glob("*.json")) if PROTOCOLS_DIR.is_dir() else []


def load_protocol(protocol_id: str):
    from ..models.protocol import PlanningProtocol

    path = PROTOCOLS_DIR / f"{protocol_id}.json"
    if not path.is_file():
        raise AutoplanError(f"protocol {protocol_id!r} not found; shipped: {builtin_protocols()}")
    return PlanningProtocol.model_validate_json(path.read_text(encoding="utf-8"))


class AutoplanStore:
    """``{artifact_dir}/autoplans/{run_id}/meta.json`` with a cache index."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _index(self) -> Path:
        return self.base_dir / "_index.json"

    def _load_index(self) -> Dict[str, str]:
        try:
            return json.loads(self._index.read_text(encoding="utf-8")) if self._index.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def get_by_id(self, run_id: str):
        from ..models.protocol import ProtocolRunResult

        meta = self.base_dir / run_id / "meta.json"
        if not meta.is_file():
            return None
        try:
            return ProtocolRunResult.model_validate_json(meta.read_text(encoding="utf-8"))
        except Exception:
            return None

    def lookup_by_cache_key(self, key: str):
        rid = self._load_index().get(key)
        return self.get_by_id(rid) if rid else None

    def list_ids(self) -> List[str]:
        return sorted(d.name for d in self.base_dir.iterdir() if d.is_dir() and (d / "meta.json").is_file()) if self.base_dir.is_dir() else []

    def save(self, result) -> None:
        root = self.base_dir / result.run_id
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / "meta.json.tmp"
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, root / "meta.json")
        index = self._load_index()
        index[result.cache_key] = result.run_id
        tmp_i = self._index.with_suffix(".json.tmp")
        tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_i, self._index)


def _noop(stage, fraction: float, message: str) -> None:
    pass


class AutoplanService:
    """Runs a planning protocol on a geometry: structures, the goal-driven loop, a normalised deliverable plan, its goals."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        from ..config import get_settings

        self.store = AutoplanStore(Path(base_dir) if base_dir else Path(get_settings().artifact_dir) / "autoplans")

    @staticmethod
    def resolve(request):
        return request.protocol if request.protocol is not None else load_protocol(request.protocol_id)

    def cache_key(self, request) -> str:
        from .geometry import GeometryService

        geo = GeometryService().store.get_by_id(request.geometry_id)
        if geo is None:
            raise AutoplanError(f"geometry {request.geometry_id!r} not found")
        return hashlib.sha256(f"autoplan|{AUTOPLAN_VERSION}|{geo.cache_key}|{self.resolve(request).digest()}".encode("utf-8")).hexdigest()

    def run(self, request, progress_callback=None):
        from ..models.evaluation import EvaluationRequest, GoalSetSpec
        from ..models.geometry import GeometryDeriveRequest, StructureOperation
        from ..models.protocol import AutoplanStage, GoalOutcome, ProtocolRunResult
        from .geometry import GeometryService
        from .geometry_bundle import load_geometry_arrays

        on = progress_callback or _noop
        protocol = self.resolve(request)
        key = self.cache_key(request)
        cached = self.store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        t0 = time.time()
        gsvc = GeometryService()
        geo = gsvc.store.get_by_id(request.geometry_id)
        rx, target = protocol.prescription.dose_gy, protocol.prescription.target
        if protocol.beams.technique == "vmat" and protocol.engine.name != "pb":
            raise AutoplanError("VMAT recomputes its control-point doses with the pencil-beam engine: set engine to pb")

        # 1. structures: aliases copied to the protocol's names, then the protocol's derivations
        on(AutoplanStage.structures, 0.05, "structures")
        lower = {k.lower(): k for k in geo.structure_index}
        ops: List[StructureOperation] = []
        aliased: Dict[str, str] = {}
        for name, aliases in protocol.structure_aliases.items():
            if name.lower() in lower:
                continue
            found = next((lower[a.lower()] for a in aliases if a.lower() in lower), None)
            if found is not None:
                ops.append(StructureOperation(op="union", name=name, sources=[found]))
                aliased[name] = found
        ops += list(protocol.structures)
        pgeo = gsvc.derive(geo.geometry_id, GeometryDeriveRequest(operations=ops)) if ops else geo
        if target not in pgeo.structure_index:
            raise AutoplanError(f"the target {target!r} is not in the geometry after the protocol's structures ({sorted(pgeo.structure_index)})")
        arrays = load_geometry_arrays(pgeo)
        goals = [g.model_dump() for g in protocol.goals]
        cover = next(g for g in goals if g["structure"] == target and g["op"] == ">=")

        # 2. the goal-driven loop, then the deliverable plan
        on(AutoplanStage.planning, 0.15, f"{protocol.beams.technique} planning")
        # each goal-driven round as it starts (the first also computes the dose matrix, the longest step)
        def on_round(r: int, n: int) -> None:
            on(AutoplanStage.planning, 0.15 + 0.55 * (r - 1) / n, f"{protocol.beams.technique} planning, round {r} of up to {n}")
        sequence_id = vmat_id = None
        if protocol.beams.technique == "imrt":
            from ..models.apertures import SequenceRequest
            from .apertures import ApertureService

            b = protocol.beams
            beams = {"count": b.count, "start_deg": b.start_deg, **({"spacing_deg": b.spacing_deg} if b.spacing_deg else {})}
            bm, opt, _, arrays, history = plan_static(pgeo, target, rx, goals, beams, protocol.beamlet_mm, protocol.iterations,
                                                      jaw_margin_mm=protocol.jaw_margin_mm, engine_name=protocol.engine.name,
                                                      rounds=protocol.rounds, machine=protocol.machine, extra=protocol.extra_objectives,
                                                      engine_params=protocol.engine.params, on_round=on_round)
            on(AutoplanStage.deliverable, 0.75, "sequencing apertures")
            seq = ApertureService().sequence(opt.optimization_id, SequenceRequest(
                objectives=objectives_for(arrays, target, rx, goals, {}, {}) + list(protocol.extra_objectives),
                levels=b.sequence_levels, max_iterations=protocol.iterations, machine_model_id=protocol.machine))
            sequence_id, src_bm, src_dose, deliverable = seq.sequence_id, seq.beam_model_id, seq.dose_id, seq.deliverable
            from .dose import DoseService
            raw = read_volume(DoseService().dose_store.get_by_id(src_dose).dose_grid_uri)
            _, k = normalise_to_goal(raw, raw[arrays.mask_zyx(arrays.structure_index[target])], cover["metric"], cover["gy"] * NORMALISATION_HEADROOM)
            optimization_id = opt.optimization_id
        else:
            out = plan_vmat(pgeo, arrays, target, rx, goals, list(protocol.extra_objectives), protocol.beams.arcs, protocol.beamlet_mm,
                            protocol.iterations, protocol.rounds, protocol.prescription.fractions,
                            {"jaw_margin_mm": protocol.jaw_margin_mm, "machine": protocol.machine, "arc_rounds": protocol.arc_rounds,
                             "pb_params": dict(protocol.engine.params)}, on_round=on_round)
            vm, k, history = out["vm"], out["k"], out["history"]
            vmat_id, src_bm, src_dose, deliverable, optimization_id = vm.vmat_id, vm.beam_model_id, vm.dose_id, vm.deliverable, out["opt"].optimization_id

        # 3. normalised in its metersets: a deliverable beam model and its dose, both scaled by k
        on(AutoplanStage.deliverable, 0.85, f"normalising by {k:.4f}")
        bm_n, dose_n, dose_arr = self._scaled(src_bm, src_dose, k, key)
        outcomes = []
        for g in goals:
            if g["structure"] not in arrays.structure_index:
                outcomes.append(GoalOutcome(structure=g["structure"], metric=g["metric"], op=g["op"], gy=g["gy"]))
                continue
            vals = dose_arr[arrays.mask_zyx(arrays.structure_index[g["structure"]])]
            outcomes.append(GoalOutcome(structure=g["structure"], metric=g["metric"], op=g["op"], gy=g["gy"],
                                        achieved=goal_value(vals, g["metric"]), passed=goal_met(vals, g)))

        # 4. the template evaluation
        evaluation_id = None
        if protocol.evaluation_template:
            on(AutoplanStage.evaluating, 0.92, f"evaluating against {protocol.evaluation_template}")
            from .evaluation import EvaluationService
            ev = EvaluationService().run(EvaluationRequest(dose_id=dose_n.dose_id, geometry_id=pgeo.geometry_id, prescription_gy=rx,
                                                           target_structure=target, fractions=protocol.prescription.fractions,
                                                           goals=GoalSetSpec(template_id=protocol.evaluation_template)))
            evaluation_id = ev.evaluation_id
        result = ProtocolRunResult(
            run_id=str(uuid.uuid4()), protocol=protocol, geometry_id=geo.geometry_id, planning_geometry_id=pgeo.geometry_id,
            aliased=aliased,
            optimization_id=optimization_id, sequence_id=sequence_id, vmat_id=vmat_id, beam_model_id=bm_n.beam_model_id,
            dose_id=dose_n.dose_id, normalisation=float(k), goals=outcomes, passed=all(o.passed is not False for o in outcomes),
            deliverable=bool(deliverable), evaluation_id=evaluation_id, history=history, seconds=round(time.time() - t0, 1),
            cache_key=key, created_at=datetime.now(timezone.utc))
        self.store.save(result)
        on(AutoplanStage.done, 1.0, f"run {result.run_id}")
        logger.info("Protocol {} on geometry {}: {} goals, passed={}, normalised by {:.4f}, {:.0f} s", protocol.protocol_id,
                    geo.geometry_id, len(outcomes), result.passed, k, result.seconds)
        return result

    @staticmethod
    def _scaled(beam_model_id: str, dose_id: str, k: float, key: str):
        """The plan with every meterset times ``k`` (dose is linear in them) and its dose times ``k``."""
        from ..models.beam_model import FluenceElementSet, PerBeamElements
        from ..models.photon_plan import PhotonPlan
        from .beam_model import BeamModelService
        from .beam_persistence import BeamModelPaths
        from .dose import DoseService, _summary_stats
        from .dose_persistence import DOSE_FILENAME
        from .vmat import with_metersets

        bms, ds = BeamModelService(), DoseService()
        src = bms.store.get_by_id(beam_model_id)
        plan = bms.store.load_plan(beam_model_id)
        if not isinstance(plan, PhotonPlan):
            raise AutoplanError("auto-planning makes photon plans")
        beams = []
        for b in plan.beams:
            if b.arc is not None:
                beams.append(with_metersets(b, np.asarray([sg.mu for sg in b.segments], float) * k))
            else:
                beams.append(b.model_copy(update={"segments": [sg.model_copy(update={"mu": float(sg.mu) * k}) for sg in b.segments]}))
        scaled = PhotonPlan(name=f"{plan.name}-normalised", beams=beams)
        bm_key = f"{SCALED_PREFIX}{beam_model_id}:{k:.6f}:{key}"
        bm_new = bms.store.lookup_by_cache_key(bm_key)
        if bm_new is None:
            bm_id = str(uuid.uuid4())
            per_beam = [PerBeamElements(beam_id=b.beam_id, element_count=b.n_beamlets, active_beamlets=b.n_beamlets) for b in scaled.beams]
            bm_new = src.model_copy(update={"beam_model_id": bm_id, "cache_key": bm_key, "plan_weights_uri": None,
                                            "fluence_elements": FluenceElementSet(total_count=scaled.n_beamlets, per_beam=per_beam),
                                            "beam_model_ref_uri": str(BeamModelPaths.for_id(bms.store.base_dir, bm_id).plan)})
            bms.store.save(beam_model_id=bm_id, cache_key=bm_key, plan=scaled, result=bm_new)
        d_src = ds.dose_store.get_by_id(dose_id)
        arr = read_volume(d_src.dose_grid_uri) * np.float32(k)
        d_key = f"autoplan-dose|{bm_new.beam_model_id}|{d_src.cache_key}|{k:.6f}"
        d_new = ds.dose_store.lookup_by_cache_key(d_key)
        if d_new is None:
            did = str(uuid.uuid4())
            d_new = d_src.model_copy(update={"dose_id": did, "beam_model_id": bm_new.beam_model_id, "cache_key": d_key, "scenario_doses": None,
                                             "dose_grid_uri": str(ds.dose_store.base_dir / did / DOSE_FILENAME), "statistics": _summary_stats(arr),
                                             "created_at": datetime.now(timezone.utc)})
            ds.dose_store.save(dose_id=did, cache_key=d_key, nominal_dose=arr, spacing_mm=tuple(read_spacing(d_src.dose_grid_uri)),
                               scenario_doses=None, result=d_new)
        return bm_new, d_new, arr


def read_spacing(uri: str) -> Tuple[float, float, float]:
    import SimpleITK as sitk
    return tuple(float(v) for v in sitk.ReadImage(uri[len("file://"):] if uri.startswith("file://") else uri).GetSpacing())


__all__ = ["OAR_WEIGHT", "NORMALISATION_HEADROOM", "read_volume", "dose_at", "structure_extent_mm", "goal_value", "goal_met",
           "target_names", "objectives_for", "normalise_to_goal", "plan_static", "plan_vmat", "AutoplanError", "AutoplanService",
           "AutoplanStore", "builtin_protocols", "load_protocol"]
