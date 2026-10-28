"""``ApertureService`` (roadmap R4): an optimization → a deliverable step-and-shoot plan.

Takes the weights of a photon optimization, sequences them on a machine
(:mod:`radiarch.services.sequencing`), re-optimizes the segment metersets
against the optimization's objectives, and persists the aperture plan as a
new beam model plus the dose of its segments as a dose result, so the usual
evaluation and the RT writer (R6) consume them like any other.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from loguru import logger
from scipy.sparse import csr_matrix

from ..config import get_settings
from ..models.apertures import BeamDeliverabilityReport, SequenceRequest, SequenceResult
from ..models.beam_model import BeamModelResult, FluenceElementSet, Modality, PerBeamElements
from ..models.dose import DoseResult, DoseStatistics, EngineSpec, InfluenceBuildRequest, dose_units_for
from ..models.optimization import OptimizationResult
from ..models.photon_plan import PhotonPlan
from .beam_model import BeamModelService
from .dose import DoseService, _summary_stats
from .dose_persistence import DOSE_FILENAME
from .machine_model import PhotonMachineModel
from .optimization import OptimizationService
from .sequencing import sequence_plan


class ApertureStore:
    """``{artifact_dir}/apertures/{sequence_id}/meta.json`` with a cache index, like the other stores."""

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

    def lookup_by_cache_key(self, key: str) -> Optional[SequenceResult]:
        sid = self._load_index().get(key)
        return self.get_by_id(sid) if sid else None

    def get_by_id(self, sequence_id: str) -> Optional[SequenceResult]:
        meta = self.base_dir / sequence_id / "meta.json"
        if not meta.is_file():
            return None
        try:
            return SequenceResult.model_validate_json(meta.read_text())
        except Exception:
            return None

    def save(self, result: SequenceResult, segment_mu: np.ndarray) -> None:
        root = self.base_dir / result.sequence_id
        root.mkdir(parents=True, exist_ok=True)
        np.save(root / "segment_mu.npy", np.asarray(segment_mu, dtype=np.float64))
        tmp = root / "meta.json.tmp"
        tmp.write_text(result.model_dump_json(indent=2))
        os.replace(tmp, root / "meta.json")
        index = self._load_index()
        index[result.cache_key] = result.sequence_id
        tmp_i = self._index.with_suffix(".json.tmp")
        tmp_i.write_text(json.dumps(index, indent=2, sort_keys=True))
        os.replace(tmp_i, self._index)

    def list_ids(self):
        return sorted(p.name for p in self.base_dir.iterdir() if (p / "meta.json").is_file())


class ApertureService:
    def __init__(self, base_dir: Optional[Path] = None, dose_service: Optional[DoseService] = None,
                 optimization_service: Optional[OptimizationService] = None,
                 beam_model_service: Optional[BeamModelService] = None) -> None:
        settings = get_settings()
        self.store = ApertureStore(Path(base_dir) if base_dir else Path(settings.artifact_dir) / "apertures")
        self.dose_service = dose_service or DoseService()
        self.optimization_service = optimization_service or OptimizationService(dose_service=self.dose_service)
        self.beam_model_service = beam_model_service or BeamModelService()

    def sequence(self, optimization_id: str, request: SequenceRequest) -> SequenceResult:
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
            raise ValueError("sequencing applies to photon beam models; proton plans deliver their spots directly")
        plan = beam_model.plan
        if not isinstance(plan, PhotonPlan):
            raise ValueError("the beam model holds no PhotonPlan")
        if weights.shape[0] != plan.n_beamlets:
            raise ValueError(f"optimization has {weights.shape[0]} weights, the plan {plan.n_beamlets} beamlets")
        machine_id = request.machine_model_id or beam_model.result.machine_model_id or "default"
        machine = PhotonMachineModel.from_id(machine_id).spec

        # the open-field Dij the optimization used (from the influence cache when the engine matches)
        engine = EngineSpec(name=opt.engine_name)
        inf_result = self.dose_service.build_influence(InfluenceBuildRequest(
            plan_id=request.plan_id, geometry_id=opt.geometry_id, beam_model_id=opt.beam_model_id, engine=engine, rbe=opt.rbe_factor,
        ))
        inf = self.dose_service.influence_store.load_influence(inf_result.influence_id)
        dij = csr_matrix((inf.data, inf.indices, inf.indptr), shape=(inf.n_voxels, inf.n_elements))
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

        res = sequence_plan(plan, weights, dij, grid_shape, cost_terms, machine, levels=request.levels,
                            method=request.solver_method, max_iterations=request.max_iterations,
                            energy_mv=request.energy_mv, name=f"{plan.name}-{machine.machine_id}")

        # the aperture plan as a beam model of its own
        sequence_id = str(uuid.uuid4())
        bm_id = str(uuid.uuid4())
        from .beam_persistence import BeamModelPaths
        bm_paths = BeamModelPaths.for_id(self.beam_model_service.store.base_dir, bm_id)
        per_beam = [PerBeamElements(beam_id=b.beam_id, element_count=b.n_beamlets, active_beamlets=b.n_beamlets) for b in res.plan.beams]
        bm_result = BeamModelResult(
            beam_model_id=bm_id, geometry_id=opt.geometry_id, modality=Modality.photon_imrt,
            fluence_elements=FluenceElementSet(total_count=res.plan.n_beamlets, per_beam=per_beam),
            beam_model_ref_uri=str(bm_paths.plan), machine_model_id=machine.machine_id, cache_key=f"apertures:{sequence_id}",
        )
        self.beam_model_service.store.save(beam_model_id=bm_id, cache_key=bm_result.cache_key, plan=res.plan, result=bm_result)

        # the segment dose as a dose result
        dose_id = str(uuid.uuid4())
        dose_root = self.dose_service.dose_store.base_dir / dose_id
        dose_result = DoseResult(
            dose_id=dose_id, plan_id=request.plan_id, geometry_id=opt.geometry_id, beam_model_id=bm_id,
            modality=Modality.photon_imrt, engine_name=f"{opt.engine_name}+segments", engine_version=opt.engine_version,
            dose_grid_uri=str(dose_root / DOSE_FILENAME), statistics=_summary_stats(res.dose),
            rbe_factor=opt.rbe_factor, dose_units=dose_units_for(opt.rbe_factor), cache_key=f"apertures:{sequence_id}",
        )
        self.dose_service.dose_store.save(dose_id=dose_id, cache_key=dose_result.cache_key, nominal_dose=res.dose,
                                          spacing_mm=geometry.spacing_mm, scenario_doses=None, result=dose_result)

        reports = [BeamDeliverabilityReport(**r.__dict__) for r in res.deliverability]
        result = SequenceResult(
            sequence_id=sequence_id, cache_key=cache_key, optimization_id=optimization_id, geometry_id=opt.geometry_id,
            source_beam_model_id=opt.beam_model_id, beam_model_id=bm_id, dose_id=dose_id, machine_model_id=machine.machine_id,
            n_segments=int(res.segment_mu.shape[0]), total_mu=float(res.segment_mu.sum()),
            segment_mu=[float(v) for v in res.segment_mu],
            segments_per_beam={b.beam_id: len(b.segments) for b in res.plan.beams},
            levels=res.n_levels, dropped_segments=res.dropped_segments, convergence=res.convergence,
            deliverability=reports, deliverable=not any(r.issues for r in reports),
            dose_units=dose_units_for(opt.rbe_factor), plan_id=request.plan_id,
        )
        self.store.save(result, res.segment_mu)
        logger.info("Sequenced optimization {} on {}: {} segments, {:.1f} MU, deliverable={}",
                    optimization_id, machine.machine_id, result.n_segments, result.total_mu, result.deliverable)
        return result


__all__ = ["ApertureStore", "ApertureService"]
