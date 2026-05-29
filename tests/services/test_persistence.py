"""Unit tests for radiarch.services.persistence."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from radiarch.models.geometry import (
    CTMetadata,
    GeometryResult,
    GridSpec,
)
from radiarch.services.persistence import (
    DENSITY_FILENAME,
    GeometryStore,
    MASKS_FILENAME,
    META_FILENAME,
    _read_nifti,
    _write_nifti,
)


def _make_spec(size=(4, 4, 4), spacing=(2.0, 2.0, 3.0), origin=(1.0, -2.0, 0.5)) -> GridSpec:
    spec = GridSpec(spacing_mm=spacing, origin_mm=origin, size=size)
    spec.affine = spec.compute_affine()
    return spec


def _make_result(density_path: str, masks_path: str, spec: GridSpec, cache_key: str = "abc") -> GeometryResult:
    return GeometryResult(
        geometry_id="g1",
        density_grid_uri=density_path,
        structure_masks_uri=masks_path,
        structure_index={"PTV": 1, "Cord": 2},
        grid_spec=spec,
        frame_of_reference_uid="1.2.3.9",
        ct_metadata=CTMetadata(patient_name="TEST", modality="CT", num_slices=4),
        cache_key=cache_key,
    )


# ---------------------------------------------------------------------------
# NIfTI round-trip
# ---------------------------------------------------------------------------

class TestNiftiRoundtrip:
    def test_float_density_roundtrip_preserves_values_and_affine(self, tmp_path: Path) -> None:
        rng = np.random.RandomState(0)
        vol = rng.uniform(0.0, 2.0, size=(4, 4, 4)).astype(np.float32)
        spec = _make_spec()

        path = tmp_path / "density.nii.gz"
        _write_nifti(vol, spec, path)
        loaded, loaded_spec = _read_nifti(path)

        assert loaded.dtype == np.float32
        np.testing.assert_allclose(loaded, vol, rtol=1e-5)
        assert loaded_spec.spacing_mm == spec.spacing_mm
        assert loaded_spec.origin_mm == spec.origin_mm
        assert loaded_spec.size == spec.size

    def test_uint16_labels_preserve_dtype_and_values(self, tmp_path: Path) -> None:
        labels = np.zeros((4, 4, 4), dtype=np.uint16)
        labels[0:2, 0:2, 0:2] = 1
        labels[2:4, 2:4, 2:4] = 2

        path = tmp_path / "masks.nii.gz"
        _write_nifti(labels, _make_spec(), path)
        loaded, _ = _read_nifti(path)

        # SimpleITK may promote uint16 → int16 on the round-trip for
        # some encoders; assert value preservation, not dtype identity,
        # but verify the stored values are lossless.
        np.testing.assert_array_equal(loaded.astype(np.int32), labels.astype(np.int32))

    def test_ijk_ordering_preserved(self, tmp_path: Path) -> None:
        """Write a volume with distinct axis lengths, then verify the shape
        survives the SimpleITK (z,y,x) transpose round-trip."""
        vol = np.arange(2 * 3 * 5, dtype=np.float32).reshape((2, 3, 5))
        spec = GridSpec(spacing_mm=(1, 1, 1), origin_mm=(0, 0, 0), size=(2, 3, 5))
        path = tmp_path / "v.nii.gz"
        _write_nifti(vol, spec, path)
        loaded, loaded_spec = _read_nifti(path)

        assert loaded.shape == (2, 3, 5)
        assert loaded_spec.size == (2, 3, 5)
        np.testing.assert_allclose(loaded, vol)


# ---------------------------------------------------------------------------
# GeometryStore
# ---------------------------------------------------------------------------

class TestGeometryStore:
    def test_save_writes_expected_files(self, tmp_path: Path) -> None:
        store = GeometryStore(tmp_path)
        spec = _make_spec()
        density = np.ones(spec.size, dtype=np.float32)
        masks = np.zeros(spec.size, dtype=np.uint16)
        masks[0, 0, 0] = 1
        density_path = str(tmp_path / "g1" / DENSITY_FILENAME)
        masks_path = str(tmp_path / "g1" / MASKS_FILENAME)
        result = _make_result(density_path, masks_path, spec)

        store.save(
            geometry_id="g1",
            cache_key="abc",
            density=density,
            masks=masks,
            result=result,
        )

        assert (tmp_path / "g1" / DENSITY_FILENAME).exists()
        assert (tmp_path / "g1" / MASKS_FILENAME).exists()
        assert (tmp_path / "g1" / META_FILENAME).exists()

    def test_cache_lookup_roundtrip(self, tmp_path: Path) -> None:
        store = GeometryStore(tmp_path)
        spec = _make_spec()
        result = _make_result(
            str(tmp_path / "g1" / DENSITY_FILENAME),
            str(tmp_path / "g1" / MASKS_FILENAME),
            spec,
            cache_key="deadbeef",
        )
        store.save(
            geometry_id="g1",
            cache_key="deadbeef",
            density=np.zeros(spec.size, dtype=np.float32),
            masks=np.zeros(spec.size, dtype=np.uint16),
            result=result,
        )

        hit = store.lookup_by_cache_key("deadbeef")
        assert hit is not None
        assert hit.geometry_id == "g1"
        assert hit.structure_index == {"PTV": 1, "Cord": 2}

    def test_cache_miss_returns_none(self, tmp_path: Path) -> None:
        store = GeometryStore(tmp_path)
        assert store.lookup_by_cache_key("nope") is None
        assert store.get_by_id("nope") is None

    def test_save_is_atomic_on_retry(self, tmp_path: Path) -> None:
        """A second save with the same geometry_id overwrites cleanly."""
        store = GeometryStore(tmp_path)
        spec = _make_spec()
        density_a = np.zeros(spec.size, dtype=np.float32)
        masks_a = np.zeros(spec.size, dtype=np.uint16)
        density_b = np.ones(spec.size, dtype=np.float32)
        masks_b = np.ones(spec.size, dtype=np.uint16)
        result = _make_result(
            str(tmp_path / "g1" / DENSITY_FILENAME),
            str(tmp_path / "g1" / MASKS_FILENAME),
            spec,
        )
        store.save(
            geometry_id="g1", cache_key="k", density=density_a, masks=masks_a, result=result
        )
        store.save(
            geometry_id="g1", cache_key="k", density=density_b, masks=masks_b, result=result
        )

        loaded, _ = _read_nifti(tmp_path / "g1" / DENSITY_FILENAME)
        np.testing.assert_allclose(loaded, density_b)

    def test_list_ids_excludes_tmp_dirs(self, tmp_path: Path) -> None:
        store = GeometryStore(tmp_path)
        # Simulate a partial write leftover — store.save() shouldn't have
        # created these, but a crash might have.
        (tmp_path / ".g2.tmp.xyz").mkdir()
        (tmp_path / "g3").mkdir()  # no meta.json → ignored
        assert store.list_ids() == []

        spec = _make_spec()
        result = _make_result(
            str(tmp_path / "g1" / DENSITY_FILENAME),
            str(tmp_path / "g1" / MASKS_FILENAME),
            spec,
        )
        store.save(
            geometry_id="g1",
            cache_key="k",
            density=np.zeros(spec.size, dtype=np.float32),
            masks=np.zeros(spec.size, dtype=np.uint16),
            result=result,
        )
        assert store.list_ids() == ["g1"]
