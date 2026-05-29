"""End-to-end tests for the /uploads/* routes.

Generates a tiny valid-enough DICOM file in-memory (one CT instance +
one RTSTRUCT instance), packs them into a ZIP, POSTs the ZIP, and
checks:

* The upload endpoint returns the right counts.
* GET /uploads/{id} returns the same shape.
* DELETE removes the directory and a second GET 404s.
* The geometry build endpoint can resolve an upload_id and dispatch
  without trying to reach Orthanc.
"""

from __future__ import annotations

import io
import tempfile
import types
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

import numpy as np
import pydicom
import pytest
from fastapi.testclient import TestClient
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from radiarch import app as radiarch_app
from radiarch.api.routes import geometry as geometry_route
from radiarch.api.routes import uploads as uploads_route
from radiarch.app import create_app
from radiarch.core import store as store_module
from radiarch.services.geometry import GeometryService, _LoadedCT
from radiarch.tasks import geometry_tasks as geometry_tasks_module


# ---------------------------------------------------------------------------
# DICOM file synthesis
# ---------------------------------------------------------------------------

def _minimal_dicom(modality: str, sop_class_uid: str) -> bytes:
    """Build a minimal valid DICOM Part-10 file with the given modality."""
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = sop_class_uid
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(
        "in-memory",
        {},
        file_meta=file_meta,
        preamble=b"\x00" * 128,
    )
    ds.PatientName = "TEST^PATIENT"
    ds.PatientID = "TEST_ID"
    ds.StudyInstanceUID = "1.2.3"
    ds.SeriesInstanceUID = generate_uid()
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = sop_class_uid
    ds.Modality = modality
    if modality == "CT":
        # Add minimal CT pixel info so pydicom's writer is happy.
        ds.Rows = 2
        ds.Columns = 2
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.PixelData = (np.zeros((2, 2), dtype=np.int16)).tobytes()

    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _make_zip(file_specs: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in file_specs:
            zf.writestr(name, payload)
    return buf.getvalue()


# CT SOP Class: "CT Image Storage"
_CT_SOP = "1.2.840.10008.5.1.4.1.1.2"
# RTSTRUCT SOP Class: "RT Structure Set Storage"
_RT_SOP = "1.2.840.10008.5.1.4.1.1.481.3"


@pytest.fixture
def study_zip_bytes() -> bytes:
    """Two CT slices + one RTSTRUCT, all packed into a single ZIP."""
    return _make_zip([
        ("study/ct_0001.dcm", _minimal_dicom("CT", _CT_SOP)),
        ("study/ct_0002.dcm", _minimal_dicom("CT", _CT_SOP)),
        ("study/rtstruct.dcm", _minimal_dicom("RTSTRUCT", _RT_SOP)),
    ])


# ---------------------------------------------------------------------------
# Test fixtures — reuse the same sandbox pattern as test_api_geometry
# ---------------------------------------------------------------------------

@dataclass
class _FakePatient:
    name: str = "UPLOAD_TEST"
    rtStructs: list = field(default_factory=list)


@dataclass
class _FakeCT:
    imageArray: np.ndarray
    origin: Tuple[float, float, float]
    spacing: Tuple[float, float, float]
    patient: _FakePatient
    seriesInstanceUID: str = "1.2.3.4"
    studyInstanceUID: str = "1.2.3"
    frameOfReferenceUID: str = "1.2.3.9"


@dataclass
class _FakeMask:
    imageArray: np.ndarray


@dataclass
class _FakeContour:
    name: str
    mask: np.ndarray

    def getBinaryMask(self, origin, gridSize, spacing):
        return _FakeMask(imageArray=self.mask.astype(bool))


def _build_loaded_ct() -> _LoadedCT:
    ct_array = np.zeros((8, 8, 8), dtype=np.int16)
    ct_array[2:6, 2:6, 2:6] = 50
    ptv = np.zeros(ct_array.shape, dtype=bool)
    ptv[2:6, 2:6, 2:6] = True
    ct = _FakeCT(imageArray=ct_array, origin=(0, 0, 0),
                 spacing=(1, 1, 1), patient=_FakePatient())
    return _LoadedCT(ct=ct, patient=ct.patient,
                     contours=[_FakeContour("PTV", ptv)])


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    """Same harness as test_api_geometry, plus a tempdir for uploads."""
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()

    # Point the upload helper at our tempdir. The real _upload_root is
    # lru_cached, but monkeypatch.setattr replaces the symbol entirely so
    # subsequent _upload_root() calls inside the route hit our lambda.
    monkeypatch.setattr(uploads_route, "_upload_root",
                        lambda: upload_root, raising=True)

    # Point GeometryService at the same tempdir for upload_id resolution.
    import radiarch.services.geometry as geometry_service_module

    def _resolve_upload_path_stub(upload_id: str) -> Path:
        path = upload_root / upload_id
        if not path.is_dir():
            raise ValueError(f"Upload id not found: {upload_id!r}.")
        return path

    monkeypatch.setattr(
        geometry_service_module.GeometryService,
        "_resolve_upload_path",
        staticmethod(_resolve_upload_path_stub),
    )

    # Stub the geometry build itself — we're testing the upload plumbing,
    # not OpenTPS. The stub still honors the upload-id contract: if the
    # request carries an upload_id we run the (patched) resolver so a
    # stale id surfaces as a ValueError just like in production.
    def _load_honoring_upload(self, req):
        if req.patient_ref.upload_id:
            self._resolve_upload_path(req.patient_ref.upload_id)
        return _build_loaded_ct()

    artifacts = tempfile.TemporaryDirectory()
    svc = GeometryService(base_dir=artifacts.name)
    monkeypatch.setattr(svc, "_load", lambda req: _load_honoring_upload(svc, req))
    store_module.reset_store()
    geometry_route._service.cache_clear()
    monkeypatch.setattr(geometry_route, "_service", lambda: svc)
    monkeypatch.setattr(GeometryService, "_load", _load_honoring_upload)

    original_init = GeometryService.__init__

    def _init_to_tmp(self, base_dir=None, adapter=None):
        original_init(self, base_dir=artifacts.name, adapter=adapter)

    monkeypatch.setattr(GeometryService, "__init__", _init_to_tmp)
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)

    def _eager_delay(job_id, request_payload):
        geometry_tasks_module.build_geometry_job.run(job_id, request_payload)
        return types.SimpleNamespace(id=job_id)

    monkeypatch.setattr(
        geometry_tasks_module.build_geometry_job, "delay", _eager_delay
    )

    app = create_app()
    with TestClient(app) as c:
        yield c
    artifacts.cleanup()
    store_module.reset_store()


