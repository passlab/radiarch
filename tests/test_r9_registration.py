"""Roadmap R9: the Registration Service on a synthetic thorax with a known motion."""

from __future__ import annotations

import uuid

import numpy as np
import pytest
import SimpleITK as sitk

from radiarch.models.geometry import CTMetadata, GeometryResult, GridSpec
from radiarch.models.registration import DeformableMethod, LandmarkPair, PropagateRequest, RegistrationRequest
from radiarch.services.geometry import GeometryService
from radiarch.services.geometry_bundle import load_geometry_arrays
from radiarch.services.masks import BITMASK, pack_bitmask
from radiarch.services.persistence import GeometryPaths
from radiarch.services.registration import RegistrationError, RegistrationService, to_image

S = 3.0
SHAPE = (48, 64, 64)                       # z, y, x
ORIGIN = (-94.5, -94.5, -70.5)            # x, y, z of voxel [0, 0, 0]


def _phantom():
    z, y, x = np.meshgrid(*[ORIGIN[2 - a] + np.arange(SHAPE[a]) * S for a in range(3)], indexing="ij")
    ct = np.full(SHAPE, -1000.0, np.float32)
    body = (x / 85) ** 2 + (y / 65) ** 2 <= 1
    ct[body] = 20.0
    lung_r = ((x + 38) / 28) ** 2 + (y / 40) ** 2 + (z / 60) ** 2 <= 1
    lung_l = ((x - 38) / 28) ** 2 + (y / 40) ** 2 + (z / 60) ** 2 <= 1
    ct[lung_r | lung_l] = -800.0
    spine = ((x / 12) ** 2 + ((y - 45) / 12) ** 2 <= 1) & body
    ct[spine] = 700.0
    rng = np.random.default_rng(3)
    from scipy.ndimage import gaussian_filter
    ct += gaussian_filter(rng.normal(0, 120, SHAPE), 1.5).astype(np.float32) * (ct > -900)      # texture for the deformable step
    tumour = (x + 38) ** 2 + (y + 5) ** 2 + (z - 6) ** 2 <= 12 ** 2
    ct[tumour] = 40.0
    marker = (x - 45) ** 2 + (y - 20) ** 2 + (z + 20) ** 2 <= 6 ** 2      # a bounded landmark in the soft tissue
    ct[marker] = 900.0
    return ct, {"Body": body, "Lung_R": lung_r, "Lung_L": lung_l, "Tumour": tumour, "Spine": spine, "Marker": marker}


def _save(store, ct, structures, for_uid):
    gid = str(uuid.uuid4())
    index = {n: i + 1 for i, n in enumerate(structures)}
    masks = pack_bitmask({index[n]: m for n, m in structures.items()}, SHAPE)
    paths = GeometryPaths.for_id(store.base_dir, gid)
    res = GeometryResult(geometry_id=gid, density_grid_uri=str(paths.density), structure_masks_uri=str(paths.masks), ct_grid_uri=str(paths.ct),
                         structure_index=index, mask_encoding=BITMASK, grid_spec=GridSpec(spacing_mm=(S, S, S), origin_mm=ORIGIN, size=SHAPE[::-1]),
                         frame_of_reference_uid=for_uid, ct_metadata=CTMetadata(num_slices=SHAPE[0]), cache_key=f"test-{gid}")
    store.save(geometry_id=gid, cache_key=res.cache_key, density=np.clip((ct + 1000) / 1000, 0.001, 3).astype(np.float32).transpose(2, 1, 0),
               masks=masks.transpose(2, 1, 0), ct=ct.astype(np.int16).transpose(2, 1, 0), result=res)          # the store takes (x, y, z)
    return res


def _warp(arr, tx, linear=True):
    img = to_image(arr.astype(np.float32), ORIGIN, (S, S, S))
    out = sitk.Resample(img, img, tx, sitk.sitkLinear if linear else sitk.sitkNearestNeighbor, float(arr.min()), sitk.sitkFloat32)
    return sitk.GetArrayFromImage(out)


def _moved(ct, structures, tx_inverse):
    """The phantom as seen after the motion T: moving(y) = fixed(T^-1(y))."""
    return _warp(ct, tx_inverse), {n: _warp(m.astype(np.float32), tx_inverse) >= 0.5 for n, m in structures.items()}


