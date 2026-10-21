"""Contour polygons → a mask on a grid (roadmap R15).

A port of the partial-volume rasterizer of OpenTPS 3.0.1
(``ROIContour.get_partial_volume_mask``, Apache-2.0), kept step for step so
the structure masks built before R15 rebuild identically (``tests/golden``):

* polygons are grouped by their median z (rounded to a tolerance of 2 % of
  the slice spacing); the bounding box of the contour on the grid is rasterized
  with ``skimage.draw.polygon2mask`` on a supersampled grid (``precision`` per
  axis, reduced for large boxes) and averaged down to a partial volume; polygons
  on the same slice combine by exclusive-or (holes);
* when the grid is finer than the contour slices, slices in between are
  interpolated from their neighbours; otherwise every grid slice between the
  first and last contour takes the nearest contour;
* the result is thresholded at 0.5 and placed into the full ``(x, y, z)`` grid.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from skimage.draw import polygon2mask


def _round_half_away_from_zero(value: float) -> int:
    if value >= 0:
        return int(np.floor(value + 0.5))
    return int(np.ceil(value - 0.5))


def _polygon_to_mask_slice(polygons_xy: Sequence[np.ndarray], origin_xy, spacing_xy, grid_xy,
                           precision: int, combine_mode: str = "xor") -> np.ndarray:
    gx, gy = int(grid_xy[0]), int(grid_xy[1])
    hr_shape = (gx * precision, gy * precision)
    slice_mask = np.zeros((gx, gy), dtype=np.float32)
    ox, oy = float(origin_xy[0]), float(origin_xy[1])
    sx, sy = float(spacing_xy[0]), float(spacing_xy[1])
    shift_x = 0.5 * (1.0 - sx)
    shift_y = 0.5 * (1.0 - sy)
    center_offset = 0.5 * (precision - 1)
    for poly in polygons_xy:
        rows = ((poly[:, 0] + shift_x - ox) / sx) * precision + center_offset
        cols = ((poly[:, 1] + shift_y - oy) / sy) * precision + center_offset
        polygon_mask = polygon2mask(hr_shape, np.column_stack((rows, cols)))
        if precision == 1:
            down = polygon_mask.astype(np.float32)
        else:
            down = polygon_mask.astype(np.float32).reshape(gx, precision, gy, precision).mean(axis=(1, 3))
        if combine_mode == "union":
            slice_mask = np.maximum(slice_mask, down)
        else:
            slice_mask = np.abs(slice_mask - down)
    return np.clip(slice_mask, 0.0, 1.0)


def _group_polygons_by_z(polygon_mesh: Sequence[np.ndarray], z_tolerance: float) -> Dict[float, List[np.ndarray]]:
    grouped: Dict[float, List[np.ndarray]] = {}
    for contour_data in polygon_mesh:
        coords = np.asarray(contour_data, dtype=float)
        if coords.size < 9 or coords.size % 3 != 0:
            continue
        triplets = coords.reshape(-1, 3)
        z = float(np.median(triplets[:, 2]))
        if z_tolerance > 0:
            z = float(np.round(z / z_tolerance) * z_tolerance)
        grouped.setdefault(z, []).append(triplets[:, :2])
    return grouped


def _interpolate_between_two_slices(lower_slice: np.ndarray, upper_slice: np.ndarray) -> np.ndarray:
    lower = np.clip(lower_slice, 0.0, 1.0).astype(np.float32)
    upper = np.clip(upper_slice, 0.0, 1.0).astype(np.float32)
    out = 0.5 * (lower + upper)
    eps = 1e-8
    lower_zero = np.abs(lower) <= eps
    upper_zero = np.abs(upper) <= eps
    out[lower_zero & (~upper_zero)] = upper[lower_zero & (~upper_zero)]
    out[upper_zero & (~lower_zero)] = lower[upper_zero & (~lower_zero)]
    lower_one = np.abs(lower - 1.0) <= eps
    upper_one = np.abs(upper - 1.0) <= eps
    out[lower_one | upper_one] = 1.0
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def partial_volume_mask(polygon_mesh: Sequence[np.ndarray], origin, grid_size, spacing, precision: int = 16,
                        threshold: Optional[float] = 0.5) -> np.ndarray:
    """Rasterize polygons (flat ``x y z`` lists) onto a grid: an ``(x, y, z)`` array,
    boolean when ``threshold`` is given, else the partial volume in [0, 1]."""
    if spacing is None:
        spacing = (1.0, 1.0, 1.0)
    precision = int(precision)
    if precision <= 0:
        raise ValueError("precision must be a positive integer")
    spacing = np.asarray(spacing, dtype=float)
    origin = np.asarray(origin, dtype=float)
    grid_size = np.asarray(grid_size, dtype=int)
    full_shape = tuple(int(v) for v in grid_size)
    out_dtype = bool if threshold is not None else np.float32

    all_x, all_y, all_z = [], [], []
    for contour_data in polygon_mesh:
        coords = np.asarray(contour_data, dtype=float)
        if coords.size < 9 or coords.size % 3 != 0:
            continue
        all_x.append(coords[0::3]); all_y.append(coords[1::3]); all_z.append(float(np.mean(coords[2::3])))
    if not all_x:
        return np.zeros(full_shape, dtype=out_dtype)
    all_x = np.sort(np.concatenate(all_x)); all_y = np.sort(np.concatenate(all_y)); all_z = np.sort(np.asarray(all_z))
    contour_min = np.array([all_x[0], all_y[0], all_z[0]])
    contour_max = np.array([all_x[-1], all_y[-1], all_z[-1]])

    z_diff = np.abs(np.diff(all_z))
    z_diff[z_diff == 0] = np.inf
    finite = z_diff[np.isfinite(z_diff)]
    native_z_spacing = float(finite.min()) if finite.size > 0 else float(spacing[2])

    box_start = np.floor((contour_min - origin) / spacing - 0.5).astype(int)
    box_end = np.ceil((contour_max - origin) / spacing + 0.5).astype(int)
    if float(spacing[2]) < native_z_spacing:
        box_end[2] += 1
    box_start = np.maximum(box_start, 0)
    box_end = np.minimum(box_end, grid_size - 1)
    if np.any(box_end < box_start):
        return np.zeros(full_shape, dtype=out_dtype)
    box_size = (box_end - box_start + 1).astype(int)
    box_origin = origin + box_start.astype(float) * spacing
    gx, gy, gz = int(box_size[0]), int(box_size[1]), int(box_size[2])
    local = np.zeros((gx, gy, gz), dtype=np.float32)

    if max(gx, gy) >= 256:
        adaptive_precision = 1
    else:
        adaptive_precision = max(1, min(precision, int(512 / max(gx, gy)) if max(gx, gy) > 0 else precision))

    grouped = _group_polygons_by_z(polygon_mesh, max(1e-4, 0.02 * float(spacing[2])))
    if not grouped:
        return np.zeros(full_shape, dtype=out_dtype)

    if float(spacing[2]) < native_z_spacing:
        grouped_by_k: Dict[int, List[np.ndarray]] = {}
        for z_val, polys in grouped.items():
            k_global = _round_half_away_from_zero((float(z_val) - float(origin[2])) / float(spacing[2]))
            k_local = int(k_global - int(box_start[2]))
            if 0 <= k_local < gz:
                grouped_by_k.setdefault(k_local, []).extend(polys)
        if not grouped_by_k:
            return np.zeros(full_shape, dtype=out_dtype)
        contour_k = np.array(sorted(grouped_by_k), dtype=int)
        first_k, last_k = int(contour_k[0]), int(contour_k[-1])
        native_steps = max(1.0, float(native_z_spacing) / float(spacing[2]))
        hat_half_steps = 0.5 * native_steps
        exact: Dict[int, np.ndarray] = {}
        for k_exact in contour_k:
            local[:, :, int(k_exact)] = _polygon_to_mask_slice(grouped_by_k[int(k_exact)], box_origin[:2], spacing[:2],
                                                              (gx, gy), adaptive_precision, "xor")
            exact[int(k_exact)] = local[:, :, int(k_exact)].copy()
        for k in range(gz):
            if k in grouped_by_k:
                continue
            lower = contour_k[contour_k < k]
            upper = contour_k[contour_k > k]
            if lower.size == 0:
                d = float(first_k - k)
                if d <= hat_half_steps:
                    local[:, :, k] = (1.0 - d / max(hat_half_steps, 1e-6)) * exact[first_k]
                continue
            if upper.size == 0:
                d = float(k - last_k)
                if d <= hat_half_steps:
                    local[:, :, k] = (1.0 - d / max(hat_half_steps, 1e-6)) * exact[last_k]
                continue
            k0, k1 = int(lower[-1]), int(upper[0])
            if k1 <= k0:
                continue
            local[:, :, k] = _interpolate_between_two_slices(exact[k0], exact[k1])
        for k_exact, s in exact.items():
            local[:, :, k_exact] = s
    else:
        grouped_z = np.array(sorted(grouped), dtype=float)
        coarse_k = []
        for z_val in grouped_z:
            k_global = _round_half_away_from_zero((float(z_val) - float(origin[2])) / float(spacing[2]))
            k_local = int(k_global - int(box_start[2]))
            if 0 <= k_local < gz:
                coarse_k.append(k_local)
        if not coarse_k:
            return np.zeros(full_shape, dtype=out_dtype)
        coarse_precision = max(1, min(adaptive_precision, 4))
        cache: Dict[float, np.ndarray] = {}
        first_k, last_k = int(min(coarse_k)), int(max(coarse_k))
        for k in range(gz):
            if k < first_k or k > last_k:
                continue
            z_target = float(box_origin[2]) + k * float(spacing[2])
            z_sel = float(grouped_z[int(np.argmin(np.abs(grouped_z - z_target)))])
            polys = grouped[z_sel]
            if not polys:
                continue
            if z_sel not in cache:
                cache[z_sel] = _polygon_to_mask_slice(polys, box_origin[:2], spacing[:2], (gx, gy), coarse_precision, "xor")
            local[:, :, k] = cache[z_sel]

    if threshold is not None:
        local = (local >= float(threshold)).astype(bool)
    full = np.zeros(full_shape, dtype=local.dtype)
    bs = box_start
    full[bs[0]:bs[0] + gx, bs[1]:bs[1] + gy, bs[2]:bs[2] + gz] = local
    return full


__all__ = ["partial_volume_mask"]