# ---------------------------------------------------------------------------
# Upload happy path
# ---------------------------------------------------------------------------

class TestUploadHappyPath:
    def test_post_returns_201_with_counts(
        self, client: TestClient, study_zip_bytes: bytes
    ) -> None:
        r = client.post(
            "/api/v1/uploads/dicom",
            files={"file": ("study.zip", study_zip_bytes, "application/zip")},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["upload_id"]
        assert body["file_count"] == 3
        assert body["dicom_count"] == 3
        assert body["ct_slice_count"] == 2
        assert body["rtstruct_count"] == 1
        assert body["total_bytes"] > 0

    def test_get_returns_same_shape(
        self, client: TestClient, study_zip_bytes: bytes
    ) -> None:
        upload_id = client.post(
            "/api/v1/uploads/dicom",
            files={"file": ("study.zip", study_zip_bytes, "application/zip")},
        ).json()["upload_id"]

        r = client.get(f"/api/v1/uploads/{upload_id}")
        assert r.status_code == 200
        assert r.json()["upload_id"] == upload_id
        assert r.json()["ct_slice_count"] == 2

    def test_delete_returns_204_and_get_then_404s(
        self, client: TestClient, study_zip_bytes: bytes
    ) -> None:
        upload_id = client.post(
            "/api/v1/uploads/dicom",
            files={"file": ("study.zip", study_zip_bytes, "application/zip")},
        ).json()["upload_id"]

        assert client.delete(f"/api/v1/uploads/{upload_id}").status_code == 204
        assert client.get(f"/api/v1/uploads/{upload_id}").status_code == 404


# ---------------------------------------------------------------------------
# Upload error paths
# ---------------------------------------------------------------------------

class TestUploadErrors:
    def test_non_zip_is_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/uploads/dicom",
            files={"file": ("not_a_zip.txt", b"hello", "text/plain")},
        )
        assert r.status_code == 400

    def test_empty_zip_rejected(self, client: TestClient) -> None:
        empty = _make_zip([])
        r = client.post(
            "/api/v1/uploads/dicom",
            files={"file": ("empty.zip", empty, "application/zip")},
        )
        assert r.status_code == 400
        assert "no DICOM" in r.json()["detail"]

    def test_zip_with_only_non_dicom_rejected(self, client: TestClient) -> None:
        zip_bytes = _make_zip([("readme.txt", b"just text")])
        r = client.post(
            "/api/v1/uploads/dicom",
            files={"file": ("readme.zip", zip_bytes, "application/zip")},
        )
        assert r.status_code == 400

    def test_unknown_upload_id_is_404(self, client: TestClient) -> None:
        assert client.get("/api/v1/uploads/does-not-exist").status_code == 404
        assert client.delete("/api/v1/uploads/does-not-exist").status_code == 404


# ---------------------------------------------------------------------------
# Geometry build can resolve an upload_id
# ---------------------------------------------------------------------------

class TestGeometryWithUpload:
    def test_build_with_upload_id_dispatches(
        self, client: TestClient, study_zip_bytes: bytes
    ) -> None:
        upload_id = client.post(
            "/api/v1/uploads/dicom",
            files={"file": ("study.zip", study_zip_bytes, "application/zip")},
        ).json()["upload_id"]

        payload = {
            "patient_ref": {"upload_id": upload_id},
            "grid_spec": None,
            "hu_to_density_model": "LINEAR",
        }
        r = client.post("/api/v1/geometry/build", json=payload)
        # Cache miss → 202 (Celery eager path runs the stubbed _load).
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]

        status = client.get(f"/api/v1/geometry/jobs/{job_id}").json()
        assert status["state"] == "succeeded"
        assert status["geometry_id"]

    def test_build_with_stale_upload_id_is_422(self, client: TestClient) -> None:
        payload = {
            "patient_ref": {"upload_id": "bogus-id"},
            "grid_spec": None,
            "hu_to_density_model": "LINEAR",
        }
        r = client.post("/api/v1/geometry/build", json=payload)
        # The job dispatches but fails inside the task — surface check is
        # via the jobs endpoint.
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        status = client.get(f"/api/v1/geometry/jobs/{job_id}").json()
        assert status["state"] == "failed"
        assert "Upload id not found" in (status.get("message") or "")

    def test_patient_ref_requires_one_source(self, client: TestClient) -> None:
        payload = {
            "patient_ref": {},  # neither dicom_study_uid nor upload_id
            "grid_spec": None,
            "hu_to_density_model": "LINEAR",
        }
        r = client.post("/api/v1/geometry/build", json=payload)
        assert r.status_code == 422
