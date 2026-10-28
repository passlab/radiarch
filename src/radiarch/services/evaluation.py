"""``EvaluationService`` — the public entry point for Service 6 (Evaluation).

The read-only end of the pipeline: given a computed dose volume (from Service 3
or the final dose of Service 4) and the geometry's structure masks, it produces a
clinician-readable report — per-structure DVHs, target plan-quality indices
(conformity / homogeneity / coverage), and an optional gamma comparison against a
reference dose.

It does no engine or solver work. Geometry loading is delegated to
:class:`DoseService` so the two services agree on bundle shapes; the dose itself
is resolved either from the dose cache (``dose_id``) or a direct ``file://`` URI.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
from loguru import logger

from ..config import get_settings
from ..models.evaluation import (
    DVHBand,
    DVHCurve,
    DVHMetrics,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStage,
    GoalResult,
    GoalsReport,
    NTCPResult,
    RobustIndices,
    RobustStructureMetrics,
    TCPResult,
)
from .dose import DoseService
from .dose_persistence import read_dose_volume
from .dvh import cumulative_dvh, dvh_metrics, dvh_on_bins
from .evaluation_persistence import EvaluationStore
from .gamma import gamma_index
from .indices import dose_indices
from .masks import structure_mask

EvaluationProgressCallback = Callable[[EvaluationStage, float, str], None]


class EvaluationService:
    """Stateless orchestrator. Reused across requests; persistence on disk."""

    def __init__(
        self,
        base_dir: Optional[str | Path] = None,
        dose_service: Optional[DoseService] = None,
    ) -> None:
        if base_dir is None:
            base_dir = Path(get_settings().artifact_dir) / "evaluation"
        self.store = EvaluationStore(base_dir)
        self.dose_service = dose_service or DoseService()

    def run(
        self,
        request: EvaluationRequest,
        progress_callback: Optional[EvaluationProgressCallback] = None,
    ) -> EvaluationResult:
        on_progress = progress_callback or _noop_progress
        t0 = time.monotonic()
        cache_key = request.compute_cache_key()

        cached = self.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            logger.info("Evaluation cache hit {} → {}", cache_key[:10],
                        cached.evaluation_id)
            on_progress(EvaluationStage.done, 1.0, "cache hit")
            return cached

        on_progress(EvaluationStage.loading, 0.05, "Loading dose + geometry")
        dose = self._load_dose(request)
        dose_units = "Gy"
        scenario_doses: Dict[str, np.ndarray] = {}
        if request.dose_id:
            dose_result = self.dose_service.dose_store.get_by_id(request.dose_id)
            if dose_result is not None:
                dose_units = dose_result.dose_units
                if request.include_scenarios and dose_result.scenario_doses:
                    for entry in dose_result.scenario_doses:
                        scenario_doses[entry.scenario_name] = read_dose_volume(Path(entry.dose_grid_uri))
        geometry = self.dose_service._load_geometry(request.geometry_id)
        masks = np.asarray(geometry.masks)
        if dose.shape != masks.shape:
            raise ValueError(
                f"dose shape {dose.shape} != geometry mask shape {masks.shape}"
            )
        index = geometry.result.structure_index
        encoding = getattr(geometry.result, "mask_encoding", "labels")

        def mask_of(name: str) -> np.ndarray:
            return structure_mask(masks, index[name], encoding)
        voxel_volume_cc = float(np.prod(geometry.spacing_mm)) / 1000.0

        # --- DVH per structure ---------------------------------------
        on_progress(EvaluationStage.computing_dvh, 0.25, "Computing DVHs")
        names = request.structures or list(index.keys())
        curves: List[DVHCurve] = []
        for name in names:
            if name not in index:
                raise ValueError(
                    f"structure {name!r} not in geometry (have: {sorted(index)})"
                )
            mask = mask_of(name)
            dose_bins, vol = cumulative_dvh(dose, mask, request.dvh_bins)
            metrics = dvh_metrics(dose, mask, request.prescription_gy, voxel_volume_cc)
            curves.append(DVHCurve(
                structure_name=name,
                dose_bins_gy=[float(x) for x in dose_bins],
                volume_pct=[float(x) for x in vol],
                metrics=metrics,
            ))

        # --- DVH bands and worst-case metrics over the scenarios (R3) ---
        bands: List[DVHBand] = []
        robust_metrics: List[RobustStructureMetrics] = []
        robust_indices = None
        if scenario_doses:
            on_progress(EvaluationStage.computing_dvh, 0.40, f"DVH bands over {len(scenario_doses)} scenarios")
            for name in names:
                mask = mask_of(name)
                top = max([float(dose[mask].max()) if mask.any() else 0.0] +
                          [float(d[mask].max()) if mask.any() else 0.0 for d in scenario_doses.values()])
                bins = np.linspace(0.0, top, request.dvh_bins) if top > 0 else np.zeros(request.dvh_bins)
                nominal_pct = dvh_on_bins(dose, mask, bins)
                curves_pct = np.stack([nominal_pct] + [dvh_on_bins(d, mask, bins) for d in scenario_doses.values()])
                bands.append(DVHBand(
                    structure_name=name, dose_bins_gy=[float(x) for x in bins],
                    nominal_pct=[float(x) for x in nominal_pct],
                    min_pct=[float(x) for x in curves_pct.min(axis=0)], max_pct=[float(x) for x in curves_pct.max(axis=0)],
                    n_scenarios=len(scenario_doses),
                ))
                nominal_m = dvh_metrics(dose, mask, request.prescription_gy, voxel_volume_cc)
                per = {sc: dvh_metrics(d, mask, request.prescription_gy, voxel_volume_cc) for sc, d in scenario_doses.items()}
                robust_metrics.append(RobustStructureMetrics(
                    structure_name=name, nominal=nominal_m,
                    lowest=_envelope([nominal_m] + list(per.values()), min),
                    highest=_envelope([nominal_m] + list(per.values()), max),
                    per_scenario=per,
                ))
            if request.target_structure and request.target_structure in index:
                tgt_mask = mask_of(request.target_structure)
                per_idx = {sc: dose_indices(d, tgt_mask, request.target_structure, request.prescription_gy)
                           for sc, d in scenario_doses.items()}
                per_idx["nominal"] = dose_indices(dose, tgt_mask, request.target_structure, request.prescription_gy)
                per_m = {sc: dvh_metrics(d, tgt_mask, request.prescription_gy, voxel_volume_cc) for sc, d in scenario_doses.items()}
                per_m["nominal"] = dvh_metrics(dose, tgt_mask, request.prescription_gy, voxel_volume_cc)
                worst = min(per_idx, key=lambda k: per_idx[k].coverage_pct)
                robust_indices = RobustIndices(
                    target_structure=request.target_structure, prescription_gy=request.prescription_gy,
                    n_scenarios=len(scenario_doses),
                    worst_coverage_pct=min(i.coverage_pct for i in per_idx.values()),
                    worst_d95_gy=min(m.d95_gy for m in per_m.values()),
                    worst_d98_gy=min(m.d98_gy for m in per_m.values()),
                    worst_d2_gy=max(m.d2_gy for m in per_m.values()),
                    worst_hotspot_gy=max(i.hotspot_gy for i in per_idx.values()),
                    worst_homogeneity_index=max(i.homogeneity_index for i in per_idx.values()),
                    worst_conformity_index=min(i.conformity_index for i in per_idx.values()),
                    worst_scenario=worst,
                )

        # --- clinical goals, NTCP, TCP (R5) ------------------------------
        goals_report = None
        ntcp_results: List[NTCPResult] = []
        tcp_results: List[TCPResult] = []
        if request.goals is not None or request.ntcp or request.tcp:
            on_progress(EvaluationStage.computing_indices, 0.50, "Grading clinical goals")
            goals_report, ntcp_results, tcp_results = self._grade(request, dose, scenario_doses, masks, index, encoding, voxel_volume_cc)

        # --- indices (target) ----------------------------------------
        indices = None
        if request.target_structure:
            on_progress(EvaluationStage.computing_indices, 0.55, "Computing indices")
            if request.target_structure not in index:
                raise ValueError(
                    f"target_structure {request.target_structure!r} not in geometry"
                )
            tgt_mask = mask_of(request.target_structure)
            indices = dose_indices(dose, tgt_mask, request.target_structure,
                                   request.prescription_gy)

        # --- gamma (optional) ----------------------------------------
        gamma = None
        if request.gamma is not None:
            on_progress(EvaluationStage.computing_gamma, 0.70, "Computing gamma")
            reference = self._load_reference_dose(request.gamma)
            # spacing_mm is (sx, sy, sz); dose arrays are (nz, ny, nx).
            sx, sy, sz = geometry.spacing_mm
            gamma = gamma_index(
                dose, reference, spacing_mm=(sz, sy, sx),
                dose_percent=request.gamma.dose_percent,
                distance_mm=request.gamma.distance_mm,
                threshold_pct=request.gamma.threshold_pct,
                local=request.gamma.local,
            )

        # --- persist -------------------------------------------------
        on_progress(EvaluationStage.persisting, 0.92, "Writing report")
        evaluation_id = str(uuid.uuid4())
        result = EvaluationResult(
            evaluation_id=evaluation_id,
            cache_key=cache_key,
            dvh_curves=curves,
            indices=indices,
            gamma=gamma,
            dvh_bands=bands,
            robust_metrics=robust_metrics,
            robust_indices=robust_indices,
            n_scenarios=len(scenario_doses),
            dose_units=dose_units,
            goals=goals_report,
            ntcp=ntcp_results,
            tcp=tcp_results,
            dose_id=request.dose_id,
            geometry_id=request.geometry_id,
            compute_time_s=round(time.monotonic() - t0, 4),
        )
        self.store.save(evaluation_id=evaluation_id, cache_key=cache_key,
                        result=result)
        on_progress(EvaluationStage.done, 1.0, f"evaluation_id={evaluation_id}")
        logger.info("Evaluation {} done: {} DVH curves, indices={}, gamma={}",
                    evaluation_id, len(curves), indices is not None,
                    gamma is not None)
        return result

    # -----------------------------------------------------------------
    # Clinical goals and radiobiology (R5)
    # -----------------------------------------------------------------

    def _grade(self, request: EvaluationRequest, dose: np.ndarray, scenario_doses: Dict[str, np.ndarray],
               masks: np.ndarray, index: Dict[str, int], encoding: str, voxel_volume_cc: float):
        from .clinical_goals import evaluate_goal, load_template, resolve_structure
        from .radiobiology import NTCP_MODELS, TCP_MODELS, default_alpha_beta, eqd2, lkb_ntcp, poisson_tcp

        available = list(index.keys())
        ntcp_results: List[NTCPResult] = []
        tcp_results: List[TCPResult] = []

        def doses_of(name: str, volume: np.ndarray) -> np.ndarray:
            return np.asarray(volume, dtype=np.float64)[structure_mask(masks, index[name], encoding)]

        def eqd2_of(name: str, volume: np.ndarray, alpha_beta: float) -> np.ndarray:
            if request.fractions is None:
                raise ValueError("EQD2 goals and models need the plan's fractions (request.fractions)")
            return eqd2(doses_of(name, volume), request.fractions, alpha_beta)

        goals_report = None
        if request.goals is not None:
            spec = request.goals
            template = load_template(spec.template_id) if spec.template_id else None
            goals = list(template.goals) if template else []
            goals += list(spec.goals)
            aliases = dict(template.aliases) if template else {}
            basis = spec.dose_basis or (template.dose_basis if template else "physical")
            prescription = request.prescription_gy
            results: List[GoalResult] = []
            for goal in goals:
                resolved = resolve_structure(goal.structure, available, aliases, spec.structure_aliases)
                if resolved is None:
                    results.append(GoalResult(structure=goal.structure, metric=goal.metric, op=goal.op, value=goal.value,
                                              priority=goal.priority, note=goal.note, source=goal.source or (template.source if template else ""),
                                              missing=True, passed=None if spec.skip_missing else False))
                    continue
                if basis == "EQD2":
                    ab = spec.alpha_beta_gy.get(resolved, spec.alpha_beta_gy.get(goal.structure, default_alpha_beta(resolved)))
                    nominal = eqd2_of(resolved, dose, ab)
                    scen = {k: eqd2_of(resolved, v, ab) for k, v in scenario_doses.items()}
                else:
                    nominal = doses_of(resolved, dose)
                    scen = {k: doses_of(resolved, v) for k, v in scenario_doses.items()}
                r = evaluate_goal(goal, nominal, voxel_volume_cc, prescription, scen or None, resolved)
                if not r.source and template is not None:
                    r.source = template.source
                results.append(r)
            evaluable = [r for r in results if not r.missing]
            passed_by = {p: sum(1 for r in evaluable if r.priority == p and r.passed) for p in (1, 2, 3)}
            failed_by = {p: sum(1 for r in evaluable if r.priority == p and not r.passed) for p in (1, 2, 3)}
            goals_report = GoalsReport(
                template_id=spec.template_id, dose_basis=basis, fractions=request.fractions,
                n_goals=len(results), n_passed=sum(1 for r in evaluable if r.passed), n_failed=sum(1 for r in evaluable if not r.passed),
                n_missing=sum(1 for r in results if r.missing),
                passed_by_priority=passed_by, failed_by_priority=failed_by,
                all_priority1_passed=all(r.passed for r in evaluable if r.priority == 1),
                robust_all_passed=(all(r.passed_all_scenarios for r in evaluable) if scenario_doses and evaluable else None),
                results=results,
            )

        for spec in request.ntcp:
            params = spec.parameters or NTCP_MODELS.get(spec.model_id or "")
            if params is None:
                raise ValueError(f"unknown NTCP model {spec.model_id!r}; built-in: {sorted(NTCP_MODELS)}")
            name = resolve_structure(spec.structure or params.structure, available, {})
            if name is None:
                raise ValueError(f"NTCP {params.model_id}: structure {spec.structure or params.structure!r} not in the geometry ({available})")
            use_eqd2 = request.fractions is not None
            nominal = eqd2_of(name, dose, params.alpha_beta_gy) if use_eqd2 else doses_of(name, dose)
            r = lkb_ntcp(nominal, params.td50_gy, params.m, params.n)
            per = {}
            for k, v in scenario_doses.items():
                sd = eqd2_of(name, v, params.alpha_beta_gy) if use_eqd2 else doses_of(name, v)
                per[k] = lkb_ntcp(sd, params.td50_gy, params.m, params.n)["ntcp"]
            ntcp_results.append(NTCPResult(model_id=params.model_id, structure=name, endpoint=params.endpoint, parameters=params,
                                           geud_gy=r["geud_gy"], ntcp=r["ntcp"], eqd2_applied=use_eqd2,
                                           worst_case_ntcp=max([r["ntcp"]] + list(per.values())) if per else None, per_scenario=per))

        for spec in request.tcp:
            params = spec.parameters or TCP_MODELS.get(spec.model_id or "")
            if params is None:
                raise ValueError(f"unknown TCP model {spec.model_id!r}; built-in: {sorted(TCP_MODELS)}")
            name = resolve_structure(spec.structure or request.target_structure or params.structure, available, {})
            if name is None:
                raise ValueError(f"TCP {params.model_id}: structure {spec.structure or params.structure!r} not in the geometry ({available})")
            use_eqd2 = request.fractions is not None
            nominal = eqd2_of(name, dose, params.alpha_beta_gy) if use_eqd2 else doses_of(name, dose)
            r = poisson_tcp(nominal, params.d50_gy, params.gamma50)
            per = {}
            for k, v in scenario_doses.items():
                sd = eqd2_of(name, v, params.alpha_beta_gy) if use_eqd2 else doses_of(name, v)
                per[k] = poisson_tcp(sd, params.d50_gy, params.gamma50)["tcp"]
            tcp_results.append(TCPResult(model_id=params.model_id, structure=name, endpoint=params.endpoint, parameters=params,
                                         eud_gy=r["eud_gy"], tcp=r["tcp"], eqd2_applied=use_eqd2,
                                         worst_case_tcp=min([r["tcp"]] + list(per.values())) if per else None, per_scenario=per))
        return goals_report, ntcp_results, tcp_results

    # -----------------------------------------------------------------
    # Dose loading
    # -----------------------------------------------------------------

    def _load_dose(self, request: EvaluationRequest) -> np.ndarray:
        if request.dose_id:
            result = self.dose_service.dose_store.get_by_id(request.dose_id)
            if result is None:
                raise ValueError(f"dose_id {request.dose_id!r} not found")
            return read_dose_volume(Path(result.dose_grid_uri))
        return self._read_uri(request.dose_ref_uri)

    def _load_reference_dose(self, gamma_spec) -> np.ndarray:
        if gamma_spec.reference_dose_id:
            result = self.dose_service.dose_store.get_by_id(gamma_spec.reference_dose_id)
            if result is None:
                raise ValueError(
                    f"reference_dose_id {gamma_spec.reference_dose_id!r} not found"
                )
            return read_dose_volume(Path(result.dose_grid_uri))
        return self._read_uri(gamma_spec.reference_dose_uri)

    @staticmethod
    def _read_uri(uri: Optional[str]) -> np.ndarray:
        if not uri:
            raise ValueError("missing dose URI")
        path = uri[len("file://"):] if uri.startswith("file://") else uri
        if "://" in path:
            raise ValueError(f"unsupported dose URI scheme: {uri!r} (file:// only)")
        return read_dose_volume(Path(path))


def _envelope(metrics: List[DVHMetrics], pick) -> DVHMetrics:
    """Per-field ``min`` or ``max`` over a list of DVH metrics."""
    fields = {name: pick(getattr(m, name) for m in metrics) for name in DVHMetrics.model_fields}
    return DVHMetrics(**fields)


def _noop_progress(stage: EvaluationStage, fraction: float, message: str) -> None:
    del stage, fraction, message


__all__ = ["EvaluationService", "EvaluationProgressCallback"]
