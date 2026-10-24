"""R4, parts A and B: machine models, structure operations, derived geometries, overlapping structures."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pytest

from radiarch.models.geometry import GeometryBuildRequest, GeometryDeriveRequest, PatientRef, StructureOperation
from radiarch.services import structure_ops as ops
from radiarch.services.masks import BITMASK, pack_bitmask, set_structure, structure_mask, to_bitmask


# ---------------------------------------------------------------------------
# Machine models
# ---------------------------------------------------------------------------

class TestMachineModels:
    def test_builtin_photon_machines(self):
        from radiarch.services.machine_model import DEFAULT_PHOTON_MACHINE, PhotonMachineModel, builtin_photon_machines, load_photon_spec

        assert set(builtin_photon_machines()) == {"synthetic-120", "synthetic-160"} and DEFAULT_PHOTON_MACHINE == "synthetic-120"
        s120, s160 = load_photon_spec("synthetic-120"), load_photon_spec("synthetic-160")
        assert s120.mlc.n_pairs == 60 and s160.mlc.n_pairs == 80
        assert s120.mlc.leaf_widths_mm[0] == 10.0 and s120.mlc.leaf_widths_mm[30] == 5.0 and set(s160.mlc.leaf_widths_mm) == {5.0}
        assert s120.mlc.extent_mm == (-200.0, 200.0) and s120.mlc.pair_index(0.0) == 30 and s120.mlc.pair_index(-200.0) == 0
        assert s120.mlc.pair_index(200.0) is None and s120.mlc.pair_index(199.9) == 59
        assert s120.energy(6.0).output_cgy_per_mu == 1.0 and s120.default_energy.dose_rate_mu_min == (100.0, 600.0)
        with pytest.raises(ValueError):
            s120.energy(10.0)
        default = PhotonMachineModel.from_default()
        assert default.spec.machine_id == "synthetic-120" and default.mlc_leaf_width_mm == 5.0
        assert default.max_jaw_opening_mm == 200.0 and default.beam_quality_mv == 6.0
        assert PhotonMachineModel.from_id("synthetic-160").spec.mlc.min_leaf_gap_mm == 0.0

    def test_custom_photon_machine_from_the_library(self, monkeypatch, tmp_path):
        from radiarch.config import get_settings
        from radiarch.services.machine_model import MachineModelError, PhotonMachineModel, load_photon_spec

        monkeypatch.setenv("RADIARCH_BEAM_LIBRARY_DIR", str(tmp_path))
        get_settings.cache_clear()
        try:
            with pytest.raises(MachineModelError, match="not found"):
                PhotonMachineModel.from_id("site-linac")
            spec = load_photon_spec("synthetic-160").model_dump()
            spec["machine_id"] = "site-linac"; spec["kind"] = "commissioned"; spec["mlc"]["max_leaf_speed_mm_s"] = 50.0
            (tmp_path / "site-linac").mkdir()
            (tmp_path / "site-linac" / "machine.json").write_text(json.dumps(spec))
            m = PhotonMachineModel.from_id("site-linac")
            assert m.spec.kind == "commissioned" and m.spec.mlc.max_leaf_speed_mm_s == 50.0
            (tmp_path / "site-linac" / "machine.json").write_text("{not json")
            with pytest.raises(MachineModelError, match="invalid machine file"):
                load_photon_spec("site-linac")
        finally:
            get_settings.cache_clear()

    def test_proton_spec_from_the_bdl(self):
        from radiarch.services.machine_model import ProtonMachineModel

        spec = ProtonMachineModel.from_default().spec
        assert spec.energy_range_mev == (20.0, 225.0) and len(spec.energies_mev) == len(spec.protons_per_mu)
        assert spec.range_shifters and spec.range_shifters[0].water_equivalent_thickness_mm > 0
        assert spec.nozzle_to_isocenter_mm == 410.0


# ---------------------------------------------------------------------------
# Masks: bitmask encoding
# ---------------------------------------------------------------------------

class TestBitmask:
    def test_pack_set_and_read(self):
        a = np.zeros((2, 3, 4), bool); a[0] = True
        b = np.zeros((2, 3, 4), bool); b[:, 1] = True
        m = pack_bitmask({1: a, 2: b}, a.shape)
        assert m.dtype == np.uint64 and np.array_equal(structure_mask(m, 1, BITMASK), a) and np.array_equal(structure_mask(m, 2, BITMASK), b)
        assert structure_mask(m, 3, BITMASK).sum() == 0
        m2 = set_structure(m, 3, a & b)
        assert np.array_equal(structure_mask(m2, 3, BITMASK), a & b) and np.array_equal(structure_mask(m2, 1, BITMASK), a)
        labels = np.zeros((2, 3, 4), np.uint16); labels[0] = 1; labels[1, 1] = 2
        conv = to_bitmask(labels, [1, 2], "labels")
        assert np.array_equal(structure_mask(conv, 2, BITMASK), labels == 2)
        with pytest.raises(ValueError):
            structure_mask(m, 65, BITMASK)

    def test_rasterizer_keeps_overlapping_structures(self):
        from radiarch.models.geometry import GridSpec
        from radiarch.services.rasterization import rasterize_contours

        @dataclass
        class _Mask:
            imageArray: np.ndarray

        @dataclass
        class _Contour:
            name: str
            mask: np.ndarray

            def getBinaryMask(self, origin, gridSize, spacing):
                return _Mask(self.mask)

        ptv = np.zeros((6, 6, 6), bool); ptv[1:5, 1:5, 1:5] = True
        cord = np.zeros((6, 6, 6), bool); cord[:, 2:4, 2:4] = True           # runs through the PTV
        grid = GridSpec(spacing_mm=(1, 1, 1), origin_mm=(0, 0, 0), size=(6, 6, 6))
        masks, index = rasterize_contours([_Contour("SpinalCord", cord), _Contour("PTV", ptv)], grid)
        assert index == {"PTV": 1, "SpinalCord": 2} and masks.dtype == np.uint64
        assert structure_mask(masks, 2, BITMASK).sum() == cord.sum()         # nothing lost under the PTV
        assert structure_mask(masks, 1, BITMASK).sum() == ptv.sum()


# ---------------------------------------------------------------------------
# Structure operations
# ---------------------------------------------------------------------------

def _ball(n=30, spacing=2.0, radius=10.0):
    zz, yy, xx = np.mgrid[:n, :n, :n]
    c = (n - 1) / 2.0
    return ((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2) * spacing ** 2 <= radius ** 2


class TestStructureOps:
    def test_expand_and_erode_by_distance(self):
        sp = (2.0, 2.0, 2.0)
        m = _ball()
        grown = ops.expand(m, sp, 5.0)
        shrunk = ops.erode(m, sp, 5.0)
        assert grown[m].all() and grown.sum() > m.sum() > shrunk.sum() > 0 and m[shrunk].all()
        # radii: 10 → 15 and 10 → 5 mm (volume ∝ r³)
        assert grown.sum() / m.sum() == pytest.approx((15 / 10) ** 3, rel=0.15)
        assert shrunk.sum() / m.sum() == pytest.approx((5 / 10) ** 3, rel=0.35)
        assert np.array_equal(ops.expand(m, sp, 0.0), m)

    def test_anisotropic_margin(self):
        sp = (2.0, 2.0, 2.0)
        m = _ball()
        g = ops.expand(m, sp, (2.0, 2.0, 10.0))
        zz, yy, xx = np.nonzero(g)
        c = 14.5
        # z extent grows by 10 mm (5 voxels), x only by 1 voxel
        assert (zz.max() - c) * 2.0 >= 19.0 and (xx.max() - c) * 2.0 <= 13.0

    def test_ring_and_booleans(self):
        sp = (2.0, 2.0, 2.0)
        m = _ball()
        r = ops.ring(m, sp, 0.0, 6.0)
        assert not (r & m).any() and r.sum() > 0 and np.array_equal(r, ops.expand(m, sp, 6.0) & ~m)
        r2 = ops.ring(m, sp, 2.0, 6.0)
        assert r2.sum() < r.sum() and not (r2 & ops.expand(m, sp, 2.0)).any()
        other = np.zeros_like(m); other[:, :, :15] = True
        assert ops.union(m, other).sum() == (m | other).sum()
        assert np.array_equal(ops.intersection(m, other), m & other)
        assert np.array_equal(ops.subtract(m, other), m & ~other)
        assert ops.volume_cc(m, sp) == pytest.approx(m.sum() * 8.0 / 1000.0)

    def test_couch_slab(self):
        slab = ops.couch_slab((4, 10, 6), (0.0, -10.0, 0.0), (2.0, 2.0, 2.0), y_top_mm=0.0, thickness_mm=6.0)
        rows = np.nonzero(slab[0, :, 0])[0]
        assert list(rows) == [5, 6, 7] and slab[:, 5, :].all()


# ---------------------------------------------------------------------------
# Derived geometries through the service and the API
# ---------------------------------------------------------------------------

@dataclass
class _Patient:
    name: str = "DERIVE"


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
    """(x, y, z) arrays, 2 mm voxels: water cube with a CTV ball and a cord through it."""
    from radiarch.services.geometry import _LoadedCT

    n = 30
    ct = np.zeros((n, n, n), np.int16)
    xx, yy, zz = np.mgrid[:n, :n, :n]
    c = (n - 1) / 2.0
    ctv = ((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2) * 4.0 <= 10.0 ** 2
    cord = ((xx - c) ** 2 + (yy - c + 2) ** 2) * 4.0 <= 3.0 ** 2
    vol = _CT(imageArray=ct, origin=(-c * 2.0, -c * 2.0, -c * 2.0), spacing=(2.0, 2.0, 2.0), patient=_Patient())
    return _LoadedCT(ct=vol, patient=vol.patient, contours=[_Contour("CTV", ctv), _Contour("SpinalCord", cord)])


@pytest.fixture
def geometry_service(monkeypatch, tmp_path):
    from radiarch.services.geometry import GeometryService

    monkeypatch.setattr(GeometryService, "_load", lambda self, _req: _loaded_ct())
    return GeometryService(base_dir=tmp_path / "geometry")


class TestDerivedGeometry:
    def test_ptv_ring_boolean_override_and_couch(self, geometry_service):
        from radiarch.services.geometry_bundle import load_geometry_arrays
        from radiarch.services.persistence import _read_nifti

        svc = geometry_service
        parent = svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
        assert parent.mask_encoding == "bitmask" and parent.hu_to_density_model == "LINEAR"
        req = GeometryDeriveRequest(operations=[
            StructureOperation(op="expand", source="CTV", margin_mm=5.0, name="PTV"),
            StructureOperation(op="ring", source="PTV", inner_mm=0.0, outer_mm=10.0, name="Ring_PTV"),
            StructureOperation(op="subtract", source="SpinalCord", sources=["PTV"], name="Cord_outside_PTV"),
            StructureOperation(op="density_override", source="SpinalCord", hu=200.0),
            StructureOperation(op="couch", y_top_mm=20.0, thickness_mm=6.0, hu=-700.0),
        ])
        derived = svc.derive(parent.geometry_id, req)
        assert derived.parent_geometry_id == parent.geometry_id and len(derived.derived_operations) == 5
        assert set(derived.structure_index) == {"CTV", "SpinalCord", "PTV", "Ring_PTV", "Cord_outside_PTV", "Couch"}
        assert derived.geometry_id != parent.geometry_id and derived.grid_spec == parent.grid_spec
        arrays = load_geometry_arrays(derived)
        ctv, ptv = arrays.mask_zyx(arrays.label_of("CTV")), arrays.mask_zyx(arrays.label_of("PTV"))
        ring = arrays.mask_zyx(arrays.label_of("Ring_PTV"))
        cord = arrays.mask_zyx(arrays.label_of("SpinalCord"))
        assert ptv[ctv].all() and ptv.sum() > ctv.sum() and not (ring & ptv).any() and ring.sum() > 0
        assert cord.sum() > 0 and (cord & ptv).any()                                  # the cord keeps its voxels inside the PTV
        assert arrays.target() == ("PTV", arrays.label_of("PTV"))
        # overrides reached the CT and the density (LINEAR model: 1 + HU/1000)
        assert int(np.median(arrays.ct_hu[cord])) == 200
        density, _ = _read_nifti(Path(derived.density_grid_uri))
        density = np.transpose(density, (2, 1, 0))
        assert np.allclose(density[cord], 1.2, atol=1e-5)
        couch = arrays.mask_zyx(arrays.label_of("Couch"))
        assert couch.sum() == 3 * 30 * 30 and np.allclose(density[couch], 0.3, atol=1e-5) and int(arrays.ct_hu[couch].max()) == -700
        # cached: the same request returns the same geometry
        assert svc.derive(parent.geometry_id, req).geometry_id == derived.geometry_id
        with pytest.raises(ValueError, match="not in the geometry"):
            svc.derive(parent.geometry_id, GeometryDeriveRequest(operations=[StructureOperation(op="expand", source="GTV", margin_mm=3.0, name="X")]))

    def test_derived_volumes_keep_the_parent_orientation(self, monkeypatch, tmp_path):
        """A non-cubic grid and an off-centre structure: the derived CT is the parent's voxel for voxel, and an
        expansion surrounds its source (before R9 the derived volumes were written with x and z swapped)."""
        from radiarch.services.geometry import GeometryService, _LoadedCT
        from radiarch.services.geometry_bundle import load_geometry_arrays

        nx, ny, nz = 40, 30, 20
        xx, yy, zz = np.mgrid[:nx, :ny, :nz]
        ct = (xx * 10 + yy * 3 + zz).astype(np.int16)                                        # every voxel distinct
        ctv = (xx - 8) ** 2 + (yy - 20) ** 2 + (zz - 5) ** 2 <= 3 ** 2                        # off centre in x, y and z
        vol = _CT(imageArray=ct, origin=(-40.0, -30.0, -20.0), spacing=(2.0, 2.0, 2.0), patient=_Patient())
        loaded = _LoadedCT(ct=vol, patient=vol.patient, contours=[_Contour("CTV", ctv)])
        monkeypatch.setattr(GeometryService, "_load", lambda self, _req: loaded)
        svc = GeometryService(base_dir=tmp_path / "geometry")
        parent = svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
        derived = svc.derive(parent.geometry_id, GeometryDeriveRequest(operations=[StructureOperation(op="expand", source="CTV", margin_mm=4.0, name="PTV")]))
        pa, da = load_geometry_arrays(parent), load_geometry_arrays(derived)
        assert pa.ct_hu.shape == da.ct_hu.shape == (nz, ny, nx)
        assert np.array_equal(pa.ct_hu, da.ct_hu)
        assert np.array_equal(pa.mask_zyx(pa.label_of("CTV")), da.mask_zyx(da.label_of("CTV")))
        assert da.mask_zyx(da.label_of("PTV"))[pa.mask_zyx(pa.label_of("CTV"))].all()

    def test_operation_validation(self):
        with pytest.raises(ValueError):
            StructureOperation(op="expand", source="CTV", name="PTV")
        with pytest.raises(ValueError):
            StructureOperation(op="grow", source="CTV", margin_mm=1.0, name="PTV")
        with pytest.raises(ValueError):
            StructureOperation(op="density_override", source="CTV")
        assert StructureOperation(op="couch", y_top_mm=10.0, thickness_mm=5.0).name is None

    def test_evaluation_sees_overlapping_structures(self, geometry_service, monkeypatch, tmp_path):
        """A dose on the derived geometry: the cord's DVH counts its voxels inside the PTV."""
        from radiarch.models.evaluation import EvaluationRequest
        from radiarch.services.dose import DoseService
        from radiarch.services.dose_persistence import _write_dose_volume
        from radiarch.services.evaluation import EvaluationService

        svc = geometry_service
        parent = svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
        derived = svc.derive(parent.geometry_id, GeometryDeriveRequest(operations=[
            StructureOperation(op="expand", source="CTV", margin_mm=4.0, name="PTV")]))
        monkeypatch.setattr("radiarch.services.dose.GeometryService", lambda: svc)
        dose_svc = DoseService(dose_dir=tmp_path / "dose", influence_dir=tmp_path / "inf")
        bundle = dose_svc._load_geometry(derived.geometry_id)
        assert bundle.masks.dtype == np.uint64
        ptv = structure_mask(bundle.masks, derived.structure_index["PTV"], BITMASK)
        dose = np.where(ptv, 60.0, 0.0).astype(np.float32)
        dose_path = tmp_path / "dose.nii.gz"
        _write_dose_volume(dose_path, dose, bundle.spacing_mm)
        ev = EvaluationService(base_dir=tmp_path / "eval", dose_service=dose_svc)
        out = ev.run(EvaluationRequest(dose_ref_uri=str(dose_path), geometry_id=derived.geometry_id, prescription_gy=60.0, target_structure="PTV"))
        by = {c.structure_name: c.metrics for c in out.dvh_curves}
        assert by["PTV"].v_prescription_pct == pytest.approx(100.0) and by["CTV"].v_prescription_pct == pytest.approx(100.0)
        assert by["SpinalCord"].max_gy == pytest.approx(60.0) and 0 < by["SpinalCord"].v_prescription_pct < 100


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.app import create_app
    from radiarch.core import store as store_module
    from radiarch.services.geometry import GeometryService

    monkeypatch.setenv("RADIARCH_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("RADIARCH_ENVIRONMENT", "dev")
    monkeypatch.setenv("RADIARCH_API_KEY", "")
    from radiarch.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(GeometryService, "_load", lambda self, _req: _loaded_ct())
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    app = create_app()
    with TestClient(app) as c:
        yield c
    store_module.reset_store()
    get_settings.cache_clear()


def test_api_derive_and_machines(client):
    from radiarch.services.geometry import GeometryService

    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    r = client.post(f"/api/v1/geometry/{geo.geometry_id}/derive",
                    json={"operations": [{"op": "expand", "source": "CTV", "margin_mm": [3.0, 3.0, 5.0], "name": "PTV"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_geometry_id"] == geo.geometry_id and "PTV" in body["structure_index"] and body["mask_encoding"] == "bitmask"
    assert client.post(f"/api/v1/geometry/{geo.geometry_id}/derive", json={"operations": [{"op": "expand", "source": "Nope", "margin_mm": 1.0, "name": "X"}]}).status_code == 422
    assert client.post("/api/v1/geometry/missing/derive", json={"operations": [{"op": "expand", "source": "CTV", "margin_mm": 1.0, "name": "X"}]}).status_code == 404
    m = client.get("/api/v1/beam-model/machines").json()
    assert [p["machine_id"] for p in m["photon"]] == ["synthetic-120", "synthetic-160"] and m["proton"][0]["energy_range_mev"] == [20.0, 225.0]
    full = client.get("/api/v1/beam-model/machines/photon/synthetic-160").json()
    assert len(full["mlc"]["leaf_boundaries_mm"]) == 81 and full["default_field_mm"] == 200.0
    assert client.get("/api/v1/beam-model/machines/photon/nope").status_code == 404
