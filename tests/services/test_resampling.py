"""Unit tests for the grid resampling module."""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.models.geometry import GridSpec
from radiarch.services.resampling import (
    identity_grid_from_affine,
    resample_to_grid,
)


def _identity_affine(spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0)) -> np.ndarray:
    sx, sy, sz = spacing
    ox, oy, oz = origin
    return np.array(
        [
            [sx, 0.0, 0.0, ox],
            [0.0, sy, 0.0, oy],
            [0.0, 0.0, sz, oz],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


class TestIdentityResample:
    def test_same_grid_is_a_noop(self) -> None:
        rng = np.random.RandomState(0)
        vol = rng.uniform(-1000, 1000, size=(8, 8, 8)).astype(np.float32)
        affine = _identity_affine(spacing=(2.0, 2.0, 3.0), origin=(10.0, -20.0, 0.0))
        target = identity_grid_from_affine(affine, size=vol.shape)

        out = resample_to_grid(vol, affine, target, order=1)
        np.testing.assert_allclose(out, vol, atol=1e-5)

    def test_identity_grid_from_affine_roundtrip(self) -> None:
        affine = _identity_affine(spacing=(1.5, 1.5, 2.0), origin=(5.0, 5.0, 5.0))
        spec = identity_grid_from_affine(affine, size=(4, 4, 4))
        assert spec.spacing_mm == (1.5, 1.5, 2.0)
        assert spec.origin_mm == (5.0, 5.0, 5.0)
        assert spec.size == (4, 4, 4)
        np.testing.assert_allclose(spec.to_numpy_affine(), affine)


class TestContinuousResample:
    def test_upsample_halving_spacing_preserves_smooth_field(self) -> None:
        # Build a low-frequency linear ramp on a coarse grid, then
        # upsample 2× — trilinear must reproduce the analytic field.
        x = np.arange(10, dtype=np.float32)
        y = np.arange(10, dtype=np.float32)
        z = np.arange(10, dtype=np.float32)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        ramp = (X + 2 * Y + 3 * Z).astype(np.float32)
        src_affine = _identity_affine(spacing=(2.0, 2.0, 2.0), origin=(0.0, 0.0, 0.0))

        # Target: same extent, half the spacing, so 2× more voxels per axis.
        target = GridSpec(
            spacing_mm=(1.0, 1.0, 1.0),
            origin_mm=(0.0, 0.0, 0.0),
            size=(19, 19, 19),
        )
        out = resample_to_grid(ramp, src_affine, target, order=1)

        # Analytic comparison: at target index (i,j,k), mm coords are
        # (i*1, j*1, k*1); in source index that's (i/2, j/2, k/2); the
        # ramp value there is i/2 + 2*(j/2) + 3*(k/2) = 0.5i + j + 1.5k.
        ii, jj, kk = np.meshgrid(
            np.arange(19), np.arange(19), np.arange(19), indexing="ij"
        )
        expected = (0.5 * ii + jj + 1.5 * kk).astype(np.float32)
        np.testing.assert_allclose(out, expected, atol=1e-4)

    def test_out_of_bounds_filled_with_cval(self) -> None:
        vol = np.ones((4, 4, 4), dtype=np.float32) * 7.0
        src_affine = _identity_affine(spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0))
        # Target extends past the source → out-of-bounds voxels filled with cval.
        target = GridSpec(
            spacing_mm=(1.0, 1.0, 1.0),
            origin_mm=(0.0, 0.0, 0.0),
            size=(8, 8, 8),
        )
        out = resample_to_grid(vol, src_affine, target, order=1, cval=-999.0)

        # The inner 4×4×4 block is still 7.0; the rest is -999.
        assert out[0, 0, 0] == pytest.approx(7.0)
        assert out[7, 7, 7] == pytest.approx(-999.0)


class TestLabelResample:
    def test_nearest_neighbor_preserves_integer_labels(self) -> None:
        labels = np.zeros((4, 4, 4), dtype=np.uint16)
        labels[1:3, 1:3, 1:3] = 5  # cube of label 5
        src_affine = _identity_affine(spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0))
        # Shift + upsample the target grid, forcing real resampling.
        target = GridSpec(
            spacing_mm=(0.5, 0.5, 0.5),
            origin_mm=(0.0, 0.0, 0.0),
            size=(7, 7, 7),
        )
        out = resample_to_grid(labels, src_affine, target, order=0, cval=0)

        # No fractional labels were invented.
        unique = set(np.unique(out).tolist())
        assert unique <= {0, 5}
        assert out.dtype == labels.dtype

    def test_label_resample_integer_cval(self) -> None:
        labels = np.ones((3, 3, 3), dtype=np.uint16) * 9
        src_affine = _identity_affine()
        target = GridSpec(
            spacing_mm=(1.0, 1.0, 1.0),
            origin_mm=(-5.0, -5.0, -5.0),
            size=(3, 3, 3),
        )
        out = resample_to_grid(labels, src_affine, target, order=0, cval=0)
        # Completely outside source → all background.
        assert np.all(out == 0)


class TestAffineValidation:
    def test_rejects_rotated_affine(self) -> None:
        rotated = _identity_affine()
        # Plant a small rotation into the x/y plane.
        rotated[0, 1] = 0.1
        rotated[1, 0] = -0.1
        target = GridSpec(spacing_mm=(1, 1, 1), origin_mm=(0, 0, 0), size=(2, 2, 2))
        vol = np.zeros((2, 2, 2), dtype=np.float32)
        with pytest.raises(NotImplementedError, match="Rotated affines"):
            resample_to_grid(vol, rotated, target, order=1)

    def test_rejects_zero_spacing(self) -> None:
        bad = _identity_affine(spacing=(1.0, 0.0, 1.0))
        target = GridSpec(spacing_mm=(1, 1, 1), origin_mm=(0, 0, 0), size=(2, 2, 2))
        vol = np.zeros((2, 2, 2), dtype=np.float32)
        with pytest.raises(ValueError, match="Non-positive spacing"):
            resample_to_grid(vol, bad, target, order=1)

    def test_requires_fully_specified_target(self) -> None:
        partial = GridSpec(spacing_mm=(1, 1, 1))  # origin/size omitted
        vol = np.zeros((2, 2, 2), dtype=np.float32)
        with pytest.raises(ValueError, match="fully specified"):
            resample_to_grid(vol, _identity_affine(), partial, order=1)
