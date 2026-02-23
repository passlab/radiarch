"""Proton IMPT Basic workflow — simple MCsquare dose calculation."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from loguru import logger

from ._helpers import (
    PlannerError,
    build_gantry_angles,
    build_mc_calculator,
    compute_dvh,
    export_rtdose,
    find_target_roi,
    load_ct_and_patient,
    setup_calibration,
    setup_sim_dir,
)
from ...models.plan import PlanDetail


def run(plan: PlanDetail, adapter=None) -> Dict[str, Any]:
    """Run basic proton IMPT dose calculation (no optimization)."""
    logger.info("Initializing basic proton workflow for plan %s", plan.id)

    from opentps.core.data.plan import ProtonPlanDesign
    from opentps.core.utils.programSettings import ProgramSettings

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
    plan_design.gantryAngles = [0.0]
    plan_design.couchAngles = [0.0]

    # Find target
    target_roi = find_target_roi(patient, fallback_to_first=True)
    if target_roi:
        logger.info("Using ROI %s as target", target_roi.name)
        plan_design.defineTargetMaskAndPrescription(target_roi, plan.prescription_gy)
    else:
        logger.warning("No ROI found. Plan building might fail.")

    proton_plan = plan_design.buildPlan()

    # 3. Dose calculation
    logger.info("Running MCsquare dose calculation...")
    mc_calc = build_mc_calculator(ct, calibration, nb_primaries=1e4)
    dose_image = mc_calc.computeDose(ct, proton_plan)

    # 4. Export
    rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
    export_rtdose(dose_image, ct, rtdose_path)
    dvh_data = compute_dvh(dose_image, target_roi, ct) if target_roi else {}

    return {
        "engine": "opentps",
        "patientName": patient.name,
        "beamCount": len(plan_design.gantryAngles),
        "maxDose": float(dose_image.imageArray.max()),
        "meanDose": float(dose_image.imageArray.mean()),
        "simDir": sim_dir,
        "rtdosePath": rtdose_path,
        "dvh": dvh_data,
        "notes": "Success: OpenTPS MCsquare execution",
    }
