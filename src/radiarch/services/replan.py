"""Adaptive replanning (roadmap R9): a plan checked on a later image of the patient.

Assessment, in order:

1. **Registration** of the day's image (fixed) and the planning CT (moving): rigid, then B-spline by default (a
   cone-beam CT's calibration differs; Demons for a re-planning CT).
2. **The day's geometry**: the planning structures propagated onto the day's image; for a cone-beam CT, whose HU
   are not calibrated for dose, the planning CT's HU deformed onto it give the density (``deformed_planning_ct``).
3. **The plan on the day**: its isocenter moved by the rigid part of the registration, as the couch shift that sets
   the patient up does (the rigid rotation is reported, not corrected), its metersets recomputed on the day's
   anatomy (photon apertures through the engine's aperture path).
4. **Goals** graded on the planned dose and on the day's dose, side by side; the planned dose mapped onto the day's
   grid for comparison.

A new plan on the day's geometry (optimization as for any plan, warm-started from the old one's weights when its
beams are the same) is exported with the old plan as its PREDECESSOR; the delivered course is the accumulation of
each plan's dose by the fractions delivered with it (``FourDService.accumulate`` with absolute weights), written
as a MULTI_PLAN RT Dose.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from loguru import logger

from ..config import get_settings
from ..models.replan import DensitySource, GoalComparison, ReplanAssessment, ReplanAssessRequest

REPLAN_VERSION = "1"
REPLAN_PREFIX = "replan:"          # a day plan's cache key: replan:{the planned beam model}:{assessment key} (lineage reads it)


class ReplanError(ValueError):
    pass


class ReplanStore:
    """``{artifact_dir}/replan/{id}/meta.json`` with a cache index."""

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

    def get_by_id(self, assessment_id: str) -> Optional[ReplanAssessment]:
        meta = self.base_dir / assessment_id / "meta.json"
        if not meta.is_file():
            return None
        try:
            return ReplanAssessment.model_validate_json(meta.read_text(encoding="utf-8"))
        except Exception:
            return None

    def lookup_by_cache_key(self, key: str) -> Optional[ReplanAssessment]:
        aid = self._load_index().get(key)
        return self.get_by_id(aid) if aid else None

    def list_ids(self) -> List[str]:
        return sorted(d.name for d in self.base_dir.iterdir() if d.is_dir() and (d / "meta.json").is_file()) if self.base_dir.is_dir() else []

    def save(self, result: ReplanAssessment) -> None:
        root = self.base_dir / result.assessment_id
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / "meta.json.tmp"
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, root / "meta.json")
        index = self._load_index()
        index[result.cache_key] = result.assessment_id
        tmp_i = self._index.with_suffix(".json.tmp")
        tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_i, self._index)


class ReplanService:
    def __init__(self, base_dir: Optional[Path] = None, four_d=None) -> None:
        from .four_d import FourDService

        self.store = ReplanStore(Path(base_dir) if base_dir else Path(get_settings().artifact_dir) / "replan")
        self.four_d = four_d or FourDService()
        self.geometry_service = self.four_d.geometry_service
        self.dose_service = self.four_d.dose_service
        self.registration_service = self.four_d.registration_service

    def _geometry(self, geometry_id: str):
        g = self.geometry_service.store.get_by_id(geometry_id)
        if g is None:
            raise ReplanError(f"geometry {geometry_id!r} not found")
        return g

    def get(self, assessment_id: str) -> ReplanAssessment:
        a = self.store.get_by_id(assessment_id)
        if a is None:
            raise ReplanError(f"assessment {assessment_id!r} not found")
        return a

    def assess(self, request: ReplanAssessRequest) -> ReplanAssessment:
        from ..models.photon_plan import PhotonPlan
        from ..models.registration import PropagateRequest, RegistrationRequest

        planning, day = self._geometry(request.planning_geometry_id), self._geometry(request.day_geometry_id)
        bm = self.dose_service._load_beam_model(request.beam_model_id)
        if not isinstance(bm.plan, PhotonPlan):
            raise ReplanError("replanning handles photon plans (the proton isocenter and range shift are not carried over yet)")
        payload = request.model_dump(mode="json", exclude={"planning_geometry_id", "day_geometry_id", "beam_model_id"})
        key = hashlib.sha256(json.dumps({"v": REPLAN_VERSION, "planning": planning.cache_key, "day": day.cache_key, "plan": bm.result.cache_key,
                                         **payload}, sort_keys=True).encode("utf-8")).hexdigest()
        cached = self.store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        t0 = time.time()

        # 1. registration: the day's image fixed, the planning CT moving
        reg = self.registration_service.register(RegistrationRequest(
            fixed_geometry_id=day.geometry_id, moving_geometry_id=planning.geometry_id, deformable=request.deformable,
            rigid_init=request.rigid_init, working_spacing_mm=request.working_spacing_mm))

        # 2. the day's geometry: planning structures propagated, and the density
        geo = self.registration_service.propagate(reg.registration_id, PropagateRequest(structures=request.structures, suffix=request.suffix))
        if request.density is DensitySource.deformed_planning_ct:
            geo = self._deformed_density(geo, planning, reg)

        # 3. the plan on the day: the isocenter moved by the rigid part (fixed → moving is y = A x + b)
        m = np.asarray(reg.rigid_matrix, float)
        a, b = m[:3, :3], m[:3, 3]
        beams, shifts = [], []
        for beam in bm.plan.beams:
            iso = np.asarray(beam.isocenter_mm, float)
            day_iso = np.linalg.solve(a, iso - b)
            shifts.append(day_iso - iso)
            beams.append(beam.model_copy(update={"isocenter_mm": tuple(float(v) for v in day_iso)}))
        day_plan = PhotonPlan(name=f"{bm.plan.name}-day", beams=beams)
        day_bm = self._save_beam_model(bm, day_plan, geo.geometry_id, f"{REPLAN_PREFIX}{bm.result.beam_model_id}:{key}")
        from ..models.four_d import PhaseDoseRequest
        day_dose = self.four_d.phase_doses(PhaseDoseRequest(beam_model_id=day_bm.beam_model_id, geometry_ids=[geo.geometry_id], engine=request.engine))[0]

        # 4. goals, planned and on the day
        mapped = None
        if request.planned_dose_id:
            planned = self.dose_service.dose_store.get_by_id(request.planned_dose_id)
            if planned is None:
                raise ReplanError(f"dose {request.planned_dose_id!r} not found")
            if planned.geometry_id != planning.geometry_id:
                raise ReplanError(f"the planned dose is on geometry {planned.geometry_id}, not on the planning geometry {planning.geometry_id}")
            mapped = self.registration_service.map_dose(reg.registration_id, request.planned_dose_id, dose_service=self.dose_service)
        goals = self._compare_goals(request, planning.geometry_id, geo.geometry_id, day_dose.dose_id) if request.goals else []

        r = reg.rigid_parameters
        result = ReplanAssessment(
            assessment_id=str(uuid.uuid4()), request=request, registration_id=reg.registration_id, registration_quality=reg.quality,
            day_geometry_id=geo.geometry_id, day_beam_model_id=day_bm.beam_model_id, day_dose_id=day_dose.dose_id,
            mapped_planned_dose_id=mapped.dose_id if mapped is not None else None,
            isocenter_shift_mm=[float(v) for v in np.mean(shifts, axis=0)],
            residual_rotation_deg=[float(r.get("rx_deg", 0.0)), float(r.get("ry_deg", 0.0)), float(r.get("rz_deg", 0.0))],
            goals=goals, cache_key=key, created_at=datetime.now(timezone.utc))
        self.store.save(result)
        logger.info("Replan assessment {}: plan {} on geometry {} (shift {} mm), {} goal(s), {:.0f} s", result.assessment_id, bm.result.beam_model_id,
                    geo.geometry_id, [round(v, 1) for v in result.isocenter_shift_mm], len(goals), time.time() - t0)
        return result

    # ----- steps -------------------------------------------------------------

    def _deformed_density(self, geo, planning, reg):
        """The day's geometry with the planning CT's HU, pulled back through the registration, as its CT and density."""
        from .four_d import read_geometry_volumes, save_derived_geometry
        from .geometry_bundle import load_ct_hu
        from .hu_density import get_model
        from .registration import _grid
        from ..models.geometry import HUDensityModel

        key = hashlib.sha256(f"replan-density|{REPLAN_VERSION}|{geo.cache_key}|{reg.cache_key}".encode("utf-8")).hexdigest()
        cached = self.geometry_service.store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        hu = load_ct_hu(planning)
        if hu is None:
            raise ReplanError(f"the planning geometry {planning.geometry_id} has no CT on disk")
        origin, spacing = _grid(planning)
        day_hu = self.registration_service.map_volume(reg.registration_id, hu.astype(np.float32), origin, spacing, default=-1000.0)
        model = get_model(planning.hu_to_density_model or HUDensityModel.stoichiometric.value)
        _, masks, _, index = read_geometry_volumes(geo)
        return save_derived_geometry(self.geometry_service.store, geo, key, model.convert(day_hu).astype(np.float32), masks,
                                     np.rint(day_hu).astype(np.int16), index,
                                     {"op": "density_from_registration", "registration_id": reg.registration_id,
                                      "geometry_id": planning.geometry_id, "hu_model": planning.hu_to_density_model})

    def _save_beam_model(self, bm, plan, geometry_id: str, cache_key: str):
        from ..models.beam_model import FluenceElementSet, PerBeamElements
        from .beam_model import BeamModelService
        from .beam_persistence import BeamModelPaths

        svc = BeamModelService()
        cached = svc.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            return cached
        bm_id = str(uuid.uuid4())
        per_beam = [PerBeamElements(beam_id=b.beam_id, element_count=b.n_beamlets, active_beamlets=b.n_beamlets) for b in plan.beams]
        result = bm.result.model_copy(update={
            "beam_model_id": bm_id, "geometry_id": geometry_id, "cache_key": cache_key,
            "fluence_elements": FluenceElementSet(total_count=plan.n_beamlets, per_beam=per_beam),
            "beam_model_ref_uri": str(BeamModelPaths.for_id(svc.store.base_dir, bm_id).plan)})
        svc.store.save(beam_model_id=bm_id, cache_key=cache_key, plan=plan, result=result)
        return result

    def _compare_goals(self, request: ReplanAssessRequest, planning_geometry_id: str, day_geometry_id: str, day_dose_id: str) -> List[GoalComparison]:
        from ..models.evaluation import EvaluationRequest
        from .evaluation import EvaluationService

        ev = EvaluationService(dose_service=self.dose_service)
        goals = request.goals
        if request.suffix:
            aliases = dict(goals.structure_aliases)
            names = request.structures or list(self._geometry(planning_geometry_id).structure_index)
            aliases.update({n: n + request.suffix for n in names if n not in aliases})
            day_goals = goals.model_copy(update={"structure_aliases": aliases})
        else:
            day_goals = goals
        target = request.target_structure
        day_target = (target + request.suffix) if target and request.suffix else target
        day = ev.run(EvaluationRequest(dose_id=day_dose_id, geometry_id=day_geometry_id, prescription_gy=request.prescription_gy,
                                       target_structure=day_target, fractions=request.fractions, goals=day_goals))
        planned = None
        if request.planned_dose_id:
            planned = ev.run(EvaluationRequest(dose_id=request.planned_dose_id, geometry_id=planning_geometry_id, prescription_gy=request.prescription_gy,
                                               target_structure=target, fractions=request.fractions, goals=goals))
        by_key = {(g.structure, g.metric, g.op, g.value): g for g in (planned.goals.results if planned and planned.goals else [])}
        out = []
        for g in (day.goals.results if day.goals else []):
            p = by_key.get((g.structure, g.metric, g.op, g.value))
            out.append(GoalComparison(structure=g.structure, metric=g.metric, op=g.op, value=g.value, priority=int(g.priority),
                                      planned=p.achieved if p else None, day=g.achieved, planned_passed=p.passed if p else None, day_passed=g.passed))
        return out


__all__ = ["ReplanError", "ReplanService", "ReplanStore"]
