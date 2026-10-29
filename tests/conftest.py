"""Top-level pytest configuration for the Radiarch test suite.

Prepends the in-tree ``src/`` directory to ``sys.path`` so the tests
always run against the live source tree, regardless of how (or whether)
``radiarch`` has been installed into the active environment.

**Why this exists.** setuptools' modern *strict* editable install
snapshots the package list at install time; a package added after the
install is routed through PEP-420 namespace lookup by the stale finder
and may fail to import. Putting ``src/`` on ``sys.path`` first sidesteps
the editable-install finder entirely for test runs. Production (the
Docker image) uses a proper site-packages install and is unaffected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir():
    src_str = str(_SRC)
    # Prepend so the in-tree source wins over any (possibly stale)
    # editable install in the active venv.
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    elif sys.path.index(src_str) != 0:
        sys.path.remove(src_str)
        sys.path.insert(0, src_str)


# ---------------------------------------------------------------------------
# Test-only fake workflow runner
#
# Production has no fake path: if an engine is missing or a runner fails, the
# plan job fails. Tests that only exercise the API contract (plans, jobs,
# artifacts, sessions) swap the real runners for this stand-in so they stay
# fast and never invoke MCsquare. Opt in per module with
# ``pytestmark = pytest.mark.usefixtures("fake_workflow_runners")``; tests
# that need the real pipeline must not use it.
# ---------------------------------------------------------------------------

def _fake_workflow_runner(plan, adapter=None):
    """Deterministic stand-in for a ``core.workflows`` runner.

    Returns only the QA-summary keys the API tests assert on. ``engine`` is
    ``"fake"`` so a result from this runner can never be mistaken for one
    from an engine.
    """
    wf_id = plan.workflow_id.value if hasattr(plan.workflow_id, "value") else str(plan.workflow_id)
    beam_count = getattr(plan, "beam_count", 1) or 1
    return {
        "engine": "fake",
        "beamCount": beam_count,
        "gantryAngles": [round(i * (360.0 / beam_count), 1) for i in range(beam_count)],
        "notes": f"fake runner ({wf_id}); test-only, no dose computed",
    }


@pytest.fixture(scope="module")
def fake_workflow_runners():
    """Replace every registered workflow runner with ``_fake_workflow_runner``.

    The planner looks runners up in ``RUNNERS`` at call time, so patching
    the dict is enough — no planner or task instance needs rebuilding.
    Restored when the module's tests finish.
    """
    from radiarch.core.workflows import RUNNERS

    with pytest.MonkeyPatch.context() as mp:
        for wf_id in list(RUNNERS):
            mp.setitem(RUNNERS, wf_id, _fake_workflow_runner)
        yield


# ---------------------------------------------------------------------------
# Router service caches
#
# Every router keeps its service in an ``lru_cache`` (``_service()``), and a
# service binds the artifact directory it was created with. Test modules give
# each test its own artifact directory, so a service cached by an earlier test
# answers "not found" for everything a later test builds. Clearing the caches
# before every test removes that order coupling. Only modules already imported
# are touched: nothing new is imported here.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_router_service_caches():
    for name, module in list(sys.modules.items()):
        if name.startswith("radiarch.api.routes.") and module is not None:
            for attr, svc in list(vars(module).items()):      # _service, and the mco routes' _navigation, _deliverables
                if attr.startswith("_") and callable(svc) and hasattr(svc, "cache_clear"):
                    svc.cache_clear()
    yield
