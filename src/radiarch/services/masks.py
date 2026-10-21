"""Structure masks on the geometry grid (roadmap R4).

A geometry stores every structure in one volume. Two encodings exist:

* ``"labels"``: a ``uint16`` label map, one label per voxel, the encoding of
  geometries built before R4. Overlapping structures lost voxels to the
  structure with the lower label (targets first), so a spinal cord inside a
  PTV had no voxels there.
* ``"bitmask"``: a ``uint64`` volume in which bit ``label - 1`` is set for
  every structure containing the voxel. Structures overlap freely; a
  geometry holds up to 64 of them.

Every consumer goes through :func:`structure_mask`, which reads either.
"""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

import numpy as np

LABELS = "labels"
BITMASK = "bitmask"
MAX_BITMASK_STRUCTURES = 64


def structure_mask(masks: np.ndarray, label: int, encoding: str = LABELS) -> np.ndarray:
    """The boolean mask of the structure with ``label`` (1-based)."""
    label = int(label)
    if label < 1:
        raise ValueError("structure labels start at 1")
    arr = np.asarray(masks)
    if encoding == BITMASK:
        if label > MAX_BITMASK_STRUCTURES:
            raise ValueError(f"label {label} exceeds the {MAX_BITMASK_STRUCTURES} structures a bitmask holds")
        return (arr.astype(np.uint64, copy=False) & np.uint64(1 << (label - 1))) != 0
    if encoding == LABELS:
        return arr == label
    raise ValueError(f"unknown mask encoding {encoding!r}")


def pack_bitmask(masks_by_label: Dict[int, np.ndarray], shape: Tuple[int, ...]) -> np.ndarray:
    """A ``uint64`` bitmask volume from ``{label: bool array}``."""
    out = np.zeros(shape, dtype=np.uint64)
    for label, mask in masks_by_label.items():
        label = int(label)
        if not 1 <= label <= MAX_BITMASK_STRUCTURES:
            raise ValueError(f"label {label} outside 1..{MAX_BITMASK_STRUCTURES}")
        m = np.asarray(mask, dtype=bool)
        if m.shape != tuple(shape):
            raise ValueError(f"mask of label {label} has shape {m.shape}, expected {tuple(shape)}")
        out[m] |= np.uint64(1 << (label - 1))
    return out


def set_structure(masks: np.ndarray, label: int, mask: np.ndarray, encoding: str = BITMASK) -> np.ndarray:
    """``masks`` with the structure ``label`` replaced by ``mask`` (bitmask only)."""
    if encoding != BITMASK:
        raise ValueError("structures can only be added to a bitmask geometry")
    arr = np.asarray(masks).astype(np.uint64, copy=True)
    bit = np.uint64(1 << (int(label) - 1))
    arr &= ~bit
    arr[np.asarray(mask, dtype=bool)] |= bit
    return arr


def to_bitmask(masks: np.ndarray, labels: Iterable[int], encoding: str) -> np.ndarray:
    """Re-encode a label map as a bitmask (a bitmask passes through)."""
    if encoding == BITMASK:
        return np.asarray(masks).astype(np.uint64, copy=False)
    arr = np.asarray(masks)
    return pack_bitmask({int(l): arr == int(l) for l in labels}, arr.shape)


def voxel_count(masks: np.ndarray, label: int, encoding: str = LABELS) -> int:
    return int(structure_mask(masks, label, encoding).sum())


__all__ = ["LABELS", "BITMASK", "MAX_BITMASK_STRUCTURES", "structure_mask", "pack_bitmask", "set_structure",
           "to_bitmask", "voxel_count"]
