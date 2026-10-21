"""Proton IMPT optimized workflow — influence matrix, inverse optimization, final MCsquare dose."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from loguru import logger

from ._helpers import (
    build_beam_model, build_geometry, build_objectives, compute_dvh, ct_provenance, dose_image, dose_summary,
    export_rtdose, mcsquare_engine, read_dose, read_masks, setup_sim_dir, solver_method, target_of,
)
from ...models.beam_model import Modality
from ...models.common import RESEARCH_USE_ONLY
from ...models.dose import DoseComputeRequest, ScenarioSetSpec, WeightVector
from ...models.optimization import OptimizationRunRequest, RobustnessSpec, SolverConfig
from ...models.plan import PlanDetail


def optimize_and_compute(plan: PlanDetail, robustness: Optional[RobustnessSpec] = None,
                         scenarios: Optional[ScenarioSetSpec] = None) -> Dict[str, Any]:
    """The shared pipeline of the optimized and robust workflows."""
    from ...services.dose import DoseService
    from ...services.optimization import OptimizationService

    sim_dir = setup_sim_dir(plan.id)
    geometry = build_geometry(plan)
    target_name, target_label = target_of(geometry)
    beam_model = build_beam_model(plan, geometry, Modality.proton_pbs)
    n = beam_model.fluence_elements.total_count
    if n < 1:
        raise RuntimeError("the beam model has no spots")

    method = solver_method(plan.optimization_method)
    logger.info("Optimizing %d spots with %s (%d iterations max)...", n, method, plan.max_iterations)
    request = OptimizationRunRequest(
        plan_id=plan.id, geometry_id=geometry.geometry_id, beam_model_id=beam_model.beam_model_id,
        dose_engine=mcsquare_engine(plan.nb_primaries_beamlets),
        objectives=build_objectives(plan, geometry, target_name),
        solver=SolverConfig(method=method, max_iterations=int(plan.max_iterations)),
        robustness=robustness or RobustnessSpec(),
    )
    opt = OptimizationService().run(request)
    logger.info("Optimization complete. Success: %s, cost %.4g", opt.convergence.success, opt.convergence.final_cost)

    logger.info("Computing final dose (%g primaries)...", plan.nb_primaries_final)
    dose_result = DoseService().compute_dose(DoseComputeRequest(
        plan_id=plan.id, geometry_id=geometry.geometry_id, beam_model_id=beam_model.beam_model_id,
        engine=mcsquare_engine(plan.nb_primaries_final),
        weights=WeightVector(length=n, weights_uri=opt.weights_ref_uri), scenarios=scenarios,
    ))
    dose = read_dose(dose_result.dose_grid_uri)
    rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
    export_rtdose(dose_image(dose, geometry), ct_provenance(geometry), rtdose_path)
    masks = read_masks(geometry)

    summary: Dict[str, Any] = {
        "engineVersion": dose_result.engine_version,
        "intended_use": RESEARCH_USE_ONLY,
        "beamCount": len(beam_model.fluence_elements.per_beam),
        "spots": n,
        "geometryId": geometry.geometry_id,
        "beamModelId": beam_model.beam_model_id,
        "optimizationId": opt.optimization_id,
        "doseId": dose_result.dose_id,
        **dose_summary(dose),
        "rtdosePath": rtdose_path,
        "simDir": sim_dir,
        "dvh": compute_dvh(dose, masks == target_label, target_name),
        "optimization": {
            "success": bool(opt.convergence.success),
            "iterations": int(opt.convergence.iterations),
            "final_cost": float(opt.convergence.final_cost),
            "solver_method": method,
        },
    }
    if dose_result.scenario_doses:
        summary["scenarioDoses"] = [
            {"name": s.scenario_name, "maxDose": s.statistics.max_gy, "meanDose": s.statistics.mean_gy}
            for s in dose_result.scenario_doses
        ]
    if opt.robust_stats is not None:
        summary["robustStats"] = opt.robust_stats.model_dump()
    return summary


def run(plan: PlanDetail) -> Dict[str, Any]:
    logger.info("Starting IMPT optimization for plan %s", plan.id)
    summary = optimize_and_compute(plan)
    summary["engine"] = "mcsquare_optimized"
    return summary
