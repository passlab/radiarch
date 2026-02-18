import sys
import os
print(f"DEBUG: sys.executable: {sys.executable}")
print(f"DEBUG: sys.path: {sys.path}")

try:
    import opentps
    print(f"DEBUG: OpenTPS imported successfully from {opentps.__file__}")
except ImportError as e:
    print(f"DEBUG: OpenTPS import failed: {e}")

import pytest
from unittest.mock import MagicMock
from radiarch.core.planner import RadiarchPlanner
from radiarch.models.plan import PlanDetail
from radiarch.models.job import JobState

# Skip if opentps logic cannot be run (e.g. no data)
# But we expect it to work with testData
import os
import traceback
from radiarch.config import get_settings

import pytest
from unittest.mock import MagicMock
from datetime import datetime
from radiarch.core.planner import RadiarchPlanner
from radiarch.models.plan import PlanDetail
from radiarch.models.job import JobState
from radiarch.config import get_settings

@pytest.mark.asyncio
async def test_opentps_integration():
    settings = get_settings()
    # Use specific subfolder for speed
    settings.opentps_data_root = os.path.join(settings.opentps_data_root, "SimpleFantomWithStruct")
    
    # Check if OpenTPS is importable
    try:
        import opentps
    except ImportError:
        pytest.fail("OpenTPS not importable - sys.path setup might have failed or venv missing")

    # Mock adapter
    adapter = MagicMock()
    # We don't need real study/segmentation from adapter because _run_opentps currently 
    # loads from settings.opentps_data_root directly as a fallback.
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
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        artifact_ids=[],
        segmentation_uid=None,
        notes="Integration test"
    )

    # Run planner
    # This invokes _run_opentps which does heavy lifting: loading DICOMs, MCsquare
    # It might fail if testData is missing or incompatible binaries
    
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
