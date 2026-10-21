"""The legacy ``/plans`` workflows run on the services (roadmap R15).

The basic proton workflow runs on every machine with the MCsquare binary (a few
seconds on the bundled phantom). The photon, optimized and robust workflows take
minutes on the phantom's native 1 mm grid and are opt-in with
``RADIARCH_RUN_MCSQUARE_VALIDATION=1`` (the nightly job sets it).
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

_SLOW = os.environ.get("RADIARCH_RUN_MCSQUARE_VALIDATION", "").lower() not in ("", "0", "false", "no")


def _mcsquare_available() -> bool:
    try:
        from radiarch.services.dose_engines.registry import engine_health
        return bool(engine_health("mcsquare").get("available"))
    except Exception:
        return False


def _ccc_available() -> bool:
    try:
        from radiarch.services.dose_engines.ccc import CCCEngine
        return CCCEngine().driver().availability()[0]
    except Exception:
        return False


@pytest.fixture
def env(monkeypatch):
    from radiarch.validation import goldens as G

    if not G.SIMPLEFANTOM.is_dir():
        pytest.skip("SimpleFantom test data not present")
    tmp = tempfile.TemporaryDirectory(prefix="radiarch-plans-")
    for k, v in {
        "RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
        "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://", "RADIARCH_DICOMWEB_URL": "",
        "RADIARCH_ARTIFACT_DIR": tmp.name, "RADIARCH_DATA_ROOT": str(G.SIMPLEFANTOM),
        "RADIARCH_MCSQUARE_SEED": "7", "RADIARCH_MCSQUARE_N_THREADS": "0",
    }.items():
        monkeypatch.setenv(k, v)
    from radiarch.config import get_settings
    get_settings.cache_clear()
    yield tmp.name
    get_settings.cache_clear()
    tmp.cleanup()


def _plan(workflow, **kw):
    from radiarch.core.store import InMemoryStore
    from radiarch.models.plan import PlanRequest

    plan, _job = InMemoryStore().create_plan(PlanRequest(study_instance_uid="1.2.3", workflow_id=workflow, prescription_gy=2.0, **kw))
    return plan


def _run(plan):
    from radiarch.core.planner import RadiarchPlanner

    result = RadiarchPlanner().run(plan)
    qa = result.qa_summary
    assert os.path.isfile(qa["rtdosePath"]) and os.path.isfile(result.artifact_path)
    assert qa["maxDose"] > 0 and qa["dvh"]["roiName"] == "TargetVolume" and qa["dvh"]["maxDoseGy"] > 0
    assert "intended_use" in qa
    return qa


@pytest.mark.skipif(not _mcsquare_available(), reason="MCsquare not available")
def test_basic_proton_workflow_runs_on_the_phantom(env):
    from radiarch.models.plan import PlanWorkflow

    qa = _run(_plan(PlanWorkflow.proton_impt_basic))
    assert qa["engine"] == "mcsquare" and qa["beamCount"] == 1 and 500 < qa["spots"] < 1200   # 846 on the native grid
    assert qa["doseUnits"] == "Gy(RBE)" and qa["rbe"] == 1.1
    import pydicom
    ds = pydicom.dcmread(qa["rtdosePath"])
    assert ds.DoseType == "EFFECTIVE"
    assert qa["geometryId"] and qa["beamModelId"] and qa["doseId"]


@pytest.mark.skipif(not (_SLOW and _ccc_available()), reason="opt-in: RADIARCH_RUN_MCSQUARE_VALIDATION=1 and the CCC binary")
def test_photon_ccc_workflow_runs_on_the_phantom(env):
    from radiarch.models.plan import PlanWorkflow

    qa = _run(_plan(PlanWorkflow.photon_ccc, beam_count=2))
    assert qa["engine"] == "ccc" and qa["beamCount"] == 2 and qa["beamlets"] > 0


@pytest.mark.skipif(not (_SLOW and _mcsquare_available()), reason="opt-in: RADIARCH_RUN_MCSQUARE_VALIDATION=1 and MCsquare")
def test_optimized_and_robust_workflows_run_on_the_phantom(env):
    from radiarch.models.plan import PlanWorkflow, RobustnessConfig

    qa = _run(_plan(PlanWorkflow.proton_impt_optimized, max_iterations=5, nb_primaries_beamlets=2000, nb_primaries_final=5000))
    assert qa["engine"] == "mcsquare_optimized" and qa["optimization"]["iterations"] >= 1
    assert qa["optimization"]["solver_method"] == "L-BFGS-B"

    qa = _run(_plan(PlanWorkflow.proton_robust, max_iterations=3, nb_primaries_beamlets=2000, nb_primaries_final=5000,
                    robustness=RobustnessConfig(selection_strategy="REDUCED_SET", setup_systematic_error_mm=[2, 2, 2],
                                                range_systematic_error_pct=3)))
    # REDUCED_SET is 21 scenarios; with a zero random setup error MCsquare leaves out the
    # one that coincides with the nominal plan
    assert qa["engine"] == "mcsquare_robust" and qa["robustness"]["scenarios"] in (20, 21)
    assert len(qa["scenarioDoses"]) == qa["robustness"]["scenarios"] and qa["robustStats"]
    assert qa["doseUnits"] == "Gy(RBE)" and qa["rbe"] == 1.1