def _breathing_inverse():
    """A smooth motion of the right lung region: up to 8 mm along z and 3 mm along y, Gaussian fall-off (35 mm)."""
    shape_xyz = SHAPE[::-1]
    field = np.zeros(SHAPE + (3,), np.float64)
    z, y, x = np.meshgrid(*[ORIGIN[2 - a] + np.arange(SHAPE[a]) * S for a in range(3)], indexing="ij")
    w = np.exp(-(((x + 38) ** 2 + y ** 2 + z ** 2) / (2 * 35.0 ** 2)))
    field[..., 2] = -8.0 * w                  # the inverse motion: sampling point moves the other way
    field[..., 1] = -3.0 * w
    img = sitk.GetImageFromArray(field, isVector=True)
    img.SetOrigin(ORIGIN); img.SetSpacing((S, S, S))
    del shape_xyz
    return sitk.DisplacementFieldTransform(img)


@pytest.fixture()
def svc(tmp_path):
    return RegistrationService(base_dir=tmp_path / "reg", geometry_service=GeometryService(base_dir=tmp_path / "geo"))


def _dice(a, b):
    return 2 * (a & b).sum() / max(a.sum() + b.sum(), 1)


def test_rigid_recovers_a_known_rotation_and_shift(svc):
    ct, st = _phantom()
    fixed = _save(svc.geometry_service.store, ct, st, "1.2.3.fixed")
    t = sitk.Euler3DTransform((0.0, 0.0, 0.0), 0.0, 0.0, np.radians(3.0), (6.0, -4.0, 9.0))      # T: fixed -> moving
    mct, mst = _moved(ct, st, t.GetInverse())
    moving = _save(svc.geometry_service.store, mct, mst, "1.2.3.moving")
    res = svc.register(RegistrationRequest(fixed_geometry_id=fixed.geometry_id, moving_geometry_id=moving.geometry_id, deformable=DeformableMethod.none,
                                           landmarks=[LandmarkPair(fixed_structure="Tumour", moving_structure="Tumour"),
                                                      LandmarkPair(fixed_structure="Marker", moving_structure="Marker")]))
    lm = {l.fixed_structure: l for l in res.quality.landmarks}
    assert lm["Tumour"].before_mm > 8.0 and lm["Tumour"].after_mm < 1.5
    assert lm["Marker"].after_mm < 1.5
    assert abs(res.rigid_parameters["rz_deg"] - 3.0) < 0.5
    assert res.quality.after.ncc > res.quality.before.ncc and res.quality.after.mean_abs_hu < res.quality.before.mean_abs_hu
    assert res.quality.jacobian is None                                     # rigid: no field to fold
    # the same request is cached
    again = svc.register(res.request)
    assert again.registration_id == res.registration_id


def test_demons_undoes_a_breathing_motion_without_folding(svc):
    ct, st = _phantom()
    fixed = _save(svc.geometry_service.store, ct, st, "1.2.3.4dct")
    mct, mst = _moved(ct, st, _breathing_inverse())
    moving = _save(svc.geometry_service.store, mct, mst, "1.2.3.4dct")              # a phase: the same frame of reference
    res = svc.register(RegistrationRequest(fixed_geometry_id=fixed.geometry_id, moving_geometry_id=moving.geometry_id,
                                           deformable=DeformableMethod.demons, demons_iterations=40,
                                           landmarks=[LandmarkPair(fixed_structure="Tumour", moving_structure="Tumour")]))
    lm = res.quality.landmarks[0]
    assert lm.before_mm > 6.0 and lm.after_mm < 2.0
    assert res.quality.jacobian.min > 0.0 and res.quality.jacobian.fraction_nonpositive == 0.0
    assert res.quality.after.ncc > res.quality.rigid.ncc
    # the moving tumour, propagated onto the fixed CT, lies on the fixed tumour
    g = svc.propagate(res.registration_id, PropagateRequest(structures=["Tumour", "Lung_R"], suffix="_prop"))
    arr = load_geometry_arrays(g)
    tum = arr.mask_zyx(arr.structure_index["Tumour"])
    prop = arr.mask_zyx(arr.structure_index["Tumour_prop"])
    moved = mst["Tumour"]
    assert _dice(prop, tum) > 0.85 and _dice(moved, tum) < _dice(prop, tum)
    assert g.parent_geometry_id == fixed.geometry_id and g.derived_operations[-1]["op"] == "propagate"
    with pytest.raises(RegistrationError):
        svc.propagate(res.registration_id, PropagateRequest(structures=["Tumour"]))          # the fixed geometry has a Tumour already


