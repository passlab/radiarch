"""R0 hygiene: the intended-use statement on every artifact, API-key auth on
every router, test-only engine gating, the RTDOSE writer's labels, the OpenTPS
photon plan builder and the robustness translation (roadmap R0)."""

from __future__ import annotations

import types

import numpy as np
import pytest

from radiarch.models.common import NOT_FOR_CLINICAL_USE, RESEARCH_USE_ONLY


def _opentps_available() -> bool:
    try:
        import opentps.core  # noqa: F401
        return True
    except Exception:
        return False


needs_opentps = pytest.mark.skipif(not _opentps_available(), reason="vendored OpenTPS not importable")


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    """App with an API key configured, in-memory stores, artifacts under tmp."""
    monkeypatch.setenv("RADIARCH_API_KEY", "test-key-abc123")
    monkeypatch.setenv("RADIARCH_ENVIRONMENT", "dev")
    monkeypatch.setenv("RADIARCH_ORTHANC_USE_MOCK", "true")
    monkeypatch.setenv("RADIARCH_DATABASE_URL", "")
    monkeypatch.setenv("RADIARCH_BROKER_URL", "memory://")
    monkeypatch.setenv("RADIARCH_RESULT_BACKEND", "cache+memory://")
    monkeypatch.setenv("RADIARCH_ARTIFACT_DIR", str(tmp_path))
    from radiarch.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from radiarch.app import create_app
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Intended-use statement
# ---------------------------------------------------------------------------

class TestDisclaimer:
    def test_every_result_model_carries_the_statement(self):
        from radiarch.models.bao import BAOResult
        from radiarch.models.beam_model import BeamModelResult
        from radiarch.models.dose import DoseResult, InfluenceResult
        from radiarch.models.evaluation import EvaluationResult
        from radiarch.models.geometry import GeometryResult
        from radiarch.models.optimization import OptimizationResult
        from radiarch.models.plan import PlanDetail, PlanSummary

        for cls in (
            GeometryResult, BeamModelResult, DoseResult, InfluenceResult,
            OptimizationResult, BAOResult, EvaluationResult, PlanSummary, PlanDetail,
        ):
            assert "disclaimer" in cls.model_fields, cls.__name__
            assert cls.model_fields["disclaimer"].default == RESEARCH_USE_ONLY, cls.__name__

    def test_info_is_open_and_states_intended_use(self, app_client):
        r = app_client.get("/api/v1/info")  # deliberately no API key
        assert r.status_code == 200
        body = r.json()
        assert body["intended_use"] == RESEARCH_USE_ONLY
        assert body["models"]["photon-ccc"]["status"] == "unavailable"


# ---------------------------------------------------------------------------
# API key on every router
# ---------------------------------------------------------------------------

class TestAuthEverywhere:
    @pytest.mark.parametrize("path", [
        "/api/v1/workflows",
        "/api/v1/plans",
        "/api/v1/jobs/none",
        "/api/v1/artifacts/none",
        "/api/v1/sessions/none",
        "/api/v1/geometry/none",
        "/api/v1/beam-model/none",
        "/api/v1/uploads/none",
        "/api/v1/dose/engines",
        "/api/v1/optimize/none",
        "/api/v1/bao/none",
        "/api/v1/evaluate/none",
    ])
    def test_every_service_route_requires_the_key(self, app_client, path):
        assert app_client.get(path).status_code == 401

    def test_key_opens_the_route(self, app_client):
        r = app_client.get("/api/v1/workflows", headers={"X-API-Key": "test-key-abc123"})
        assert r.status_code == 200

    def test_root_and_info_stay_open(self, app_client):
        assert app_client.get("/").status_code == 200
        assert app_client.get("/api/v1/info").status_code == 200


# ---------------------------------------------------------------------------
# Test-only engines
# ---------------------------------------------------------------------------

