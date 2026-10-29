"""The SDK's domain objects. Each wraps one service result (``.result``, its fields readable directly on the object)
and offers the next planning steps as methods, so a plan reads as a chain:

>>> geo = rx.build_geometry("1.2.3", data_root="/data/case1", spacing_mm=3)
>>> geo = geo.derive(ops.expand("PTV", "CTV", 5), ops.ring("Ring", "PTV", 3, 20))
>>> bm = geo.photon_beams([0, 72, 144, 216, 288], machine="synthetic-120")
>>> opt = bm.optimize([obj.uniform("PTV", 60), obj.max("SpinalCord", 45)], engine="pb")
>>> seq = opt.sequence(objectives)
>>> ev = seq.dose().evaluate(60, goals="rtog-0617", target="PTV", fractions=30)
>>> ev.goals_table()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence as Seq, Union

from pydantic import BaseModel

from ..models.dose import EngineSpec


def _engine(engine: Union[str, EngineSpec, dict, None], default: str = "pb") -> EngineSpec:
    if engine is None:
        return EngineSpec(name=default)
    if isinstance(engine, str):
        return EngineSpec(name=engine)
    return engine if isinstance(engine, EngineSpec) else EngineSpec(**engine)


class _Object:
    """One service result and the client that made it."""

    id_field = ""

    def __init__(self, client, result: BaseModel) -> None:
        self.client, self.result = client, result

    @property
    def id(self) -> str:
        return getattr(self.result, self.id_field)

    def __getattr__(self, name: str) -> Any:              # the result's fields read directly
        if name in ("client", "result"):
            raise AttributeError(name)
        return getattr(self.result, name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.id})"

    def lineage(self) -> Dict[str, Any]:
        kind = {"Geometry": "geometry", "BeamModel": "beam_model", "Dose": "dose", "Optimization": "optimization",
                "Sequence": "sequence", "Evaluation": "evaluation", "Export": "rt_export", "Registration": "registration",
                "ParetoSet": "mco"}[type(self).__name__]
        return self.client.get(f"/lineage/{kind}/{self.id}")


class Geometry(_Object):
    """A patient's CT, density and structures on one grid (a built or derived geometry)."""

    id_field = "geometry_id"

    @property
    def structures(self) -> List[str]:
        return sorted(self.result.structure_index)

    def derive(self, *operations) -> "Geometry":
        """A new geometry with structure operations applied (``sdk.ops``: expand, ring, union, subtract, …)."""
        from ..models.geometry import GeometryDeriveRequest, GeometryResult, StructureOperation

        flat = [o for op in operations for o in (op if isinstance(op, (list, tuple)) else [op])]
        req = GeometryDeriveRequest(operations=[o if isinstance(o, StructureOperation) else StructureOperation(**o) for o in flat])
        return Geometry(self.client, self.client.post(f"/geometry/{self.id}/derive", req, GeometryResult))

    def beams(self, beams: Seq[Any], *, modality: str = "PHOTON_IMRT", machine: Optional[str] = None,
              isocenter_mm: Optional[Seq[float]] = None, **delivery) -> "BeamModel":
        """A beam model: ``beams`` are ``BeamSpec``s, dicts, or gantry angles; ``delivery`` sets the delivery parameters
        (``beamlet_size_mm``, ``jaw_opening_mm``, ``spot_spacing_mm``, …)."""
        from ..models.beam_model import BeamModelBuildRequest, BeamModelResult, BeamSetSpec, BeamSpec, DeliveryParams, Modality

        specs = []
        for i, b in enumerate(beams):
            if isinstance(b, BeamSpec):
                specs.append(b)
            elif isinstance(b, dict):
                specs.append(BeamSpec(**b))
            else:
                specs.append(BeamSpec(beam_id=f"B{i + 1}", gantry_deg=float(b)))
        req = BeamModelBuildRequest(geometry_id=self.id, modality=Modality(modality), machine_model_id=machine,
                                    beam_set=BeamSetSpec(isocenter_mm=tuple(isocenter_mm) if isocenter_mm else None, beams=specs),
                                    delivery_params=DeliveryParams(**delivery))
        return BeamModel(self.client, self.client.submit("beam-model", "/beam-model/build", req, BeamModelResult))

    def photon_beams(self, gantry_deg: Seq[float], *, machine: str = "synthetic-120", **delivery) -> "BeamModel":
        return self.beams(list(gantry_deg), modality="PHOTON_IMRT", machine=machine, **delivery)

    def arc_sectors(self, arcs: Seq[Any], *, machine: str = "synthetic-120", isocenter_mm: Optional[Seq[float]] = None, **delivery) -> "BeamModel":
        """The sector beams of VMAT arcs (``ArcSpec``s or dicts), to optimize and then turn into arcs."""
        from ..models.beam_model import BeamSpec
        from ..models.vmat import ArcSpec, sector_beams

        specs = [a if isinstance(a, ArcSpec) else ArcSpec(**a) for a in arcs]
        beams = [BeamSpec(beam_id=b, gantry_deg=g, couch_deg=c, collimator_deg=col) for b, g, c, col in sector_beams(specs)]
        return self.beams(beams, modality="PHOTON_IMRT", machine=machine, isocenter_mm=isocenter_mm, **delivery)

    def evaluate(self, dose: Union["Dose", str], prescription_gy: float, **kwargs) -> "Evaluation":
        dose_id = dose.id if isinstance(dose, Dose) else dose
        return _evaluate(self.client, self.id, prescription_gy, dose_id=dose_id, **kwargs)

    def register_to(self, fixed: Union["Geometry", str], **options) -> "Registration":
        """Register this geometry (moving) to ``fixed``; options as ``RegistrationRequest``."""
        from ..models.registration import RegistrationRequest, RegistrationResult

        fid = fixed.id if isinstance(fixed, Geometry) else fixed
        res = self.client.post("/registrations", RegistrationRequest(fixed_geometry_id=fid, moving_geometry_id=self.id, **options), RegistrationResult)
        return Registration(self.client, res)

    def run_protocol(self, protocol) -> "ProtocolRun":
        """Plan this geometry with a protocol (a shipped id, a ``PlanningProtocol`` or a dict)."""
        return self.client.run_protocol(protocol, self)

    def delete(self) -> None:
        self.client.request("DELETE", f"/geometry/{self.id}")