def test_bspline_improves_on_rigid(svc):
    ct, st = _phantom()
    fixed = _save(svc.geometry_service.store, ct, st, "1.2.3.ct")
    mct, mst = _moved(ct, st, _breathing_inverse())
    mct = 0.85 * mct + 60.0                       # a cone-beam calibration: another linear HU scale
    moving = _save(svc.geometry_service.store, mct, mst, "1.2.3.cbct")
    res = svc.register(RegistrationRequest(fixed_geometry_id=fixed.geometry_id, moving_geometry_id=moving.geometry_id,
                                           deformable=DeformableMethod.bspline, bspline_grid_mm=30.0, bspline_iterations=60,
                                           landmarks=[LandmarkPair(fixed_structure="Tumour", moving_structure="Tumour")]))
    lm = res.quality.landmarks[0]
    assert lm.after_mm < lm.rigid_mm and lm.after_mm < 1.5
    assert res.quality.jacobian.fraction_nonpositive == 0.0


def test_map_volume_moves_a_dose_with_the_anatomy(svc):
    ct, st = _phantom()
    fixed = _save(svc.geometry_service.store, ct, st, "1.2.3.a")
    t = sitk.Euler3DTransform((0.0, 0.0, 0.0), 0.0, 0.0, 0.0, (0.0, 0.0, 9.0))
    mct, mst = _moved(ct, st, t.GetInverse())
    moving = _save(svc.geometry_service.store, mct, mst, "1.2.3.b")
    res = svc.register(RegistrationRequest(fixed_geometry_id=fixed.geometry_id, moving_geometry_id=moving.geometry_id, deformable=DeformableMethod.none))
    dose_on_moving = mst["Tumour"].astype(np.float32) * 60.0
    mapped = svc.map_volume(res.registration_id, dose_on_moving, ORIGIN, (S, S, S))
    assert mapped.shape == SHAPE
    assert mapped[st["Tumour"]].mean() > 50.0                            # the dose follows the tumour back onto the fixed CT


def _dose_on(geometry_id, dose_zyx):
    """A dose record on a geometry, as the dose service would write it."""
    from radiarch.models.beam_model import Modality
    from radiarch.models.dose import DoseResult
    from radiarch.services.dose import DoseService, _summary_stats
    from radiarch.services.dose_persistence import DOSE_FILENAME

    store = DoseService().dose_store
    did = str(uuid.uuid4())
    res = DoseResult(dose_id=did, geometry_id=geometry_id, beam_model_id="bm-test", modality=Modality.photon_imrt, engine_name="analytic",
                     engine_version="test", dose_grid_uri=str(store.base_dir / did / DOSE_FILENAME), statistics=_summary_stats(dose_zyx),
                     cache_key=f"test-dose-{did}")
    store.save(dose_id=did, cache_key=res.cache_key, nominal_dose=dose_zyx, spacing_mm=(S, S, S), scenario_doses=None, result=res)
    return did


@pytest.fixture()
def api_env(monkeypatch, tmp_path):
    from radiarch.api.routes import registration as routes
    from radiarch.config import get_settings

    for k, v in {"RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
                 "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://",
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path), "RADIARCH_API_KEY": "", "RADIARCH_DICOMWEB_URL": ""}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    routes._service.cache_clear()
    yield tmp_path
    routes._service.cache_clear()
    get_settings.cache_clear()


