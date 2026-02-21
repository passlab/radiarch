"""
Unit tests for backend functions that serve the Radiarch API routes.

Tests the core backend modules directly (not via HTTP):
  - InMemoryStore: plan/job/artifact CRUD
  - WorkflowRegistry: register/get/list/contains
  - DeliverySimulator: synthetic simulation results
  - Session helpers: lifecycle, cleanup, expiry
  - Pydantic models: serialization, validation, enums
"""

import os
import sys
import time
import tempfile

import pytest

# ── Path setup ──────────────────────────────────────────────────────
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
_service_dir = os.path.join(_repo_root, "service")
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

# Force dev mode env vars BEFORE any radiarch import
os.environ["RADIARCH_ENVIRONMENT"] = "dev"
os.environ["RADIARCH_FORCE_SYNTHETIC"] = "true"
os.environ["RADIARCH_ORTHANC_USE_MOCK"] = "true"
os.environ["RADIARCH_DATABASE_URL"] = ""
os.environ["RADIARCH_BROKER_URL"] = "memory://"
os.environ["RADIARCH_RESULT_BACKEND"] = "cache+memory://"
os.environ["RADIARCH_DICOMWEB_URL"] = ""

_tmpdir = tempfile.mkdtemp(prefix="radiarch_test_")
os.environ["RADIARCH_ARTIFACT_DIR"] = _tmpdir

# ── Import radiarch submodules BYPASSING __init__.py ──────────────
# radiarch/__init__.py eagerly imports create_app → database → sqlalchemy,
# pulling in the entire dependency tree.  We only need the models, store,
# simulator, sessions, and workflows — none of which require sqlalchemy.
import importlib

# Swap out _service_dir/radiarch/__init__.py temporarily so Python doesn't
# run it (it triggers create_app → sqlalchemy).
import types
_radiarch_pkg = types.ModuleType("radiarch")
_radiarch_pkg.__path__ = [os.path.join(_service_dir, "radiarch")]
_radiarch_pkg.__package__ = "radiarch"
sys.modules["radiarch"] = _radiarch_pkg

# Now import submodules directly
from radiarch.models.plan import (  # noqa: E402
    PlanRequest, PlanDetail, PlanSummary,
    DoseObjective, ObjectiveType, RobustnessConfig, PlanWorkflow,
)
from radiarch.models.job import JobState, JobStatus  # noqa: E402
from radiarch.models.artifact import ArtifactRecord  # noqa: E402
from radiarch.models.simulation import (  # noqa: E402
    SimulationRequest, SimulationResult, SimulationStatus,
)
from radiarch.core.store import InMemoryStore  # noqa: E402
from radiarch.core.simulator import DeliverySimulator  # noqa: E402
from radiarch.api.routes.workflows import (  # noqa: E402
    WorkflowRegistry, Workflow, WorkflowParameter, ParameterType,
    registry as builtin_registry,
)
from radiarch.api.routes.sessions import (  # noqa: E402
    _sessions, _session_dir, _cleanup_expired, SessionInfo,
)


# ===========================================================================
# 1. InMemoryStore — plan/job/artifact CRUD
# ===========================================================================

