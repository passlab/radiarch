"""``POST /beam-model/templates/craniospinal`` on a persisted geometry (R3)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pytest
from fastapi.testclient import TestClient

import radiarch.app as radiarch_app
from radiarch.app import create_app
from radiarch.core import store as store_module
from radiarch.models.geometry import GeometryBuildRequest, PatientRef
from radiarch.services.geometry import GeometryService, _LoadedCT


@dataclass
class _Patient:
    name: str = "CSI"


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
        return _Mask(imageArray=self.mask.astype(bool))


def _long_target() -> _LoadedCT:
    """(x, y, z) arrays: a 440 mm long canal plus a ball on top, 4 mm voxels."""
    nx, ny, nz, sp = 20, 20, 120, 4.0
    xx, yy, zz = np.mgrid[:nx, :ny, :nz]
    cx, cy = (nx - 1) / 2.0, (ny - 1) / 2.0
    canal = (((xx - cx) ** 2 + (yy - cy) ** 2) * sp ** 2 <= 16.0 ** 2) & (zz < 100)
    ball = ((xx - cx) ** 2 + (yy - cy) ** 2 + (zz - 108) ** 2) * sp ** 2 <= 28.0 ** 2
    ct = np.zeros((nx, ny, nz), dtype=np.int16)
    vol = _CT(imageArray=ct, origin=(-cx * sp, -cy * sp, -200.0), spacing=(sp, sp, sp), patient=_Patient())
    return _LoadedCT(ct=vol, patient=vol.patient, contours=[_Contour("PTV_CSI", canal | ball)])


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("RADIARCH_ARTIFACT_DIR", tmp.name)
    monkeypatch.setenv("RADIARCH_ENVIRONMENT", "dev")
    monkeypatch.setenv("RADIARCH_API_KEY", "")
    from radiarch.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(GeometryService, "_load", lambda self, _req: _long_target())
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    app = create_app()
    with TestClient(app) as c:
        yield c
    tmp.cleanup()
    store_module.reset_store()
    get_settings.cache_clear()


def test_craniospinal_template_endpoint(client: TestClient):
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    r = client.post("/api/v1/beam-model/templates/craniospinal",
                    json={"geometry_id": geo.geometry_id, "field_length_mm": 300.0, "overlap_mm": 40.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_structure"] == "PTV_CSI" and len(body["fields"]) == 2 and len(body["junctions_mm"]) == 1
    beams = body["beam_set"]["beams"]
    assert [b["beam_id"] for b in beams] == ["CSI1", "CSI2"]
    assert all(b["isocenter_mm"] is not None and b["target_z_range_mm"] is not None for b in beams)
    assert beams[0]["target_z_range_mm"][1] > beams[1]["target_z_range_mm"][1]
    assert body["junctions_mm"][0][1] - body["junctions_mm"][0][0] == pytest.approx(40.0)
    # the beam set is a valid build request body
    r2 = client.post("/api/v1/beam-model/templates/craniospinal", json={"geometry_id": "nope"})
    assert r2.status_code == 404
    r3 = client.post("/api/v1/beam-model/templates/craniospinal", json={"geometry_id": geo.geometry_id, "target_structure": "Lung_L"})
    assert r3.status_code == 422
    r4 = client.post("/api/v1/beam-model/templates/craniospinal", json={"geometry_id": geo.geometry_id, "preset": "clinical"})
    assert r4.status_code == 200 and [b["beam_id"] for b in r4.json()["beam_set"]["beams"]] == ["CSI1L", "CSI1R", "CSI2"]
