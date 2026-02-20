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
    from opentps.core.data.plan._photonPlan import PhotonPlan
    from opentps.core.data.plan._planPhotonBeam import PlanPhotonBeam
    from opentps.core.data.plan._planPhotonSegment import PlanPhotonSegment

    sim_dir = setup_sim_dir(plan.id)

    # 1. Load CT
    ct, patient, _ = load_ct_and_patient()
    calibration, _ = setup_calibration()

    # 2. Build photon plan
    photon_plan = PhotonPlan()
    beam_count = plan.beam_count
    for i in range(beam_count):
        gantry = i * (360.0 / beam_count)
        beam = PlanPhotonBeam()
        beam.gantryAngle = gantry
        beam.couchAngle = 0.0
        segment = PlanPhotonSegment()
        segment.monitorUnits = plan.mu_per_beam
        segment.jawOpeningMM = plan.jaw_opening_mm
        beam.segments = [segment]
        photon_plan.beams.append(beam)

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