class BeamModel(_Object):
    """Beams on a geometry: open-field beamlets or spots to optimize, or a deliverable plan with metersets."""

    id_field = "beam_model_id"

    def optimize(self, objectives: Iterable[Any], *, engine: Union[str, EngineSpec, dict, None] = "pb", method: str = "L-BFGS-B",
                 max_iterations: int = 200, init_weights_uri: Optional[str] = None, **extra) -> "Optimization":
        from ..models.optimization import ObjectiveSpec, OptimizationResult, OptimizationRunRequest, SolverConfig

        objs = [o if isinstance(o, ObjectiveSpec) else ObjectiveSpec(**o) for o in objectives]
        req = OptimizationRunRequest(geometry_id=self.result.geometry_id, beam_model_id=self.id, dose_engine=_engine(engine), objectives=objs,
                                     solver=SolverConfig(method=method, max_iterations=int(max_iterations)), init_weights_uri=init_weights_uri, **extra)
        return Optimization(self.client, self.client.submit("optimize", "/optimize/run", req, OptimizationResult))

    def mco(self, tradeoffs: Iterable[Any], *, hard_constraints: Iterable[Any] = (), engine: Union[str, EngineSpec, dict, None] = "pb",
            max_iterations: int = 300, **request) -> "ParetoSet":
        """The Pareto set of this beam model over ``tradeoffs`` (``ops.mean_dose``, ``ops.uniform_rms``, ...) under
        ``hard_constraints`` (``ops.hard``): anchors, a balance plan and sandwich plans to an error bound (R11)."""
        from ..models.mco import MCORunRequest, MCOResult
        from ..models.optimization import HardConstraint, ObjectiveSpec, SolverConfig

        req = MCORunRequest(geometry_id=self.result.geometry_id, beam_model_id=self.id, dose_engine=_engine(engine),
                            tradeoffs=[o if isinstance(o, ObjectiveSpec) else ObjectiveSpec(**o) for o in tradeoffs],
                            hard_constraints=[c if isinstance(c, HardConstraint) else HardConstraint(**c) for c in hard_constraints],
                            solver=SolverConfig(method="L-BFGS-B", max_iterations=int(max_iterations)), **request)
        return ParetoSet(self.client, self.client.submit("mco", "/mco/run", req, MCOResult))

    def dose(self, weights: Seq[float], *, engine: Union[str, EngineSpec, dict, None] = "pb", geometry: Union[Geometry, str, None] = None) -> "Dose":
        """The dose of explicit element weights (on this beam model's geometry, or another in the same frame)."""
        from ..models.dose import DoseComputeRequest, DoseResult, WeightVector

        gid = geometry.id if isinstance(geometry, Geometry) else (geometry or self.result.geometry_id)
        w = [float(v) for v in weights]
        req = DoseComputeRequest(geometry_id=gid, beam_model_id=self.id, engine=_engine(engine), weights=WeightVector(length=len(w), values=w))
        return Dose(self.client, self.client.submit("dose", "/dose/compute", req, DoseResult))

    def export(self, *, dose: Union["Dose", str, None] = None, **request) -> "Export":
        """RT objects of a plan with its own metersets (an imported plan, arcs, a sequence's apertures)."""
        dose_id = dose.id if isinstance(dose, Dose) else dose
        return _export(self.client, beam_model_id=self.id, dose_id=dose_id, **request)

    def delete(self) -> None:
        self.client.request("DELETE", f"/beam-model/{self.id}")


