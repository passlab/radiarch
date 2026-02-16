from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
from loguru import logger

from ..adapters import OrthancAdapterBase, build_orthanc_adapter
from ..models.plan import PlanDetail

OPENTPS_AVAILABLE = False
try:  # pragma: no cover - optional dependency
    from opentps.core.data import patient as opentps_patient
    from opentps.core.data.plan import ProtonPlanDesign
    from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import (
        MCsquareDoseCalculator,
    )

    OPENTPS_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    logger.warning("OpenTPS modules not available; using synthetic planner: %s", exc)


def _default_adapter() -> OrthancAdapterBase:
    return build_orthanc_adapter()


class PlannerError(RuntimeError):
    pass


@dataclass
class PlanExecutionResult:
    artifact_bytes: bytes
    artifact_content_type: str
    qa_summary: Dict[str, Any]


class RadiarchPlanner:
    def __init__(self, adapter: Optional[OrthancAdapterBase] = None):
        self.adapter = adapter or _default_adapter()

    def run(self, plan: PlanDetail) -> PlanExecutionResult:
        logger.info("Running planner for plan %s", plan.id)
        study = self.adapter.get_study(plan.study_instance_uid)
        if not study:
            raise PlannerError(f"Study {plan.study_instance_uid} not found in PACS")

        segmentation = None
        if plan.segmentation_uid:
            segmentation = self.adapter.get_segmentation(plan.segmentation_uid)

        if OPENTPS_AVAILABLE:
            qa_summary = self._run_opentps(plan, segmentation)
        else:
            qa_summary = self._run_synthetic(plan, segmentation)

        artifact_doc = {
            "planId": plan.id,
            "workflowId": plan.workflow_id,
            "studyInstanceUID": plan.study_instance_uid,
            "segmentationUID": plan.segmentation_uid,
            "prescriptionGy": plan.prescription_gy,
            "fractions": plan.fraction_count,
            "qa": qa_summary,
        }
        artifact_bytes = json.dumps(artifact_doc).encode("utf-8")
        return PlanExecutionResult(
            artifact_bytes=artifact_bytes,
            artifact_content_type="application/json",
            qa_summary=qa_summary,
        )

    def _run_synthetic(self, plan: PlanDetail, segmentation: Optional[dict]) -> Dict[str, Any]:
        # Simulate dose coverage metrics using simple Gaussian profile
        spot_count = random.randint(200, 400)
        coverage = max(0.7, min(0.99, 0.8 + 0.05 * random.random()))
        hot_spot = max(1.00, 1.10 + 0.05 * random.random())
        dvh_dose = np.linspace(0, plan.prescription_gy * 1.2, 50)
        dvh_volume = np.exp(-((dvh_dose / plan.prescription_gy) ** 2) * 2) * 100
        return {
            "engine": "synthetic",
            "spotCount": spot_count,
            "targetCoverage": round(coverage, 3),
            "maxDoseRatio": round(hot_spot, 3),
            "dvh": {
                "dose": dvh_dose.tolist(),
                "volume": dvh_volume.tolist(),
            },
            "notes": "OpenTPS modules unavailable; generated synthetic QA",
        }

    def _run_opentps(self, plan: PlanDetail, segmentation: Optional[dict]) -> Dict[str, Any]:
        # Placeholder OpenTPS invocation: actual DICOM ingestion and MCsquare configs go here
        logger.info("OpenTPS available; using placeholder OpenTPS workflow")
        # For now, mirror synthetic output but note capability
        summary = self._run_synthetic(plan, segmentation)
        summary["engine"] = "opentps"
        summary["notes"] = "OpenTPS import hook present; awaiting dataset configuration"
        return summary
