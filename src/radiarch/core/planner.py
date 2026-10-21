"""RadiarchPlanner — thin orchestrator that delegates to per-workflow modules.

Responsibilities:
  1. Build the dispatch table (`run`)
  2. Run the workflow (`_dispatch_workflow`)
  3. Package artifacts (`_package_result`)

The workflows in ``core.workflows.*`` run on the services (geometry, beam
model, dose, optimization). There is no synthetic fallback: a plan either
runs the real engine or its job fails.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger

from ..adapters import OrthancAdapterBase, build_orthanc_adapter
from ..config import get_settings
from ..models.common import RESEARCH_USE_ONLY
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
    def __init__(self, adapter: Optional[OrthancAdapterBase] = None):
        self.adapter = adapter or _default_adapter()

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
        """Run the real runner. Any failure propagates to the task layer,
        which records the job as failed — never a made-up result."""
        qa_summary = runner(plan)
        return self._package_result(plan, qa_summary)

    def _package_result(self, plan: PlanDetail, qa_summary: dict) -> PlanExecutionResult:
        """JSON artifact + disk persistence."""
        wf_id = plan.workflow_id.value if hasattr(plan.workflow_id, "value") else str(plan.workflow_id)
        artifact_doc = {
            "intended_use": RESEARCH_USE_ONLY,
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
