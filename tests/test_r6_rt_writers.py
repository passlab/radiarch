"""R6: the DICOM RT writers — round trips through radiarch's readers, the IOD
validators (dicom-validator; dciodvfy when installed) and an opt-in round
trip through a DICOMweb server (``RADIARCH_TEST_DICOMWEB_URL``)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom
import pytest

from radiarch.dicom import read_rtdose, read_rtplan
from radiarch.dicom.drr import beam_frame, compute_drr
from radiarch.dicom.rtstruct import read_rtstruct
from radiarch.dicom.uids import SOP
from radiarch.dicom.writers import (
    CaseContext, CourseSummary, PlanWriteOptions, Prescription, Session, Structure, write_rtdose, write_rtimage, write_rtplan,
    write_rtstruct, write_summary_record, write_treatment_record,
)
from radiarch.dicom.writers.rtstruct import interpreted_type, mask_to_polygons
from radiarch.models.common import NOT_FOR_CLINICAL_USE
from radiarch.models.photon_plan import MLCRow, PhotonBeam, PhotonPlan, PhotonSegment
from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot, RangeShifterSetting

N, SP = 24, (2.0, 2.0, 3.0)
ORIGIN = (-(N - 1) / 2 * SP[0], -(N - 1) / 2 * SP[1], -(N - 1) / 2 * SP[2])


def _case():
    ct = np.full((N, N, N), -1000, np.int16)
    ct[4:20, 4:20, 4:20] = 0
    ct[8:12, 8:12, 8:16] = 800                  # a bone block
    ptv = np.zeros((N, N, N), bool); ptv[10:16, 9:15, 9:15] = True
    body = ct > -500
    ctx = CaseContext(patient_name="R6^Writers", patient_id="R6-1", patient_sex="F", ct_series_instance_uid="1.2.826.0.1.3680043.8.498.7777",
                      ct_sop_instance_uids=[f"1.2.826.0.1.3680043.8.498.7777.{k}" for k in range(N)], now=datetime(2026, 10, 21, 12, 0, 0))
    rows = [MLCRow(y_min_mm=y, y_max_mm=y + 5, x_left_mm=-10 if abs(y) < 10 else 0, x_right_mm=10 if abs(y) < 10 else 0) for y in range(-15, 15, 5)]
    rows2 = [MLCRow(y_min_mm=y, y_max_mm=y + 5, x_left_mm=-5, x_right_mm=15) for y in range(-15, 15, 5)]
    seg = lambda mu, r, k: PhotonSegment(control_point_index=k, mu=mu, x_jaw_mm=(-12, 16), y_jaw_mm=(-15, 15), mlc_rows=r)  # noqa: E731
    pplan = PhotonPlan(name="smoke", beams=[PhotonBeam(beam_id="AP", gantry_deg=0, segments=[seg(50, rows, 0), seg(30, rows2, 1)], energy_mv=6),
                                            PhotonBeam(beam_id="LAT", gantry_deg=90, couch_deg=-10, segments=[seg(40, rows, 0)], energy_mv=6)])
    layers = [ProtonLayer(energy_mev=e, spots=[ProtonSpot(x_mm=x, y_mm=y, mu=1.5) for x in (-5, 0, 5) for y in (-5, 5)],
                          range_shifter=RangeShifterSetting(setting="IN", isocenter_to_range_shifter_mm=300)) for e in (100.0, 110.0)]
    iplan = ProtonPlan(name="ion", n_fractions=30, beams=[ProtonBeam(beam_id="G90", name="G90", gantry_deg=90, isocenter_mm=(0, 0, 0),
                                                                     range_shifter_id="RS40", layers=layers)])
    dose = np.zeros((N, N, N), np.float32); dose[ptv] = 60.0; dose[body & ~ptv] = 10.0
    return ctx, ct, ptv, body, pplan, iplan, dose


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """Every object type written once: paths, UIDs and the inputs they came from."""
    out = tmp_path_factory.mktemp("r6")
    ctx, ct, ptv, body, pplan, iplan, dose = _case()
    rs = write_rtstruct(ctx, [Structure("PTV", mask_zyx=ptv), Structure("Body", mask_zyx=body)], out / "RS.dcm", origin_mm=ORIGIN, spacing_mm=SP)
    plan_uid = "1.2.826.0.1.3680043.8.498.9999"
    drr = compute_drr(ct, ORIGIN, SP, (0, 0, 0), 0.0, sad_mm=1000, size_mm=(60, 60), pixel_mm=(1, 1))
    im = write_rtimage(ctx, drr, out / "RI.dcm", beam_number=1, beam_name="AP", plan_sop_class=SOP.RTPLAN, plan_sop_instance=plan_uid)
    opt = PlanWriteOptions(label="SMOKE", prescription=Prescription(dose_gy=60, fractions=30, target_name="PTV", target_roi_number=1),
                           drr_refs={"AP": (SOP.RTIMAGE, im.sop_instance_uid)}, sop_instance_uid=plan_uid)
    rp = write_rtplan(ctx, pplan, out / "RP.dcm", rtstruct_uid=rs.sop_instance_uid, options=opt)
    rd = write_rtdose(ctx, dose, ORIGIN, SP, out / "RD.dcm", plan_sop_class=rp.sop_class_uid, plan_sop_instance=rp.sop_instance_uid)
    rdb = write_rtdose(ctx, dose * 0.5, ORIGIN, SP, out / "RD_B1.dcm", plan_sop_class=rp.sop_class_uid, plan_sop_instance=rp.sop_instance_uid,
                       summation="BEAM", beam_number=1, rbe=1.1, dose_units="Gy(RBE)")
    ip = write_rtplan(ctx, iplan, out / "RP_ion.dcm", rtstruct_uid=rs.sop_instance_uid,
                      options=PlanWriteOptions(label="ION", prescription=Prescription(dose_gy=60, fractions=30)))
    s1 = Session(fraction_number=1, treatment_date="20261022")
    s2 = Session(fraction_number=2, treatment_date="20261023", delivered=0.5, termination="OPERATOR", referenced_record_uids=[])
    r1 = write_treatment_record(ctx, pplan, s1, out / "RT1.dcm", plan_sop_instance=rp.sop_instance_uid, options=opt)
    s2.referenced_record_uids = [r1.sop_instance_uid]
    r2 = write_treatment_record(ctx, pplan, s2, out / "RT2.dcm", plan_sop_instance=rp.sop_instance_uid, options=opt)
    ri = write_treatment_record(ctx, iplan, s1, out / "RTI1.dcm", plan_sop_instance=ip.sop_instance_uid)
    sm = write_summary_record(ctx, CourseSummary(sessions=[s1, s2], fractions_planned=30, status="ON_TREATMENT", prescription_dose_gy=60),
                              out / "RTS.dcm", plan_sop_class=rp.sop_class_uid, plan_sop_instance=rp.sop_instance_uid)
    return dict(out=out, ctx=ctx, ct=ct, ptv=ptv, body=body, pplan=pplan, iplan=iplan, dose=dose, rs=rs, rp=rp, rd=rd, rdb=rdb, ip=ip,
                im=im, r1=r1, r2=r2, ri=ri, sm=sm, drr=drr)


# ---------------------------------------------------------------------------
# Round trips through the readers
# ---------------------------------------------------------------------------

def test_rtstruct_round_trip(written):
    st = read_rtstruct(str(written["out"] / "RS.dcm"))
    assert [c.name for c in st.contours] == ["PTV", "Body"] and st.referenced_ct_series_uid == written["ctx"].ct_series_instance_uid
    assert st.frame_of_reference_uid == written["ctx"].frame_of_reference_uid
    for contour, truth in ((st.contours[0], written["ptv"]), (st.contours[1], written["body"])):
        m = contour.getBinaryMask(origin=np.array(ORIGIN), gridSize=np.array([N, N, N]), spacing=np.array(SP)).imageArray
        m = np.transpose(m, (2, 1, 0))
        dice = 2 * np.logical_and(m, truth).sum() / (m.sum() + truth.sum())
        assert dice > 0.99, (contour.name, dice)
    ds = pydicom.dcmread(str(written["out"] / "RS.dcm"))
    obs = {int(o.ReferencedROINumber): str(o.RTROIInterpretedType) for o in ds.RTROIObservationsSequence}
    assert obs == {1: "PTV", 2: "EXTERNAL"} and written["rs"].roi_numbers == {"PTV": 1, "Body": 2}
    series = ds.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0].RTReferencedSeriesSequence[0]
    assert len(series.ContourImageSequence) == N and float(ds.StructureSetROISequence[0].ROIVolume) == pytest.approx(216 * 12 / 1000)


def test_mask_to_polygons_handles_holes_and_islands():
    mask = np.zeros((1, 20, 20), bool)
    mask[0, 2:18, 2:18] = True
    mask[0, 8:12, 8:12] = False          # a hole
    mask[0, 0, 0] = True                 # a single-voxel island at the edge
    polys = mask_to_polygons(mask, (0, 0, 0), (1, 1, 1))
    assert len(polys) == 3 and all(p.shape[0] % 3 == 0 and p.shape[0] >= 9 for p in polys)
    assert interpreted_type("CTV_Prostate") == "CTV" and interpreted_type("SpinalCord") == "ORGAN" and interpreted_type("Couch") == "SUPPORT"


def test_photon_plan_round_trip(written):
    back = read_rtplan(str(written["out"] / "RP.dcm"))
    plan = written["pplan"]
    assert isinstance(back, PhotonPlan) and [b.beam_id for b in back.beams] == ["AP", "LAT"]
    for b0, b1 in zip(plan.beams, back.beams):
        assert b1.gantry_deg == b0.gantry_deg and b1.couch_deg == pytest.approx(b0.couch_deg) and len(b1.segments) == len(b0.segments)
        for s0, s1 in zip(b0.segments, b1.segments):
            assert s1.mu == pytest.approx(s0.mu) and s1.x_jaw_mm == s0.x_jaw_mm and s1.y_jaw_mm == s0.y_jaw_mm
            assert [(r.x_left_mm, r.x_right_mm) for r in s1.mlc_rows] == [(r.x_left_mm, r.x_right_mm) for r in s0.mlc_rows]
    assert back.dicom.n_fractions == 30 and back.dicom.structure_set_uid == written["rs"].sop_instance_uid
    ds = pydicom.dcmread(str(written["out"] / "RP.dcm"))
    ap = ds.BeamSequence[0]
    assert int(ap.NumberOfControlPoints) == 4 and float(ap.FinalCumulativeMetersetWeight) == 80.0
    assert [float(r.BeamMeterset) for r in ds.FractionGroupSequence[0].ReferencedBeamSequence] == [80.0, 40.0]
    assert float(ds.DoseReferenceSequence[0].TargetPrescriptionDose) == 60.0 and int(ds.DoseReferenceSequence[0].ReferencedROINumber) == 1
    assert ap.ReferencedReferenceImageSequence[0].ReferencedSOPInstanceUID == written["im"].sop_instance_uid
    assert ds.RTPlanGeometry == "PATIENT" and ds.ApprovalStatus == "UNAPPROVED" and ds.PlanIntent == "RESEARCH"


def test_ion_plan_round_trip(written):
    back = read_rtplan(str(written["out"] / "RP_ion.dcm"))
    assert isinstance(back, ProtonPlan) and back.n_fractions == 30 and len(back.beams) == 1
    b = back.beams[0]
    assert b.name == "G90" and b.gantry_deg == 90.0 and b.n_spots == 12 and b.meterset == pytest.approx(18.0)
    assert b.range_shifter_id == "RS40" and b.layers[0].range_shifter.setting == "IN"
    assert b.layers[0].range_shifter.isocenter_to_range_shifter_mm == 300.0
    assert [l.energy_mev for l in b.layers] == [100.0, 110.0] and all(s.mu == pytest.approx(1.5) for l in b.layers for s in l.spots)


def test_rtdose_round_trip(written):
    vol = read_rtdose(str(written["out"] / "RD.dcm"))
    assert np.allclose(vol.dose_zyx, written["dose"], atol=1e-5) and vol.spacing_mm == pytest.approx(SP) and vol.origin_mm == pytest.approx(ORIGIN)
    assert vol.referenced_plan_uid == written["rp"].sop_instance_uid and vol.dose_type == "PHYSICAL"
    beam = pydicom.dcmread(str(written["out"] / "RD_B1.dcm"))
    assert beam.DoseType == "EFFECTIVE" and beam.DoseSummationType == "BEAM" and "RBE 1.1" in beam.DoseComment
    ref = beam.ReferencedRTPlanSequence[0].ReferencedFractionGroupSequence[0]
    assert int(ref.ReferencedBeamSequence[0].ReferencedBeamNumber) == 1 and beam.BitsAllocated == 32


# ---------------------------------------------------------------------------
# DRR
# ---------------------------------------------------------------------------

def test_beam_frame_matches_the_spot_placer():
    from radiarch.services.spot_placement import beam_direction
    for g, c in ((0, 0), (90, 0), (180, 0), (270, 0), (45, 30), (300, -20)):
        x, y, d = beam_frame(g, c)
        assert np.allclose(d, beam_direction(g, c), atol=1e-9)
        assert abs(np.dot(x, d)) < 1e-9 and abs(np.dot(y, d)) < 1e-9 and abs(np.dot(x, y)) < 1e-9


def test_drr_sees_the_bone(written):
    ct = written["ct"]
    ap = written["drr"]
    assert ap.image.shape == (60, 60) and ap.image.max() > 0
    # the bone block (x -7..7 mm, y -7..-1 mm, z -10.5..-1.5 mm) at gantry 0 projects onto the BEV at x ≈ 0, y (= patient z) ≈ -6
    rows, cols = ap.image.shape
    u = (np.arange(cols) - (cols - 1) / 2.0); v = ((rows - 1) / 2.0 - np.arange(rows))
    col_bone = np.argmin(np.abs(u - 0)); col_water = np.argmin(np.abs(u - 12))
    row_bone = np.argmin(np.abs(v - (-6)))
    assert ap.image[row_bone, col_bone] > ap.image[row_bone, col_water] * 1.2
    lat = compute_drr(ct, ORIGIN, SP, (0, 0, 0), 90.0, sad_mm=1000, size_mm=(60, 60), pixel_mm=(1, 1))
    assert not np.allclose(lat.image, ap.image)
    ds = pydicom.dcmread(str(written["out"] / "RI.dcm"))
    assert ds.RTImagePlane == "NORMAL" and float(ds.RTImageSID) == float(ds.RadiationMachineSAD) == 1000.0
    assert list(ds.RTImagePosition) == [-29.5, 29.5] and int(ds.ReferencedBeamNumber) == 1 and ds.Rows == ds.Columns == 60
    assert ds.ImageType[2] == "DRR" and ds.PatientPosition == "HFS"


# ---------------------------------------------------------------------------
# Records and context
# ---------------------------------------------------------------------------

def test_treatment_records(written):
    assert written["r1"].delivered_metersets == {"AP": 80.0, "LAT": 40.0} and written["r2"].delivered_metersets == {"AP": 40.0, "LAT": 20.0}
    assert written["ri"].delivered_metersets == {"G90": 18.0}
    r2 = pydicom.dcmread(str(written["out"] / "RT2.dcm"))
    assert r2.ReferencedTreatmentRecordSequence[0].ReferencedSOPInstanceUID == written["r1"].sop_instance_uid
    beam = r2.TreatmentSessionBeamSequence[0]
    assert beam.TreatmentTerminationStatus == "OPERATOR" and int(beam.CurrentFractionNumber) == 2
    assert float(beam.ControlPointDeliverySequence[-1].DeliveredMeterset) == 40.0 and float(beam.ControlPointDeliverySequence[-1].SpecifiedMeterset) == 80.0
    ri = pydicom.dcmread(str(written["out"] / "RTI1.dcm"))
    ion = ri.TreatmentSessionIonBeamSequence[0]
    assert ion.RecordedRangeShifterSequence[0].RangeShifterID == "RS40" and len(ion.IonControlPointDeliverySequence) == 4
    assert sum(ion.IonControlPointDeliverySequence[0].ScanSpotMetersetsDelivered) == pytest.approx(9.0)
    sm = pydicom.dcmread(str(written["out"] / "RTS.dcm"))
    fg = sm.FractionGroupSummarySequence[0]
    assert int(fg.NumberOfFractionsDelivered) == 2 and int(fg.NumberOfFractionsPlanned) == 30 and sm.CurrentTreatmentStatus == "ON_TREATMENT"
    assert float(sm.TreatmentSummaryCalculatedDoseReferenceSequence[0].CumulativeDoseToDoseReference) == pytest.approx(60 * 1.5 / 30)
    assert sm.FirstTreatmentDate == "20261022" and sm.MostRecentTreatmentDate == "20261023"


def test_case_context_is_stable_and_sane():
    a = CaseContext(ct_series_instance_uid="1.2.3.4", patient_sex="Helicopter")
    b = CaseContext(ct_series_instance_uid="1.2.3.4")
    assert a.frame_of_reference_uid == b.frame_of_reference_uid and a.study_instance_uid == b.study_instance_uid
    assert a.patient_sex == "O" and a.patient_position == "HFS" and len(a.frame_of_reference_uid) <= 64
    c = CaseContext(ct_series_instance_uid="1.2.3.4", frame_of_reference_uid="9.9", study_instance_uid="8.8")
    assert c.frame_of_reference_uid == "9.9" and c.study_instance_uid == "8.8"


def test_every_object_says_research_use_only(written):
    for f in sorted(written["out"].glob("*.dcm")):
        ds = pydicom.dcmread(str(f))
        block = ds.private_block(0x7779, "RADIARCH")
        assert block[0x01].value == NOT_FOR_CLINICAL_USE, f.name
        assert NOT_FOR_CLINICAL_USE in str(ds.SeriesDescription) and ds.Manufacturer == "Radiarch", f.name
        assert ds.PatientID == "R6-1" and ds.StudyInstanceUID == written["ctx"].study_instance_uid


# ---------------------------------------------------------------------------
# IOD validation
# ---------------------------------------------------------------------------

def _files(written):
    return sorted(str(p) for p in written["out"].glob("*.dcm"))


def test_iod_validation_with_dicom_validator(written):
    exe = Path(sys.executable).parent / "validate_iods"
    if not exe.is_file():
        exe = shutil.which("validate_iods")
    if not exe:
        pytest.skip("dicom-validator is not installed (pip install dicom-validator)")
    proc = subprocess.run([str(exe), *_files(written)], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 and ("Download" in proc.stdout + proc.stderr or "urlopen" in proc.stderr or "Connection" in proc.stderr):
        pytest.skip("the DICOM standard could not be downloaded for dicom-validator")
    out = proc.stdout + proc.stderr
    assert "Errors" not in out, out
    assert out.count("Validating DICOM file") == len(_files(written))


def test_iod_validation_with_dciodvfy(written):
    exe = shutil.which("dciodvfy")
    if not exe:
        if os.environ.get("RADIARCH_REQUIRE_DCIODVFY"):
            pytest.fail("dciodvfy (dicom3tools) is required but not on PATH")
        pytest.skip("dciodvfy (dicom3tools) is not installed")
    errors = {}
    for f in _files(written):
        proc = subprocess.run([exe, f], capture_output=True, text=True, timeout=120)
        lines = [l for l in (proc.stdout + proc.stderr).splitlines() if l.startswith("Error")]
        if lines:
            errors[Path(f).name] = lines
    assert not errors, errors


# ---------------------------------------------------------------------------
# Opt-in: round trip through a DICOMweb server (Orthanc)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("RADIARCH_TEST_DICOMWEB_URL"), reason="set RADIARCH_TEST_DICOMWEB_URL to a STOW/WADO-RS base URL")
def test_round_trip_through_dicomweb(written, tmp_path):
    from radiarch.adapters.dicomweb import DICOMwebNotifier

    url = os.environ["RADIARCH_TEST_DICOMWEB_URL"]
    notifier = DICOMwebNotifier(url=url, username=os.environ.get("RADIARCH_TEST_DICOMWEB_USER"), password=os.environ.get("RADIARCH_TEST_DICOMWEB_PASSWORD"))
    files = _files(written)
    assert notifier.store_instances(files, raise_errors=True)
    client = notifier._get_client()
    study = written["ctx"].study_instance_uid
    try:
        instances = client.search_for_instances(study)
        got = {i["00080018"]["Value"][0] for i in instances}
        want = {str(pydicom.dcmread(f, stop_before_pixels=True).SOPInstanceUID) for f in files}
        assert want <= got, want - got
        # the plan and the dose read back from the server as they were written
        rp = client.retrieve_instance(study, written["rp"].series_instance_uid, written["rp"].sop_instance_uid)
        back = read_rtplan(rp)
        assert [b.beam_id for b in back.beams] == ["AP", "LAT"] and back.beams[0].segments[0].mu == pytest.approx(50.0)
        rd = client.retrieve_instance(study, written["rd"].series_instance_uid, written["rd"].sop_instance_uid)
        assert np.allclose(read_rtdose(rd).dose_zyx, written["dose"], atol=1e-5)
    finally:
        try:
            client.delete_study(study)
        except Exception:
            # Orthanc's REST API as the fallback
            import requests
            base = url.rsplit("/dicom-web", 1)[0]
            auth = (os.environ.get("RADIARCH_TEST_DICOMWEB_USER"), os.environ.get("RADIARCH_TEST_DICOMWEB_PASSWORD")) if os.environ.get("RADIARCH_TEST_DICOMWEB_USER") else None
            r = requests.post(f"{base}/tools/find", json={"Level": "Study", "Query": {"StudyInstanceUID": study}}, auth=auth, timeout=30)
            for oid in r.json():
                requests.delete(f"{base}/studies/{oid}", auth=auth, timeout=60)
