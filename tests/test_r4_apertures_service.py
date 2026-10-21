"""R4, part C through the services: geometry → photon beam model → optimization → apertures → evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pytest

from radiarch.models.apertures import SequenceRequest
from radiarch.models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
from radiarch.models.dose import EngineSpec
from radiarch.models.geometry import GeometryBuildRequest, PatientRef
from radiarch.models.optimization import ObjectiveSpec, OptimizationRunRequest, SolverConfig


@dataclass
class _Patient:
    name: str = "APERTURES"


@dataclass
class _CT:
    imageArray: np.ndarray
    origin: Tuple[float, float, float]
    spacing: Tuple[float, float, float]
    patient: _Patient
    seriesInstanceUID: str = "1.2.3.4"
    studyInstanceUID: str = "1.2.3"
    frameOfReferenceUID: str = "1.2.3.9"


@dataclass
class _Mask:
    imageArray: np.ndarray


@dataclass
class _Contour:
    name: str
    mask: np.ndarray

    def getBinaryMask(self, origin, gridSize, spacing):
        return _Mask(self.mask)


def _loaded_ct():
    from radiarch.services.geometry import _LoadedCT

    n, sp = 16, 5.0
    ct = np.zeros((n, n, n), np.int16)
    xx, yy, zz = np.mgrid[:n, :n, :n]
    c = (n - 1) / 2.0
    ptv = (np.abs(xx - c) <= 2) & (np.abs(yy - c) <= 2) & (np.abs(zz - c) <= 2)
    oar = (np.abs(xx - c) <= 4) & (yy - c > 3) & (yy - c <= 5) & (np.abs(zz - c) <= 2)
    vol = _CT(imageArray=ct, origin=(-c * sp, -c * sp, -c * sp), spacing=(sp, sp, sp), patient=_Patient())
    return _LoadedCT(ct=vol, patient=vol.patient, contours=[_Contour("PTV", ptv), _Contour("OAR", oar)])


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Dev settings, the stub loader, and two custom machines whose minimum MU is 0: the analytic
    engine's dose per unit weight is far from a linac's, so its optimized weights are tiny."""
    import json
    from radiarch.config import get_settings
    from radiarch.services.geometry import GeometryService
    from radiarch.services.machine_model import load_photon_spec

    library = tmp_path / "machines"
    for base, mid in (("synthetic-120", "test-120"), ("synthetic-160", "test-160")):
        spec = load_photon_spec(base).model_dump()
        spec.update({"machine_id": mid, "min_mu_per_segment": 0.0, "min_segment_area_mm2": 0.0})
        (library / mid).mkdir(parents=True)
        (library / mid / "machine.json").write_text(json.dumps(spec))
    for k, v in {"RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
                 "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://",
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path), "RADIARCH_ALLOW_TEST_ENGINES": "1", "RADIARCH_API_KEY": "",
                 "RADIARCH_BEAM_LIBRARY_DIR": str(library)}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr(GeometryService, "_load", lambda self, _req: _loaded_ct())
    yield tmp_path
    get_settings.cache_clear()


def _pipeline():
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.geometry import GeometryService
    from radiarch.services.optimization import OptimizationService

    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id="test-120",
        beam_set=BeamSetSpec(beams=[BeamSpec(beam_id="B1", gantry_deg=0.0), BeamSpec(beam_id="B2", gantry_deg=90.0)]),
        delivery_params=DeliveryParams(jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0)),
    ))
    objectives = [ObjectiveSpec(type="DUniform", structure_name="PTV", dose_gy=2.0, weight=1.0),
                  ObjectiveSpec(type="DMax", structure_name="OAR", dose_gy=0.5, weight=1.0)]
    opt = OptimizationService().run(OptimizationRunRequest(
        geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=EngineSpec(name="analytic"),
        objectives=objectives, solver=SolverConfig(method="L-BFGS-B", max_iterations=50),
    ))
    return geo, bm, opt, objectives


def test_sequence_through_the_services(env):
    from radiarch.models.evaluation import EvaluationRequest
    from radiarch.services.apertures import ApertureService
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.dose import DoseService
    from radiarch.services.evaluation import EvaluationService

    geo, bm, opt, objectives = _pipeline()
    svc = ApertureService()
    res = svc.sequence(opt.optimization_id, SequenceRequest(objectives=objectives, levels=5, max_iterations=50))
    assert res.optimization_id == opt.optimization_id and res.machine_model_id == "test-120"
    assert res.n_segments == len(res.segment_mu) == sum(res.segments_per_beam.values()) >= 1
    assert all(mu >= 0.0 for mu in res.segment_mu) and res.total_mu == pytest.approx(sum(res.segment_mu))
    assert res.dose_units == "Gy" and res.deliverability and res.deliverable

    # the aperture plan is a beam model with segments, jaws and MLC rows
    new_bm = BeamModelService().store.get_by_id(res.beam_model_id)
    plan = BeamModelService().store.load_plan(res.beam_model_id)
    assert new_bm is not None and new_bm.fluence_elements.total_count == plan.n_beamlets > 0
    for beam in plan.beams:
        assert beam.energy_mv == 6.0
        for seg in beam.segments:
            assert seg.mu >= 0.0 and seg.mlc_rows and seg.x_jaw_mm[1] > seg.x_jaw_mm[0]
            assert all(r.y_max_mm - r.y_min_mm in (5.0, 10.0) for r in seg.mlc_rows)

    # the segment dose is a dose result the evaluation can read
    dose = DoseService().dose_store.get_by_id(res.dose_id)
    assert dose is not None and dose.engine_name == "analytic+segments" and Path(dose.dose_grid_uri).is_file()
    ev = EvaluationService().run(EvaluationRequest(dose_id=res.dose_id, geometry_id=geo.geometry_id, prescription_gy=2.0, target_structure="PTV"))
    assert ev.indices is not None and ev.indices.hotspot_gy > 0        # the analytic engine has the wrong physics by design

    # cached on the same request; a second machine gives a different result
    assert svc.sequence(opt.optimization_id, SequenceRequest(objectives=objectives, levels=5, max_iterations=50)).sequence_id == res.sequence_id
    other = svc.sequence(opt.optimization_id, SequenceRequest(objectives=objectives, levels=5, max_iterations=50, machine_model_id="test-160"))
    assert other.sequence_id != res.sequence_id and other.machine_model_id == "test-160"
    with pytest.raises(ValueError, match="minimum MU"):        # a real machine's 2 MU floor on the analytic engine's tiny weights
        svc.sequence(opt.optimization_id, SequenceRequest(objectives=objectives, levels=5, max_iterations=50, machine_model_id="synthetic-120"))
    assert svc.store.get_by_id(res.sequence_id).n_segments == res.n_segments

    with pytest.raises(ValueError, match="not found"):
        svc.sequence("nope", SequenceRequest(objectives=objectives))


def test_sequence_endpoint(env, monkeypatch):
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.app import create_app
    from radiarch.core import store as store_module

    geo, bm, opt, objectives = _pipeline()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    app = create_app()
    with TestClient(app) as client:
        r = client.post(f"/api/v1/optimize/{opt.optimization_id}/sequence",
                        json={"objectives": [o.model_dump() for o in objectives], "levels": 4, "max_iterations": 30})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_segments"] >= 1 and body["beam_model_id"] and body["dose_id"]
        assert client.get(f"/api/v1/optimize/sequences/{body['sequence_id']}").status_code == 200
        assert client.post("/api/v1/optimize/missing/sequence", json={"objectives": [o.model_dump() for o in objectives]}).status_code == 404
    store_module.reset_store()
