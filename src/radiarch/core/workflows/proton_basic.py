"""Proton IMPT basic workflow — spots on the target, unit metersets, one MCsquare dose."""

from __future__ import annotations

import os
from typing import Any, Dict

from loguru import logger

from ._helpers import (
    build_beam_model, build_geometry, compute_dvh, ct_provenance, dose_image, dose_summary, export_rtdose,
    mcsquare_engine, read_dose, read_masks, setup_sim_dir, target_of,
)
from ...models.beam_model import Modality
from ...models.common import RESEARCH_USE_ONLY
from ...models.dose import DoseComputeRequest, WeightVector
from ...models.plan import PlanDetail

BASIC_PRIMARIES = 1e4


def run(plan: PlanDetail, adapter=None) -> Dict[str, Any]:
    """Geometry → proton beam model → MCsquare dose with 1 MU per spot (no optimization)."""
    from ...services.dose import DoseService

    logger.info("Initializing basic proton workflow for plan %s", plan.id)
    sim_dir = setup_sim_dir(plan.id)

    geometry = build_geometry(plan)
    target_name, target_label = target_of(geometry)
    beam_model = build_beam_model(plan, geometry, Modality.proton_pbs)
    n = beam_model.fluence_elements.total_count
    if n < 1:
        raise RuntimeError("the beam model has no spots")

    logger.info("Running MCsquare dose calculation (%d spots, %g primaries)...", n, BASIC_PRIMARIES)
    dose_result = DoseService().compute_dose(DoseComputeRequest(
        plan_id=plan.id, geometry_id=geometry.geometry_id, beam_model_id=beam_model.beam_model_id,
        engine=mcsquare_engine(BASIC_PRIMARIES), weights=WeightVector(length=n, values=[1.0] * n),
    ))
    dose = read_dose(dose_result.dose_grid_uri)

    rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
    export_rtdose(dose_image(dose, geometry), ct_provenance(geometry), rtdose_path)
    masks = read_masks(geometry)

    return {
        "engine": "mcsquare",
        "engineVersion": dose_result.engine_version,
        "intended_use": RESEARCH_USE_ONLY,
        "patientName": geometry.ct_metadata.patient_name,
        "beamCount": len(beam_model.fluence_elements.per_beam),
        "spots": n,
        "geometryId": geometry.geometry_id,
        "beamModelId": beam_model.beam_model_id,
        "doseId": dose_result.dose_id,
        **dose_summary(dose),
        "simDir": sim_dir,
        "rtdosePath": rtdose_path,
        "dvh": compute_dvh(dose, masks == target_label, target_name),
        "notes": "Success: MCsquare dose through radiarch's driver",
    }