def test_the_api_registers_propagates_and_records_the_lineage(api_env, monkeypatch):
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.app import create_app
    from radiarch.models.lineage import VersionRef
    from radiarch.services.lineage import LineageService

    store = GeometryService().store
    ct, st = _phantom()
    fixed = _save(store, ct, st, "1.2.3.a")
    t = sitk.Euler3DTransform((0.0, 0.0, 0.0), 0.0, 0.0, 0.0, (0.0, 6.0, 0.0))
    mct, mst = _moved(ct, st, t.GetInverse())
    moving = _save(store, mct, mst, "1.2.3.b")
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with TestClient(create_app()) as client:
        body = {"fixed_geometry_id": fixed.geometry_id, "moving_geometry_id": moving.geometry_id, "deformable": "none",
                "landmarks": [{"fixed_structure": "Tumour", "moving_structure": "Tumour"}]}
        r = client.post("/api/v1/registrations", json=body)
        assert r.status_code == 200, r.text
        reg = r.json()
        assert reg["quality"]["landmarks"][0]["after_mm"] < 1.5
        rid = reg["registration_id"]
        assert client.get(f"/api/v1/registrations/{rid}").json()["cache_key"] == reg["cache_key"]
        assert client.get(f"/api/v1/registrations/{rid}/field").status_code == 200
        assert client.post("/api/v1/registrations", json={**body, "moving_geometry_id": "nope"}).status_code == 404
        assert client.post(f"/api/v1/registrations/{rid}/propagate", json={"structures": ["Tumour"]}).status_code == 422     # name clash
        p = client.post(f"/api/v1/registrations/{rid}/propagate", json={"structures": ["Tumour"], "suffix": "_b"})
        assert p.status_code == 200, p.text
        gid = p.json()["geometry_id"]
        # the propagated geometry derives from the fixed geometry and the registration; the registration from both geometries
        node = LineageService().node(VersionRef(kind="geometry", id=gid))
        assert {r.key for r in node.parents} == {f"geometry:{fixed.geometry_id}", f"registration:{rid}"}
        rnode = LineageService().node(VersionRef(kind="registration", id=rid))
        assert {r.key for r in rnode.parents} == {f"geometry:{fixed.geometry_id}", f"geometry:{moving.geometry_id}"}
        # a dose on the moving geometry, mapped onto the fixed one, follows the tumour
        moving_dose = _dose_on(moving.geometry_id, mst["Tumour"].astype(np.float32) * 60.0)
        m = client.post(f"/api/v1/registrations/{rid}/map-dose", json={"dose_id": moving_dose})
        assert m.status_code == 200, m.text
        mapped = m.json()
        assert mapped["geometry_id"] == fixed.geometry_id and mapped["mapped_from"] == {"dose_id": moving_dose, "registration_id": rid}
        from radiarch.services.dose_persistence import read_dose_volume
        from pathlib import Path
        assert read_dose_volume(Path(mapped["dose_grid_uri"]))[st["Tumour"]].mean() > 50.0
        dnode = LineageService().node(VersionRef(kind="dose", id=mapped["dose_id"]))
        assert {f"dose:{moving_dose}", f"registration:{rid}", f"geometry:{fixed.geometry_id}"} <= {r.key for r in dnode.parents}
        assert client.post(f"/api/v1/registrations/{rid}/map-dose", json={"dose_id": mapped["dose_id"]}).status_code == 422   # not on the moving geometry
        assert client.delete(f"/api/v1/registrations/{rid}").status_code == 204
        assert client.get(f"/api/v1/registrations/{rid}").status_code == 404


def test_contour_metrics_of_two_shifted_spheres():
    from radiarch.services.contour_metrics import compare

    z, y, x = np.mgrid[:40, :40, :40]
    a = (x - 20) ** 2 + (y - 20) ** 2 + (z - 20) ** 2 <= 10 ** 2
    b = (x - 23) ** 2 + (y - 20) ** 2 + (z - 20) ** 2 <= 10 ** 2           # shifted 3 voxels along x
    same = compare(a, a, (2.0, 2.0, 2.0))
    assert same["dice"] == 1.0 and same["hd95_mm"] == 0.0 and same["msd_mm"] == 0.0
    c = compare(a, b, (2.0, 2.0, 2.0))
    assert 0.75 < c["dice"] < 0.8                                          # two unit spheres 0.3 radii apart: 0.776
    assert 5.0 <= c["hd95_mm"] <= 6.5                                      # the shift is 6 mm at the poles of the x axis
    assert 1.0 < c["msd_mm"] < 4.0
    assert compare(a, np.zeros_like(a), (1, 1, 1))["hd95_mm"] is None


