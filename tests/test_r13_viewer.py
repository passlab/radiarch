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


def _export(push: bool = False):
    from radiarch.services.rt_export import RTExportService

    _geo, _bm, _opt, seq = _photon_pipeline()
    svc = RTExportService()
    res = svc.export(RTExportRequest(sequence_id=seq.sequence_id, label="R13", prescription=PrescriptionSpec(dose_gy=2.0, fractions=2),
                                     push=push))
    return svc, res


def _ct_slices(out: Path):
    """The stub CT of the export tests as DICOM CT images, one file per slice, with the UIDs the export references."""
    vol = _loaded_ct().ct
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
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = vol.studyInstanceUID, vol.seriesInstanceUID, vol.frameOfReferenceUID
        ds.StudyDate, ds.StudyTime, ds.StudyID, ds.AccessionNumber = vol.studyDate, "120000", "1", ""
        ds.ReferringPhysicianName, ds.SeriesNumber, ds.InstanceNumber = "", 1, k + 1
        ds.PatientPosition, ds.ImageType = vol.patientPosition, ["ORIGINAL", "PRIMARY", "AXIAL"]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [vol.origin[0], vol.origin[1], vol.origin[2] + k * vol.spacing[2]]
        ds.PixelSpacing, ds.SliceThickness = [vol.spacing[1], vol.spacing[0]], vol.spacing[2]
        ds.Rows, ds.Columns, ds.SamplesPerPixel, ds.PhotometricInterpretation = ny, nx, 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleIntercept, ds.RescaleSlope, ds.KVP = 0, 1, 120
        ds.PixelData = np.ascontiguousarray(vol.imageArray[k], dtype=np.int16).tobytes()
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