class TestTestOnlyEngines:
    def test_analytic_is_flagged_and_mcsquare_is_not(self):
        from radiarch.services.dose_engines import registry  # registers engines on import
        from radiarch.services.dose_engines.analytic import AnalyticEngine

        assert AnalyticEngine().test_only is True
        assert registry.engine_health("analytic")["test_only"] is True
        assert registry.engine_health("mcsquare")["test_only"] is False

    def test_refused_when_not_allowed(self, monkeypatch):
        import radiarch.config as config
        from radiarch.services.dose_engines.analytic import AnalyticEngine
        from radiarch.services.dose_engines.registry import TestOnlyEngineError, ensure_engine_allowed

        monkeypatch.setattr(
            config, "get_settings",
            lambda: types.SimpleNamespace(allow_test_engines=False, environment="production"),
        )
        with pytest.raises(TestOnlyEngineError):
            ensure_engine_allowed(AnalyticEngine())

    def test_allowed_when_permitted(self, monkeypatch):
        import radiarch.config as config
        from radiarch.services.dose_engines.analytic import AnalyticEngine
        from radiarch.services.dose_engines.registry import ensure_engine_allowed

        monkeypatch.setattr(
            config, "get_settings",
            lambda: types.SimpleNamespace(allow_test_engines=True, environment="dev"),
        )
        ensure_engine_allowed(AnalyticEngine())  # no raise

    def test_real_engines_are_never_gated(self, monkeypatch):
        import radiarch.config as config
        from radiarch.services.dose_engines.registry import ensure_engine_allowed, get_engine

        monkeypatch.setattr(
            config, "get_settings",
            lambda: types.SimpleNamespace(allow_test_engines=False, environment="production"),
        )
        ensure_engine_allowed(get_engine("mcsquare"))  # no raise

    def test_default_follows_environment(self, monkeypatch):
        from radiarch.config import get_settings

        monkeypatch.delenv("RADIARCH_ALLOW_TEST_ENGINES", raising=False)
        try:
            monkeypatch.setenv("RADIARCH_ENVIRONMENT", "production")
            get_settings.cache_clear()
            assert get_settings().allow_test_engines is False
            monkeypatch.setenv("RADIARCH_ENVIRONMENT", "dev")
            get_settings.cache_clear()
            assert get_settings().allow_test_engines is True
        finally:
            get_settings.cache_clear()


# ---------------------------------------------------------------------------
# RTDOSE writer labels
# ---------------------------------------------------------------------------

class TestRtdoseLabels:
    def test_export_rtdose_marks_research_and_frame_of_reference(self, tmp_path):
        import pydicom
        from radiarch.core.workflows._helpers import export_rtdose

        rng = np.random.default_rng(0)
        dose = types.SimpleNamespace(
            imageArray=(rng.random((4, 5, 6)) * 10).astype(np.float32),
            spacing=(2.0, 2.0, 3.0),
            origin=(0.0, 0.0, 0.0),
        )
        ct = types.SimpleNamespace(
            frameOfReferenceUID="1.2.826.0.1.3680043.8.498.1",
            patientName="ANON", patientID="ANON-1", studyInstanceUID="1.2.3",
        )
        out = tmp_path / "rtdose.dcm"
        export_rtdose(dose, ct, str(out))

        ds = pydicom.dcmread(str(out))
        assert ds.Modality == "RTDOSE"
        assert ds.SeriesDescription == "RESEARCH - " + NOT_FOR_CLINICAL_USE
        assert ds.DoseComment == NOT_FOR_CLINICAL_USE
        assert ds.FrameOfReferenceUID == ct.frameOfReferenceUID
        block = ds.private_block(0x7779, "RADIARCH")
        assert block[0x01].value == NOT_FOR_CLINICAL_USE


# ---------------------------------------------------------------------------
# Geometry bundle (persisted geometry → OpenTPS objects)
# ---------------------------------------------------------------------------

