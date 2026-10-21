"""Rebuild OpenTPS objects from a persisted geometry.

The Geometry Service writes three NIfTI volumes per geometry (CT in HU, mass
density, uint16 structure labels) and a ``GeometryResult`` record. Every
downstream service works from those files, never from a second DICOM read,
so that the geometry the caller named is the one that gets used.

``wrap_ct_image`` used to live in ``dose.py``; it is here so the Dose and
Beam Model services share one definition. SimpleITK hands back arrays in
(z, y, x) order and OpenTPS wants (x, y, z), so every wrapper transposes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import SimpleITK as sitk
from loguru import logger

from .rasterization import _target_priority


def _grid_origin_spacing(geom) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    grid = geom.grid_spec
    spacing = tuple(float(s) for s in grid.spacing_mm)
    origin = tuple(float(o) for o in (grid.origin_mm or (0.0, 0.0, 0.0)))
    return origin, spacing


def wrap_ct_image(ct_hu: np.ndarray, geom) -> Optional[Any]:
    """Wrap a (z, y, x) HU array in an OpenTPS ``CTImage``, or return None.

    Returns None when OpenTPS isn't importable in this environment — the
    caller still has the raw ``ct_hu`` for engines that don't need OpenTPS.
    Provenance (frameOfReferenceUID, seriesInstanceUID) comes from the
    persisted GeometryResult so the CTImage matches the original series.
    """
    try:
        from opentps.core.data.images import CTImage
    except Exception:  # pragma: no cover — exercised on import-failure machines
        return None

    # Contiguous: OpenTPS's C ray tracer reads the buffer directly.
    arr_ijk = np.ascontiguousarray(np.transpose(np.asarray(ct_hu), (2, 1, 0)), dtype=np.int16)
    origin, spacing = _grid_origin_spacing(geom)

    series_uid = ""
    try:
        series_uid = str(geom.ct_metadata.series_instance_uid or "")
    except Exception:  # pragma: no cover
        pass
    for_uid = str(getattr(geom, "frame_of_reference_uid", "") or "")

    return CTImage(
        imageArray=arr_ijk,
        name=f"CT[{geom.geometry_id}]",
        origin=origin,
        spacing=spacing,
        seriesInstanceUID=series_uid,
        frameOfReferenceUID=for_uid,
    )


def wrap_roi_mask(mask_zyx: np.ndarray, geom, name: str) -> Optional[Any]:
    """Wrap a (z, y, x) boolean mask in an OpenTPS ``ROIMask`` on the geometry grid."""
    try:
        from opentps.core.data.images import ROIMask
    except Exception:  # pragma: no cover
        return None

    arr_ijk = np.ascontiguousarray(np.transpose(np.asarray(mask_zyx, dtype=bool), (2, 1, 0)))
    origin, spacing = _grid_origin_spacing(geom)
    return ROIMask(imageArray=arr_ijk, name=name, origin=origin, spacing=spacing)


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


def load_opentps_geometry(geom) -> Tuple[Any, Any, Optional[Any]]:
    """Return ``(CTImage, Patient, target ROIMask or None)`` for a persisted geometry.

    Raises ``ValueError`` when the CT grid is not on disk or OpenTPS is not
    importable: a beam model cannot be built without either, and silently
    reading some other CT is exactly the defect this module replaces.
    """
    ct_hu = load_ct_hu(geom)
    if ct_hu is None:
        raise ValueError(
            f"geometry {geom.geometry_id!r} has no CT grid on disk "
            f"(ct_grid_uri={getattr(geom, 'ct_grid_uri', None)!r}); rebuild the geometry."
        )
    ct = wrap_ct_image(ct_hu, geom)
    if ct is None:
        raise ValueError("OpenTPS is not importable; cannot build OpenTPS objects for the beam model.")

    from opentps.core.data import Patient

    patient_name = str(getattr(getattr(geom, "ct_metadata", None), "patient_name", "") or "ANONYMOUS")
    patient = Patient(name=patient_name)
    patient.appendPatientData(ct)

    target = None
    chosen = target_structure(geom.structure_index)
    if chosen is None:
        logger.warning(
            "Geometry %s has no PTV/GTV/CTV in its structure index (%s); "
            "the beam model will build without a target.",
            geom.geometry_id, sorted(geom.structure_index),
        )
    else:
        name, label = chosen
        masks = sitk.GetArrayFromImage(sitk.ReadImage(str(geom.structure_masks_uri)))
        target = wrap_roi_mask(masks == label, geom, name)
        if target is not None:
            patient.appendPatientData(target)
    return ct, patient, target


__all__ = [
    "wrap_ct_image",
    "wrap_roi_mask",
    "target_structure",
    "load_ct_hu",
    "load_opentps_geometry",
]
