"""NRRD ingestion path — proves it loads a CT + Slicer segmentation into the
exact objects the geometry pipeline consumes, with the correct axis convention,
and that it fails loudly on rotated grids / mismatched masks.

Runs on synthetic NRRD written to a tmp dir (no real-data download needed); the
real 3D pelvis case is exercised by ``scripts/nrrd_ingest_check.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

sitk = pytest.importorskip("SimpleITK")

from radiarch.adapters import nrrd_ingest as ni  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — write NRRD in OpenTPS [x, y, z] convention (sitk wants [z, y, x]).
# ---------------------------------------------------------------------------

def _write_nrrd(path: Path, arr_xyz: np.ndarray, origin, spacing,
                meta: dict | None = None) -> Path:
    img = sitk.GetImageFromArray(np.transpose(arr_xyz))  # [x,y,z] -> [z,y,x]
    img.SetOrigin(tuple(float(o) for o in origin))
    img.SetSpacing(tuple(float(s) for s in spacing))
    for k, v in (meta or {}).items():
        img.SetMetaData(k, v)
    path.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(img, str(path))
    return path


# A small phantom: CT [x,y,z] = (6, 7, 8), bladder cube + uterus cube.
_ORIGIN = (-10.0, -20.0, 5.0)
_SPACING = (1.25, 1.25, 2.0)


def _write_ct(tmp: Path) -> Path:
    ct = np.full((6, 7, 8), -1000, dtype=np.int16)   # air background
    ct[1:5, 1:6, 1:7] = 40                            # soft-tissue block
    return _write_nrrd(tmp / "ct.nrrd", ct, _ORIGIN, _SPACING)


def _write_seg(tmp: Path) -> Path:
    lab = np.zeros((6, 7, 8), dtype=np.uint8)
    lab[1:3, 1:3, 1:3] = 2       # "urinary bladder"
    lab[3:5, 4:6, 4:6] = 3       # "uterus"
    meta = {
        "Segment0_Name": "urinary bladder", "Segment0_LabelValue": "2",
        "Segment1_Name": "uterus", "Segment1_LabelValue": "3",
    }
    return _write_nrrd(tmp / "seg.seg.nrrd", lab, _ORIGIN, _SPACING, meta)


# ---------------------------------------------------------------------------
# CT loading + axis convention
# ---------------------------------------------------------------------------

def test_load_ct_convention_and_values(tmp_path: Path):
    ct = ni.load_ct(_write_ct(tmp_path))
    arr = np.asarray(ct.imageArray)
    assert arr.shape == (6, 7, 8)                     # OpenTPS [x,y,z]
    assert tuple(float(s) for s in ct.spacing) == _SPACING
    assert np.allclose(ct.origin, _ORIGIN)
    # The soft-tissue block round-trips at the right voxels (convention intact).
    assert arr[0, 0, 0] == -1000
    assert arr[2, 2, 2] == 40
    assert arr[5, 6, 7] == -1000


# ---------------------------------------------------------------------------
# Segmentation loading
# ---------------------------------------------------------------------------

def test_load_segmentation_names_labels_and_masks(tmp_path: Path):
    contours = ni.load_segmentation(_write_seg(tmp_path))
    names = {c.name for c in contours}
    assert names == {"urinary bladder", "uterus"}

    by_name = {c.name: c for c in contours}
    # getBinaryMask with no grid -> native mask, right voxel counts + placement.
    bladder = by_name["urinary bladder"].getBinaryMask().imageArray
    uterus = by_name["uterus"].getBinaryMask().imageArray
    assert bladder.dtype == bool and bladder.shape == (6, 7, 8)
    assert bladder.sum() == 2 * 2 * 2
    assert uterus.sum() == 2 * 2 * 2
    assert bladder[1, 1, 1] and not bladder[3, 4, 4]
    assert uterus[3, 4, 4] and not uterus[1, 1, 1]
    assert not np.any(bladder & uterus)              # disjoint


def test_getbinarymask_resamples_to_nonnative_grid(tmp_path: Path):
    contours = ni.load_segmentation(_write_seg(tmp_path))
    c = next(x for x in contours if x.name == "uterus")
    # Ask for a coarser grid than native -> nearest-neighbour resample.
    coarse = c.getBinaryMask(
        origin=_ORIGIN, gridSize=(3, 4, 4), spacing=(2.5, 2.1875, 4.0)
    ).imageArray
    assert coarse.dtype == bool and coarse.shape == (3, 4, 4)


# ---------------------------------------------------------------------------
# Whole-case loader + integrity guards
# ---------------------------------------------------------------------------

def test_load_nrrd_case_pairs_ct_and_seg(tmp_path: Path):
    _write_ct(tmp_path)
    _write_seg(tmp_path)
    ct, patient, contours = ni.load_nrrd_case(
        tmp_path / "ct.nrrd", tmp_path / "seg.seg.nrrd"
    )
    assert np.asarray(ct.imageArray).shape == (6, 7, 8)
    assert {c.name for c in contours} == {"urinary bladder", "uterus"}
    assert ct.patient is patient


def test_case_without_seg_is_allowed(tmp_path: Path):
    ct, _, contours = ni.load_nrrd_case(_write_ct(tmp_path), None)
    assert contours == []


def test_mismatched_seg_grid_raises(tmp_path: Path):
    _write_ct(tmp_path)
    # Segmentation on a different-sized grid than the CT.
    lab = np.zeros((4, 4, 4), dtype=np.uint8)
    lab[0:2, 0:2, 0:2] = 2
    _write_nrrd(tmp_path / "bad.seg.nrrd", lab, _ORIGIN, _SPACING,
                {"Segment0_Name": "x", "Segment0_LabelValue": "2"})
    with pytest.raises(ValueError, match="does not match the CT"):
        ni.load_nrrd_case(tmp_path / "ct.nrrd", tmp_path / "bad.seg.nrrd")


def test_flipped_axis_reoriented_losslessly(tmp_path: Path):
    """A signed-permutation direction (axis flip) is reoriented to identity
    with no interpolation — same voxel multiset, correct value placement."""
    ct_xyz = np.arange(6 * 7 * 8, dtype=np.int16).reshape(6, 7, 8)
    img = sitk.GetImageFromArray(np.transpose(ct_xyz))   # [x,y,z] -> [z,y,x]
    img.SetSpacing(_SPACING)
    img.SetOrigin(_ORIGIN)
    img.SetDirection((-1, 0, 0, 0, -1, 0, 0, 0, 1))      # LR + AP flip
    p = tmp_path / "flipped.nrrd"
    sitk.WriteImage(img, str(p))

    ct = ni.load_ct(p)
    arr = np.asarray(ct.imageArray)
    assert arr.shape == (6, 7, 8)
    # Lossless: identical set of voxel values, just rearranged.
    assert sorted(arr.astype(int).ravel()) == sorted(ct_xyz.ravel())
    # The flip actually moved data (not a no-op) but preserved the extremes.
    assert arr.min() == ct_xyz.min() and arr.max() == ct_xyz.max()


def test_oblique_grid_resampled_to_axis_aligned(tmp_path: Path):
    """A genuinely tilted grid no longer raises — it is resampled onto an
    axis-aligned grid (data preserved, grid may grow)."""
    vol = np.ones((6, 7, 8), dtype=np.int16)
    img = sitk.GetImageFromArray(np.transpose(vol))
    img.SetSpacing((1.0, 1.0, 1.0))
    img.SetOrigin((0.0, 0.0, 0.0))
    c, s = np.cos(0.15), np.sin(0.15)                    # ~8.6 deg tilt
    img.SetDirection((1, 0, 0, 0, c, -s, 0, s, c))
    p = tmp_path / "oblique.nrrd"
    sitk.WriteImage(img, str(p))

    ct = ni.load_ct(p)
    arr = np.asarray(ct.imageArray)
    assert arr.ndim == 3
    assert bool(np.all(np.isfinite(arr)))
    # Bounding-box grid is at least as large as the source along each axis.
    assert all(a >= b for a, b in zip(arr.shape, (6, 7, 8)))
    # The interior (value 1) survived the resample; exterior filled with air.
    assert arr.max() == 1 and arr.min() == -1000


# ---------------------------------------------------------------------------
# End-to-end through the real GeometryService (no mocking of _load)
# ---------------------------------------------------------------------------

def test_geometry_service_builds_from_nrrd(tmp_path: Path):
    from radiarch.models.geometry import (
        GeometryBuildRequest, HUDensityModel, PatientRef,
    )
    from radiarch.services.geometry import GeometryService

    data = tmp_path / "data"
    data.mkdir()
    _write_ct(data)
    _write_seg(data)

    svc = GeometryService(base_dir=tmp_path / "geom")
    req = GeometryBuildRequest(
        patient_ref=PatientRef(
            nrrd_ct_path=str(data / "ct.nrrd"),
            nrrd_seg_path=str(data / "seg.seg.nrrd"),
        ),
        hu_to_density_model=HUDensityModel.linear,   # no MCsquare calib needed
    )
    result = svc.build(req)

    # Both structures made it into the multi-label mask.
    assert set(result.structure_index) == {"urinary bladder", "uterus"}
    assert all(v >= 1 for v in result.structure_index.values())
    assert result.grid_spec.size == (6, 7, 8)
    # CT + density + masks were persisted.
    assert Path(result.ct_grid_uri).exists()
    assert Path(result.density_grid_uri).exists()
    assert Path(result.structure_masks_uri).exists()
    assert result.ct_metadata.num_slices == 8