class TestGeometryBundle:
    def test_target_structure_prefers_ptv_then_gtv_then_ctv(self):
        from radiarch.services.geometry_bundle import target_structure

        assert target_structure({"Lung_L": 3, "GTV": 2, "PTV_60": 1}) == ("PTV_60", 1)
        assert target_structure({"Lung_L": 3, "CTV": 2, "GTV_p": 5}) == ("GTV_p", 5)
        assert target_structure({"Lung_L": 3}) is None

    @staticmethod
    def _geom(tmp_path, with_ct=True):
        import SimpleITK as sitk

        ct_zyx = np.full((4, 5, 6), -1000, dtype=np.int16)
        ct_zyx[1:3, 1:4, 2:5] = 40
        masks_zyx = np.zeros((4, 5, 6), dtype=np.uint16)
        masks_zyx[1:3, 1:3, 2:4] = 1      # PTV
        masks_zyx[3, 4, 5] = 2            # an OAR
        ct_path = tmp_path / "ct.nii.gz"
        masks_path = tmp_path / "masks.nii.gz"
        sitk.WriteImage(sitk.GetImageFromArray(ct_zyx), str(ct_path))
        sitk.WriteImage(sitk.GetImageFromArray(masks_zyx), str(masks_path))
        return types.SimpleNamespace(
            geometry_id="g-1",
            ct_grid_uri=str(ct_path) if with_ct else None,
            structure_masks_uri=str(masks_path),
            structure_index={"PTV": 1, "SpinalCord": 2},
            grid_spec=types.SimpleNamespace(spacing_mm=(1.0, 1.5, 2.0), origin_mm=(-1.0, 0.0, 3.0)),
            ct_metadata=types.SimpleNamespace(patient_name="ANON", series_instance_uid="1.2.3"),
            frame_of_reference_uid="1.2.3.4",
        ), ct_zyx, masks_zyx

    @needs_opentps
    def test_load_opentps_geometry_uses_the_persisted_volumes(self, tmp_path):
        from radiarch.services.geometry_bundle import load_opentps_geometry

        geom, ct_zyx, masks_zyx = self._geom(tmp_path)
        ct, patient, target = load_opentps_geometry(geom)

        assert ct.imageArray.shape == (6, 5, 4)           # (x, y, z)
        assert np.array_equal(ct.imageArray, np.transpose(ct_zyx, (2, 1, 0)))
        assert tuple(ct.spacing) == (1.0, 1.5, 2.0)
        assert tuple(ct.origin) == (-1.0, 0.0, 3.0)
        assert ct.frameOfReferenceUID == "1.2.3.4"
        assert target is not None and target.name == "PTV"
        assert int(target.imageArray.sum()) == int((masks_zyx == 1).sum())
        assert patient.name == "ANON"

    def test_missing_ct_grid_is_an_error_not_a_fallback(self, tmp_path):
        from radiarch.services.geometry_bundle import load_opentps_geometry

        geom, _, _ = self._geom(tmp_path, with_ct=False)
        with pytest.raises(ValueError, match="no CT grid"):
            load_opentps_geometry(geom)


# ---------------------------------------------------------------------------
# OpenTPS photon plan builder (defect 1) and robustness translation (defect 2)
# ---------------------------------------------------------------------------

@needs_opentps
class TestPhotonPlanBuilder:
    def test_beams_are_attached_and_carry_beamlets(self):
        from radiarch.services.photon_beamlets import build_photon_plan

        plan = build_photon_plan(
            beams=[(0.0, 0.0), (90.0, 0.0)],
            jaw_x_mm=(-100.0, 100.0), jaw_y_mm=(-100.0, 100.0),
            leaf_width_mm=10.0, mu_per_beam=100.0, beamlet_spacing_mm=(5.0, 5.0),
        )
        assert len(plan.beams) == 2
        assert [b.gantryAngle_degree for b in plan.beams] == [0.0, 90.0]
        seg = plan.beams[1].beamSegments[0]
        assert seg.x_jaw_mm == [-100.0, 100.0]
        assert seg.y_jaw_mm == [-100.0, 100.0]
        assert seg.mu == 100.0
        assert seg.Xmlc_mm.shape == (20, 4)
        n = int(plan.beams[0].numberOfBeamlets)
        assert n == 1600, n                       # 40 × 40 beamlets of 5 mm in a 200 mm field
        assert plan.numberOfBeamlets == 2 * n

    def test_generate_reports_opentps_beamlet_count(self):
        from radiarch.models.beam_model import BeamSetSpec, BeamSpec, DeliveryParams
        from radiarch.services.machine_model import PhotonMachineModel
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=BeamSetSpec(isocenter_mm=(0, 0, 0), beams=[BeamSpec(beam_id="B1", gantry_deg=30.0)]),
            params=DeliveryParams(),
        )
        assert len(result.plan.beams) == 1
        assert result.fluence_elements.per_beam[0].active_beamlets == 1600


