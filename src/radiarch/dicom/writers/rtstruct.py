"""RT Structure Set writer (roadmap R6).

Structures are given as binary masks on a grid (what the geometry store
holds) or as polygons already in the patient frame. Masks become closed
planar contours slice by slice: the 0.5 iso-line of each slice
(``skimage.measure.find_contours``), simplified with Douglas–Peucker at a
third of a voxel so straight runs collapse, every polygon on a slice its own
contour item (holes and islands included; readers combine the contours of
one slice by the usual even–odd rule, as radiarch's rasterizer does).

Names are written as given — TG-263 names are the caller's job (the
clinical-goal templates and the structure resolver already speak them). The
interpreted type follows the name: ``PTV*`` → PTV, ``CTV*`` → CTV, ``GTV*`` →
GTV, ``Body``/``External`` → EXTERNAL, couch structures → SUPPORT, the rest
ORGAN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from pydicom.dataset import Dataset

from ..uids import SOP
from .common import DETACHED_STUDY_SOP_CLASS, CaseContext, ct_image_refs, ds_list, new_dataset, ref, research_text, save, seq

# A palette that keeps neighbouring structures apart on screen.
PALETTE = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255),
    (255, 128, 0), (128, 0, 255), (0, 128, 255), (128, 255, 0), (255, 0, 128), (0, 255, 128),
    (192, 64, 64), (64, 192, 64), (64, 64, 192), (192, 192, 64),
]


@dataclass
class Structure:
    """One ROI: its name and either a mask on a grid or polygons in mm."""

    name: str
    mask_zyx: Optional[np.ndarray] = None
    polygons: List[np.ndarray] = field(default_factory=list)     # flat x y z ... per polygon, in mm
    color: Optional[Tuple[int, int, int]] = None
    interpreted_type: Optional[str] = None
    description: str = ""
    generation: str = "AUTOMATIC"      # AUTOMATIC | SEMIAUTOMATIC | MANUAL


def interpreted_type(name: str) -> str:
    n = name.strip().lower()
    if n.startswith("ptv"):
        return "PTV"
    if n.startswith("ctv"):
        return "CTV"
    if n.startswith("gtv"):
        return "GTV"
    if n in ("body", "external", "skin", "outer contour") or n.startswith("external"):
        return "EXTERNAL"
    if "couch" in n or n.startswith("table") or n.startswith("support"):
        return "SUPPORT"
    if n.startswith("itv"):
        return "CTV"
    if n.startswith("prv") or n.startswith("ring") or n.startswith("avoid") or re.match(r"^z_", n):
        return "AVOIDANCE"
    return "ORGAN"


# ---------------------------------------------------------------------------
# Masks → polygons
# ---------------------------------------------------------------------------

def mask_to_polygons(mask_zyx: np.ndarray, origin_mm: Sequence[float], spacing_mm: Sequence[float],
                     tolerance_voxels: float = 0.34, min_points: int = 3) -> List[np.ndarray]:
    """Closed planar polygons (flat ``x y z`` arrays in mm) of a ``(z, y, x)`` mask.

    ``origin_mm`` is the centre of voxel ``[0, 0, 0]`` in ``(x, y, z)``.
    """
    from skimage.measure import approximate_polygon, find_contours

    mask = np.asarray(mask_zyx).astype(bool)
    ox, oy, oz = (float(v) for v in origin_mm)
    sx, sy, sz = (float(v) for v in spacing_mm)
    out: List[np.ndarray] = []
    for k in np.flatnonzero(mask.reshape(mask.shape[0], -1).any(axis=1)):
        sl = np.pad(mask[k].astype(np.float32), 1)          # a border of zeros closes structures at the edge
        for coords in find_contours(sl, 0.5):
            if len(coords) > 1 and np.allclose(coords[0], coords[-1]):
                coords = coords[:-1]
            if tolerance_voxels > 0 and len(coords) > min_points:
                coords = approximate_polygon(np.vstack([coords, coords[:1]]), tolerance=tolerance_voxels)
                if len(coords) > 1 and np.allclose(coords[0], coords[-1]):
                    coords = coords[:-1]
            if len(coords) < min_points:
                continue
            rows = coords[:, 0] - 1.0
            cols = coords[:, 1] - 1.0
            poly = np.empty((len(coords), 3), dtype=float)
            poly[:, 0] = ox + cols * sx
            poly[:, 1] = oy + rows * sy
            poly[:, 2] = oz + float(k) * sz
            out.append(poly.reshape(-1))
    return out


def _volume_cc(mask_zyx: Optional[np.ndarray], spacing_mm: Sequence[float]) -> Optional[float]:
    if mask_zyx is None:
        return None
    return float(np.count_nonzero(mask_zyx)) * float(np.prod([float(s) for s in spacing_mm])) / 1000.0


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

@dataclass
class RTStructResult:
    path: str
    sop_instance_uid: str
    series_instance_uid: str
    roi_numbers: Dict[str, int]


def build_rtstruct(ctx: CaseContext, structures: Sequence[Structure], *, origin_mm: Optional[Sequence[float]] = None,
                   spacing_mm: Optional[Sequence[float]] = None, label: str = "radiarch", description: str = "",
                   series_number: int = 100, series_instance_uid: Optional[str] = None,
                   sop_instance_uid: Optional[str] = None, approval: str = "UNAPPROVED") -> Dataset:
    """The RT Structure Set dataset for ``structures`` on the CT of ``ctx``."""
    if not ctx.ct_sop_instance_uids:
        raise ValueError("an RT Structure Set references the CT slices: the case context has no CT SOP Instance UIDs "
                         "(rebuild the geometry with this radiarch, or give the CT directory)")
    ds = new_dataset(ctx, SOP.RTSTRUCT, "RTSTRUCT", series_number=series_number, series_instance_uid=series_instance_uid,
                     sop_instance_uid=sop_instance_uid)

    # Structure Set
    ds.StructureSetLabel = label[:16]
    ds.StructureSetName = label[:64]
    ds.StructureSetDescription = research_text(description)
    ds.StructureSetDate = ctx.date
    ds.StructureSetTime = ctx.time
    series = Dataset()
    series.SeriesInstanceUID = ctx.ct_series_instance_uid
    series.ContourImageSequence = seq(ct_image_refs(ctx))
    study = ref(DETACHED_STUDY_SOP_CLASS, ctx.study_instance_uid)
    study.RTReferencedSeriesSequence = seq([series])
    frame = Dataset()
    frame.FrameOfReferenceUID = ctx.frame_of_reference_uid
    frame.RTReferencedStudySequence = seq([study])
    ds.ReferencedFrameOfReferenceSequence = seq([frame])

    roi_items, contour_items, obs_items = [], [], []
    for number, s in enumerate(structures, start=1):
        polygons = list(s.polygons)
        if s.mask_zyx is not None:
            if origin_mm is None or spacing_mm is None:
                raise ValueError(f"structure {s.name!r} is a mask: origin_mm and spacing_mm are needed")
            polygons += mask_to_polygons(s.mask_zyx, origin_mm, spacing_mm)
        roi = Dataset()
        roi.ROINumber = number
        roi.ReferencedFrameOfReferenceUID = ctx.frame_of_reference_uid
        roi.ROIName = s.name[:64]
        if s.description:
            roi.ROIDescription = s.description[:64]
        vol = _volume_cc(s.mask_zyx, spacing_mm) if spacing_mm is not None else None
        if vol is not None:
            roi.ROIVolume = float(f"{vol:.6g}")
        roi.ROIGenerationAlgorithm = s.generation
        roi_items.append(roi)

        rc = Dataset()
        rc.ReferencedROINumber = number
        rc.ROIDisplayColor = list(s.color or PALETTE[(number - 1) % len(PALETTE)])
        items = []
        for ci, poly in enumerate(polygons, start=1):
            c = Dataset()
            c.ContourGeometricType = "CLOSED_PLANAR"
            c.NumberOfContourPoints = int(len(poly) // 3)
            c.ContourNumber = ci
            c.ContourData = ds_list(poly)
            items.append(c)
        if items:
            rc.ContourSequence = seq(items)
        contour_items.append(rc)

        ob = Dataset()
        ob.ObservationNumber = number
        ob.ReferencedROINumber = number
        ob.RTROIInterpretedType = s.interpreted_type or interpreted_type(s.name)
        ob.ROIInterpreter = ""
        obs_items.append(ob)

    ds.StructureSetROISequence = seq(roi_items)
    ds.ROIContourSequence = seq(contour_items)
    ds.RTROIObservationsSequence = seq(obs_items)
    ds.ApprovalStatus = approval
    return ds


def write_rtstruct(ctx: CaseContext, structures: Sequence[Structure], path: Union[str, Path], **kw) -> RTStructResult:
    ds = build_rtstruct(ctx, structures, **kw)
    save(ds, path)
    return RTStructResult(path=str(path), sop_instance_uid=str(ds.SOPInstanceUID),
                          series_instance_uid=str(ds.SeriesInstanceUID),
                          roi_numbers={str(r.ROIName): int(r.ROINumber) for r in ds.StructureSetROISequence})


__all__ = ["Structure", "RTStructResult", "PALETTE", "interpreted_type", "mask_to_polygons", "build_rtstruct", "write_rtstruct"]