class Optimization(_Object):
    """Optimized element weights and their dose."""

    id_field = "optimization_id"

    def evaluate(self, prescription_gy: float, **kwargs) -> "Evaluation":
        return _evaluate(self.client, self.result.geometry_id, prescription_gy, dose_ref_uri=self.result.dose_ref_uri, **kwargs)

    def sequence(self, objectives: Iterable[Any], **request) -> "Sequence":
        """Step-and-shoot apertures from the fluence (photons), segment metersets re-optimized against ``objectives``."""
        from ..models.apertures import SequenceRequest, SequenceResult
        from ..models.optimization import ObjectiveSpec

        req = SequenceRequest(objectives=[o if isinstance(o, ObjectiveSpec) else ObjectiveSpec(**o) for o in objectives], **request)
        return Sequence(self.client, self.client.post(f"/optimize/{self.id}/sequence", req, SequenceResult))

    def arcs(self, arcs: Seq[Any], objectives: Iterable[Any], *, fractions: int = 1, engine: Union[str, EngineSpec, dict, None] = "pb",
             **request) -> "Arcs":
        """VMAT arcs from an optimization of the arcs' sector beams (``Geometry.arc_sectors``)."""
        from ..models.optimization import ObjectiveSpec
        from ..models.vmat import ArcRequest, ArcResult, ArcSpec

        req = ArcRequest(arcs=[a if isinstance(a, ArcSpec) else ArcSpec(**a) for a in arcs],
                         objectives=[o if isinstance(o, ObjectiveSpec) else ObjectiveSpec(**o) for o in objectives],
                         fractions=int(fractions), dose_engine=_engine(engine), **request)
        return Arcs(self.client, self.client.post(f"/optimize/{self.id}/arcs", req, ArcResult))

    def weights(self):
        """The optimal element weights (a NumPy array, from the service's ``.npy``)."""
        import io
        import numpy as np

        return np.load(io.BytesIO(self.client.request("GET", f"/optimize/{self.id}/weights").content))


class _Deliverable(_Object):
    """A plan with metersets made from an optimization (a sequence or arcs): its beam model and dose."""

    def beam_model(self) -> BeamModel:
        return self.client.beam_model(self.result.beam_model_id)

    def dose(self) -> "Dose":
        return self.client.dose(self.result.dose_id)

    def evaluate(self, prescription_gy: float, **kwargs) -> "Evaluation":
        return _evaluate(self.client, self.result.geometry_id, prescription_gy, dose_id=self.result.dose_id, **kwargs)

    def export(self, **request) -> "Export":
        return _export(self.client, beam_model_id=self.result.beam_model_id, dose_id=self.result.dose_id, **request)


