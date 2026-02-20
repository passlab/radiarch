"""RadiarchPlanner — thin orchestrator that delegates to per-workflow modules.

Responsibilities:
  1. Build the dispatch table (`run`)
  2. Handle synthetic fallback (`_dispatch_workflow`)
  3. Package artifacts (`_package_result`)
  4. Provide the synthetic QA fallback (`_run_synthetic`)

All real OpenTPS logic lives in ``core.workflows.*`` modules.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
from loguru import logger

from ..adapters import OrthancAdapterBase, build_orthanc_adapter
from ..config import get_settings
from ..models.plan import PlanDetail
from .workflows import RUNNERS
from .workflows._helpers import PlannerError

# Ensure settings are loaded (and sys.path updated) before first use
_ = get_settings()


def _default_adapter() -> OrthancAdapterBase:
    return build_orthanc_adapter()


@dataclass
class PlanExecutionResult:
    artifact_bytes: bytes
    artifact_content_type: str
    qa_summary: Dict[str, Any]
    artifact_path: Optional[str] = None


class RadiarchPlanner:
    def __init__(self, adapter: Optional[OrthancAdapterBase] = None, force_synthetic: bool = False):
        self.adapter = adapter or _default_adapter()
        self._force_synthetic = force_synthetic or os.environ.get(
            "RADIARCH_FORCE_SYNTHETIC", ""
        ).lower() in ("1", "true", "yes")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, plan: PlanDetail) -> PlanExecutionResult:
        logger.info("Running planner for plan %s (Workflow: %s)", plan.id, plan.workflow_id)

        wf_id = plan.workflow_id.value if hasattr(plan.workflow_id, "value") else str(plan.workflow_id)
        runner = RUNNERS.get(wf_id)
        if not runner:
            raise PlannerError(f"Unknown workflow: {wf_id}")
        return self._dispatch_workflow(plan, runner)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _dispatch_workflow(self, plan: PlanDetail, runner) -> PlanExecutionResult:
        """Try the real runner; fall back to synthetic if OpenTPS is missing."""
        wf_id = plan.workflow_id
        wf_label = wf_id.value if hasattr(wf_id, "value") else str(wf_id)

        if self._force_synthetic:
            logger.info("force_synthetic enabled — skipping %s", wf_label)
            qa_summary = self._run_synthetic(plan, None)
            qa_summary["notes"] = f"Synthetic result ({wf_label} skipped)"
        else:
            try:
                import opentps  # noqa: F401 – availability check
                qa_summary = runner(plan)
            except ImportError:
                logger.warning("OpenTPS not found; falling back to synthetic for %s", wf_label)
                qa_summary = self._run_synthetic(plan, None)
                qa_summary["notes"] = f"OpenTPS missing ({wf_label} skipped)"

        return self._package_result(plan, qa_summary)

    def _package_result(self, plan: PlanDetail, qa_summary: dict) -> PlanExecutionResult:
        """JSON artifact + disk persistence."""
        wf_id = plan.workflow_id.value if hasattr(plan.workflow_id, "value") else str(plan.workflow_id)
        artifact_doc = {
            "planId": plan.id,
            "workflowId": wf_id,
            "studyInstanceUID": plan.study_instance_uid,
            "segmentationUID": plan.segmentation_uid,
            "prescriptionGy": plan.prescription_gy,
            "fractions": plan.fraction_count,
            "qa": qa_summary,
        }
        artifact_bytes = json.dumps(artifact_doc, indent=2).encode("utf-8")

        settings = get_settings()
        summary_dir = os.path.join(settings.artifact_dir, "summaries")
        os.makedirs(summary_dir, exist_ok=True)
        summary_path = os.path.join(summary_dir, f"{plan.id}.json")
        with open(summary_path, "wb") as f:
            f.write(artifact_bytes)

        return PlanExecutionResult(
            artifact_bytes=artifact_bytes,
            artifact_content_type="application/json",
            qa_summary=qa_summary,
            artifact_path=summary_path,
        )

    @staticmethod
    def _run_synthetic(plan: PlanDetail, segmentation: Optional[dict]) -> Dict[str, Any]:
        beam_count = getattr(plan, "beam_count", 1) or 1
        spot_count = random.randint(200, 400) * beam_count
        coverage = max(0.7, min(0.99, 0.8 + 0.05 * random.random()))
        hot_spot = max(1.00, 1.10 + 0.05 * random.random())
        dvh_dose = np.linspace(0, plan.prescription_gy * 1.2, 50)
        dvh_volume = np.exp(-((dvh_dose / plan.prescription_gy) ** 2) * 2) * 100
        gantry_angles = [round(i * (360.0 / beam_count), 1) for i in range(beam_count)]

        return {
            "engine": "synthetic",
            "beamCount": beam_count,
            "gantryAngles": gantry_angles,
            "spotCount": spot_count,
            "targetCoverage": round(coverage, 3),
            "maxDoseRatio": round(hot_spot, 3),
            "dvh": {
                "dose": dvh_dose.tolist(),
                "volume": dvh_volume.tolist(),
            },
            "notes": "OpenTPS modules unavailable; generated synthetic QA",
        }
