"""Gamma analysis for the Evaluation Service (Service 6; interpolated search since R5).

The gamma index (Low et al. 1998) compares an evaluated dose with a reference:

    γ(r) = min over r' of sqrt( (D_e(r') − D_r(r))² / ΔD² + |r' − r|² / DTA² )

A point passes when ``γ ≤ 1``. The pass rate is the fraction of reference
points above a low-dose threshold that pass; ``ΔD`` is ``dose_percent`` of
the reference maximum (global) or of the local reference value (local).

The search is over the evaluated dose **interpolated** on a sub-voxel grid
(``interp_fraction`` steps per DTA, TG-218's ≤ DTA/3 rule met with the
default 5), within a sphere of ``search_factor × DTA``, vectorized over all
reference points: offsets are visited in order of increasing distance and
the search stops when the distance term alone exceeds the worst remaining
γ. The conventions follow pymedphys (reference points, evaluated
interpolated), which the validation harness cross-checks.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from scipy.ndimage import map_coordinates

from ..models.evaluation import GammaResult


def gamma_map(
    evaluated: np.ndarray,
    reference: np.ndarray,
    spacing_mm: Tuple[float, float, float],
    dose_percent: float = 3.0,
    distance_mm: float = 3.0,
    threshold_pct: float = 10.0,
    local: bool = False,
    interp_fraction: int = 5,
    search_factor: float = 2.0,
    max_points: Optional[int] = None,
) -> np.ndarray:
    """Gamma at every reference point above the threshold; NaN elsewhere. ``spacing_mm`` is (sz, sy, sx)."""
    ev = np.asarray(evaluated, dtype=np.float64)
    ref = np.asarray(reference, dtype=np.float64)
    if ev.shape != ref.shape:
        raise ValueError(f"evaluated shape {ev.shape} != reference shape {ref.shape}")
    out = np.full(ref.shape, np.nan, dtype=np.float64)
    ref_max = float(ref.max()) if ref.size else 0.0
    if ref_max <= 0:
        return out
    spacing = np.asarray(spacing_mm, dtype=np.float64)
    thresh = threshold_pct / 100.0 * ref_max
    idx = np.argwhere(ref > thresh)
    if idx.size == 0:
        return out
    if max_points is not None and idx.shape[0] > max_points:
        rng = np.random.default_rng(0)
        idx = idx[rng.choice(idx.shape[0], size=max_points, replace=False)]
    pts = idx.astype(np.float64)                                   # voxel coordinates (z, y, x)
    d_ref = ref[idx[:, 0], idx[:, 1], idx[:, 2]]
    dd_crit = (dose_percent / 100.0) * (d_ref if local else np.full(d_ref.shape, ref_max))
    dd_crit = np.where(dd_crit > 1e-12, dd_crit, 1e-12)

    # offsets on a sub-voxel grid within the search sphere, in mm, sorted by distance
    step_mm = distance_mm / float(max(1, interp_fraction))
    radius = search_factor * distance_mm
    n_steps = int(np.ceil(radius / step_mm))
    axis = np.arange(-n_steps, n_steps + 1) * step_mm
    oz, oy, ox = np.meshgrid(axis, axis, axis, indexing="ij")
    offsets = np.stack([oz.ravel(), oy.ravel(), ox.ravel()], axis=1)
    dist = np.sqrt((offsets ** 2).sum(axis=1))
    keep = dist <= radius + 1e-9
    offsets, dist = offsets[keep], dist[keep]
    order = np.argsort(dist, kind="stable")
    offsets, dist = offsets[order], dist[order]

    best = np.full(pts.shape[0], np.inf)
    active = np.ones(pts.shape[0], dtype=bool)
    for off, d_mm in zip(offsets, dist):
        dist_term = (d_mm / distance_mm) ** 2
        if active.any():
            # no remaining point can improve once the distance term alone exceeds its best γ²
            active &= best > dist_term
        if not active.any():
            break
        sel = np.flatnonzero(active)
        coords = (pts[sel] + off / spacing).T
        d_ev = map_coordinates(ev, coords, order=1, mode="nearest")
        g2 = ((d_ev - d_ref[sel]) / dd_crit[sel]) ** 2 + dist_term
        best[sel] = np.minimum(best[sel], g2)
    out[idx[:, 0], idx[:, 1], idx[:, 2]] = np.sqrt(best)
    return out


def gamma_index(
    evaluated: np.ndarray,
    reference: np.ndarray,
    spacing_mm: Tuple[float, float, float],
    dose_percent: float = 3.0,
    distance_mm: float = 3.0,
    threshold_pct: float = 10.0,
    local: bool = False,
    interp_fraction: int = 5,
) -> GammaResult:
    """The gamma pass rate of ``evaluated`` against ``reference``.

    ``spacing_mm`` is ``(sz, sy, sx)`` matching the array axis order. Only
    reference points above ``threshold_pct`` of the reference maximum count.
    """
    g = gamma_map(evaluated, reference, spacing_mm, dose_percent, distance_mm, threshold_pct, local, interp_fraction)
    vals = g[~np.isnan(g)]
    if vals.size == 0:
        return GammaResult(dose_percent=dose_percent, distance_mm=distance_mm, threshold_pct=threshold_pct, local=local,
                           pass_rate_pct=100.0, mean_gamma=0.0, evaluated_voxels=0)
    return GammaResult(
        dose_percent=dose_percent, distance_mm=distance_mm, threshold_pct=threshold_pct, local=local,
        pass_rate_pct=float(100.0 * np.mean(vals <= 1.0)), mean_gamma=float(vals.mean()), evaluated_voxels=int(vals.size),
    )


__all__ = ["gamma_map", "gamma_index"]
