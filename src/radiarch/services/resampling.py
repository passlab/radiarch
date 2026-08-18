"""Grid resampling between axis-aligned voxel grids.

The Geometry Service frequently needs to map a source volume (defined on
the native CT grid with some affine ``A_src``) onto a user-specified
target grid (defined by a :class:`GridSpec`). This module provides one
function that does exactly that, correctly and in a single pass.

Design notes
------------
* **Axis-aligned only.** v1 assumes the CT's patient-LPS axes are aligned
  with the target grid's axes. The affines are diagonal apart from the
  translation component. We deliberately reject rotated affines here
  rather than silently resampling them incorrectly — rotational
  resampling is a separate, more expensive operation we'll add when we
  actually encounter a rotated scanner.
* **Interpolation order.** Order 1 (trilinear) is correct for continuous
  fields (density, dose). Order 0 (nearest-neighbor) is correct for
  label volumes (masks, segmentations); anything higher than 0 corrupts
  integer labels.
* **Out-of-bounds.** Fill with a caller-supplied constant (0.0 by default
  for densities, 0 for masks — 0 = "outside / background" for both).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
from scipy.ndimage import map_coordinates

from ..models.geometry import GridSpec


def _extract_diagonal_affine(affine: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return (spacing, origin) from a 4×4 affine; raise if not axis-aligned.

    Tolerates tiny floating-point noise in the off-diagonal entries
    (<= 1e-9) — DICOM ImageOrientationPatient is often not bit-exactly
    identity even on unrotated scans.
    """
    affine = np.asarray(affine, dtype=np.float64)
    if affine.shape != (4, 4):
        raise ValueError(f"Expected 4×4 affine, got shape {affine.shape}")

    rot = affine[:3, :3]
    off_diag = rot - np.diag(np.diagonal(rot))
    if np.any(np.abs(off_diag) > 1e-6):
        raise NotImplementedError(
            "Rotated affines are not supported in v1 of the Geometry Service. "
            f"Off-diagonal magnitude: {np.abs(off_diag).max():.3g}"
        )

    spacing = np.diagonal(rot).copy()
    if np.any(spacing <= 0):
        raise ValueError(f"Non-positive spacing on affine diagonal: {spacing}")
    origin = affine[:3, 3].copy()
    return spacing, origin


def resample_to_grid(
    volume: np.ndarray,
    src_affine: np.ndarray,
    target: GridSpec,
    *,
    order: int = 1,
    cval: float = 0.0,
) -> np.ndarray:
    """Resample ``volume`` onto ``target`` and return the resampled array.

    Parameters
    ----------
    volume
        Source volume, shape ``(ni, nj, nk)``. Dtype is preserved for
        integer order=0 (labels) and cast to float32 for order >= 1
        (continuous fields).
    src_affine
        4×4 voxel-index → patient-LPS affine of ``volume``. Must be
        axis-aligned; rotational affines raise.
    target
        Fully-specified :class:`GridSpec` (must have non-None ``origin_mm``
        and ``size``).
    order
        Interpolation order. ``1`` (trilinear) for density/dose, ``0``
        (nearest-neighbor) for masks/labels. Values > 1 are valid but
        rarely useful here.
    cval
        Fill value for out-of-bounds voxels (outside the source extent).

    Returns
    -------
    numpy.ndarray
        Volume on the target grid, shape == ``target.size``.
    """
    if not target.is_fully_specified():
        raise ValueError(
            "resample_to_grid requires a fully specified target GridSpec "
            "(origin_mm and size must both be set)"
        )

    volume = np.asarray(volume)
    if volume.ndim != 3:
        raise ValueError(f"volume must be 3D, got shape {volume.shape}")

    src_spacing, src_origin = _extract_diagonal_affine(np.asarray(src_affine))
    tgt_spacing = np.asarray(target.spacing_mm, dtype=np.float64)
    tgt_origin = np.asarray(target.origin_mm, dtype=np.float64)
    tgt_size = np.asarray(target.size, dtype=np.int64)

    # Build the target-voxel-index grid (i, j, k).
    ii, jj, kk = np.meshgrid(
        np.arange(tgt_size[0]),
        np.arange(tgt_size[1]),
        np.arange(tgt_size[2]),
        indexing="ij",
    )

    # Target voxel index → patient-LPS mm → source voxel index.
    # Because both affines are diagonal, this collapses to per-axis
    # arithmetic: src_idx = (tgt_origin + tgt_idx * tgt_spacing - src_origin) / src_spacing
    src_i = (tgt_origin[0] + ii * tgt_spacing[0] - src_origin[0]) / src_spacing[0]
    src_j = (tgt_origin[1] + jj * tgt_spacing[1] - src_origin[1]) / src_spacing[1]
    src_k = (tgt_origin[2] + kk * tgt_spacing[2] - src_origin[2]) / src_spacing[2]

    coords = np.stack([src_i, src_j, src_k], axis=0)

    # Preserve integer dtype for labels; cast continuous fields to float32.
    if order == 0 and np.issubdtype(volume.dtype, np.integer):
        work = volume
        out_dtype = volume.dtype
    else:
        work = volume.astype(np.float32, copy=False)
        out_dtype = np.float32

    resampled = map_coordinates(
        work, coords, order=order, mode="constant", cval=cval, prefilter=(order > 1)
    )
    return resampled.astype(out_dtype, copy=False)


def identity_grid_from_affine(affine: np.ndarray, size: Tuple[int, int, int]) -> GridSpec:
    """Build the :class:`GridSpec` that matches ``affine`` + ``size`` exactly.

    Convenience: lets callers reuse the source CT grid as the target
    GridSpec when no explicit grid is requested (the "null grid_spec"
    fast path in ``GeometryBuildRequest``).
    """
    spacing, origin = _extract_diagonal_affine(np.asarray(affine))
    spec = GridSpec(
        spacing_mm=tuple(float(s) for s in spacing),
        origin_mm=tuple(float(o) for o in origin),
        size=tuple(int(s) for s in size),
    )
    spec.affine = spec.compute_affine()
    return spec


__all__ = ["resample_to_grid", "identity_grid_from_affine"]
