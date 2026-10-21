"""Hand-built DICOM RT objects for the reader tests (roadmap R2).

These builders write the attributes a planning system writes; the R6 writers
will replace them with radiarch's own. Kept as a plain module (not conftest)
so the tests import what they use.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence as DSeq
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from radiarch.dicom.uids import SOP


def _base(sop_class: str, modality: str, for_uid: str) -> Dataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128, is_implicit_VR=False, is_little_endian=True)
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = modality
    ds.PatientName = "ANON"
    ds.PatientID = "ANON-1"
    ds.StudyInstanceUID = "1.2.826.0.1.3680043.8.498.100"
    ds.SeriesInstanceUID = generate_uid()
    ds.FrameOfReferenceUID = for_uid
    return ds


def _seq(items: List[Dataset]) -> DSeq:
    return DSeq(items)


def photon_rtplan(beams: List[dict], metersets: Dict[int, float], *, bounds: Optional[Sequence[float]] = None,
                  n_fractions: int = 1, for_uid: str = "1.2.826.0.1.3680043.8.498.1", label: str = "TestPlan") -> Dataset:
    """``beams``: dicts with number, name, delivery ("TREATMENT"), sad, cps: list of dicts
    (cmw, gantry, couch, coll, iso, energy, xj, yj, mlc) — attributes given only where set,
    as DICOM allows after the first control point."""
    ds = _base(SOP.RTPLAN, "RTPLAN", for_uid)
    ds.RTPlanLabel = label
    ds.RTPlanName = label
    ds.ApprovalStatus = "UNAPPROVED"
    rss = Dataset(); rss.ReferencedSOPClassUID = SOP.RTSTRUCT; rss.ReferencedSOPInstanceUID = "1.2.826.0.1.3680043.8.498.77"
    ds.ReferencedStructureSetSequence = _seq([rss])
    fg = Dataset(); fg.FractionGroupNumber = 1; fg.NumberOfFractionsPlanned = n_fractions
    refs = []
    for number, mu in metersets.items():
        r = Dataset(); r.ReferencedBeamNumber = number; r.BeamMeterset = mu; refs.append(r)
    fg.ReferencedBeamSequence = _seq(refs)
    ds.FractionGroupSequence = _seq([fg])
    out = []
    for b in beams:
        bd = Dataset()
        bd.BeamNumber = b["number"]; bd.BeamName = b.get("name", f"B{b['number']}")
        bd.TreatmentDeliveryType = b.get("delivery", "TREATMENT"); bd.BeamType = "STATIC"; bd.RadiationType = "PHOTON"
        bd.SourceAxisDistance = b.get("sad", 1000.0)
        devs = []
        for kind in ("X", "Y"):
            d = Dataset(); d.RTBeamLimitingDeviceType = kind; d.NumberOfLeafJawPairs = 1; devs.append(d)
        if bounds is not None:
            d = Dataset(); d.RTBeamLimitingDeviceType = "MLCX"; d.NumberOfLeafJawPairs = len(bounds) - 1
            d.LeafPositionBoundaries = [float(v) for v in bounds]; devs.append(d)
        bd.BeamLimitingDeviceSequence = _seq(devs)
        cps = []
        for k, cp in enumerate(b["cps"]):
            c = Dataset(); c.ControlPointIndex = k; c.CumulativeMetersetWeight = cp["cmw"]
            for key, attr in (("gantry", "GantryAngle"), ("couch", "PatientSupportAngle"), ("coll", "BeamLimitingDeviceAngle"),
                              ("iso", "IsocenterPosition"), ("energy", "NominalBeamEnergy")):
                if key in cp:
                    setattr(c, attr, cp[key])
            pos = []
            for key, kind in (("xj", "X"), ("yj", "Y"), ("mlc", "MLCX")):
                if key in cp:
                    pd = Dataset(); pd.RTBeamLimitingDeviceType = kind; pd.LeafJawPositions = [float(v) for v in cp[key]]; pos.append(pd)
            if pos:
                c.BeamLimitingDevicePositionSequence = _seq(pos)
            cps.append(c)
        bd.NumberOfControlPoints = len(cps)
        bd.FinalCumulativeMetersetWeight = b.get("final_cmw", cps[-1].CumulativeMetersetWeight)
        bd.ControlPointSequence = _seq(cps)
        out.append(bd)
    ds.BeamSequence = _seq(out)
    return ds


def ion_rtplan(beams: List[dict], metersets: Dict[int, float], *, n_fractions: int = 1,
               for_uid: str = "1.2.826.0.1.3680043.8.498.1", label: str = "IonPlan") -> Dataset:
    """``beams``: dicts with number, name, gantry, couch, iso, range_shifter_id (optional), layers: list of
    (energy, [(x, y, weight), ...], rs_setting dict or None). Each layer becomes a control point with
    weights and a zero-weight control point after it, as planning systems write."""
    ds = _base(SOP.RTIONPLAN, "RTPLAN", for_uid)
    ds.RTPlanLabel = label
    fg = Dataset(); fg.FractionGroupNumber = 1; fg.NumberOfFractionsPlanned = n_fractions
    refs = []
    for number, mu in metersets.items():
        r = Dataset(); r.ReferencedBeamNumber = number; r.BeamMeterset = mu; refs.append(r)
    fg.ReferencedBeamSequence = _seq(refs)
    ds.FractionGroupSequence = _seq([fg])
    out = []
    for b in beams:
        bd = Dataset()
        bd.BeamNumber = b["number"]; bd.BeamName = b.get("name", f"IB{b['number']}")
        bd.TreatmentDeliveryType = b.get("delivery", "TREATMENT"); bd.BeamType = "STATIC"; bd.RadiationType = "PROTON"
        bd.ScanMode = "MODULATED"
        if b.get("range_shifter_id"):
            rs = Dataset(); rs.RangeShifterNumber = 1; rs.RangeShifterID = b["range_shifter_id"]; rs.RangeShifterType = "BINARY"
            bd.RangeShifterSequence = _seq([rs])
            bd.NumberOfRangeShifters = 1
        else:
            bd.NumberOfRangeShifters = 0
        total = sum(w for _, spots, _ in b["layers"] for _, _, w in spots)
        cps = []
        cmw = 0.0
        k = 0
        for li, (energy, spots, rs_setting) in enumerate(b["layers"]):
            for phase in (0, 1):
                c = Dataset(); c.ControlPointIndex = k; k += 1
                c.NominalBeamEnergy = energy
                if k == 1:
                    c.GantryAngle = b.get("gantry", 0.0); c.PatientSupportAngle = b.get("couch", 0.0)
                    c.IsocenterPosition = list(b.get("iso", (0.0, 0.0, 0.0)))
                c.NumberOfScanSpotPositions = len(spots)
                c.ScanSpotPositionMap = [float(v) for x, y, _ in spots for v in (x, y)]
                c.ScanSpotMetersetWeights = [float(w) if phase == 0 else 0.0 for _, _, w in spots]
                if phase == 0:
                    cmw += sum(w for _, _, w in spots)
                c.CumulativeMetersetWeight = cmw if phase == 1 else cmw - sum(w for _, _, w in spots)
                c.ScanSpotTuneID = "1"
                c.NumberOfPaintings = 1
                if rs_setting is not None:
                    s = Dataset(); s.ReferencedRangeShifterNumber = 1
                    s.RangeShifterSetting = rs_setting.get("setting", "IN")
                    s.IsocenterToRangeShifterDistance = rs_setting.get("distance", 0.0)
                    if "wet" in rs_setting:
                        s.RangeShifterWaterEquivalentThickness = rs_setting["wet"]
                    c.RangeShifterSettingsSequence = _seq([s])
                cps.append(c)
        bd.NumberOfControlPoints = len(cps)
        bd.FinalCumulativeMetersetWeight = total
        bd.IonControlPointSequence = _seq(cps)
        out.append(bd)
    ds.IonBeamSequence = _seq(out)
    return ds


def rtdose(dose_zyx: np.ndarray, spacing_xyz: Tuple[float, float, float], origin_xyz: Tuple[float, float, float], *,
           descending: bool = False, absolute_offsets: bool = False, for_uid: str = "1.2.826.0.1.3680043.8.498.1",
           plan_uid: str = "1.2.826.0.1.3680043.8.498.55") -> Dataset:
    ds = _base(SOP.RTDOSE, "RTDOSE", for_uid)
    nz, ny, nx = dose_zyx.shape
    ds.DoseUnits = "GY"; ds.DoseType = "PHYSICAL"; ds.DoseSummationType = "PLAN"
    r = Dataset(); r.ReferencedSOPClassUID = SOP.RTPLAN; r.ReferencedSOPInstanceUID = plan_uid
    ds.ReferencedRTPlanSequence = _seq([r])
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing = [spacing_xyz[1], spacing_xyz[0]]       # row (y), column (x)
    ds.Rows, ds.Columns, ds.NumberOfFrames = ny, nx, nz
    z = origin_xyz[2] + spacing_xyz[2] * np.arange(nz)
    frames = dose_zyx
    if descending:
        z = z[::-1]; frames = frames[::-1]
    ds.ImagePositionPatient = [origin_xyz[0], origin_xyz[1], float(z[0])]
    ds.GridFrameOffsetVector = [float(v) for v in (z if absolute_offsets else z - z[0])]
    scaling = float(frames.max()) / 65000.0 if frames.max() > 0 else 1.0
    ds.DoseGridScaling = scaling
    ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 0; ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.round(frames / scaling).astype("<u2").tobytes()
    return ds


def spatial_registration(for_uid: str, matrices: Dict[str, np.ndarray]) -> Dataset:
    ds = _base(SOP.SPATIAL_REGISTRATION, "REG", for_uid)
    items = []
    for src_for, m in matrices.items():
        item = Dataset(); item.FrameOfReferenceUID = src_for
        mr = Dataset(); mat = Dataset()
        mat.FrameOfReferenceTransformationMatrixType = "RIGID"
        mat.FrameOfReferenceTransformationMatrix = [float(v) for v in np.asarray(m).reshape(-1)]
        mr.MatrixSequence = _seq([mat]); item.MatrixRegistrationSequence = _seq([mr])
        items.append(item)
    ds.RegistrationSequence = _seq(items)
    return ds


def deformable_registration(for_uid: str, src_for: str, displacement_zyx: np.ndarray,
                            origin_xyz: Tuple[float, float, float], spacing_xyz: Tuple[float, float, float]) -> Dataset:
    ds = _base(SOP.DEFORMABLE_SPATIAL_REGISTRATION, "REG", for_uid)
    item = Dataset(); item.SourceFrameOfReferenceUID = src_for
    grid = Dataset()
    nz, ny, nx = displacement_zyx.shape[:3]
    grid.ImagePositionPatient = list(origin_xyz); grid.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    grid.GridDimensions = [nx, ny, nz]; grid.GridResolution = list(spacing_xyz)
    grid.VectorGridData = np.ascontiguousarray(displacement_zyx, dtype="<f4").tobytes()
    item.DeformableRegistrationGridSequence = _seq([grid])
    ds.DeformableRegistrationSequence = _seq([item])
    return ds


def save(ds: Dataset, path) -> str:
    ds.save_as(str(path), write_like_original=False)
    return str(path)
