"""CT series and study directories (roadmap R15).

:class:`CTVolume` is radiarch's CT: Hounsfield units as float32 in the
``(x, y, z)`` array order the geometry pipeline works in internally (the
geometry store transposes to ``(z, y, x)`` on write), with the grid origin at
the centre of voxel ``[0, 0, 0]`` in the patient (LPS) frame. The attribute
names (``imageArray``, ``origin``, ``spacing``, ``gridSize``,
``frameOfReferenceUID``, ...) are those the services already read; the
loading rules are the ones OpenTPS applied, so geometries built before R15
rebuild identically:

* slices sorted by ``ImagePositionPatient`` z, HU = pixels × RescaleSlope +
  RescaleIntercept in float64 then cast to float32;
* slice spacing from ``SpacingBetweenSlices`` when present, else
  ``SliceThickness``, else the mean slice distance;
* ``spacing = (PixelSpacing[1], PixelSpacing[0], slice spacing)`` and
  ``origin = (IPP.x, IPP.y, lowest slice z)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pydicom
from loguru import logger

from .uids import SOP


@dataclass
class PatientInfo:
    name: str = "ANONYMOUS"
    id: str = ""
    birth_date: str = ""
    sex: str = ""


@dataclass
class CTVolume:
    """A CT series as a volume (HU, float32, ``(x, y, z)``)."""

    imageArray: np.ndarray
    origin: np.ndarray
    spacing: np.ndarray
    name: str = "CT"
    frameOfReferenceUID: str = ""
    seriesInstanceUID: str = ""
    studyInstanceUID: str = ""
    sopInstanceUIDs: List[str] = field(default_factory=list)
    sliceLocation: Optional[np.ndarray] = None
    patient: PatientInfo = field(default_factory=PatientInfo)
    patientPosition: str = ""
    studyDate: str = ""
    studyTime: str = ""
    studyID: str = ""
    accessionNumber: str = ""
    studyDescription: str = ""

    @property
    def gridSize(self) -> np.ndarray:
        return np.asarray(self.imageArray.shape, dtype=int)

    @property
    def shape_zyx(self) -> Tuple[int, int, int]:
        nx, ny, nz = self.imageArray.shape
        return (int(nz), int(ny), int(nx))

    def hu_zyx(self) -> np.ndarray:
        """The volume in radiarch's ``(z, y, x)`` order (a C-contiguous copy)."""
        return np.ascontiguousarray(np.transpose(self.imageArray, (2, 1, 0)))

    def copy(self) -> "CTVolume":
        return CTVolume(self.imageArray.copy(), self.origin.copy(), self.spacing.copy(), self.name,
                        self.frameOfReferenceUID, self.seriesInstanceUID, self.studyInstanceUID,
                        list(self.sopInstanceUIDs), None if self.sliceLocation is None else self.sliceLocation.copy(),
                        self.patient, self.patientPosition, self.studyDate, self.studyTime, self.studyID,
                        self.accessionNumber, self.studyDescription)


def _patient(ds: pydicom.Dataset) -> PatientInfo:
    return PatientInfo(
        name=str(getattr(ds, "PatientName", "") or "ANONYMOUS"),
        id=str(getattr(ds, "PatientID", "") or ""),
        birth_date=str(getattr(ds, "PatientBirthDate", "") or ""),
        sex=str(getattr(ds, "PatientSex", "") or ""),
    )


