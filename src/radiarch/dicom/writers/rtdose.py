"""RT Dose writer (roadmap R6).

A ``(z, y, x)`` dose on an axis-aligned grid whose origin is the centre of
voxel ``[0, 0, 0]`` becomes a multi-frame RT Dose: frames by ascending z,
``GridFrameOffsetVector`` relative to the first frame, 32-bit unsigned pixels
scaled by ``DoseGridScaling`` over 31 bits (a 70 Gy plan resolves to
3e-8 Gy). ``DoseType`` is EFFECTIVE for an RBE-weighted dose and
PHYSICAL otherwise; the RBE and the units go into ``DoseComment``. Summation
PLAN references the plan, BEAM references the plan, its fraction group and
the beam.

Given the structure set's ROI numbers and masks on the dose grid, the dose also
carries the RT DVH module (R13): one cumulative DVH per ROI in cm³, bins of a
uniform width from 0 Gy, with each ROI's minimum, maximum and mean dose, so a
viewer shows radiarch's DVH without its API.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from pydicom.dataset import Dataset

from ..uids import SOP
from .common import CaseContext, ds_list, new_dataset, ref, research_text, save, seq, with_frame_of_reference


DVH_MAX_BINS = 1000        # DVH Data is DS, whose explicit-VR length field caps it at 64 KiB: 1000 pairs fit
DVH_MIN_BIN_GY = 0.01


def dvh_bin_width(dose_max_gy: float) -> float:
    """The DVH bin width: 1, 2 or 5 × 10^k Gy, at least 0.01 Gy, so the maximum dose fits in DVH_MAX_BINS bins."""
    target = max(DVH_MIN_BIN_GY, float(dose_max_gy) / (DVH_MAX_BINS - 1))
    k = math.floor(math.log10(target))
    for m in (1.0, 2.0, 5.0, 10.0):
        if m * 10**k >= target * (1 - 1e-9):
            return float(f"{m * 10**k:.6g}")
    return float(10 ** (k + 1))


def dvh_items(dose_zyx: np.ndarray, rois: Sequence[Tuple[int, np.ndarray]], voxel_cc: float, dose_type: str) -> List[Dataset]:
    """DVH Sequence items: per ROI, the cumulative DVH (volume in cm³ at or above each bin's lower edge)."""
    from ...services.dvh import dvh_on_bins

    dose = np.asarray(dose_zyx, dtype=np.float64)
    width = dvh_bin_width(float(dose.max()) if dose.size else 0.0)
    items = []
    for number, mask in rois:
        m = np.asarray(mask, dtype=bool)
        if m.shape != dose.shape:
            raise ValueError(f"ROI {number}: mask shape {m.shape} != dose shape {dose.shape}")
        if not m.any():
            continue
        d = dose[m]
        n_bins = int(math.floor(float(d.max()) / width)) + 1
        volume = dvh_on_bins(dose, m, np.arange(n_bins) * width) / 100.0 * m.sum() * voxel_cc
        item = Dataset()
        roi = Dataset()
        roi.ReferencedROINumber = int(number)
        roi.DVHROIContributionType = "INCLUDED"
        item.DVHReferencedROISequence = seq([roi])
        item.DVHType = "CUMULATIVE"
        item.DoseUnits = "GY"
        item.DoseType = dose_type
        item.DVHDoseScaling = 1.0
        item.DVHVolumeUnits = "CM3"
        item.DVHNumberOfBins = n_bins
        item.DVHData = [v for pair in zip([width] * n_bins, ds_list(volume)) for v in pair]
        item.DVHMinimumDose, item.DVHMaximumDose, item.DVHMeanDose = ds_list([d.min(), d.max(), d.mean()])
        items.append(item)
    return items


@dataclass
class RTDoseResult:
    path: str
    sop_instance_uid: str
    series_instance_uid: str
    summation_type: str
    beam_number: Optional[int]
    max_gy: float


def build_rtdose(ctx: CaseContext, dose_zyx: np.ndarray, origin_mm: Sequence[float], spacing_mm: Sequence[float], *,
                 plan_sop_class: str, plan_sop_instance: str, summation: str = "PLAN", beam_number: Optional[int] = None,
                 fraction_group_number: int = 1, rbe: float = 1.0, dose_units: str = "Gy", comment: str = "",
                 series_number: int = 300, series_instance_uid: Optional[str] = None,
                 sop_instance_uid: Optional[str] = None, instance_number: int = 1,
                 heterogeneity: str = "IMAGE", other_plans: Sequence[Tuple[str, str]] = (),
                 rtstruct_uid: Optional[str] = None, dvh_rois: Sequence[Tuple[int, np.ndarray]] = ()) -> Dataset:
    dose = np.asarray(dose_zyx, dtype=np.float32)
    if dose.ndim != 3:
        raise ValueError("dose must be a (z, y, x) volume")
    if summation not in ("PLAN", "BEAM", "FRACTION", "MULTI_PLAN", "CONTROL_POINT"):
        raise ValueError(f"unsupported DoseSummationType {summation}")
    if summation == "BEAM" and beam_number is None:
        raise ValueError("a BEAM dose needs the beam number")
    if other_plans and summation != "MULTI_PLAN":
        raise ValueError("only a MULTI_PLAN dose references other plans")
    if dvh_rois and not rtstruct_uid:
        raise ValueError("DVHs reference the structure set: give rtstruct_uid")
    nz, ny, nx = dose.shape
    sx, sy, sz = (float(v) for v in spacing_mm)
    ox, oy, oz = (float(v) for v in origin_mm)

    ds = new_dataset(ctx, SOP.RTDOSE, "RTDOSE", series_number=series_number,
                     series_instance_uid=series_instance_uid, sop_instance_uid=sop_instance_uid, instance_number=instance_number)
    with_frame_of_reference(ds, ctx)

    # General Image / Image Plane / Image Pixel / Multi-frame
    ds.ImageType = ["DERIVED", "SECONDARY"]
    ds.ContentDate = ctx.date
    ds.ContentTime = ctx.time
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.ImagePositionPatient = ds_list([ox, oy, oz])
    ds.PixelSpacing = ds_list([sy, sx])          # row spacing (y), column spacing (x)
    ds.SliceThickness = float(f"{sz:.6g}")
    ds.Rows = int(ny)
    ds.Columns = int(nx)
    ds.NumberOfFrames = int(nz)
    ds.FrameIncrementPointer = (0x3004, 0x000C)
    ds.GridFrameOffsetVector = ds_list([k * sz for k in range(nz)])
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 32
    ds.BitsStored = 32
    ds.HighBit = 31
    ds.PixelRepresentation = 0

    # RT Dose
    effective = abs(float(rbe) - 1.0) > 1e-9 or dose_units.upper().endswith("(RBE)")
    ds.DoseUnits = "GY"
    ds.DoseType = "EFFECTIVE" if effective else "PHYSICAL"
    text = f"RBE {float(rbe):g}, {dose_units}" if effective else ""
    ds.DoseComment = research_text(f"{text}; {comment}" if comment else text)
    ds.DoseSummationType = summation
    plan_ref = ref(plan_sop_class, plan_sop_instance)
    if summation in ("BEAM", "FRACTION", "CONTROL_POINT"):
        fg = Dataset()
        fg.ReferencedFractionGroupNumber = int(fraction_group_number)
        if summation != "FRACTION":
            b = Dataset()
            b.ReferencedBeamNumber = int(beam_number)
            fg.ReferencedBeamSequence = seq([b])
        plan_ref.ReferencedFractionGroupSequence = seq([fg])
    ds.ReferencedRTPlanSequence = seq([plan_ref] + [ref(c, u) for c, u in other_plans])     # MULTI_PLAN: every plan summed
    ds.TissueHeterogeneityCorrection = heterogeneity

    # unsigned pixel data: an engine's round-off below zero (the pencil beam's FFT gives -1e-5 Gy) must not wrap to
    # the top of the range (it did before R9: 2^32 x the scaling, about twice the maximum, at those voxels)
    dose = np.clip(np.nan_to_num(dose, nan=0.0, posinf=0.0, neginf=0.0), 0.0, None)
    dose_max = float(dose.max()) if dose.size else 0.0
    if dose_max > 0.0:
        scaling = dose_max / float(2**31 - 1)
        scaled = np.rint(dose.astype(np.float64) / scaling).astype(np.uint32)
    else:
        scaling = 1.0
        scaled = np.zeros(dose.shape, dtype=np.uint32)
    ds.DoseGridScaling = float(f"{scaling:.10g}")
    ds.PixelData = np.ascontiguousarray(scaled).tobytes()

    # RT DVH: from the dose as stored (the scaled integers), so it is the DVH of what a reader of this file gets
    if dvh_rois:
        items = dvh_items(scaled.astype(np.float64) * float(ds.DoseGridScaling), dvh_rois, sx * sy * sz / 1000.0, str(ds.DoseType))
        if items:
            ds.ReferencedStructureSetSequence = seq([ref(SOP.RTSTRUCT, rtstruct_uid)])
            ds.DVHSequence = seq(items)
    return ds


def write_rtdose(ctx: CaseContext, dose_zyx: np.ndarray, origin_mm: Sequence[float], spacing_mm: Sequence[float],
                 path: Union[str, Path], **kw) -> RTDoseResult:
    ds = build_rtdose(ctx, dose_zyx, origin_mm, spacing_mm, **kw)
    save(ds, path)
    return RTDoseResult(path=str(path), sop_instance_uid=str(ds.SOPInstanceUID), series_instance_uid=str(ds.SeriesInstanceUID),
                        summation_type=str(ds.DoseSummationType), beam_number=kw.get("beam_number"),
                        max_gy=float(np.asarray(dose_zyx, dtype=np.float32).max()) if np.asarray(dose_zyx).size else 0.0)


__all__ = ["RTDoseResult", "build_rtdose", "write_rtdose", "dvh_items", "dvh_bin_width"]
