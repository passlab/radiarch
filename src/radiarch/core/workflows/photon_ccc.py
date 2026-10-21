"""Photon CCC Dose Computation workflow — collapsed-cone convolution dose engine."""

from __future__ import annotations

import os
from typing import Any, Dict

from loguru import logger

from ._helpers import (
    PlannerError,
    compute_dvh,
    export_rtdose,
    find_target_roi,
    load_ct_and_patient,
    setup_calibration,
    setup_sim_dir,
)
from ...models.plan import PlanDetail


def run(plan: PlanDetail) -> Dict[str, Any]:
    """Phase 8B: Photon CCC dose computation."""
    logger.info("Starting Photon CCC workflow for plan %s", plan.id)

    from opentps.core.processing.doseCalculation.photons.cccDoseCalculator import CCCDoseCalculator
    sim_dir = setup_sim_dir(plan.id)

    # 1. Load CT
    ct, patient, _ = load_ct_and_patient()
    calibration, _ = setup_calibration()

    # 2. Build photon plan: equally spaced gantry angles, one open field each
    from ...services.photon_beamlets import build_photon_plan

    beam_count = plan.beam_count
    jaw = (float(plan.jaw_opening_mm[0]), float(plan.jaw_opening_mm[1]))
    photon_plan = build_photon_plan(
        beams=[(i * (360.0 / beam_count), 0.0) for i in range(beam_count)],
        jaw_x_mm=jaw,
        jaw_y_mm=jaw,
        leaf_width_mm=plan.mlc_leaf_width_mm,
        mu_per_beam=plan.mu_per_beam,
        name=f"photon-ccc-{plan.id}",
    )

    # 3. CCC dose
    logger.info("Running CCC dose calculation...")
    ccc = CCCDoseCalculator()
    ccc.ctCalibration = calibration
    dose_image = ccc.computeDose(ct, photon_plan)

    # 4. Export
    rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
    export_rtdose(dose_image, ct, rtdose_path)

    target_roi = find_target_roi(patient)

    return {
        "engine": "opentps_photon_ccc",
        "beamCount": beam_count,
        "maxDose": float(dose_image.imageArray.max()),
        "meanDose": float(dose_image.imageArray.mean()),
        "rtdosePath": rtdose_path,
        "simDir": sim_dir,
        "dvh": compute_dvh(dose_image, target_roi, ct) if target_roi else {},
    }