class TestInMemoryStore:
    """Unit tests for radiarch.core.store.InMemoryStore."""

    @pytest.fixture(autouse=True)
    def fresh_store(self):
        self.store = InMemoryStore()

    @pytest.fixture
    def sample_request(self):
        return PlanRequest(
            study_instance_uid="1.2.3.4.5",
            workflow_id="proton-impt-basic",
            prescription_gy=2.0,
            fraction_count=1,
        )

    # ── Plans ──

    def test_create_plan(self, sample_request):
        plan, job = self.store.create_plan(sample_request)
        assert plan.id is not None
        assert job.id is not None
        assert plan.study_instance_uid == "1.2.3.4.5"
        assert plan.workflow_id == "proton-impt-basic"
        assert plan.prescription_gy == 2.0
        assert plan.job_id == job.id
        assert job.plan_id == plan.id
        assert job.state == "queued"

    def test_list_plans_empty(self):
        assert self.store.list_plans() == []

    def test_list_plans_after_create(self, sample_request):
        self.store.create_plan(sample_request)
        plans = self.store.list_plans()
        assert len(plans) == 1
        assert plans[0].workflow_id == "proton-impt-basic"

    def test_get_plan_existing(self, sample_request):
        plan, _ = self.store.create_plan(sample_request)
        fetched = self.store.get_plan(plan.id)
        assert fetched is not None
        assert fetched.id == plan.id

    def test_get_plan_not_found(self):
        assert self.store.get_plan("nonexistent") is None

    def test_delete_plan(self, sample_request):
        plan, job = self.store.create_plan(sample_request)
        result = self.store.delete_plan(plan.id)
        assert result is True
        assert self.store.get_plan(plan.id) is None

    def test_delete_plan_not_found(self):
        result = self.store.delete_plan("nonexistent")
        assert result is False

    def test_create_multiple_plans(self, sample_request):
        self.store.create_plan(sample_request)
        req2 = PlanRequest(
            study_instance_uid="9.8.7.6",
            workflow_id="photon-ccc",
            prescription_gy=3.0,
        )
        self.store.create_plan(req2)
        plans = self.store.list_plans()
        assert len(plans) == 2

    # ── Jobs ──

    def test_get_job(self, sample_request):
        plan, job = self.store.create_plan(sample_request)
        fetched = self.store.get_job(job.id)
        assert fetched is not None
        assert fetched.state == "queued"
        assert fetched.plan_id == plan.id

    def test_get_job_not_found(self):
        assert self.store.get_job("nonexistent") is None

    def test_update_job_state(self, sample_request):
        _, job = self.store.create_plan(sample_request)
        self.store.update_job(job.id, state=JobState.running, progress=0.5)
        updated = self.store.get_job(job.id)
        assert updated.state == "running"
        assert updated.progress == 0.5

    def test_update_job_succeeded(self, sample_request):
        _, job = self.store.create_plan(sample_request)
        self.store.update_job(
            job.id,
            state=JobState.succeeded,
            progress=1.0,
            message="Done",
            stage="complete",
        )
        updated = self.store.get_job(job.id)
        assert updated.state == "succeeded"
        assert updated.progress == 1.0
        assert updated.message == "Done"
        assert updated.finished_at is not None

    def test_update_job_failed(self, sample_request):
        _, job = self.store.create_plan(sample_request)
        self.store.update_job(job.id, state=JobState.failed, message="error")
        updated = self.store.get_job(job.id)
        assert updated.state == "failed"
        assert updated.finished_at is not None

    # ── Artifacts ──

    def test_register_artifact(self, sample_request, tmp_path):
        plan, _ = self.store.create_plan(sample_request)
        dummy_file = str(tmp_path / "dose.dcm")
        with open(dummy_file, "w") as f:
            f.write("dummy")

        artifact_id = self.store.register_artifact(
            plan_id=plan.id,
            file_path=dummy_file,
            content_type="application/dicom",
            file_name="dose.dcm",
        )
        assert isinstance(artifact_id, str)
        assert len(artifact_id) > 0
        # Verify it was stored
        fetched = self.store.get_artifact(artifact_id)
        assert fetched is not None
        assert fetched.plan_id == plan.id
        assert fetched.file_path == dummy_file

    def test_get_artifact(self, sample_request, tmp_path):
        plan, _ = self.store.create_plan(sample_request)
        dummy_file = str(tmp_path / "dose.dcm")
        with open(dummy_file, "w") as f:
            f.write("dummy")

        artifact_id = self.store.register_artifact(plan.id, dummy_file)
        fetched = self.store.get_artifact(artifact_id)
        assert fetched is not None
        assert fetched.id == artifact_id

    def test_get_artifact_not_found(self):
        assert self.store.get_artifact("nonexistent") is None

    def test_attach_artifact_to_plan(self, sample_request, tmp_path):
        plan, _ = self.store.create_plan(sample_request)
        dummy_file = str(tmp_path / "dose.dcm")
        with open(dummy_file, "w") as f:
            f.write("dummy")

        artifact_id = self.store.register_artifact(plan.id, dummy_file)
        # register_artifact already calls attach_artifact internally
        updated_plan = self.store.get_plan(plan.id)
        assert artifact_id in updated_plan.artifact_ids

    def test_set_plan_summary(self, sample_request):
        plan, _ = self.store.create_plan(sample_request)
        summary = {"engine": "synthetic", "dose_max": 2.1}
        self.store.set_plan_summary(plan.id, summary)

        updated = self.store.get_plan(plan.id)
        assert updated.qa_summary is not None
        assert updated.qa_summary["engine"] == "synthetic"


# ===========================================================================
# 2. WorkflowRegistry
# ===========================================================================

