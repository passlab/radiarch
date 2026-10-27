"""Geometry from a real Orthanc: the adapter's DICOMweb root, and a study fetched by QIDO-RS and WADO-RS.

Until 2026-10-27 the adapter gave Orthanc's base URL to the DICOMweb client as its root; Orthanc answers its own REST
API there, so no study was ever found. With RADIARCH_TEST_DICOMWEB_URL (CI's Full Tests runs Orthanc with its
DICOMweb plugin), a CT and a structure set are stored and the geometry service builds the study from Orthanc.
"""

from __future__ import annotations

import os

import pytest

from test_r6_rt_export_service import env  # noqa: F401
from test_r13_viewer import _ct_slices, _export, _loaded_ct

DICOMWEB = os.environ.get("RADIARCH_TEST_DICOMWEB_URL", "").rstrip("/")


@pytest.mark.parametrize("base, root, expected", [
    ("http://orthanc:8042", "/dicom-web", "http://orthanc:8042/dicom-web"),
    ("http://orthanc:8042/", "dicom-web/", "http://orthanc:8042/dicom-web"),
    ("http://orthanc:8042/dicom-web", "/dicom-web", "http://orthanc:8042/dicom-web"),
    ("https://pacs.example/wado", "", "https://pacs.example/wado"),
])
def test_the_dicomweb_root(base, root, expected):
    from radiarch.adapters.orthanc import dicomweb_url
    from radiarch.config import Settings

    assert dicomweb_url(Settings(orthanc_base_url=base, orthanc_dicomweb_root=root)) == expected


@pytest.mark.skipif(not DICOMWEB, reason="needs a DICOMweb server: RADIARCH_TEST_DICOMWEB_URL (CI runs Orthanc)")
def test_a_geometry_built_from_orthanc(env, tmp_path, monkeypatch):  # noqa: F811
    from radiarch.adapters.dicomweb import DICOMwebNotifier
    from radiarch.config import get_settings
    from radiarch.models.geometry import GeometryBuildRequest, PatientRef
    from radiarch.services.geometry import GeometryService

    # the CT and a structure set of its study (radiarch's own, from the export tests' case) into Orthanc
    vol = _loaded_ct().ct
    ct_dir = tmp_path / "ct"
    ct_dir.mkdir()
    svc, res = _export()
    assert DICOMwebNotifier(url=DICOMWEB).store_instances([str(p) for p in _ct_slices(ct_dir)] + [str(svc.file_path(res.export_id, "RS.dcm"))],
                                                          raise_errors=True)

    # then a geometry of that study, from Orthanc (not the stubbed loader of the export tests)
    monkeypatch.undo()
    for k, v in {"RADIARCH_ORTHANC_USE_MOCK": "false", "RADIARCH_ORTHANC_BASE_URL": DICOMWEB[: -len("/dicom-web")],
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path / "artifacts"), "RADIARCH_DATABASE_URL": ""}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid=vol.studyInstanceUID), hu_to_density_model="LINEAR"))
        assert {"PTV", "OAR"} <= set(geo.structure_index) and tuple(geo.grid_spec.size) == vol.imageArray.shape[::-1]
    finally:
        get_settings.cache_clear()
