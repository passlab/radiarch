"""R6 through the services and the API: geometry → beam model → optimization → apertures → RT objects,
an imported ion plan → RT Ion Plan, treatment records, and the push."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pydicom
import pytest

import dicom_fixtures as F
from radiarch.dicom import read_rtdose, read_rtplan
from radiarch.dicom.rtstruct import read_rtstruct
from radiarch.models.apertures import SequenceRequest
from radiarch.models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
from radiarch.models.dose import EngineSpec
from radiarch.models.geometry import GeometryBuildRequest, PatientRef
from radiarch.models.optimization import ObjectiveSpec, OptimizationRunRequest, SolverConfig
from radiarch.models.rt_export import PrescriptionSpec, RTExportRequest, RTRecordRequest, SessionSpec

FOR = "1.2.826.0.1.3680043.8.498.6001"
SERIES = "1.2.826.0.1.3680043.8.498.6002"


@dataclass
class _Patient:
    name: str = "EXPORT^R6"
    id: str = "R6-SVC"
    birth_date: str = "19700101"
    sex: str = "M"


@dataclass
class _CT:
    imageArray: np.ndarray
    origin: Tuple[float, float, float]
    spacing: Tuple[float, float, float]
    patient: _Patient
    seriesInstanceUID: str = SERIES
    studyInstanceUID: str = "1.2.826.0.1.3680043.8.498.6000"
    frameOfReferenceUID: str = FOR
    sopInstanceUIDs: List[str] = field(default_factory=lambda: [f"{SERIES}.{k}" for k in range(16)])
    patientPosition: str = "HFS"
    studyDate: str = "20261021"
    studyDescription: str = "R6 export"


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
    import json
    from radiarch.config import get_settings
    from radiarch.services.geometry import GeometryService
    from radiarch.services.machine_model import load_photon_spec

    library = tmp_path / "machines"
    spec = load_photon_spec("synthetic-120").model_dump()
    spec.update({"machine_id": "test-120", "min_mu_per_segment": 0.0, "min_segment_area_mm2": 0.0})
    (library / "test-120").mkdir(parents=True)
    (library / "test-120" / "machine.json").write_text(json.dumps(spec))
    for k, v in {"RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
                 "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://",
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path), "RADIARCH_ALLOW_TEST_ENGINES": "1", "RADIARCH_API_KEY": "",
                 "RADIARCH_BEAM_LIBRARY_DIR": str(library), "RADIARCH_DICOMWEB_URL": ""}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr(GeometryService, "_load", lambda self, _req: _loaded_ct())
    yield tmp_path
    get_settings.cache_clear()


def _photon_pipeline():
    from radiarch.services.apertures import ApertureService
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
    seq = ApertureService().sequence(opt.optimization_id, SequenceRequest(objectives=objectives, levels=5, max_iterations=50))
    return geo, bm, opt, seq


def test_export_an_aperture_sequence(env):
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.rt_export import RTExportError, RTExportService

    geo, bm, opt, seq = _photon_pipeline()
    svc = RTExportService()
    res = svc.export(RTExportRequest(sequence_id=seq.sequence_id, label="R6TEST", prescription=PrescriptionSpec(dose_gy=2.0, fractions=2),
                                     per_beam_dose=True, drr_size_mm=(80.0, 80.0), drr_pixel_mm=(2.0, 2.0)))
    kinds = sorted(o.kind for o in res.objects)
    n_beams = len(seq.segments_per_beam)
    assert kinds == sorted(["RTSTRUCT", "RTPLAN", "RTDOSE"] + ["RTDOSE"] * n_beams + ["RTIMAGE"] * n_beams)
    assert res.modality is Modality.photon_imrt and res.geometry_id == geo.geometry_id and res.beam_model_id == seq.beam_model_id
    assert res.frame_of_reference_uid == FOR and res.study_instance_uid == "1.2.826.0.1.3680043.8.498.6000"
    assert all(Path(o.path).is_file() and o.size_bytes > 0 for o in res.objects)
    assert svc.get(res.export_id) == res and svc.file_path(res.export_id, "RP.dcm").is_file()

    # the plan reads back as the aperture plan the sequence stored, MU for MU
    plan = BeamModelService().store.load_plan(seq.beam_model_id)
    back = read_rtplan(svc.file_path(res.export_id, "RP.dcm"))
    assert [b.beam_id for b in back.beams] == [b.beam_id for b in plan.beams]
    for b0, b1 in zip(plan.beams, back.beams):
        assert [s.mu for s in b1.segments] == pytest.approx([s.mu for s in b0.segments], rel=1e-5)
        assert b1.gantry_deg == b0.gantry_deg and b1.isocenter_mm == pytest.approx(b0.isocenter_mm)
    assert res.beam_metersets == pytest.approx({b.beam_id: sum(s.mu for s in b.segments) for b in plan.beams}, rel=1e-5)
    ds = pydicom.dcmread(svc.file_path(res.export_id, "RP.dcm"))
    assert int(ds.FractionGroupSequence[0].NumberOfFractionsPlanned) == 2 and ds.RTPlanLabel == "R6TEST"
    rois = {str(r.ROIName): int(r.ROINumber) for r in pydicom.dcmread(svc.file_path(res.export_id, "RS.dcm")).StructureSetROISequence}
    assert rois == {"PTV": 1, "OAR": 2} and int(ds.DoseReferenceSequence[0].ReferencedROINumber) == 1
    assert ds.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID == res.rtstruct_uid

    # the structure set reads back onto the geometry's grid
    st = read_rtstruct(svc.file_path(res.export_id, "RS.dcm"))
    assert [c.name for c in st.contours] == ["PTV", "OAR"] and len(st.contours[0].polygonMesh) == 4

    # the plan dose is the sequence's dose; beam doses sum to it (the analytic engine is linear)
    from radiarch.services.dose import DoseService
    import SimpleITK as sitk
    stored = sitk.GetArrayFromImage(sitk.ReadImage(DoseService().dose_store.get_by_id(seq.dose_id).dose_grid_uri)).astype(np.float32)
    plan_dose = read_rtdose(svc.file_path(res.export_id, "RD.dcm")).dose_zyx
    assert np.allclose(plan_dose, stored, atol=stored.max() * 1e-6)
    beam_doses = [read_rtdose(o.path).dose_zyx for o in res.objects if o.kind == "RTDOSE" and o.summation == "BEAM"]
    assert len(beam_doses) == n_beams and np.allclose(sum(beam_doses), plan_dose, atol=plan_dose.max() * 1e-3)
    drr = pydicom.dcmread(next(o.path for o in res.objects if o.kind == "RTIMAGE"))
    assert drr.Rows == drr.Columns == 40 and drr.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID == res.plan_sop_instance_uid

    # a photon optimization is not deliverable until sequenced
    with pytest.raises(RTExportError, match="sequence it first"):
        svc.export(RTExportRequest(optimization_id=opt.optimization_id))
    with pytest.raises(RTExportError, match="not found"):
        svc.export(RTExportRequest(sequence_id="nope"))
    with pytest.raises(RTExportError, match="no dose to write"):
        svc.export(RTExportRequest(beam_model_id=bm.beam_model_id))

    # records: two sessions, then the summary of the course
    rec = svc.records(res.export_id, RTRecordRequest(sessions=[SessionSpec(fraction_number=1, treatment_date="20261101")]))
    assert [o.kind for o in rec.objects] == ["RTRECORD", "RTSUMMARY"] and rec.fractions_delivered == 1 and rec.status == "ON_TREATMENT"
    rec2 = svc.records(res.export_id, RTRecordRequest(sessions=[SessionSpec(fraction_number=2, treatment_date="20261102", delivered=0.5, termination="MACHINE")]))
    assert rec2.fractions_delivered == 2 and rec2.status == "COMPLETED"
    manifest = svc.get(res.export_id)
    assert sorted(o.fraction_number for o in manifest.objects if o.kind == "RTRECORD") == [1, 2]
    assert sum(1 for o in manifest.objects if o.kind == "RTSUMMARY") == 1
    sm = pydicom.dcmread(next(o.path for o in manifest.objects if o.kind == "RTSUMMARY"))
    fg = sm.FractionGroupSummarySequence[0]
    assert int(fg.NumberOfFractionsDelivered) == 2 and [str(f.TreatmentTerminationStatus) for f in fg.FractionStatusSummarySequence] == ["NORMAL", "MACHINE"]
    assert float(sm.TreatmentSummaryCalculatedDoseReferenceSequence[0].CumulativeDoseToDoseReference) == pytest.approx(2.0 * 1.5 / 2)
    r2 = pydicom.dcmread(next(o.path for o in rec2.objects if o.kind == "RTRECORD"))
    assert r2.ReferencedTreatmentRecordSequence[0].ReferencedSOPInstanceUID == rec.objects[0].sop_instance_uid

    # every object is the same patient, study and frame
    for o in manifest.objects:
        d = pydicom.dcmread(o.path, stop_before_pixels=True)
        assert d.PatientID == "R6-SVC" and d.StudyInstanceUID == res.study_instance_uid and d.PatientSex == "M"


def test_export_an_imported_ion_plan(env, tmp_path):
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.geometry import GeometryService
    from radiarch.services.plan_import import import_rtplan
    from radiarch.services.rt_export import RTExportService

    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    ds = F.ion_rtplan([{"number": 1, "name": "PA", "gantry": 180.0, "iso": (0, 0, 0), "range_shifter_id": "RS40",
                        "layers": [(150.0, [(0, 0, 0.5), (10, 0, 0.5)], {"setting": "IN", "distance": 300.0}),
                                   (120.0, [(0, 10, 1.0)], {"setting": "IN", "distance": 300.0})]}], {1: 100.0}, n_fractions=5, for_uid=FOR)
    path = F.save(ds, tmp_path / "ionplan.dcm")
    imported = import_rtplan(path, geo, BeamModelService().store)
    res = RTExportService().export(RTExportRequest(beam_model_id=imported.beam_model.beam_model_id, objects=["rtstruct", "rtplan", "rtimage"],
                                                   drr_size_mm=(60.0, 60.0), drr_pixel_mm=(3.0, 3.0), machine_name="PROTON1"))
    assert sorted(o.kind for o in res.objects) == ["RTIMAGE", "RTIONPLAN", "RTSTRUCT"] and res.modality is Modality.proton_pbs
    back = read_rtplan(next(o.path for o in res.objects if o.kind == "RTIONPLAN"))
    b = back.beams[0]
    assert back.n_fractions == 5 and b.name == "PA" and b.gantry_deg == 180.0 and b.n_spots == 3 and b.meterset == pytest.approx(100.0)
    assert [s.mu for l in b.layers for s in l.spots] == pytest.approx([25.0, 25.0, 50.0]) and b.range_shifter_id == "RS40"
    plan = pydicom.dcmread(next(o.path for o in res.objects if o.kind == "RTIONPLAN"))
    assert plan.IonBeamSequence[0].TreatmentMachineName == "PROTON1" and len(plan.IonBeamSequence[0].VirtualSourceAxisDistances) == 2
    rec = RTExportService().records(res.export_id, RTRecordRequest(sessions=[SessionSpec(fraction_number=1, treatment_date="20261105")], summary=False))
    assert [o.kind for o in rec.objects] == ["RTRECORD"] and rec.objects[0].sop_class_uid.endswith("481.9")
    r = pydicom.dcmread(rec.objects[0].path)
    assert float(r.TreatmentSessionIonBeamSequence[0].DeliveredPrimaryMeterset) == pytest.approx(100.0)


def test_export_endpoints(env, monkeypatch):
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.app import create_app
    from radiarch.core import store as store_module

    geo, bm, opt, seq = _photon_pipeline()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/api/v1/rt/export", json={"sequence_id": seq.sequence_id, "objects": ["rtstruct", "rtplan", "rtdose"],
                                                   "prescription": {"dose_gy": 2.0, "fractions": 3, "target_structure": "PTV"}})
        assert r.status_code == 200, r.text
        body = r.json()
        export_id = body["export_id"]
        assert sorted(o["kind"] for o in body["objects"]) == ["RTDOSE", "RTPLAN", "RTSTRUCT"] and body["n_fractions"] == 3
        assert body["disclaimer"].startswith("RESEARCH USE ONLY")
        assert client.get(f"/api/v1/rt/exports/{export_id}").json()["export_id"] == export_id
        f = client.get(f"/api/v1/rt/exports/{export_id}/files/RP.dcm")
        assert f.status_code == 200 and f.headers["content-type"].startswith("application/dicom") and f.content[128:132] == b"DICM"
        assert client.get(f"/api/v1/rt/exports/{export_id}/files/nope.dcm").status_code == 404
        rec = client.post(f"/api/v1/rt/exports/{export_id}/records",
                          json={"sessions": [{"fraction_number": 1, "treatment_date": "20261110"}, {"fraction_number": 2, "treatment_date": "20261111"}]})
        assert rec.status_code == 200, rec.text
        assert rec.json()["fractions_delivered"] == 2 and rec.json()["status"] == "ON_TREATMENT"
        # pushing to nowhere reports the error instead of raising
        p = client.post(f"/api/v1/rt/exports/{export_id}/push", json={"url": "http://127.0.0.1:9/dicom-web"})
        assert p.status_code == 200 and p.json()["pushed"] == 0 and p.json()["error"]
        assert client.post("/api/v1/rt/export", json={"sequence_id": "missing"}).status_code == 404
        assert client.post("/api/v1/rt/export", json={"optimization_id": opt.optimization_id}).status_code == 422
        assert client.post("/api/v1/rt/export", json={}).status_code == 422
        assert client.get("/api/v1/rt/exports/missing").status_code == 404
    store_module.reset_store()
