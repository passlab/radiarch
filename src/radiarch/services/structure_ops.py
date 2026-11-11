"""Structure operations on the geometry grid (roadmap R4).

Boolean masks in radiarch's ``(z, y, x)`` order with the grid spacing in
``(x, y, z)`` mm. Margins are Euclidean: an expansion by ``m`` keeps every
voxel whose centre lies within ``m`` of the structure (per-axis margins give
an ellipsoid), an erosion removes every voxel within ``m`` of the outside.

Directional margins (``expand_directional``, ``erode_directional``) give each
patient direction its own margin, 0 included: the ellipsoid's half-axis on
each side is that side's margin. With the six margins equal in pairs they give
what ``expand`` and ``erode`` give. The grid is in patient coordinates (LPS),
so +x is the patient's left, +y posterior and +z superior.
"""

from __future__ import annotations

from typing import Mapping, Sequence, Tuple, Union

import numpy as np
from scipy import ndimage, signal

Margin = Union[float, Sequence[float]]

# (negative side, positive side) of each array axis in (z, y, x) order
SIDES_ZYX = (("inferior", "superior"), ("anterior", "posterior"), ("right", "left"))


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


def _directional_element(spacing_xyz: Sequence[float], sides: Mapping[str, float]) -> Tuple[np.ndarray, Tuple[Tuple[int, int], ...]]:
    """The voxel offsets inside the directional ellipsoid, centred in an odd-sized (z, y, x) array, and per axis the
    number of voxels it reaches on the negative and the positive side."""
    spacing_zyx = (float(spacing_xyz[2]), float(spacing_xyz[1]), float(spacing_xyz[0]))
    reach, half, offsets = [], [], []
    for (neg, pos), sp in zip(SIDES_ZYX, spacing_zyx):
        m_neg, m_pos = float(sides.get(neg, 0.0)), float(sides.get(pos, 0.0))
        n_neg, n_pos = int(np.floor(m_neg / sp + 1e-9)), int(np.floor(m_pos / sp + 1e-9))
        r = max(n_neg, n_pos)
        k = np.arange(-r, r + 1, dtype=np.float64)
        # each offset over its side's margin; an offset on a side with no margin is outside
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(k < 0, k * sp / m_neg if m_neg > 0 else np.where(k == 0, 0.0, np.inf),
                         k * sp / m_pos if m_pos > 0 else np.where(k == 0, 0.0, np.inf))
        t = np.where(k == 0, 0.0, t)
        reach.append((n_neg, n_pos))
        half.append(r)
        offsets.append(t)
    tz, ty, tx = np.meshgrid(*offsets, indexing="ij")
    element = np.sqrt(tz ** 2 + ty ** 2 + tx ** 2) <= 1.0 + 1e-9
    return element, tuple(reach)


def _dilate(mask: np.ndarray, element: np.ndarray) -> np.ndarray:
    """The mask dilated by the element's offsets (centred), by an FFT convolution of the counts."""
    return signal.fftconvolve(mask.astype(np.float64), element.astype(np.float64), mode="same") > 0.5


def _sides(sides: Mapping[str, float]) -> Mapping[str, float]:
    bad = [k for k in sides if k not in {s for pair in SIDES_ZYX for s in pair}]
    if bad:
        raise ValueError(f"unknown margin directions {bad}; the directions are right, left, anterior, posterior, superior, inferior")
    if any(float(v) < 0 for v in sides.values()):
        raise ValueError("a directional margin is 0 or more")
    return sides


def expand_directional(mask: np.ndarray, spacing_xyz: Sequence[float], sides: Mapping[str, float]) -> np.ndarray:
    """The structure grown by a margin per patient direction (``right``, ``left``, ``anterior``, ``posterior``,
    ``superior``, ``inferior``, in mm; a direction left out is 0)."""
    m = np.asarray(mask, dtype=bool)
    if max((float(v) for v in _sides(sides).values()), default=0.0) <= 0 or not m.any():
        return m.copy()
    element, reach = _directional_element(spacing_xyz, sides)
    # work on the structure's box grown by the reach on each side
    nz = np.nonzero(m)
    box = tuple(slice(max(int(idx.min()) - lo, 0), min(int(idx.max()) + hi + 1, n))
                for idx, (lo, hi), n in zip(nz, reach, m.shape))
    out = np.zeros_like(m)
    out[box] = _dilate(m[box], element)
    return out


def erode_directional(mask: np.ndarray, spacing_xyz: Sequence[float], sides: Mapping[str, float]) -> np.ndarray:
    """The structure shrunk by a margin per patient direction: a voxel goes when a point within that direction's
    margin of it is outside. The grid's edge is not outside, as in ``erode``."""
    m = np.asarray(mask, dtype=bool)
    if max((float(v) for v in _sides(sides).values()), default=0.0) <= 0 or not m.any():
        return m.copy()
    element, reach = _directional_element(spacing_xyz, sides)
    nz = np.nonzero(m)
    lo_idx = [int(idx.min()) for idx in nz]
    hi_idx = [int(idx.max()) + 1 for idx in nz]
    # the structure's box, with room for the element's reach; outside the grid counts as inside the structure
    pad = [(lo, hi) for lo, hi in reach]
    outside = np.zeros(tuple(h - l + a + b for l, h, (a, b) in zip(lo_idx, hi_idx, pad)), dtype=bool)
    src = tuple(slice(max(l - a, 0), min(h + b, n)) for l, h, (a, b), n in zip(lo_idx, hi_idx, pad, m.shape))
    dst = tuple(slice(s.start - (l - a), s.stop - (l - a)) for s, l, (a, _) in zip(src, lo_idx, pad))
    outside[dst] = ~m[src]
    # a voxel x goes when x + b is outside for some offset b: the outside dilated by the reflected element
    hit = _dilate(outside, element[::-1, ::-1, ::-1])
    core = tuple(slice(a, a + (h - l)) for l, h, (a, _) in zip(lo_idx, hi_idx, pad))
    out = np.zeros_like(m)
    box = tuple(slice(l, h) for l, h in zip(lo_idx, hi_idx))
    out[box] = m[box] & ~hit[core]
    return out


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


__all__ = ["expand", "erode", "expand_directional", "erode_directional", "ring", "union", "intersection", "subtract",
           "couch_slab", "volume_cc"]