@needs_opentps
class TestRobustnessConfig:
    def test_parameters_reach_opentps(self):
        from radiarch.core.workflows.proton_robust import configure_robustness
        from radiarch.models.plan import RobustnessConfig

        rob = configure_robustness(RobustnessConfig(
            setup_systematic_error_mm=[3.0, 3.0, 3.0],
            setup_random_error_mm=[1.0, 1.0, 1.0],
            range_systematic_error_pct=3.5,
            selection_strategy="ALL",
            num_scenarios=9,
        ))
        assert rob.setupSystematicError == [3.0, 3.0, 3.0]
        assert rob.setupRandomError == [1.0, 1.0, 1.0]
        assert rob.rangeSystematicError == 3.5
        assert rob.selectionStrategy is type(rob).Strategies.ALL
        assert rob.numScenarios == 9

    def test_unknown_strategy_is_an_error(self):
        from radiarch.core.workflows._helpers import PlannerError
        from radiarch.core.workflows.proton_robust import configure_robustness
        from radiarch.models.plan import RobustnessConfig

        with pytest.raises(PlannerError, match="selection_strategy"):
            configure_robustness(RobustnessConfig(selection_strategy="SOMETIMES"))


# ---------------------------------------------------------------------------
# Beam model on a persisted geometry (defect 3): spots follow the given target
# ---------------------------------------------------------------------------

@needs_opentps
class TestBeamModelOnPersistedGeometry:
    def test_proton_spots_are_placed_on_the_persisted_target(self, tmp_path):
        import SimpleITK as sitk
        from radiarch.models.beam_model import BeamSetSpec, BeamSpec, DeliveryParams, Modality
        from radiarch.services.geometry_bundle import load_opentps_geometry
        from radiarch.services.machine_model import get_machine_model
        from radiarch.services.proton_spots import generate_proton_spots

        # 80 mm water cube at 2 mm with an air shell; a 10 mm-radius PTV at the centre.
        n, sp = 40, 2.0
        ct_zyx = np.full((n, n, n), -1000, dtype=np.int16)
        ct_zyx[2:-2, 2:-2, 2:-2] = 0
        zz, yy, xx = np.mgrid[:n, :n, :n]
        c = (n - 1) / 2.0
        sphere = ((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2) * sp ** 2 <= 10.0 ** 2
        masks_zyx = np.where(sphere, 1, 0).astype(np.uint16)
        ct_path, masks_path = tmp_path / "ct.nii.gz", tmp_path / "masks.nii.gz"
        sitk.WriteImage(sitk.GetImageFromArray(ct_zyx), str(ct_path))
        sitk.WriteImage(sitk.GetImageFromArray(masks_zyx), str(masks_path))
        origin = (-c * sp,) * 3  # sphere centred on (0, 0, 0)
        geom = types.SimpleNamespace(
            geometry_id="g-sphere",
            ct_grid_uri=str(ct_path),
            structure_masks_uri=str(masks_path),
            structure_index={"PTV": 1},
            grid_spec=types.SimpleNamespace(spacing_mm=(sp, sp, sp), origin_mm=origin),
            ct_metadata=types.SimpleNamespace(patient_name="ANON", series_instance_uid="1.2.3"),
            frame_of_reference_uid="1.2.3.4",
        )

        ct, patient, target = load_opentps_geometry(geom)
        assert target is not None
        result = generate_proton_spots(
            ct=ct, patient=patient, target_contour=target,
            machine_model=get_machine_model(Modality.proton_pbs, None),
            beam_set=BeamSetSpec(isocenter_mm=(0.0, 0.0, 0.0),
                                 beams=[BeamSpec(beam_id="B1", gantry_deg=0.0)]),
            params=DeliveryParams(),
        )
        assert result.fluence_elements.total_count > 0

        xs, ys = [], []
        for beam in result.plan.beams:
            for layer in beam.layers:
                xs.extend(float(v) for v in layer.spotX)
                ys.extend(float(v) for v in layer.spotY)
        # Every spot sits within the target radius plus OpenTPS's 5 mm margin and
        # one 5 mm spot spacing of the isocenter — on the given sphere, not on the
        # default phantom the beam model used to load.
        assert max(abs(v) for v in xs + ys) <= 10.0 + 5.0 + 5.0
