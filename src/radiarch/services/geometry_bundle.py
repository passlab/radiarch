"""The persisted geometry as arrays (roadmap R15).

The Geometry Service writes three NIfTI volumes per geometry (CT in HU, mass
density, uint16 structure labels) and a ``GeometryResult`` record. Every
downstream service works from those files, never from a second DICOM read,
so that the geometry the caller named is the one that gets used.
:func:`load_geometry_arrays` reads them back into a :class:`GeometryArrays`;
the beam model builders take that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import SimpleITK as sitk
from loguru import logger

from .masks import structure_mask
from .rasterization import _target_priority

# Names that mean "the target" in phantoms and older structure sets (the
# legacy workflows accept the same set); PTV/GTV/CTV come first via
# ``_target_priority``.
_TARGET_FALLBACK_NAMES = ("target", "targetvolume", "tv")


def target_structure(structure_index: Dict[str, int]) -> Optional[Tuple[str, int]]:
    """Pick the planning target from a structure index.

    PTV first, then GTV, CTV (TG-263 prefixes included); otherwise a
    structure called ``Target``/``TargetVolume``/``TV`` or containing
    ``target``. ``None`` when nothing qualifies.
    """
    candidates = [(n, lbl) for n, lbl in structure_index.items() if _target_priority(n) < 100]
    if candidates:
        return sorted(candidates, key=lambda nl: (_target_priority(nl[0]), nl[0].lower()))[0]
    fallback = [
        (n, lbl) for n, lbl in structure_index.items()
        if n.strip().lower().replace("_", "").replace(" ", "") in _TARGET_FALLBACK_NAMES
        or "target" in n.lower()
    ]
    if not fallback:
        return None
    return sorted(fallback, key=lambda nl: nl[0].lower())[0]


def _grid_origin_spacing(geom) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    grid = geom.grid_spec
    spacing = tuple(float(s) for s in grid.spacing_mm)
    origin = tuple(float(o) for o in (grid.origin_mm or (0.0, 0.0, 0.0)))
    return origin, spacing


def load_ct_hu(geom) -> Optional[np.ndarray]:
    """Read the persisted CT grid as (z, y, x) int16, or None if it isn't on disk."""
    uri = getattr(geom, "ct_grid_uri", None)
    if not uri:
        return None
    ct_path = Path(uri)
    if not ct_path.is_file():
        logger.warning(
            "Geometry %s declares ct_grid_uri=%s but the file is missing.",
            geom.geometry_id, uri,
        )
        return None
    try:
        return sitk.GetArrayFromImage(sitk.ReadImage(str(ct_path))).astype(np.int16)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Failed to read CT NIfTI %s: %s", uri, exc)
        return None


@dataclass
class GeometryArrays:
    """A persisted geometry in memory: CT, labels and the grid, in radiarch's ``(z, y, x)`` order."""

    geometry_id: str
    ct_hu: np.ndarray                      # (z, y, x) int16
    masks: np.ndarray                      # (z, y, x) uint16 structure labels, 0 = background
    structure_index: Dict[str, int]
    origin_mm: Tuple[float, float, float]  # centre of voxel [0, 0, 0] (x, y, z)
    spacing_mm: Tuple[float, float, float]
    frame_of_reference_uid: str = ""
    patient_name: str = "ANONYMOUS"
    series_instance_uid: str = ""
    mask_encoding: str = "labels"

    @property
    def shape_zyx(self) -> Tuple[int, int, int]:
        return tuple(int(v) for v in self.ct_hu.shape)  # type: ignore[return-value]

    @property
    def grid_size_xyz(self) -> Tuple[int, int, int]:
        nz, ny, nx = self.shape_zyx
        return (nx, ny, nz)

    def ct_hu_xyz(self) -> np.ndarray:
        """The CT in ``(x, y, z)`` order (C-contiguous copy)."""
        return np.ascontiguousarray(np.transpose(self.ct_hu, (2, 1, 0)))

    def mask_zyx(self, label: int) -> np.ndarray:
        return structure_mask(self.masks, label, self.mask_encoding)

    def mask_xyz(self, label: int) -> np.ndarray:
        return np.ascontiguousarray(np.transpose(self.mask_zyx(label), (2, 1, 0)))

    def target(self) -> Optional[Tuple[str, int]]:
        """``(name, label)`` of the planning target, or None."""
        return target_structure(self.structure_index)

    def label_of(self, name: str) -> Optional[int]:
        for n, lbl in self.structure_index.items():
            if n.strip().lower() == name.strip().lower():
                return int(lbl)
        return None


def load_geometry_arrays(geom) -> GeometryArrays:
    """Read a persisted geometry's CT and labels.

    Raises ``ValueError`` when the CT grid is not on disk: a beam model cannot
    be built without it, and silently reading some other CT is exactly the
    defect this module replaces.
    """
    ct_hu = load_ct_hu(geom)
    if ct_hu is None:
        raise ValueError(
            f"geometry {geom.geometry_id!r} has no CT grid on disk "
            f"(ct_grid_uri={getattr(geom, 'ct_grid_uri', None)!r}); rebuild the geometry."
        )
    masks = sitk.GetArrayFromImage(sitk.ReadImage(str(geom.structure_masks_uri)))
    encoding = str(getattr(geom, "mask_encoding", "labels") or "labels")
    masks = masks.astype(np.uint64) if encoding == "bitmask" else masks.astype(np.uint16)
    if masks.shape != ct_hu.shape:
        raise ValueError(f"geometry {geom.geometry_id!r}: masks {masks.shape} and CT {ct_hu.shape} differ in shape")
    origin, spacing = _grid_origin_spacing(geom)
    meta = getattr(geom, "ct_metadata", None)
    arrays = GeometryArrays(
        geometry_id=str(geom.geometry_id), ct_hu=ct_hu, masks=masks,
        structure_index={str(k): int(v) for k, v in dict(geom.structure_index).items()},
        origin_mm=origin, spacing_mm=spacing,
        frame_of_reference_uid=str(getattr(geom, "frame_of_reference_uid", "") or ""),
        patient_name=str(getattr(meta, "patient_name", "") or "ANONYMOUS"),
        series_instance_uid=str(getattr(meta, "series_instance_uid", "") or ""),
        mask_encoding=encoding,
    )
    if arrays.target() is None:
        logger.warning(
            "Geometry %s has no PTV/GTV/CTV in its structure index (%s).",
            geom.geometry_id, sorted(arrays.structure_index),
        )
    return arrays


__all__ = ["target_structure", "load_ct_hu", "GeometryArrays", "load_geometry_arrays"]
