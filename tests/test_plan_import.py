"""Importing a DICOM RT Plan as a beam model and recalculating its dose (roadmap R2)."""

from __future__ import annotations

import tempfile
import types
from pathlib import Path

import numpy as np
import pytest

import dicom_fixtures as F
from radiarch.models.beam_model import Modality
from radiarch.services.beam_persistence import BeamModelStore
from radiarch.services.plan_import import PlanImportError, find_rtplan_files, import_rtplan

FOR = "1.2.826.0.1.3680043.8.498.1"


def _geometry(for_uid=FOR):
    return types.SimpleNamespace(
        geometry_id="g-1", frame_of_reference_uid=for_uid,
        grid_spec=types.SimpleNamespace(origin_mm=(-100.0, -100.0, -100.0), spacing_mm=(2.0, 2.0, 2.0), size=(100, 100, 100)),
    )


def _ion_plan_file(tmp_path, **kw):
    ds = F.ion_rtplan([{"number": 1, "gantry": 0.0, "iso": (0, 0, 0),
                        "layers": [(150.0, [(0, 0, 0.5), (10, 0, 0.5)], None), (120.0, [(0, 10, 1.0)], None)]}], {1: 100.0}, **kw)
    return F.save(ds, tmp_path / "ionplan.dcm")


def _photon_plan_file(tmp_path, **kw):
    cps = [{"cmw": 0.0, "gantry": 0.0, "iso": [0, 0, 0], "xj": [-50, 50], "yj": [-50, 50]}, {"cmw": 1.0}]
    ds = F.photon_rtplan([{"number": 1, "name": "AP", "cps": cps}], {1: 200.0}, **kw)
    return F.save(ds, tmp_path / "plan.dcm")


class TestImportService:
    def test_ion_plan_becomes_a_proton_beam_model_with_its_metersets(self, tmp_path):
        store = BeamModelStore(tmp_path / "bm")
        path = _ion_plan_file(tmp_path)
        imported = import_rtplan(path, _geometry(), store)
        bm = imported.beam_model
        assert bm.modality is Modality.proton_pbs and bm.geometry_id == "g-1"
        assert bm.fluence_elements.total_count == 3
        assert bm.fluence_elements.per_beam[0].energy_layers == [150.0, 120.0]
        assert bm.fluence_elements.per_beam[0].spots_per_layer == [2, 1]
        assert bm.imported_plan.sop_class == "RTIONPLAN" and bm.plan_weights_uri.endswith("plan_weights.npy")
        np.testing.assert_allclose(np.load(bm.plan_weights_uri), [25.0, 25.0, 50.0])
        assert store.get_by_id(bm.beam_model_id) is not None and store.load_plan(bm.beam_model_id).n_spots == 3
        again = import_rtplan(path, _geometry(), store)          # the same object again: reused
        assert again.reused and again.beam_model.beam_model_id == bm.beam_model_id
        fresh = import_rtplan(_ion_plan_file(tmp_path), _geometry(), store)   # re-exported with new UIDs: a new model
        assert not fresh.reused and fresh.beam_model.beam_model_id != bm.beam_model_id

    def test_photon_plan_becomes_a_photon_beam_model(self, tmp_path):
        store = BeamModelStore(tmp_path / "bm")
        imported = import_rtplan(_photon_plan_file(tmp_path), _geometry(), store, beamlet_spacing_mm=(10.0, 10.0))
        bm = imported.beam_model
        assert bm.modality is Modality.photon_imrt
        assert bm.fluence_elements.total_count == 100            # 100 mm field at 10 mm beamlets
        assert np.load(bm.plan_weights_uri).shape == (100,) and float(np.load(bm.plan_weights_uri)[0]) == 200.0

    def test_frame_of_reference_is_checked(self, tmp_path):
        store = BeamModelStore(tmp_path / "bm")
        path = _ion_plan_file(tmp_path, for_uid="1.2.826.0.1.3680043.8.498.999")
        with pytest.raises(PlanImportError, match="frame of reference"):
            import_rtplan(path, _geometry(), store)
        imported = import_rtplan(path, _geometry(), store, strict_frame_of_reference=False)
        assert imported.beam_model.imported_plan.frame_of_reference_uid.endswith(".999")

    def test_find_rtplan_files(self, tmp_path):
        _ion_plan_file(tmp_path)
        (tmp_path / "notes.txt").write_text("x")
        F.save(F.rtdose(np.ones((2, 2, 2), dtype=np.float32), (1, 1, 1), (0, 0, 0)), tmp_path / "dose.dcm")
        assert [p.name for p in find_rtplan_files(tmp_path)] == ["ionplan.dcm"]


