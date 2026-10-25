"""Agreement between two contours on one grid: Dice, the 95th-percentile Hausdorff distance and the mean
surface distance (roadmap R9; the measures AAPM TG-132 names for contour propagation).

Surfaces are the voxels of a mask with a neighbour outside it (6-connected); distances are from each
surface voxel's centre to the nearest surface voxel of the other mask, in mm, both ways.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np
from scipy import ndimage


def dice(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    total = int(a.sum() + b.sum())
    return 2.0 * float((a & b).sum()) / total if total else 1.0


def _surface(m: np.ndarray) -> np.ndarray:
    return m & ~ndimage.binary_erosion(m, structure=ndimage.generate_binary_structure(3, 1), border_value=0)


def surface_distances(a: np.ndarray, b: np.ndarray, spacing_zyx: Sequence[float]) -> Optional[np.ndarray]:
    """The distances (mm) from a's surface to b's and from b's to a's, concatenated; None if either is empty."""
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    if not a.any() or not b.any():
        return None
    sa, sb = _surface(a), _surface(b)
    to_b = ndimage.distance_transform_edt(~sb, sampling=spacing_zyx)
    to_a = ndimage.distance_transform_edt(~sa, sampling=spacing_zyx)
    return np.concatenate([to_b[sa], to_a[sb]])


def compare(a: np.ndarray, b: np.ndarray, spacing_zyx: Sequence[float]) -> Dict[str, Optional[float]]:
    """Dice, HD95 and mean surface distance (mm) of two masks on one grid; the volumes in cc."""
    d = surface_distances(a, b, spacing_zyx)
    voxel_cc = float(np.prod(spacing_zyx)) / 1000.0
    return {"dice": dice(a, b), "hd95_mm": None if d is None else float(np.percentile(d, 95)),
            "msd_mm": None if d is None else float(d.mean()),
            "volume_a_cc": float(np.asarray(a, bool).sum()) * voxel_cc, "volume_b_cc": float(np.asarray(b, bool).sum()) * voxel_cc}


__all__ = ["compare", "dice", "surface_distances"]
