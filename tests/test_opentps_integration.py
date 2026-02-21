"""Integration test for OpenTPS + MCsquare proton dose calculation.

Requires RADIARCH_OPENTPS_DATA_ROOT to point to a directory containing
DICOM CT + RT-Struct data (e.g. opentps/testData).
"""

import os
import traceback
from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock

from radiarch.core.planner import RadiarchPlanner
from radiarch.models.plan import PlanDetail
from radiarch.models.job import JobState
from radiarch.config import get_settings


@pytest.mark.asyncio
async def test_opentps_integration():
    settings = get_settings()

    # Override force_synthetic so real OpenTPS planner runs
    # (test_api_e2e.py sets RADIARCH_FORCE_SYNTHETIC=true as a process env var)
    os.environ.pop("RADIARCH_FORCE_SYNTHETIC", None)
    settings.force_synthetic = False

    # Use specific subfolder for speed
    settings.opentps_data_root = os.path.join(settings.opentps_data_root, "SimpleFantomWithStruct")

    # Check if OpenTPS is importable
    try:
        import opentps  # noqa: F401
    except ImportError:
        pytest.fail("OpenTPS not importable — vendored copy missing?")

    # Mock adapter
    adapter = MagicMock()
    adapter.get_study.return_value = {"valid": "study"}
    adapter.get_segmentation.return_value = None

    planner = RadiarchPlanner(adapter=adapter)

    # Create valid plan request
    plan = PlanDetail(
        id="test-plan-001",
        workflow_id="proton-impt-basic",
        study_instance_uid="1.2.3.4",
        status=JobState.queued.value,
        prescription_gy=20.0,
        fraction_count=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        artifact_ids=[],
        segmentation_uid=None,
        notes="Integration test",
    )

    # Run planner — invokes MCsquare for real proton dose calculation
    try:
        result = planner.run(plan)
    except Exception as e:
        with open("error.log", "w") as f:
            traceback.print_exc(file=f)
        pytest.fail(f"Planner run failed: {e}")

    assert result
    assert result.qa_summary
    assert result.qa_summary["engine"] == "opentps"
    assert "maxDose" in result.qa_summary
    assert result.qa_summary["maxDose"] >= 0

    print("OpenTPS Execution Result:", result.qa_summary)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_opentps_integration())

