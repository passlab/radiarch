"""Proton Robust Optimization workflow — extends IMPT with uncertainty scenarios."""

from __future__ import annotations

import os
from typing import Any, Dict

from loguru import logger

from ._helpers import (
    PlannerError,
    build_gantry_angles,
    build_mc_calculator,
    build_objectives,
    compute_dvh,
    export_rtdose,
    find_target_roi,
    load_ct_and_patient,
    setup_calibration,
    setup_sim_dir,
)
from ...models.plan import PlanDetail


def run(plan: PlanDetail) -> Dict[str, Any]:
    """Phase 8C: Robust proton optimization with error scenarios."""
    logger.info("Starting robust proton optimization for plan %s", plan.id)

    from opentps.core.data.plan import ProtonPlanDesign
    from opentps.core.data.plan._robustnessProton import RobustnessProton
    from opentps.core.utils.programSettings import ProgramSettings
    from opentps.core.processing.planOptimization.planOptimization import IntensityModulationOptimizer

    sim_dir = setup_sim_dir(plan.id)
    ps = ProgramSettings()
    ps._config["dir"]["simulationFolder"] = sim_dir

    # 1. Load data
    ct, patient, _ = load_ct_and_patient()
    calibration, _ = setup_calibration()

    # 2. Plan design
    plan_design = ProtonPlanDesign()
    plan_design.calibration = calibration
    plan_design.ct = ct
    plan_design.patient = patient
    plan_design.gantryAngles = build_gantry_angles(plan.beam_count)
    plan_design.spotSpacing = plan.spot_spacing_mm
    plan_design.layerSpacing = plan.layer_spacing_mm

    target_roi = find_target_roi(patient)
    if target_roi:
        plan_design.defineTargetMaskAndPrescription(target_roi, plan.prescription_gy)

    # 3. Robustness configuration
    robustness = RobustnessProton()
    rob_cfg = plan.robustness
    if rob_cfg:
        robustness.setupSystematicErrors = rob_cfg.setup_systematic_error_mm
        robustness.setupRandomErrors = rob_cfg.setup_random_error_mm
        robustness.rangeSystematicError = rob_cfg.range_systematic_error_pct
        robustness.selectionStrategy = rob_cfg.selection_strategy
        robustness.numScenarios = rob_cfg.num_scenarios
    plan_design.robustness = robustness

    logger.info("Building robust plan...")
    proton_plan = plan_design.buildPlan()

    # 4. Robust beamlets
    logger.info("Computing robust scenario beamlets...")
    mc_calc = build_mc_calculator(ct, calibration, nb_primaries=plan.nb_primaries_beamlets)

    rois_for_calc = [target_roi] if target_roi else []
    mc_calc.computeRobustScenarioBeamlets(ct, proton_plan, roi=rois_for_calc)

    # 5. Objectives
    objectives = build_objectives(plan, patient, target_roi)
    proton_plan.planDesign.objectives = objectives

    # 6. Optimize
    logger.info("Running robust optimizer (%s)...", plan.optimization_method)
    solver = IntensityModulationOptimizer(
        plan=proton_plan,
        method=plan.optimization_method,
        maxiter=plan.max_iterations,
    )
    res = solver.optimize()
    logger.info("Robust optimization complete. Success: %s", res.success)

    # 7. Final dose
    mc_calc.nbPrimaries = plan.nb_primaries_final
    dose_image = mc_calc.computeDose(ct, proton_plan)

    rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
    export_rtdose(dose_image, ct, rtdose_path)

    return {
        "engine": "opentps_robust",
        "beamCount": len(proton_plan.planDesign.gantryAngles),
        "maxDose": float(dose_image.imageArray.max()),
        "rtdosePath": rtdose_path,
        "simDir": sim_dir,
        "dvh": compute_dvh(dose_image, target_roi, ct) if target_roi else {},
        "robustness": {
            "scenarios": rob_cfg.num_scenarios if rob_cfg else 5,
            "rangeError": rob_cfg.range_systematic_error_pct if rob_cfg else 5.0,
        },
        "optimization": {
            "success": bool(res.success),
            "iterations": int(res.nit),
            "final_cost": float(res.fun),
        },
    }
