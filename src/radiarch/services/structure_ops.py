"""Structure operations on the geometry grid (roadmap R4).

Boolean masks in radiarch's ``(z, y, x)`` order with the grid spacing in
``(x, y, z)`` mm. Margins are Euclidean: an expansion by ``m`` keeps every
voxel whose centre lies within ``m`` of the structure (per-axis margins give
an ellipsoid), an erosion removes every voxel within ``m`` of the outside.
"""

from __future__ import annotations

from typing import Sequence, Tuple, Union

import numpy as np
from scipy import ndimage

Margin = Union[float, Sequence[float]]


def _per_axis_mm(margin: Margin) -> Tuple[float, float, float]:
    if np.isscalar(margin):
        v = float(margin)
        return (v, v, v)
    vals = [float(v) for v in margin]
    if len(vals) != 3:
        raise ValueError("a margin is one value or three (x, y, z) values in mm")
    return (vals[0], vals[1], vals[2])


def _sampling_zyx(spacing_xyz: Sequence[float], margin_xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Voxel sizes scaled so that the margin becomes 1 on every axis (an ellipsoid)."""
    sx, sy, sz = (float(v) for v in spacing_xyz)
    mx, my, mz = margin_xyz
    return (sz / mz if mz > 0 else np.inf, sy / my if my > 0 else np.inf, sx / mx if mx > 0 else np.inf)


def expand(mask: np.ndarray, spacing_xyz: Sequence[float], margin_mm: Margin) -> np.ndarray:
    """The structure grown by ``margin_mm`` (one value, or (x, y, z))."""
    m = np.asarray(mask, dtype=bool)
    margin = _per_axis_mm(margin_mm)
    if max(margin) <= 0:
        return m.copy()
    if min(margin) <= 0:
        raise ValueError("every margin must be positive for an expansion (use 0 for all axes to skip)")
    if not m.any():
        return m.copy()
    dist = ndimage.distance_transform_edt(~m, sampling=_sampling_zyx(spacing_xyz, margin))
    return dist <= 1.0 + 1e-9


def erode(mask: np.ndarray, spacing_xyz: Sequence[float], margin_mm: Margin) -> np.ndarray:
    """The structure shrunk by ``margin_mm``."""
    m = np.asarray(mask, dtype=bool)
    margin = _per_axis_mm(margin_mm)
    if max(margin) <= 0:
        return m.copy()
    if min(margin) <= 0:
        raise ValueError("every margin must be positive for an erosion")
    if not m.any():
        return m.copy()
    dist = ndimage.distance_transform_edt(m, sampling=_sampling_zyx(spacing_xyz, margin))
    return dist > 1.0 + 1e-9


def ring(mask: np.ndarray, spacing_xyz: Sequence[float], inner_mm: Margin, outer_mm: Margin) -> np.ndarray:
    """The shell between the ``inner_mm`` and ``outer_mm`` expansions of the structure."""
    outer = expand(mask, spacing_xyz, outer_mm)
    inner = expand(mask, spacing_xyz, inner_mm) if max(_per_axis_mm(inner_mm)) > 0 else np.asarray(mask, dtype=bool)
    return outer & ~inner


def union(*masks: np.ndarray) -> np.ndarray:
    out = np.zeros_like(np.asarray(masks[0], dtype=bool))
    for m in masks:
        out |= np.asarray(m, dtype=bool)
    return out


def intersection(*masks: np.ndarray) -> np.ndarray:
    out = np.ones_like(np.asarray(masks[0], dtype=bool))
    for m in masks:
        out &= np.asarray(m, dtype=bool)
    return out


def subtract(mask: np.ndarray, *others: np.ndarray) -> np.ndarray:
    out = np.asarray(mask, dtype=bool).copy()
    for m in others:
        out &= ~np.asarray(m, dtype=bool)
    return out


def couch_slab(shape_zyx: Tuple[int, int, int], origin_xyz: Sequence[float], spacing_xyz: Sequence[float],
               y_top_mm: float, thickness_mm: float) -> np.ndarray:
    """A treatment-couch slab: every voxel with ``y_top_mm <= y < y_top_mm + thickness_mm``
    (patient y grows posteriorly in LPS, so the couch lies at larger y than the patient)."""
    nz, ny, nx = shape_zyx
    y = float(origin_xyz[1]) + float(spacing_xyz[1]) * np.arange(ny)
    rows = (y >= y_top_mm - 1e-6) & (y < y_top_mm + thickness_mm - 1e-6)
    out = np.zeros(shape_zyx, dtype=bool)
    out[:, rows, :] = True
    return out


def volume_cc(mask: np.ndarray, spacing_xyz: Sequence[float]) -> float:
    return float(np.asarray(mask, dtype=bool).sum()) * float(np.prod([float(v) for v in spacing_xyz])) / 1000.0


__all__ = ["expand", "erode", "ring", "union", "intersection", "subtract", "couch_slab", "volume_cc"]