def test_dicom_registration_objects_round_trip_and_bring_a_plan_across_frames(api_env, monkeypatch):
    """The registration written as DICOM REG objects reads back with the R2 reader in the standard's direction
    (registered point + vector = source point), and a plan made on the moving CT imports onto the fixed one."""
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.app import create_app
    from radiarch.dicom.reg import DeformableRegistration, SpatialRegistration, read_registration
    from radiarch.dicom.writers import CaseContext
    from radiarch.dicom.writers.rtplan import PlanWriteOptions, write_rtplan
    from radiarch.models.photon_plan import PhotonBeam, PhotonPlan, open_field_segment
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.registration import _centroid

    svc = RegistrationService()
    store = svc.geometry_service.store
    ct, st = _phantom()
    fixed = _save(store, ct, st, "1.2.826.0.1.3680043.8.498.71")
    t = sitk.Euler3DTransform((0.0, 0.0, 0.0), 0.0, 0.0, np.radians(2.0), (8.0, -5.0, 6.0))
    mct, mst = _moved(ct, st, t.GetInverse())
    moving = _save(store, mct, mst, "1.2.826.0.1.3680043.8.498.72")
    reg = svc.register(RegistrationRequest(fixed_geometry_id=fixed.geometry_id, moving_geometry_id=moving.geometry_id, deformable=DeformableMethod.demons,
                                           demons_iterations=30))
    written = svc.export_dicom(reg.registration_id)
    assert [w["sop_class_uid"].rsplit(".", 1)[-1] for w in written] == ["1", "3"]           # 66.1 spatial, 66.3 deformable
    rigid = read_registration(written[0]["path"])
    assert isinstance(rigid, SpatialRegistration) and rigid.frame_of_reference_uid == "1.2.826.0.1.3680043.8.498.71"
    fa, ma = load_geometry_arrays(fixed), load_geometry_arrays(moving)
    c_fixed, c_moving = _centroid(fa, "Tumour"), _centroid(ma, "Tumour")
    # the rigid matrix moves the moving (source) frame into the fixed (registered) one
    assert np.linalg.norm(rigid.transform_points("1.2.826.0.1.3680043.8.498.72", c_moving)[0] - c_fixed) < 1.5
    (dsr,) = read_registration(written[1]["path"])
    assert isinstance(dsr, DeformableRegistration) and dsr.source_frame_of_reference_uid == "1.2.826.0.1.3680043.8.498.72"
    idx = np.rint((c_fixed - np.asarray(dsr.grid_origin_mm)) / np.asarray(dsr.grid_spacing_mm)).astype(int)        # x, y, z
    grid_point = np.asarray(dsr.grid_origin_mm) + idx * np.asarray(dsr.grid_spacing_mm)
    source_point = grid_point + dsr.displacement_zyx[idx[2], idx[1], idx[0]]
    assert np.linalg.norm(source_point - c_moving) < 1.5 + float(np.linalg.norm(grid_point - c_fixed))

    # a plan made on the moving CT, centred on its tumour, in the moving frame of reference
    ctx = CaseContext(patient_id="R9", study_instance_uid="1.2.826.0.1.3680043.8.498.73", frame_of_reference_uid="1.2.826.0.1.3680043.8.498.72")
    plan = PhotonPlan(name="moving", beams=[PhotonBeam(beam_id="B1", gantry_deg=0.0, isocenter_mm=tuple(float(v) for v in c_moving),
                                                       segments=[open_field_segment((-20, 20), (-20, 20), 5.0, 100.0)])])
    rp = write_rtplan(ctx, plan, api_env / "RP_moving.dcm", rtstruct_uid="1.2.826.0.1.3680043.8.498.74", options=PlanWriteOptions(label="RESEARCH"))
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with TestClient(create_app()) as client:
        body = {"geometry_id": fixed.geometry_id, "path": rp.path, "machine_model_id": "synthetic-120"}
        assert client.post("/api/v1/beam-model/import", json=body).status_code == 422                   # another frame, no registration
        for extra in ({"registration_id": reg.registration_id}, {"registration_path": written[0]["path"]}):
            r = client.post("/api/v1/beam-model/import", json={**body, **extra})
            assert r.status_code == 200, r.text
            moved = BeamModelService().store.load_plan(r.json()["beam_model_id"])
            assert np.linalg.norm(np.asarray(moved.beams[0].isocenter_mm) - c_fixed) < 1.5           # onto the fixed tumour
        assert client.post("/api/v1/registrations/" + reg.registration_id + "/dicom").status_code == 200