# ---------------------------------------------------------------------------
# The API, end to end on the SimpleFantom geometry
# ---------------------------------------------------------------------------

class TestImportAndRecalculateApi:
    @pytest.fixture
    def env(self, monkeypatch):
        from radiarch.validation import goldens as G

        if not G.SIMPLEFANTOM.is_dir():
            pytest.skip("SimpleFantom test data not present")
        tmp = tempfile.TemporaryDirectory(prefix="radiarch-r2-")
        work = Path(tmp.name)
        for k, v in {
            "RADIARCH_API_KEY": "k", "RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true",
            "RADIARCH_DATABASE_URL": "", "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://",
            "RADIARCH_ARTIFACT_DIR": str(work), "RADIARCH_MCSQUARE_SEED": "7", "RADIARCH_MCSQUARE_N_THREADS": "1",
        }.items():
            monkeypatch.setenv(k, v)
        from radiarch.config import get_settings
        get_settings.cache_clear()
        import radiarch.api.routes.beam_model as bm_route
        import radiarch.api.routes.dose as dose_route
        from radiarch.core import store as store_module
        store_module.reset_store()
        bm_route._service.cache_clear()
        dose_route._service.cache_clear()
        geo, geo_svc, bm, bm_svc = G.build_simplefantom(work)      # geometry under {work}/geometry = the app's store
        from fastapi.testclient import TestClient
        from radiarch.app import create_app
        with TestClient(create_app()) as client:
            yield client, geo, work
        get_settings.cache_clear()

    def _import(self, client, geo, path, **extra):
        r = client.post("/api/v1/beam-model/import", headers={"X-API-Key": "k"},
                        json={"geometry_id": geo.geometry_id, "path": str(path), **extra})
        assert r.status_code == 200, r.text
        return r.json()

    def test_import_then_recalculate_with_the_analytic_engine(self, env):
        client, geo, work = env
        ds = F.ion_rtplan([{"number": 1, "gantry": 0.0, "iso": (0, 0, 0),
                            "layers": [(150.0, [(0, 0, 0.5), (10, 0, 0.5)], None)]}], {1: 100.0},
                          for_uid=geo.frame_of_reference_uid or FOR)
        path = F.save(ds, work / "ion.dcm")
        bm = self._import(client, geo, path)
        assert bm["modality"] == "PROTON_PBS" and bm["fluence_elements"]["total_count"] == 2 and bm["plan_weights_uri"]
        assert bm["disclaimer"].startswith("RESEARCH USE ONLY")

        r = client.post("/api/v1/dose/recalculate", headers={"X-API-Key": "k"},
                        json={"geometry_id": geo.geometry_id, "beam_model_id": bm["beam_model_id"],
                              "engine": {"name": "analytic", "params": {}}})
        assert r.status_code in (200, 202), r.text
        if r.status_code == 202:
            job = client.get(f"/api/v1/dose/jobs/{r.json()['job_id']}", headers={"X-API-Key": "k"}).json()
            assert job["state"] == "succeeded", job
            dose_id = job["dose_id"]
        else:
            dose_id = r.json()["dose_id"]
        dose = client.get(f"/api/v1/dose/{dose_id}", headers={"X-API-Key": "k"}).json()
        assert dose["beam_model_id"] == bm["beam_model_id"] and dose["statistics"]["max_gy"] > 0

    def test_recalculate_refuses_a_built_beam_model(self, env):
        client, geo, work = env
        from radiarch.services.beam_persistence import BeamModelStore
        built = BeamModelStore(work / "beam_models").list_ids()
        assert built, "the fixture built a beam model"
        r = client.post("/api/v1/dose/recalculate", headers={"X-API-Key": "k"},
                        json={"geometry_id": geo.geometry_id, "beam_model_id": built[0], "engine": {"name": "analytic"}})
        assert r.status_code == 422 and "not imported" in r.json()["detail"]

    def test_import_errors(self, env):
        client, geo, work = env
        r = client.post("/api/v1/beam-model/import", headers={"X-API-Key": "k"},
                        json={"geometry_id": "nope", "path": str(work / "x.dcm")})
        assert r.status_code == 404
        r = client.post("/api/v1/beam-model/import", headers={"X-API-Key": "k"},
                        json={"geometry_id": geo.geometry_id, "path": str(work / "missing.dcm")})
        assert r.status_code == 422
        wrong = F.save(F.ion_rtplan([{"number": 1, "layers": [(100.0, [(0, 0, 1.0)], None)]}], {1: 1.0}, for_uid="9.9.9"), work / "wrong.dcm")
        r = client.post("/api/v1/beam-model/import", headers={"X-API-Key": "k"},
                        json={"geometry_id": geo.geometry_id, "path": str(wrong)})
        if geo.frame_of_reference_uid:
            assert r.status_code == 422 and "frame of reference" in r.json()["detail"]
        else:   # the phantom CT carries no frame of reference, so nothing can be compared
            assert r.status_code == 200

    def test_recalculated_mcsquare_dose_equals_the_engine_on_the_same_plan(self, env):
        """The imported plan reproduces the plan it was written from: the recalculated
        dose equals the engine's dose for the model plan at a fixed seed."""
        from radiarch.services.dose_engines.mcsquare_driver import MCsquareAssets, default_assets_dir
        if not MCsquareAssets(default_assets_dir()).availability()[0]:
            pytest.skip("MCsquare binaries not available")
        client, geo, work = env
        from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot
        from radiarch.services.dose_engines.mcsquare_driver import MCsquareDriver
        from radiarch.services.geometry_bundle import load_ct_hu

        spots = [(0.0, 0.0, 0.4), (8.0, -4.0, 0.6)]
        ds = F.ion_rtplan([{"number": 1, "gantry": 0.0, "iso": (0, 0, 0), "layers": [(140.0, spots, None)]}], {1: 50.0},
                          for_uid=geo.frame_of_reference_uid or FOR)
        bm = self._import(client, geo, F.save(ds, work / "mc.dcm"))
        r = client.post("/api/v1/dose/recalculate", headers={"X-API-Key": "k"},
                        json={"geometry_id": geo.geometry_id, "beam_model_id": bm["beam_model_id"],
                              "engine": {"name": "mcsquare", "params": {"nb_primaries": 3000, "seed": 7, "nb_threads": 1}}})
        assert r.status_code in (200, 202), r.text
        if r.status_code == 202:
            job = client.get(f"/api/v1/dose/jobs/{r.json()['job_id']}", headers={"X-API-Key": "k"}).json()
            assert job["state"] == "succeeded", job
            dose_id = job["dose_id"]
        else:
            dose_id = r.json()["dose_id"]
        import SimpleITK as sitk
        recalculated = sitk.GetArrayFromImage(sitk.ReadImage(client.get(f"/api/v1/dose/{dose_id}", headers={"X-API-Key": "k"}).json()["dose_grid_uri"]))

        plan = ProtonPlan(beams=[ProtonBeam(beam_id="1", gantry_deg=0.0, isocenter_mm=(0, 0, 0),
                                            layers=[ProtonLayer(energy_mev=140.0, spots=[ProtonSpot(x_mm=x, y_mm=y, mu=w * 50.0) for x, y, w in spots])])])
        ct_hu = load_ct_hu(geo)
        direct = MCsquareDriver(work_root=work / "direct", n_threads=1, seed=7).compute_dose(
            ct_hu, tuple(geo.grid_spec.spacing_mm), tuple(geo.grid_spec.origin_mm), plan, nb_primaries=3000)
        assert recalculated.shape == direct.shape
        # the service stores proton dose in Gy(RBE) with RBE 1.1 (R3); the driver returns physical Gy
        result = client.get(f"/api/v1/dose/{dose_id}", headers={"X-API-Key": "k"}).json()
        assert result["dose_units"] == "Gy(RBE)" and result["rbe_factor"] == 1.1
        np.testing.assert_allclose(recalculated, 1.1 * direct, rtol=1e-5, atol=1e-6 * direct.max())