class Sequence(_Deliverable):
    id_field = "sequence_id"


class Arcs(_Deliverable):
    id_field = "vmat_id"


class Dose(_Object):
    id_field = "dose_id"

    def evaluate(self, prescription_gy: float, **kwargs) -> "Evaluation":
        return _evaluate(self.client, self.result.geometry_id, prescription_gy, dose_id=self.id, **kwargs)

    def download(self, path: Union[str, Path]) -> Path:
        """The dose volume (NIfTI) to a local file."""
        p = Path(path)
        p.write_bytes(self.client.request("GET", f"/dose/{self.id}/artifact").content)
        return p


class Evaluation(_Object):
    id_field = "evaluation_id"

    @property
    def passed(self) -> Optional[bool]:
        """Every priority-1 goal met (None without goals)."""
        g = self.result.goals
        if g is None:
            return None
        return all(r.passed is not False for r in g.results if int(r.priority) == 1)

    def goals_table(self) -> List[Dict[str, Any]]:
        g = self.result.goals
        return [] if g is None else [{"structure": r.structure, "metric": r.metric, "op": r.op, "value": r.value, "achieved": r.achieved,
                                      "passed": r.passed, "priority": r.priority} for r in g.results]


class Export(_Object):
    id_field = "export_id"

    def files(self) -> List[str]:
        return [o.file_name for o in self.result.objects]

    def download(self, directory: Union[str, Path]) -> List[Path]:
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        paths = []
        for name in self.files():
            p = out / name
            p.write_bytes(self.client.request("GET", f"/rt/exports/{self.id}/files/{name}").content)
            paths.append(p)
        return paths

    def push(self, url: Optional[str] = None, kinds: Optional[List[str]] = None) -> Dict[str, Any]:
        body = {k: v for k, v in {"url": url, "kinds": kinds}.items() if v is not None}
        return self.client.post(f"/rt/exports/{self.id}/push", body)


class Registration(_Object):
    id_field = "registration_id"

    def propagate(self, structures: Optional[List[str]] = None, suffix: str = "", threshold: float = 0.5) -> Geometry:
        from ..models.geometry import GeometryResult
        from ..models.registration import PropagateRequest

        res = self.client.post(f"/registrations/{self.id}/propagate", PropagateRequest(structures=structures, suffix=suffix, threshold=threshold),
                               GeometryResult)
        return Geometry(self.client, res)

    def map_dose(self, dose: Union[Dose, str]) -> Dose:
        from ..models.dose import DoseResult

        dose_id = dose.id if isinstance(dose, Dose) else dose
        return Dose(self.client, self.client.post(f"/registrations/{self.id}/map-dose", {"dose_id": dose_id}, DoseResult))


class ParetoSet(_Object):
    """Pareto-optimal plans of a beam model over convex trade-offs (R11): their values, the error bound."""

    id_field = "mco_id"

    def table(self) -> List[Dict[str, Any]]:
        """One row per plan: its kind and each trade-off's value in Gy."""
        names = [f"{o.type}({o.structure_name})" for o in self.result.tradeoffs]
        return [{"plan": p.index, "kind": p.kind, **dict(zip(names, p.values_gy))} for p in self.result.plans]

    def navigate(self, *, move: Optional[Dict[str, float]] = None, reference: Optional[Dict[str, float]] = None,
                 clamps: Optional[Dict[str, float]] = None, locks: Seq[str] = (), from_state: Any = "balance",
                 goals: Union[str, Dict[str, Any], None] = None, **request):
        """A navigation state: ``move={"MeanDose(Heart)": 12}`` (a slider), ``reference={...}`` (a point), with
        ``clamps`` (upper bounds in Gy) and ``locks``, from a state (the balance plan by default). ``goals`` is a
        template id or a goal set, graded on the blended dose."""
        from ..models.mco import NavigateRequest, NavigationState

        start = getattr(from_state, "state_id", from_state)
        goal_set = {"template_id": goals} if isinstance(goals, str) else goals
        req = NavigateRequest(from_state=start, move=move or {}, reference=reference or {}, clamps=clamps or {}, locks=list(locks),
                              goals=goal_set, **request)
        return self.client.post(f"/mco/{self.id}/navigate", req, NavigationState)

    def auto_navigate(self, goals: Union[str, Dict[str, Any]], *, clamps: Optional[Dict[str, float]] = None, locks: Seq[str] = (),
                      from_state: Any = "balance", **request):
        """The blend that best meets ``goals`` (a template id or a goal set), priority 1 first, then 2, then 3."""
        from ..models.mco import AutoNavigateRequest, NavigationState

        goal_set = {"template_id": goals} if isinstance(goals, str) else goals
        req = AutoNavigateRequest(goals=goal_set, clamps=clamps or {}, locks=list(locks), from_state=getattr(from_state, "state_id", from_state),
                                  **request)
        return self.client.post(f"/mco/{self.id}/auto-navigate", req, NavigationState)

    def states(self):
        """The stored navigation states, the balance plan first."""
        from ..models.mco import NavigationState

        return [NavigationState.model_validate(s) for s in self.client.get(f"/mco/{self.id}/states")]


