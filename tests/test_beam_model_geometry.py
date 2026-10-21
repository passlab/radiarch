"""The beam model is built on the geometry the caller named (R0, defect 3).

Before R0 the Beam Model service looked the geometry id up only to check
that it existed, then re-read the data root — so every beam model came
out of the default phantom. This test writes a geometry the way the
Geometry Service persists one (NIfTI CT and label volumes plus a record):
a water cube with a spherical PTV at the origin. Proton spot placement
through ``load_geometry_arrays`` must then put every spot on that sphere.
"""

from __future__ import annotations

import types

import numpy as np
import SimpleITK as sitk

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
    from radiarch.services.geometry_bundle import load_geometry_arrays
    from radiarch.services.machine_model import get_machine_model
    from radiarch.services.proton_spots import generate_proton_spots

    geom, n_target_voxels = _write_geometry(tmp_path)
    arrays = load_geometry_arrays(geom)
    assert arrays.target() == ("PTV", 1) and int(arrays.mask_zyx(1).sum()) == n_target_voxels
    assert arrays.patient_name == "WATER" and arrays.frame_of_reference_uid == "1.2.3.4"

    result = generate_proton_spots(
        geometry=arrays,
        machine_model=get_machine_model(Modality.proton_pbs, None),
        beam_set=BeamSetSpec(isocenter_mm=(0.0, 0.0, 0.0), beams=[BeamSpec(beam_id="B1", gantry_deg=0.0)]),
        params=DeliveryParams(),
    )
    assert result.fluence_elements.total_count > 0
    xy = np.array([(s.x_mm, s.y_mm) for beam in result.plan.beams for layer in beam.layers for s in layer.spots])
    # every spot within the sphere + the 5 mm placement margin (+ half a spot spacing)
    assert np.hypot(xy[:, 0], xy[:, 1]).max() <= RADIUS_MM + 5.0 + 2.5
    assert result.plan.beams[0].isocenter_mm == tuple(0.0 for _ in range(3))