class TestWorkflowRegistry:
    """Unit tests for WorkflowRegistry."""

    @pytest.fixture(autouse=True)
    def fresh_registry(self):
        self.registry = WorkflowRegistry()

    def _make_workflow(self, wf_id="test-wf", **kwargs):
        defaults = {
            "id": wf_id,
            "name": "Test Workflow",
            "description": "A test workflow",
            "modality": "proton",
            "engine": "mcsquare",
        }
        defaults.update(kwargs)
        return Workflow(**defaults)

    def test_register_and_get(self):
        wf = self._make_workflow()
        self.registry.register(wf)
        fetched = self.registry.get("test-wf")
        assert fetched is not None
        assert fetched.id == "test-wf"

    def test_get_not_found(self):
        assert self.registry.get("nonexistent") is None

    def test_list_empty(self):
        assert self.registry.list() == []

    def test_list_after_register(self):
        self.registry.register(self._make_workflow("wf-1"))
        self.registry.register(self._make_workflow("wf-2"))
        assert len(self.registry.list()) == 2

    def test_contains(self):
        self.registry.register(self._make_workflow())
        assert "test-wf" in self.registry
        assert "nonexistent" not in self.registry

    def test_len(self):
        assert len(self.registry) == 0
        self.registry.register(self._make_workflow())
        assert len(self.registry) == 1

    def test_ids(self):
        self.registry.register(self._make_workflow("a"))
        self.registry.register(self._make_workflow("b"))
        assert set(self.registry.ids()) == {"a", "b"}

    def test_overwrite_existing(self):
        wf1 = self._make_workflow("wf", name="Original")
        wf2 = self._make_workflow("wf", name="Updated")
        self.registry.register(wf1)
        self.registry.register(wf2)
        assert self.registry.get("wf").name == "Updated"
        assert len(self.registry) == 1

    def test_builtin_workflows_registered(self):
        """Verify the singleton registry has the built-in workflows."""
        assert len(builtin_registry) >= 4
        assert "proton-impt-basic" in builtin_registry
        assert "proton-impt-optimized" in builtin_registry
        assert "proton-robust" in builtin_registry
        assert "photon-ccc" in builtin_registry

    def test_proton_impt_basic_has_parameters(self):
        wf = builtin_registry.get("proton-impt-basic")
        assert wf is not None
        assert wf.modality == "proton"
        assert wf.engine == "mcsquare"
        param_names = [p.name for p in wf.default_parameters]
        assert "gantry_angle" in param_names
        assert "nb_primaries" in param_names

    def test_photon_ccc_modality(self):
        wf = builtin_registry.get("photon-ccc")
        assert wf is not None
        assert wf.modality == "photon"
        assert wf.engine == "ccc"


# ===========================================================================
# 3. DeliverySimulator — synthetic mode
# ===========================================================================

class TestDeliverySimulator:
    """Unit tests for DeliverySimulator (synthetic mode only)."""

    def test_synthetic_mode_forced(self):
        sim = DeliverySimulator(force_synthetic=True)
        assert sim._force_synthetic is True

    def test_run_synthetic_returns_expected_fields(self):
        sim = DeliverySimulator(force_synthetic=True)
        request = SimulationRequest(
            plan_id="test-plan",
            motion_amplitude_mm=[2.0, 0.0, 5.0],
            motion_period_s=4.0,
            delivery_time_per_spot_ms=5.0,
            num_fractions=3,
        )

        result = sim.run(request, plan_qa={"engine": "synthetic"})

        assert result["engine"] == "synthetic_simulation"
        assert "delivered_dose_max_gy" in result
        assert "delivered_dose_mean_gy" in result
        assert "gamma_pass_rate" in result
        assert "dose_difference_pct" in result
        assert result["num_fractions"] == 3

    def test_synthetic_gamma_degrades_with_motion(self):
        """Higher motion amplitude should produce lower gamma on average."""
        sim = DeliverySimulator(force_synthetic=True)

        req_low = SimulationRequest(
            plan_id="low", motion_amplitude_mm=[0.0, 0.0, 0.0],
        )
        req_high = SimulationRequest(
            plan_id="high", motion_amplitude_mm=[10.0, 10.0, 10.0],
        )

        gammas_low = [sim.run(req_low, {})["gamma_pass_rate"] for _ in range(10)]
        gammas_high = [sim.run(req_high, {})["gamma_pass_rate"] for _ in range(10)]

        avg_low = sum(gammas_low) / len(gammas_low)
        avg_high = sum(gammas_high) / len(gammas_high)

        assert avg_low > avg_high, \
            f"Low-motion gamma ({avg_low:.1f}) should beat high-motion ({avg_high:.1f})"

    def test_synthetic_dose_values_positive(self):
        sim = DeliverySimulator(force_synthetic=True)
        request = SimulationRequest(plan_id="ptest")
        result = sim.run(request, plan_qa={})
        assert result["delivered_dose_max_gy"] > 0
        assert result["delivered_dose_mean_gy"] > 0


