"""RT Image writer for DRRs (roadmap R6).

The DRR plane is the isocenter plane (``RTImageSID = SAD``), normal to the
beam, so ``ImagePlanePixelSpacing`` is the pixel size at isocenter without
magnification. Rows run along the receptor's ``+x`` and columns down ``-y``
(``RTImageOrientation [1, 0, 0, 0, -1, 0]``); ``RTImagePosition`` is the
upper-left pixel centre in that plane. The image references the plan and the
beam it was cast for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np
from pydicom.dataset import Dataset

from ..drr import DRR
from ..uids import SOP
from .common import CaseContext, ds_list, new_dataset, ref, research_text, save, seq, with_frame_of_reference


@dataclass
class RTImageResult:
    path: str
    sop_instance_uid: str
    series_instance_uid: str
    beam_number: int


def build_rtimage(ctx: CaseContext, drr: DRR, *, beam_number: int, beam_name: str, plan_sop_class: str,
                  plan_sop_instance: str, machine_name: str = "RADIARCH", collimator_deg: float = 0.0,
                  series_number: int = 400, series_instance_uid: Optional[str] = None,
                  sop_instance_uid: Optional[str] = None, instance_number: int = 1) -> Dataset:
    ds = new_dataset(ctx, SOP.RTIMAGE, "RTIMAGE", series_number=series_number,
                     series_instance_uid=series_instance_uid, sop_instance_uid=sop_instance_uid,
                     instance_number=instance_number)
    with_frame_of_reference(ds, ctx)
    pixels = drr.to_uint16()
    rows, cols = pixels.shape

    # General Image / Image Pixel
    ds.ImageType = ["DERIVED", "SECONDARY", "DRR"]
    ds.ContentDate = ctx.date
    ds.ContentTime = ctx.time
    ds.PatientOrientation = ""
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = int(rows)
    ds.Columns = int(cols)
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = np.ascontiguousarray(pixels).tobytes()

    # RT Image
    ds.RTImageLabel = f"DRR {beam_name}"[:16]
    ds.RTImageName = f"DRR {beam_name}"[:64]
    ds.RTImageDescription = research_text(f"DRR of beam {beam_name}, gantry {drr.gantry_deg:g}")
    ds.ConversionType = "WSD"
    ds.RTImagePlane = "NORMAL"
    ds.XRayImageReceptorTranslation = [0.0, 0.0, 0.0]
    ds.XRayImageReceptorAngle = 0.0
    ds.RTImageOrientation = [1.0, 0.0, 0.0, 0.0, -1.0, 0.0]
    ds.ImagePlanePixelSpacing = ds_list([drr.pixel_mm[1], drr.pixel_mm[0]])      # row spacing, column spacing
    ds.RTImagePosition = ds_list(drr.upper_left_mm)
    ds.RadiationMachineName = machine_name[:16]
    ds.RadiationMachineSAD = float(drr.sad_mm)
    ds.RTImageSID = float(drr.sad_mm)
    ds.PrimaryDosimeterUnit = "MU"
    ds.GantryAngle = float(f"{drr.gantry_deg % 360.0:.6g}")
    ds.BeamLimitingDeviceAngle = float(f"{collimator_deg % 360.0:.6g}")
    ds.PatientSupportAngle = float(f"{drr.couch_deg % 360.0:.6g}")
    ds.TableTopEccentricAngle = 0.0
    ds.IsocenterPosition = ds_list(drr.isocenter_mm)
    ds.PatientPosition = ctx.patient_position
    ds.ReferencedRTPlanSequence = seq([ref(plan_sop_class, plan_sop_instance)])
    ds.ReferencedBeamNumber = int(beam_number)
    ds.ReferencedFractionGroupNumber = 1
    # no ReportedValuesOrigin: PS3.3 C.8.8.2 allows it only for SIMULATOR and PORTAL images, not a DRR
    return ds


def write_rtimage(ctx: CaseContext, drr: DRR, path: Union[str, Path], **kw) -> RTImageResult:
    ds = build_rtimage(ctx, drr, **kw)
    save(ds, path)
    return RTImageResult(path=str(path), sop_instance_uid=str(ds.SOPInstanceUID), series_instance_uid=str(ds.SeriesInstanceUID),
                         beam_number=int(kw["beam_number"]))


__all__ = ["RTImageResult", "build_rtimage", "write_rtimage"]
