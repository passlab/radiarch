"""Roadmap R13.1: radiarch's RT objects in a DICOMweb viewer (OHIF reading from Orthanc).

- The structure set carries what OHIF 3.13's RT structure loader reads (extensions/cornerstone-dicom-rt:
  the referenced CT series through the frame of reference, its contour images, closed planar contours,
  display colours), and its contours lie on CT slices.
- A pushed export links to its study in the configured viewer (RADIARCH_VIEWER_URL).
- With RADIARCH_TEST_DICOMWEB_URL (CI runs an Orthanc with its DICOMweb plugin), the CT and the export
  go to the server by STOW-RS and come back by QIDO-RS and WADO-RS in one study, every reference
  resolving to an instance the server holds.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian

from radiarch.models.rt_export import PrescriptionSpec, RTExportRequest

from test_r6_rt_export_service import _loaded_ct, _photon_pipeline, env  # noqa: F401

CT_IMAGE = "1.2.840.10008.5.1.4.1.1.2"


def _export(push: bool = False, new_export: bool = False):
    from radiarch.services.rt_export import RTExportService

    _geo, _bm, _opt, seq = _photon_pipeline()
    svc = RTExportService()
    res = svc.export(RTExportRequest(sequence_id=seq.sequence_id, label="R13", prescription=PrescriptionSpec(dose_gy=2.0, fractions=2),
                                     push=push, new_export=new_export))
    return svc, res


def _ct_slices(out: Path, hu=None, frame_of_reference: bool = True):
    """The stub CT of the export tests as DICOM CT images, one file per slice, with the UIDs the export references.
    ``hu`` replaces its values (a (z, y, x) array), e.g. so a viewer has something to draw; without
    ``frame_of_reference`` the images carry none (some CTs do not)."""
    vol = _loaded_ct().ct
    image = vol.imageArray if hu is None else np.asarray(hu, dtype=np.int16)
    nz, ny, nx = vol.imageArray.shape
    paths = []
    for k in range(nz):
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.MediaStorageSOPClassUID = CT_IMAGE
        ds.file_meta.MediaStorageSOPInstanceUID = vol.sopInstanceUIDs[k]
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID, ds.SOPInstanceUID, ds.Modality = CT_IMAGE, vol.sopInstanceUIDs[k], "CT"
        ds.PatientName, ds.PatientID = vol.patient.name, vol.patient.id
        ds.PatientBirthDate, ds.PatientSex = vol.patient.birth_date, vol.patient.sex
        ds.StudyInstanceUID, ds.SeriesInstanceUID = vol.studyInstanceUID, vol.seriesInstanceUID
        if frame_of_reference:
            ds.FrameOfReferenceUID = vol.frameOfReferenceUID
        ds.StudyDate, ds.StudyTime, ds.StudyID, ds.AccessionNumber = vol.studyDate, "120000", "1", ""
        ds.ReferringPhysicianName, ds.SeriesNumber, ds.InstanceNumber = "", 1, k + 1
        ds.PatientPosition, ds.ImageType = vol.patientPosition, ["ORIGINAL", "PRIMARY", "AXIAL"]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [vol.origin[0], vol.origin[1], vol.origin[2] + k * vol.spacing[2]]
        ds.PixelSpacing, ds.SliceThickness = [vol.spacing[1], vol.spacing[0]], vol.spacing[2]
        ds.Rows, ds.Columns, ds.SamplesPerPixel, ds.PhotometricInterpretation = ny, nx, 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleIntercept, ds.RescaleSlope, ds.KVP = 0, 1, 120
        ds.PixelData = np.ascontiguousarray(image[k], dtype=np.int16).tobytes()
        p = out / f"CT{k:03d}.dcm"
        ds.save_as(str(p), enforce_file_format=True)
        paths.append(p)
    return paths


def test_structure_set_has_what_ohif_reads(env):
    svc, res = _export()
    rs = pydicom.dcmread(svc.file_path(res.export_id, "RS.dcm"))
    vol = _loaded_ct().ct
    ct_uids = set(vol.sopInstanceUIDs)

    # OHIF derives the referenced series from the frame of reference when ReferencedSeriesSequence is absent;
    # every level must be there (it iterates ContourImageSequence without a guard)
    frame = rs.ReferencedFrameOfReferenceSequence[0]
    assert frame.FrameOfReferenceUID == vol.frameOfReferenceUID == res.frame_of_reference_uid
    study = frame.RTReferencedStudySequence[0]
    assert study.ReferencedSOPInstanceUID == vol.studyInstanceUID == rs.StudyInstanceUID
    series = study.RTReferencedSeriesSequence[0]
    assert series.SeriesInstanceUID == vol.seriesInstanceUID
    refs = series.ContourImageSequence
    assert {r.ReferencedSOPInstanceUID for r in refs} == ct_uids and {r.ReferencedSOPClassUID for r in refs} == {CT_IMAGE}

    # ROIs, their contours and colours; every contour plane is a CT slice position
    numbers = {int(r.ROINumber): str(r.ROIName) for r in rs.StructureSetROISequence}
    slice_z = {round(vol.origin[2] + k * vol.spacing[2], 3) for k in range(vol.imageArray.shape[0])}
    assert {int(c.ReferencedROINumber) for c in rs.ROIContourSequence} == set(numbers)
    for roi in rs.ROIContourSequence:
        assert len(roi.ROIDisplayColor) == 3
        assert roi.ContourSequence, numbers[int(roi.ReferencedROINumber)]
        for c in roi.ContourSequence:
            pts = np.asarray(c.ContourData, dtype=float).reshape(-1, 3)
            assert c.ContourGeometricType == "CLOSED_PLANAR" and int(c.NumberOfContourPoints) == len(pts) >= 3
            assert np.ptp(pts[:, 2]) == 0 and round(float(pts[0, 2]), 3) in slice_z


def test_a_pushed_export_links_to_its_study(env, monkeypatch):
    from radiarch.adapters import dicomweb
    from radiarch.config import get_settings
    from radiarch.services.rt_export import RTExportService

    sent = []
    monkeypatch.setattr(dicomweb.DICOMwebNotifier, "store_instances", lambda self, paths, raise_errors=False: sent.extend(paths) or True)
    monkeypatch.setenv("RADIARCH_DICOMWEB_URL", "http://pacs.invalid/dicom-web")
    get_settings.cache_clear()
    svc, res = _export()
    assert res.viewer_url is None                                   # not pushed

    out = svc.push(res.export_id)
    assert out.pushed == len(res.objects) and out.viewer_url is None    # no viewer configured

    monkeypatch.setenv("RADIARCH_VIEWER_URL", "http://ohif.invalid:3000/")
    get_settings.cache_clear()
    out = svc.push(res.export_id)
    link = f"http://ohif.invalid:3000/viewer?StudyInstanceUIDs={res.study_instance_uid}"
    assert out.viewer_url == link and RTExportService().get(res.export_id).viewer_url == link
    assert len(sent) == 2 * len(res.objects)

    # pushed while exporting: the export carries the link; a failed push carries none
    _svc, res2 = _export(push=True)
    assert res2.pushed and res2.viewer_url == link

    monkeypatch.setenv("RADIARCH_VIEWER_ROUTE", "/plan-review/")       # radiarch's viewer
    get_settings.cache_clear()
    assert svc.push(res.export_id).viewer_url == f"http://ohif.invalid:3000/plan-review?StudyInstanceUIDs={res.study_instance_uid}"
    monkeypatch.delenv("RADIARCH_VIEWER_ROUTE")
    get_settings.cache_clear()

    def refuse(self, paths, raise_errors=False):
        raise RuntimeError("unreachable")
    monkeypatch.setattr(dicomweb.DICOMwebNotifier, "store_instances", refuse)
    _svc, res3 = _export(push=True)
    assert not res3.pushed and res3.viewer_url is None and "unreachable" in res3.push_error


@pytest.mark.skipif(not os.environ.get("RADIARCH_TEST_DICOMWEB_URL"),
                    reason="needs a DICOMweb server: RADIARCH_TEST_DICOMWEB_URL (CI runs Orthanc with its DICOMweb plugin)")
def test_push_to_a_dicomweb_server_and_read_back(env, tmp_path):
    from dicomweb_client.api import DICOMwebClient

    from radiarch.adapters.dicomweb import DICOMwebNotifier

    url = os.environ["RADIARCH_TEST_DICOMWEB_URL"].rstrip("/")
    vol = _loaded_ct().ct
    ct_dir = tmp_path / "ct"
    ct_dir.mkdir()
    assert DICOMwebNotifier(url=url).store_instances([str(p) for p in _ct_slices(ct_dir)], raise_errors=True)

    svc, res = _export()
    out = svc.push(res.export_id, url=url)
    assert out.error is None and out.pushed == len(res.objects)

    client = DICOMwebClient(url=url)
    study = res.study_instance_uid
    assert study == vol.studyInstanceUID
    series = {s["0020000E"]["Value"][0]: s["00080060"]["Value"][0] for s in client.search_for_series(study)}
    assert series[vol.seriesInstanceUID] == "CT"
    assert {o.kind for o in res.objects} <= set(series.values())
    for o in res.objects:
        assert series[o.series_instance_uid] == o.kind

    instances = {i["00080018"]["Value"][0] for i in client.search_for_instances(study)}
    assert set(vol.sopInstanceUIDs) | {o.sop_instance_uid for o in res.objects} <= instances

    # the server's metadata of the structure set, plan and dose resolve to instances it holds
    def meta(kind):
        o = next(o for o in res.objects if o.kind == kind)
        return pydicom.Dataset.from_json(client.retrieve_instance_metadata(study, o.series_instance_uid, o.sop_instance_uid))

    rs = meta("RTSTRUCT")
    rs_series = rs.ReferencedFrameOfReferenceSequence[0].RTReferencedStudySequence[0].RTReferencedSeriesSequence[0]
    assert rs_series.SeriesInstanceUID == vol.seriesInstanceUID
    assert {r.ReferencedSOPInstanceUID for r in rs_series.ContourImageSequence} <= instances
    rp = meta("RTPLAN")
    assert rp.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID == res.rtstruct_uid
    rd = meta("RTDOSE")
    assert rd.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID == res.plan_sop_instance_uid in instances
    assert rd.FrameOfReferenceUID == rs.ReferencedFrameOfReferenceSequence[0].FrameOfReferenceUID == vol.frameOfReferenceUID


# --- R13.2a: what a viewer needs from radiarch beyond the objects -------------------------------------------------

def test_the_plan_dose_carries_each_structures_dvh(env):
    from radiarch.dicom.writers.rtdose import DVH_MAX_BINS, dvh_bin_width
    from radiarch.services.dvh import dvh_on_bins

    svc, res = _export()
    rd = pydicom.dcmread(svc.file_path(res.export_id, "RD.dcm"))
    rs = pydicom.dcmread(svc.file_path(res.export_id, "RS.dcm"))
    assert rd.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID == res.rtstruct_uid
    rois = {int(r.ROINumber): str(r.ROIName) for r in rs.StructureSetROISequence}
    dvhs = {int(i.DVHReferencedROISequence[0].ReferencedROINumber): i for i in rd.DVHSequence}
    assert set(dvhs) == set(rois)

    dose = np.frombuffer(rd.PixelData, dtype=np.uint32).reshape(int(rd.NumberOfFrames), rd.Rows, rd.Columns) * float(rd.DoseGridScaling)
    voxel_cc = float(rd.PixelSpacing[0]) * float(rd.PixelSpacing[1]) * float(rd.SliceThickness) / 1000.0
    from radiarch.services.geometry import GeometryService
    from radiarch.services.geometry_bundle import load_geometry_arrays

    arrays = load_geometry_arrays(GeometryService().store.get_by_id(res.geometry_id))
    masks = {name: arrays.mask_zyx(index) for name, index in arrays.structure_index.items()}
    width = dvh_bin_width(float(dose.max()))
    for number, item in dvhs.items():
        mask = masks[rois[number]]
        assert (item.DVHType, item.DoseUnits, item.DVHVolumeUnits, item.DoseType) == ("CUMULATIVE", "GY", "CM3", rd.DoseType)
        data = np.asarray(item.DVHData, dtype=float).reshape(-1, 2)
        assert len(data) == int(item.DVHNumberOfBins) <= DVH_MAX_BINS and np.all(data[:, 0] == width)
        volume = data[:, 1]
        assert volume[0] == pytest.approx(mask.sum() * voxel_cc, rel=1e-5)          # the whole ROI at 0 Gy
        assert np.all(np.diff(volume) <= 1e-9) and volume[-1] > 0                     # cumulative, the last bin holds the maximum
        expected = dvh_on_bins(dose, mask, np.arange(len(volume)) * width) / 100.0 * mask.sum() * voxel_cc
        assert np.allclose(volume, expected, rtol=1e-5, atol=1e-6)
        assert float(item.DVHMaximumDose) == pytest.approx(dose[mask].max(), rel=1e-5)
        assert float(item.DVHMeanDose) == pytest.approx(dose[mask].mean(), rel=1e-5)

    # without the structure set in the export, or when asked not to, no DVH
    _svc, res2 = _export_with(dvh=False)
    assert "DVHSequence" not in pydicom.dcmread(_svc.file_path(res2.export_id, "RD.dcm"))


def _export_with(**request):
    from radiarch.services.rt_export import RTExportService

    _geo, _bm, _opt, seq = _photon_pipeline()
    svc = RTExportService()
    return svc, svc.export(RTExportRequest(sequence_id=seq.sequence_id, **request))


def test_dvh_bin_width():
    from radiarch.dicom.writers.rtdose import DVH_MAX_BINS, dvh_bin_width

    assert [dvh_bin_width(x) for x in (0.0, 5.0, 20.0, 60.0, 74.0, 300.0)] == [0.01, 0.01, 0.05, 0.1, 0.1, 0.5]
    for x in (0.3, 9.99, 61.2, 123.0, 999.0):
        assert x / dvh_bin_width(x) < DVH_MAX_BINS


def test_a_viewer_finds_the_export_of_what_it_shows(env, monkeypatch):
    import radiarch.app as radiarch_app
    from radiarch.sdk import Radiarch

    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    svc, a = _export()
    _svc, b = _export(new_export=True)          # a second export of the same plan is a copy, asked for
    vol = _loaded_ct().ct
    dose_a = next(o for o in a.objects if o.kind == "RTDOSE")

    assert [r.export_id for r in svc.find(study_instance_uid=vol.studyInstanceUID)] == [b.export_id, a.export_id]   # newest first
    assert [r.export_id for r in svc.find(sop_instance_uid=a.plan_sop_instance_uid)] == [a.export_id]
    assert [r.export_id for r in svc.find(series_instance_uid=dose_a.series_instance_uid)] == [a.export_id]
    assert svc.find(study_instance_uid="1.2.3.4") == [] and len(svc.find(limit=1)) == 1
    assert svc.find(study_instance_uid=vol.studyInstanceUID, sop_instance_uid="1.2.3.4") == []     # every filter must match

    with Radiarch.local(poll_interval=0.01) as rx:
        found = rx.find_exports(sop_instance_uid=dose_a.sop_instance_uid)
        assert [e.id for e in found] == [a.export_id] and found[0].result.dose_id == a.dose_id
        assert len(rx.find_exports(study_instance_uid=vol.studyInstanceUID)) == 2
        assert rx.request("GET", "/rt/exports", params={"limit": 0}, expect=(422,)).status_code == 422
