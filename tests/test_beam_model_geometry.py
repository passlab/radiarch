"""The beam model is built on the geometry the caller named (R0, defect 3).

Before R0 the Beam Model service looked the geometry id up only to check
that it existed, then re-read ``opentps_data_root`` — so every beam model
came out of the default phantom. This test writes a geometry the way the
Geometry Service persists one (NIfTI CT and label volumes plus a record):
a water cube with a spherical PTV at the origin. Proton spot placement
through ``load_opentps_geometry`` must then put every spot on that sphere.
Needs the vendored OpenTPS (ray tracing in ``libRayTracing``).
"""

from __future__ import annotations

import types

import numpy as np
import pytest
import SimpleITK as sitk


def _opentps_available() -> bool:
    try:
        import opentps.core  # noqa: F401
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _opentps_available(), reason="vendored OpenTPS not importable")

N = 40                 # voxels per axis
SPACING_MM = 2.0       # → an 80 mm water cube
RADIUS_MM = 16.0       # PTV sphere


def _write_geometry(tmp_path):
    """Persist a synthetic geometry record: water cube, spherical PTV centred at 0."""
    centre_vox = (N - 1) / 2.0
    zz, yy, xx = np.mgrid[:N, :N, :N]
    r2 = (zz - centre_vox) ** 2 + (yy - centre_vox) ** 2 + (xx - centre_vox) ** 2
    sphere = r2 <= (RADIUS_MM / SPACING_MM) ** 2

    ct_zyx = np.zeros((N, N, N), dtype=np.int16)           # water everywhere
    masks_zyx = np.zeros((N, N, N), dtype=np.uint16)
    masks_zyx[sphere] = 1

    origin = (-centre_vox * SPACING_MM,) * 3                # voxel centres span ±39 mm
    paths = {}
    for name, arr in (("ct", ct_zyx), ("masks", masks_zyx)):
        img = sitk.GetImageFromArray(arr)
        img.SetSpacing((SPACING_MM,) * 3)
        img.SetOrigin(origin)
        paths[name] = tmp_path / f"{name}.nii.gz"
        sitk.WriteImage(img, str(paths[name]))

    geom = types.SimpleNamespace(
        geometry_id="g-water-sphere",
        ct_grid_uri=str(paths["ct"]),
        structure_masks_uri=str(paths["masks"]),
        structure_index={"PTV": 1},
        grid_spec=types.SimpleNamespace(spacing_mm=(SPACING_MM,) * 3, origin_mm=origin),
        ct_metadata=types.SimpleNamespace(patient_name="WATER", series_instance_uid="1.2.3"),
        frame_of_reference_uid="1.2.3.4",
    )
    return geom, int(sphere.sum())


def test_proton_spots_follow_the_named_target(tmp_path):
    from radiarch.models.beam_model import BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from radiarch.services.geometry_bundle import load_opentps_geometry
    from radiarch.services.machine_model import get_machine_model
    from radiarch.services.proton_spots import generate_proton_spots

    geom, n_target_voxels = _write_geometry(tmp_path)
    ct, patient, target = load_opentps_geometry(geom)
    assert target is not None and int(target.imageArray.sum()) == n_target_voxels

    result = generate_proton_spots(
        ct=ct,
        patient=patient,
        target_contour=target,
        machine_model=get_machine_model(Modality.proton_pbs, None),
        beam_set=BeamSetSpec(isocenter_mm=(0.0, 0.0, 0.0),
                             beams=[BeamSpec(beam_id="B1", gantry_deg=0.0)]),
        params=DeliveryParams(),
    )

    assert result.fluence_elements.total_count > 0
    xy = np.array([[x, y] for layer in result.plan.beams[0].layers for x, y in layer.spotXY], dtype=float)
    assert len(xy) == result.fluence_elements.total_count
    # Every spot sits on the sphere: radius + the 5 mm placement margin + one
    # spot spacing of slack. The default phantom's target is nowhere near this.
    spot_spacing = DeliveryParams().spot_spacing_mm or 5.0
    assert np.abs(xy).max() <= RADIUS_MM + 5.0 + spot_spacing
    # And it is centred on the sphere, not on some other CT's target.
    assert np.abs(xy.mean(axis=0)).max() <= spot_spacing


def test_beam_model_service_reads_the_persisted_geometry(tmp_path, monkeypatch):
    """Through the service: the geometry store holds the record, the beam
    model is built from it, and the OpenTPS plan ends up pickled next to it."""
    from radiarch.models.beam_model import (
        BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality,
    )
    from radiarch.services.beam_model import BeamModelService

    geom, _ = _write_geometry(tmp_path)

    class _Store:
        def get_by_id(self, geometry_id):
            return geom if geometry_id == geom.geometry_id else None

    import radiarch.services.geometry as geometry_mod
    monkeypatch.setattr(geometry_mod.GeometryService, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(geometry_mod.GeometryService, "store", _Store(), raising=False)

    svc = BeamModelService(base_dir=tmp_path / "beam_models")
    result = svc.build(BeamModelBuildRequest(
        geometry_id=geom.geometry_id,
        modality=Modality.proton_pbs,
        beam_set=BeamSetSpec(isocenter_mm=(0.0, 0.0, 0.0),
                             beams=[BeamSpec(beam_id="B1", gantry_deg=90.0)]),
        delivery_params=DeliveryParams(),
    ))
    assert result.geometry_id == geom.geometry_id
    assert result.fluence_elements.total_count > 0
    assert (tmp_path / "beam_models").exists()

    with pytest.raises(ValueError, match="not found"):
        svc.build(BeamModelBuildRequest(
            geometry_id="no-such-geometry",
            modality=Modality.proton_pbs,
            beam_set=BeamSetSpec(isocenter_mm=(0.0, 0.0, 0.0),
                                 beams=[BeamSpec(beam_id="B1", gantry_deg=0.0)]),
        ))