class ProtocolRun(_Object):
    """A planning protocol's run: the deliverable plan (normalised), its dose and its goals."""

    id_field = "run_id"

    def beam_model(self) -> BeamModel:
        return self.client.beam_model(self.result.beam_model_id)

    def dose(self) -> Dose:
        return self.client.dose(self.result.dose_id)

    def geometry(self) -> Geometry:
        return self.client.geometry(self.result.planning_geometry_id)

    def evaluation(self) -> Optional[Evaluation]:
        return self.client.evaluation(self.result.evaluation_id) if self.result.evaluation_id else None

    def goals_table(self) -> List[Dict[str, Any]]:
        return [g.model_dump() for g in self.result.goals]

    def export(self, **request) -> "Export":
        """The plan's RT objects. Its structure set holds the planning geometry's structures under the protocol's names:
        a patient's structure the protocol copied to its own name (structure_aliases) is not written twice."""
        rx = self.result.protocol.prescription
        request.setdefault("prescription", {"dose_gy": rx.dose_gy, "fractions": rx.fractions, "target_structure": rx.target})
        if request.get("structures") is None and self.result.aliased:
            index = self.geometry().result.structure_index
            copied = set(self.result.aliased.values())
            request["structures"] = [n for n in sorted(index, key=index.get) if n not in copied]
        return _export(self.client, beam_model_id=self.result.beam_model_id, dose_id=self.result.dose_id, **request)


# ---------------------------------------------------------------------------

def _evaluate(client, geometry_id: str, prescription_gy: float, *, goals: Union[str, Dict[str, Any], None] = None,
              target: Optional[str] = None, fractions: Optional[int] = None, **request) -> Evaluation:
    from ..models.evaluation import EvaluationRequest, EvaluationResult, GoalSetSpec

    goal_set = None
    if isinstance(goals, str):
        goal_set = GoalSetSpec(template_id=goals)
    elif isinstance(goals, dict):
        goal_set = GoalSetSpec(**goals)
    elif goals is not None:
        goal_set = goals
    req = EvaluationRequest(geometry_id=geometry_id, prescription_gy=float(prescription_gy), target_structure=target, fractions=fractions,
                            goals=goal_set, **request)
    return Evaluation(client, client.submit("evaluate", "/evaluate/run", req, EvaluationResult))


def _export(client, **request) -> Export:
    from ..models.rt_export import PrescriptionSpec, RTExportRequest, RTExportResult

    rx = request.pop("prescription", None)
    if isinstance(rx, dict):
        rx = PrescriptionSpec(**rx)
    req = RTExportRequest(prescription=rx, **{k: v for k, v in request.items() if v is not None})
    return Export(client, client.post("/rt/export", req, RTExportResult))


__all__ = ["Geometry", "BeamModel", "Optimization", "Sequence", "Arcs", "Dose", "Evaluation", "Export", "Registration", "ProtocolRun"]
