"""``LineageService`` — versions, parents, attribution and states over the stores (roadmap R12).

The service reads every result store radiarch has and answers: what did this
version derive from (``lineage``), what derives from it (``descendants``),
who produced it with what (``attribution``), what is its state and may it be
deleted (``status``, ``assert_deletable``), and how does it read as a SMIS
transformation record (``derivation_record``). States live in one JSON file
under the artifact directory; every transition is audited.

Parents per kind:

* geometry: the geometry it was derived from (R4), else none;
* beam model: its geometry; an aperture plan also the sequence that made it;
* influence, dose, optimization, bao: geometry and beam model (a segment
  dose also its sequence);
* sequence: the optimization and the open-field beam model it sequenced;
* evaluation: its dose (when it was a stored dose) and geometry;
* rt_export: the beam model, the dose and the geometry it wrote;
* plan (legacy workflows): the geometry, beam model and dose in its summary.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from loguru import logger

from ..config import get_settings
from ..models.lineage import (
    TRANSITIONS, Attribution, DatasetRef, DerivationRecord, LineageEdge, LineageGraph, LineageNode, StateRecord,
    VersionRef, VersionState, VersionStatus,
)
from .audit import emit, make_event

APERTURE_PREFIX = "apertures:"


class LineageError(ValueError):
    pass


class VersionLocked(LineageError):
    """The version, or one derived from it, was approved: it cannot be deleted."""


def radiarch_version() -> str:
    try:
        from importlib.metadata import version
        return version("radiarch")
    except Exception:  # pragma: no cover
        return "0.1.0"


# ---------------------------------------------------------------------------
# State store
# ---------------------------------------------------------------------------

class StateStore:
    """``{artifact_dir}/lineage/states.json``: the transition history per version."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / "states.json"

    def _load(self) -> Dict[str, List[dict]]:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            logger.warning("lineage state file {} is unreadable; starting empty", self.path)
            return {}

    def _save(self, data: Dict[str, List[dict]]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))
        os.replace(tmp, self.path)

    def history(self, ref: VersionRef) -> List[StateRecord]:
        return [StateRecord.model_validate(r) for r in self._load().get(ref.key, [])]

    def append(self, ref: VersionRef, record: StateRecord) -> List[StateRecord]:
        data = self._load()
        data.setdefault(ref.key, []).append(json.loads(record.model_dump_json()))
        self._save(data)
        return [StateRecord.model_validate(r) for r in data[ref.key]]

    def all_histories(self) -> Dict[str, List[StateRecord]]:
        return {k: [StateRecord.model_validate(r) for r in v] for k, v in self._load().items()}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LineageService:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        root = Path(base_dir) if base_dir is not None else Path(get_settings().artifact_dir) / "lineage"
        self.states = StateStore(root)
        self.version = radiarch_version()

    # ----- stores ------------------------------------------------------

    def _stores(self) -> Dict[str, Tuple[Callable[[str], Any], Callable[[], Iterable[str]]]]:
        """``kind → (get_by_id, list_ids)`` over the live stores."""
        from .apertures import ApertureService
        from .bao import BAOService
        from .beam_model import BeamModelService
        from .dose import DoseService
        from .evaluation import EvaluationService
        from .geometry import GeometryService
        from .optimization import OptimizationService
        from .rt_export import RTExportService
        from ..core.store import store as plan_store

        dose = DoseService()

        def plan_ids() -> List[str]:
            return [p.id for p in plan_store.list_plans()]

        def rt_export_ids() -> List[str]:
            svc = RTExportService()
            return [p.name for p in svc.base_dir.iterdir() if (p / "manifest.json").is_file()] if svc.base_dir.is_dir() else []

        return {
            "geometry": (GeometryService().store.get_by_id, GeometryService().store.list_ids),
            "beam_model": (BeamModelService().store.get_by_id, BeamModelService().store.list_ids),
            "influence": (dose.influence_store.get_by_id, dose.influence_store.list_ids),
            "dose": (dose.dose_store.get_by_id, dose.dose_store.list_ids),
            "optimization": (OptimizationService().store.get_by_id, OptimizationService().store.list_ids),
            "sequence": (ApertureService().store.get_by_id, ApertureService().store.list_ids),
            "bao": (BAOService().store.get_by_id, BAOService().store.list_ids),
            "evaluation": (EvaluationService().store.get_by_id, EvaluationService().store.list_ids),
            "rt_export": (RTExportService().get, rt_export_ids),
            "plan": (plan_store.get_plan, plan_ids),
        }

    def get(self, ref: VersionRef) -> Optional[Any]:
        getter, _ = self._stores()[ref.kind]
        try:
            return getter(ref.id)
        except Exception as exc:  # a store that cannot open is a missing version, not a crash
            logger.warning("lineage: {} {} unreadable: {}", ref.kind, ref.id, exc)
            return None

    def _all_refs(self) -> List[VersionRef]:
        out = []
        for kind, (_, lister) in self._stores().items():
            try:
                out += [VersionRef(kind=kind, id=str(i)) for i in lister()]
            except Exception as exc:
                logger.warning("lineage: listing {} failed: {}", kind, exc)
        return out

    # ----- nodes -------------------------------------------------------

    def node(self, ref: VersionRef) -> Optional[LineageNode]:
        n = self._node(ref)
        if n is not None:
            n.locked = n.ref.key in self.locked_keys()
        return n

    def _node(self, ref: VersionRef) -> Optional[LineageNode]:
        """The node without its immutability flag (which needs the graphs of the approved versions)."""
        obj = self.get(ref)
        if obj is None:
            return None
        parents, attribution, summary = self._describe(ref, obj)
        history = self.states.history(ref)
        state = history[-1].state if history else VersionState.draft
        return LineageNode(ref=ref, cache_key=getattr(obj, "cache_key", None), created_at=getattr(obj, "created_at", None),
                           parents=parents, attribution=attribution, state=state, locked=False, summary=summary)

    def _describe(self, ref: VersionRef, obj: Any) -> Tuple[List[VersionRef], Attribution, Dict[str, Any]]:
        g = lambda name, default=None: getattr(obj, name, default)  # noqa: E731
        parents: List[VersionRef] = []
        attr = Attribution(capability_version=self.version)
        summary: Dict[str, Any] = {}

        def add(kind: str, value: Optional[str]) -> None:
            if value:
                parents.append(VersionRef(kind=kind, id=str(value)))

        if ref.kind == "geometry":
            add("geometry", g("parent_geometry_id"))
            attr.hu_model = g("hu_to_density_model")
            attr.dataset = self._dataset_of_geometry(obj)
            summary = {"structures": sorted(dict(g("structure_index") or {})), "grid": list(g("grid_spec").size or []) if g("grid_spec") else None,
                       "derived_operations": len(g("derived_operations") or [])}
        elif ref.kind == "beam_model":
            add("geometry", g("geometry_id"))
            ck = str(g("cache_key") or "")
            if ck.startswith(APERTURE_PREFIX):
                add("sequence", ck[len(APERTURE_PREFIX):])
            attr.machine_model_id = g("machine_model_id")
            attr.modality = _enum_value(g("modality"))
            imported = g("imported_plan")
            if imported is not None:
                attr.dataset.imported_plan_uid = str(getattr(imported, "sop_instance_uid", "") or "")
            summary = {"elements": getattr(g("fluence_elements"), "total_count", None), "beams": [b.beam_id for b in getattr(g("fluence_elements"), "per_beam", [])]}
        elif ref.kind in ("influence", "dose"):
            add("geometry", g("geometry_id"))
            add("beam_model", g("beam_model_id"))
            ck = str(g("cache_key") or "")
            if ck.startswith(APERTURE_PREFIX):
                add("sequence", ck[len(APERTURE_PREFIX):])
            attr.engine_name, attr.engine_version = _engine_base(g("engine_name")), g("engine_version")
            attr.modality = _enum_value(g("modality"))
            stats = g("statistics")
            summary = {"dose_units": g("dose_units"), "rbe": g("rbe_factor"), "max": getattr(stats, "max_gy", None),
                       "scenarios": len(g("scenario_doses") or [])} if ref.kind == "dose" else {"n_elements": g("n_elements"), "nnz": g("nnz")}
        elif ref.kind == "optimization":
            add("geometry", g("geometry_id"))
            add("beam_model", g("beam_model_id"))
            attr.engine_name, attr.engine_version = g("engine_name"), g("engine_version")
            conv = g("convergence")
            summary = {"dose_units": g("dose_units"), "rbe": g("rbe_factor"), "iterations": getattr(conv, "iterations", None),
                       "final_cost": getattr(conv, "final_cost", None)}
        elif ref.kind == "sequence":
            add("optimization", g("optimization_id"))
            add("beam_model", g("source_beam_model_id"))
            attr.machine_model_id = g("machine_model_id")
            attr.modality = "PHOTON_IMRT"
            summary = {"segments": g("n_segments"), "total_mu": g("total_mu"), "deliverable": g("deliverable"),
                       "produced": {"beam_model": g("beam_model_id"), "dose": g("dose_id")}}
        elif ref.kind == "bao":
            add("geometry", g("geometry_id"))
            add("beam_model", g("beam_model_id"))
            attr.engine_name, attr.engine_version = g("engine_name"), g("engine_version")
            summary = {"angles": [getattr(a, "gantry_deg", None) for a in g("selected_angles") or []], "score": g("final_score")}
        elif ref.kind == "evaluation":
            add("dose", g("dose_id"))
            add("geometry", g("geometry_id"))
            summary = {"dose_units": g("dose_units"), "structures": [c.structure_name for c in g("dvh_curves") or [] if hasattr(c, "structure_name")][:16],
                       "goals_passed": getattr(g("goals"), "passed", None) if g("goals") is not None else None}
        elif ref.kind == "rt_export":
            add("beam_model", g("beam_model_id"))
            add("dose", g("dose_id"))
            add("geometry", g("geometry_id"))
            attr.modality = _enum_value(g("modality"))
            attr.machine_model_id = g("machine_name")
            a = g("attribution")
            if isinstance(a, dict):
                attr.engine_name, attr.engine_version = a.get("engine_name"), a.get("engine_version")
                attr.machine_model_id = a.get("machine_model_id") or attr.machine_model_id
            attr.dataset.study_instance_uid = str(g("study_instance_uid") or "")
            attr.dataset.frame_of_reference_uid = str(g("frame_of_reference_uid") or "")
            attr.dataset.rtstruct_uid = str(g("rtstruct_uid") or "")
            summary = {"objects": [o.kind for o in g("objects") or []], "plan_uid": g("plan_sop_instance_uid"), "pushed": g("pushed")}
        elif ref.kind == "plan":
            qa = dict(g("qa_summary") or {})
            add("geometry", qa.get("geometryId"))
            add("beam_model", qa.get("beamModelId"))
            add("dose", qa.get("doseId"))
            attr.engine_name, attr.engine_version = qa.get("engine"), qa.get("engineVersion")
            attr.dataset.study_instance_uid = str(g("study_instance_uid") or "")
            summary = {"workflow": _enum_value(g("workflow_id")), "status": g("status"), "prescription_gy": g("prescription_gy")}

        # a version inherits the dataset of its geometry; what it knows itself is kept
        if ref.kind != "geometry":
            geo_ref = next((p for p in parents if p.kind == "geometry"), None)
            geo = self.get(geo_ref) if geo_ref else None
            if geo is not None:
                own = {k: v for k, v in attr.dataset.model_dump().items() if v}
                attr.dataset = self._dataset_of_geometry(geo).model_copy(update=own)
                attr.hu_model = attr.hu_model or getattr(geo, "hu_to_density_model", None)
        return parents, attr, summary

    @staticmethod
    def _dataset_of_geometry(geo: Any) -> DatasetRef:
        meta = getattr(geo, "ct_metadata", None)
        return DatasetRef(
            patient_id=str(getattr(meta, "patient_id", "") or ""),
            study_instance_uid=str(getattr(meta, "study_instance_uid", "") or ""),
            ct_series_instance_uid=str(getattr(meta, "series_instance_uid", "") or ""),
            frame_of_reference_uid=str(getattr(geo, "frame_of_reference_uid", "") or ""),
        )

    # ----- graphs ------------------------------------------------------

    def lineage(self, ref: VersionRef, max_depth: int = 32) -> LineageGraph:
        """The version and everything it derives from."""
        graph = self._graph(ref, max_depth)
        locked = self.locked_keys()
        for n in graph.nodes:
            n.locked = n.ref.key in locked
        return graph

    def _graph(self, ref: VersionRef, max_depth: int = 32) -> LineageGraph:
        root = self._node(ref)
        if root is None:
            raise LineageError(f"{ref.kind} {ref.id!r} not found")
        nodes: Dict[str, LineageNode] = {ref.key: root}
        edges: List[LineageEdge] = []
        missing: List[VersionRef] = []
        frontier = [(root, 0)]
        while frontier:
            node, depth = frontier.pop()
            if depth >= max_depth:
                continue
            for parent in node.parents:
                edges.append(LineageEdge(child=node.ref, parent=parent))
                if parent.key in nodes or any(m.key == parent.key for m in missing):
                    continue
                pn = self._node(parent)
                if pn is None:
                    missing.append(parent)
                    continue
                nodes[parent.key] = pn
                frontier.append((pn, depth + 1))
        roots = [n.ref for n in nodes.values() if not n.parents]
        return LineageGraph(root=ref, nodes=list(nodes.values()), edges=edges, roots=roots, missing=missing)

    def descendants(self, ref: VersionRef) -> List[LineageNode]:
        """Every version that derives, directly or through others, from ``ref``."""
        if self.get(ref) is None:
            raise LineageError(f"{ref.kind} {ref.id!r} not found")
        by_key: Dict[str, LineageNode] = {}
        locked = self.locked_keys()
        for r in self._all_refs():
            n = self._node(r)
            if n is not None:
                n.locked = r.key in locked
                by_key[r.key] = n
        children: Dict[str, List[str]] = {}
        for n in by_key.values():
            for p in n.parents:
                children.setdefault(p.key, []).append(n.ref.key)
        out: List[LineageNode] = []
        seen: Set[str] = set()
        stack = list(children.get(ref.key, []))
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            out.append(by_key[k])
            stack += children.get(k, [])
        return out

    def attribution(self, ref: VersionRef) -> Attribution:
        node = self.node(ref)
        if node is None:
            raise LineageError(f"{ref.kind} {ref.id!r} not found")
        return node.attribution

    # ----- states ------------------------------------------------------

    def status(self, ref: VersionRef) -> VersionStatus:
        history = self.states.history(ref)
        state = history[-1].state if history else VersionState.draft
        return VersionStatus(ref=ref, state=state, locked=self.is_locked(ref), history=history)

    def transition(self, ref: VersionRef, record: StateRecord) -> VersionStatus:
        """Record a state transition decided elsewhere; refuse what the state machine does not allow."""
        if self.get(ref) is None:
            raise LineageError(f"{ref.kind} {ref.id!r} not found")
        history = self.states.history(ref)
        current = history[-1].state.value if history else VersionState.draft.value
        if record.state.value not in TRANSITIONS[current]:
            raise LineageError(f"{ref.kind} {ref.id} is {current}: it cannot become {record.state.value}")
        if record.superseded_by is not None and self.get(record.superseded_by) is None:
            raise LineageError(f"superseding version {record.superseded_by.key} not found")
        record = record.model_copy(update={"at": record.at or datetime.now(timezone.utc)})
        history = self.states.append(ref, record)
        emit(make_event("lineage.state", state="succeeded", extra={"ref": ref.key, "to": record.state.value, "actor": record.actor,
                                                                    "authority": record.authority, "reference": record.reference}))
        logger.info("lineage: {} → {} by {} under {}", ref.key, record.state.value, record.actor or "-", record.authority or "-")
        return VersionStatus(ref=ref, state=history[-1].state, locked=self.is_locked(ref), history=history)

    def _ever_approved(self) -> List[VersionRef]:
        out = []
        for key, history in self.states.all_histories().items():
            if any(r.state is VersionState.approved for r in history):
                kind, _, vid = key.partition(":")
                out.append(VersionRef(kind=kind, id=vid))
        return out

    def locked_keys(self) -> Set[str]:
        """Versions that were approved, and every version they derive from."""
        keys: Set[str] = set()
        for ref in self._ever_approved():
            keys.add(ref.key)
            try:
                graph = self._graph(ref)
            except LineageError:
                continue
            keys.update(n.ref.key for n in graph.nodes)
        return keys

    def is_locked(self, ref: VersionRef) -> bool:
        return ref.key in self.locked_keys()

    def assert_deletable(self, ref: VersionRef) -> None:
        if self.is_locked(ref):
            raise VersionLocked(f"{ref.kind} {ref.id} is immutable: it, or a version derived from it, was approved")

    # ----- SMIS transformation record ----------------------------------

    def derivation_record(self, ref: VersionRef, *, inputs: List[Dict[str, Any]], identifiability: str = "pseudonymized",
                          description: Optional[str] = None) -> DerivationRecord:
        """The version as the SMIS manifest's ``derivation`` member (design §6.1): a computation by the
        tool radiarch, with the engine, machine and ids as parameters and the DICOM objects an export wrote."""
        node = self.node(ref)
        if node is None:
            raise LineageError(f"{ref.kind} {ref.id!r} not found")
        graph = self.lineage(ref)
        started = min((n.created_at for n in graph.nodes if n.created_at), default=node.created_at)
        a = node.attribution
        params: Dict[str, Any] = {"kind": ref.kind, "id": ref.id, "cache_key": node.cache_key,
                                  "parents": [p.key for p in node.parents], "roots": [r.key for r in graph.roots]}
        for k in ("engine_name", "engine_version", "machine_model_id", "hu_model", "modality"):
            if getattr(a, k):
                params[k] = getattr(a, k)
        params["dataset"] = {k: v for k, v in a.dataset.model_dump().items() if v}
        tr: Dict[str, Any] = {
            "kind": "computation",
            "actor": {"kind": "tool", "id": a.capability_id, "version": a.capability_version},
            "identifiability": identifiability,
            "tool": {"name": a.capability_id, "version": a.capability_version},
            "parameters": params,
            "started": _iso(started), "finished": _iso(node.created_at),
            "description": description or f"radiarch {ref.kind} {ref.id}; {a.intended_use}",
        }
        outputs = None
        obj = self.get(ref)
        objects = getattr(obj, "objects", None)
        if ref.kind == "rt_export" and objects:
            series: Dict[str, Dict[str, Any]] = {}
            for o in objects:
                s = series.setdefault(o.series_instance_uid, {"study_uid": getattr(obj, "study_instance_uid", ""), "series_uid": o.series_instance_uid,
                                                               "modality": _modality_of(o.kind), "instance_count": 0})
                s["instance_count"] += 1
            outputs = {"objects_written": list(series.values())}
        return DerivationRecord(transformation=tr, inputs=[{"dataset_id": str(i["dataset_id"]), "version": int(i["version"])} for i in inputs],
                                outputs=outputs)

    # ----- capability --------------------------------------------------

    def capability(self) -> Dict[str, Any]:
        """What radiarch declares about itself to a capability registry (F2.5)."""
        from ..models.common import NOT_FOR_CLINICAL_USE, RESEARCH_USE_ONLY
        from ..models.geometry import HUDensityModel
        from .clinical_goals import builtin_templates
        from .dose_engines.registry import engine_health, list_engines
        from .machine_model import DEFAULT_PHOTON_MACHINE, builtin_photon_machines

        engines = []
        for name in list_engines():
            h = engine_health(name)
            engines.append({"name": name, "version": h.get("version"), "modalities": h.get("modalities"), "available": h.get("available")})
        return {
            "capability_id": "radiarch", "version": self.version, "actor_kind": "tool",
            "intended_use": RESEARCH_USE_ONLY,
            "reads": ["CT", "RTSTRUCT", "RTPLAN", "RTDOSE", "REG"],
            "writes": ["RTSTRUCT", "RTPLAN", "RTDOSE", "RTIMAGE", "RTRECORD"],
            "never": ["an RT Plan to a treatment queue", "an approval decision", "re-identification"],
            "object_labeling": {"SeriesDescription": "RESEARCH - " + NOT_FOR_CLINICAL_USE, "ApprovalStatus": "UNAPPROVED",
                                "PlanIntent": "RESEARCH", "private_block": "(7779,xx01) RADIARCH"},
            "engines": engines,
            "machines": {"photon": list(builtin_photon_machines()), "photon_default": DEFAULT_PHOTON_MACHINE, "proton": ["default"]},
            "hu_models": [m.value for m in HUDensityModel],
            "goal_templates": list(builtin_templates()),
            "states": {"values": [s.value for s in VersionState], "transitions": TRANSITIONS,
                       "rule": "radiarch records transitions decided by the clinic's record system; an approved version and its ancestors are immutable"},
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine_base(name: Optional[str]) -> Optional[str]:
    """``analytic+segments`` → ``analytic``: the engine, without the method suffix a service appends."""
    return (str(name).split("+")[0] or None) if name else None


def _enum_value(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(getattr(v, "value", v))


def _iso(t: Optional[datetime]) -> str:
    t = t or datetime.now(timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _modality_of(kind: str) -> str:
    return {"RTSTRUCT": "RTSTRUCT", "RTPLAN": "RTPLAN", "RTIONPLAN": "RTPLAN", "RTDOSE": "RTDOSE", "RTIMAGE": "RTIMAGE",
            "RTRECORD": "RTRECORD", "RTSUMMARY": "RTRECORD"}.get(kind, kind)


__all__ = ["LineageService", "LineageError", "VersionLocked", "StateStore", "radiarch_version"]