def read_ct_series(files: Sequence[Union[str, Path]]) -> CTVolume:
    """Build a :class:`CTVolume` from the files of one CT series."""
    files = [str(f) for f in files]
    if not files:
        raise ValueError("read_ct_series needs at least one file")
    slices = []
    z = np.zeros(len(files), dtype=float)
    uids: List[str] = []
    dcm = None
    for i, f in enumerate(files):
        dcm = pydicom.dcmread(f)
        z[i] = float(dcm.ImagePositionPatient[2])
        slices.append(dcm.pixel_array * float(dcm.RescaleSlope) + float(dcm.RescaleIntercept))
        uids.append(str(dcm.SOPInstanceUID))
    order = np.argsort(z)
    z = z[order]
    uids = [uids[k] for k in order]
    slices = [slices[k] for k in order]
    volume = np.dstack(slices).astype("float32").transpose(1, 0, 2)     # (x, y, z)

    if hasattr(dcm, "SpacingBetweenSlices") and hasattr(dcm, "SliceThickness"):
        if abs(float(dcm.SpacingBetweenSlices) - float(dcm.SliceThickness)) > 0.001:
            logger.warning("SpacingBetweenSlices {} differs from SliceThickness {}; the former is used",
                           float(dcm.SpacingBetweenSlices), float(dcm.SliceThickness))
        slice_spacing = float(dcm.SpacingBetweenSlices)
    elif hasattr(dcm, "SliceThickness"):
        slice_spacing = float(dcm.SliceThickness)
    else:
        slice_spacing = (z[-1] - z[0]) / (len(slices) - 1) if len(slices) > 1 else 1.0
        logger.warning("No SliceThickness or SpacingBetweenSlices; mean slice distance {} used", slice_spacing)

    name = str(getattr(dcm, "SeriesDescription", "") or "") or str(dcm.SeriesInstanceUID)
    return CTVolume(
        imageArray=volume,
        origin=np.array([float(dcm.ImagePositionPatient[0]), float(dcm.ImagePositionPatient[1]), float(z[0])]),
        spacing=np.array([float(dcm.PixelSpacing[1]), float(dcm.PixelSpacing[0]), slice_spacing]),
        name=name,
        frameOfReferenceUID=str(getattr(dcm, "FrameOfReferenceUID", "") or ""),
        seriesInstanceUID=str(dcm.SeriesInstanceUID),
        studyInstanceUID=str(getattr(dcm, "StudyInstanceUID", "") or ""),
        sopInstanceUIDs=uids,
        sliceLocation=z,
        patient=_patient(dcm),
        patientPosition=str(getattr(dcm, "PatientPosition", "") or ""),
        studyDate=str(getattr(dcm, "StudyDate", "") or ""),
        studyTime=str(getattr(dcm, "StudyTime", "") or ""),
        studyID=str(getattr(dcm, "StudyID", "") or ""),
        accessionNumber=str(getattr(dcm, "AccessionNumber", "") or ""),
        studyDescription=str(getattr(dcm, "StudyDescription", "") or ""),
    )


@dataclass
class DicomInventory:
    """What a directory holds, grouped by series, in sorted file order."""

    ct_series: Dict[str, List[Path]] = field(default_factory=dict)
    rtstructs: List[Path] = field(default_factory=list)
    rtplans: List[Path] = field(default_factory=list)
    rtdoses: List[Path] = field(default_factory=list)
    registrations: List[Path] = field(default_factory=list)
    other: List[Path] = field(default_factory=list)


def inventory(directory: Union[str, Path], max_depth: int = -1) -> DicomInventory:
    """Scan a directory (recursively) and group the DICOM files it holds."""
    inv = DicomInventory()
    root = Path(directory)
    for p in sorted(root.rglob("*") if max_depth < 0 else root.glob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            ds = pydicom.dcmread(str(p), stop_before_pixels=True, specific_tags=["SOPClassUID", "SeriesInstanceUID", "Modality"])
        except Exception:
            continue
        sop = str(getattr(ds, "SOPClassUID", ""))
        if sop == SOP.CT:
            inv.ct_series.setdefault(str(ds.SeriesInstanceUID), []).append(p)
        elif sop == SOP.RTSTRUCT:
            inv.rtstructs.append(p)
        elif sop in (SOP.RTPLAN, SOP.RTIONPLAN):
            inv.rtplans.append(p)
        elif sop == SOP.RTDOSE:
            inv.rtdoses.append(p)
        elif sop in (SOP.SPATIAL_REGISTRATION, SOP.DEFORMABLE_SPATIAL_REGISTRATION):
            inv.registrations.append(p)
        else:
            inv.other.append(p)
    return inv


__all__ = ["PatientInfo", "CTVolume", "read_ct_series", "DicomInventory", "inventory"]