# ===========================================================================
# 4. Session helpers (unit-level)
# ===========================================================================

class TestSessionHelpers:
    """Unit tests for session lifecycle functions."""

    @pytest.fixture(autouse=True)
    def clean_sessions(self):
        _sessions.clear()
        yield
        _sessions.clear()

    def test_session_dir_construction(self):
        sid = "abc-123"
        result = _session_dir(sid)
        assert result.endswith(os.path.join("sessions", "abc-123"))

    def test_cleanup_expired_removes_old_sessions(self):
        now = time.time()
        _sessions["expired-1"] = SessionInfo(
            id="expired-1",
            created_at=now - 7200,
            expires_at=now - 3600,
            file_count=1,
        )
        _sessions["valid-1"] = SessionInfo(
            id="valid-1",
            created_at=now,
            expires_at=now + 3600,
            file_count=1,
        )

        _cleanup_expired()

        assert "expired-1" not in _sessions
        assert "valid-1" in _sessions

    def test_session_info_model(self):
        info = SessionInfo(
            id="test-id",
            created_at=time.time(),
            expires_at=time.time() + 3600,
            file_count=2,
        )
        assert info.id == "test-id"
        assert info.file_count == 2

    def test_cleanup_leaves_fresh_sessions(self):
        now = time.time()
        _sessions["fresh"] = SessionInfo(
            id="fresh", created_at=now, expires_at=now + 9999, file_count=0,
        )
        _cleanup_expired()
        assert "fresh" in _sessions


# ===========================================================================
# 5. Pydantic models — serialization & validation
# ===========================================================================

class TestPydanticModels:
    """Test Pydantic model validation and serialization."""

    def test_plan_request_valid(self):
        req = PlanRequest(
            study_instance_uid="1.2.3",
            prescription_gy=2.0,
        )
        assert req.workflow_id == "proton-impt-basic"
        assert req.fraction_count == 1
        assert req.beam_count == 1

    def test_plan_request_invalid_prescription(self):
        with pytest.raises(Exception):
            PlanRequest(study_instance_uid="1.2.3", prescription_gy=-1.0)

    def test_job_state_enum(self):
        assert JobState.queued == "queued"
        assert JobState.succeeded == "succeeded"
        assert len(JobState) == 5

    def test_simulation_request_defaults(self):
        req = SimulationRequest(plan_id="p1")
        assert req.motion_amplitude_mm == [0.0, 0.0, 0.0]
        assert req.motion_period_s == 4.0
        assert req.num_fractions == 1

    def test_simulation_request_invalid_fractions(self):
        with pytest.raises(Exception):
            SimulationRequest(plan_id="p1", num_fractions=0)

    def test_dose_objective_model(self):
        obj = DoseObjective(
            structure_name="PTV",
            objective_type=ObjectiveType.d_min,
            dose_gy=1.8,
            weight=2.0,
        )
        assert obj.structure_name == "PTV"
        assert obj.weight == 2.0

    def test_robustness_config_defaults(self):
        rc = RobustnessConfig()
        assert rc.range_systematic_error_pct == 5.0
        assert rc.num_scenarios == 5

    def test_workflow_parameter_model(self):
        param = WorkflowParameter(
            name="gantry_angle",
            label="Gantry Angle",
            type=ParameterType.number,
            default=90.0,
            units="deg",
        )
        assert param.name == "gantry_angle"
        assert param.type == ParameterType.number

    def test_artifact_record_model(self):
        ar = ArtifactRecord(
            id="art-1",
            plan_id="plan-1",
            file_path="/tmp/dose.dcm",
        )
        assert ar.content_type == "application/dicom"
        assert ar.file_name == ""

    def test_simulation_status_enum(self):
        assert SimulationStatus.queued == "queued"
        assert SimulationStatus.succeeded == "succeeded"
        assert len(SimulationStatus) == 5

    def test_plan_request_with_objectives(self):
        req = PlanRequest(
            study_instance_uid="1.2.3",
            prescription_gy=2.0,
            objectives=[
                DoseObjective(
                    structure_name="PTV",
                    objective_type=ObjectiveType.d_uniform,
                    dose_gy=2.0,
                ),
            ],
        )
        assert len(req.objectives) == 1
        assert req.objectives[0].structure_name == "PTV"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
