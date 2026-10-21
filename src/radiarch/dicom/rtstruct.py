"""RT Structure Set → contours (roadmap R15).

A :class:`Contour` keeps the polygons exactly as the file has them (one flat
``x y z x y z ...`` list per ``ContourSequence`` item, the ``polygonMesh`` of
the OpenTPS object the services used before) and rasterizes itself on a grid
through :func:`radiarch.services.contour_raster.partial_volume_mask`, the
port of the rasterizer the goldens were captured with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pydicom
from loguru import logger

from .ct import PatientInfo
from .uids import SOP


@dataclass
class MaskVolume:
    """A boolean mask in ``(x, y, z)`` order on a grid (what the rasterizer consumes)."""

    imageArray: np.ndarray
    origin: np.ndarray
    spacing: np.ndarray


@dataclass
class Contour:
    name: str
    polygonMesh: List[np.ndarray] = field(default_factory=list)      # flat x y z ... per polygon
    displayColor: Tuple[int, int, int] = (0, 0, 0)
    referencedFrameOfReferenceUID: str = ""
    referencedSOPInstanceUIDs: List[str] = field(default_factory=list)
    roi_number: int = 0

    def getBinaryMask(self, origin=None, gridSize=None, spacing=None, precision: int = 16) -> MaskVolume:
        """Binary ``(x, y, z)`` mask on the grid (partial volume ≥ 0.5)."""
        from ..services.contour_raster import partial_volume_mask
        arr = partial_volume_mask(self.polygonMesh, origin, gridSize, spacing, precision=precision, threshold=0.5)
        return MaskVolume(arr, np.asarray(origin, dtype=float), np.asarray(spacing, dtype=float))

    @property
    def n_polygons(self) -> int:
        return len(self.polygonMesh)


@dataclass
class StructureSet:
    name: str
    contours: List[Contour]
    sop_instance_uid: str = ""
    series_instance_uid: str = ""
    frame_of_reference_uid: str = ""
    referenced_ct_series_uid: str = ""
    patient: PatientInfo = field(default_factory=PatientInfo)
    source_path: str = ""

    def __iter__(self):
        return iter(self.contours)


def read_rtstruct(src: Union[str, Path, pydicom.Dataset]) -> StructureSet:
    if isinstance(src, pydicom.Dataset):
        ds, path = src, ""
    else:
        ds, path = pydicom.dcmread(str(src)), str(src)
    if str(getattr(ds, "SOPClassUID", "")) != SOP.RTSTRUCT and str(getattr(ds, "Modality", "")) != "RTSTRUCT":
        raise ValueError("not an RT Structure Set")
    name = str(getattr(ds, "SeriesDescription", "") or "") or str(getattr(ds, "SeriesInstanceUID", ""))
    contours: List[Contour] = []
    roi_contours = list(getattr(ds, "ROIContourSequence", []))
    for roi in getattr(ds, "StructureSetROISequence", []):
        number = int(roi.ROINumber)
        match = next((c for c in roi_contours if int(c.ReferencedROINumber) == number), None)
        if match is None or not hasattr(match, "ContourSequence"):
            logger.warning("structure {} has no contours; skipped", roi.ROIName)
            continue
        color = tuple(int(c) for c in getattr(match, "ROIDisplayColor", [0, 0, 0]))
        contour = Contour(name=str(roi.ROIName), displayColor=color,
                          referencedFrameOfReferenceUID=str(getattr(roi, "ReferencedFrameOfReferenceUID", "") or ""),
                          roi_number=number)
        for item in match.ContourSequence:
            contour.polygonMesh.append(np.asarray([float(v) for v in item.ContourData], dtype=float))
            cis = getattr(item, "ContourImageSequence", None)
            if cis:
                contour.referencedSOPInstanceUIDs.append(str(cis[0].ReferencedSOPInstanceUID))
        contours.append(contour)

    for_uid, ct_series = "", ""
    for ref in getattr(ds, "ReferencedFrameOfReferenceSequence", []):
        for_uid = for_uid or str(getattr(ref, "FrameOfReferenceUID", "") or "")
        for study in getattr(ref, "RTReferencedStudySequence", []):
            for series in getattr(study, "RTReferencedSeriesSequence", []):
                ct_series = ct_series or str(getattr(series, "SeriesInstanceUID", "") or "")
    return StructureSet(
        name=name, contours=contours,
        sop_instance_uid=str(getattr(ds, "SOPInstanceUID", "")),
        series_instance_uid=str(getattr(ds, "SeriesInstanceUID", "")),
        frame_of_reference_uid=for_uid, referenced_ct_series_uid=ct_series,
        patient=PatientInfo(name=str(getattr(ds, "PatientName", "") or "ANONYMOUS"), id=str(getattr(ds, "PatientID", "") or "")),
        source_path=path,
    )


__all__ = ["MaskVolume", "Contour", "StructureSet", "read_rtstruct"]
