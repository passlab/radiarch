"""RT Plan and RT Ion Plan writers (roadmap R6).

A :class:`PhotonPlan` is written as a step-and-shoot RT Plan: every segment
becomes a pair of control points (the aperture at a cumulative meterset
weight, then the same aperture after its meterset has been delivered), so
``2 n`` control points for ``n`` segments, the leaves moving between pairs at
zero meterset. Meterset weights are in MU, the fraction group's
``BeamMeterset`` is the beam's MU, and radiarch's reader gives the same
segments back. A :class:`ProtonPlan` is written as an RT Ion Plan with one
energy layer per pair of ion control points (spot weights, then zeros), as
planning systems write them.

The MLC of a photon beam is the machine's (``leaf_boundaries_mm``) when
given, the pairs the plan does not use parked closed at the X1 jaw; else the
leaf pairs the plan's rows define. Jaws-only plans get X and Y devices only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from pydicom.dataset import Dataset

from ...models.photon_plan import MLCRow, PhotonBeam, PhotonPlan
from ...models.proton_plan import ProtonBeam, ProtonPlan
from ..uids import SOP
from .common import CaseContext, ds_list, new_dataset, ref, research_text, save, seq, stable_uid


@dataclass
class Prescription:
    """What the plan prescribes: a dose to a target over some fractions."""

    dose_gy: float
    fractions: int = 1
    target_name: str = ""
    target_roi_number: Optional[int] = None
    description: str = ""


@dataclass
class PlanWriteOptions:
    label: str = "radiarch"
    description: str = ""
    machine_name: str = "RADIARCH"
    prescription: Optional[Prescription] = None
    leaf_boundaries_mm: Optional[Sequence[float]] = None        # the machine's MLC; None = from the plan's rows
    dose_rate_mu_min: float = 600.0
    drr_refs: Dict[str, Tuple[str, str]] = field(default_factory=dict)   # beam_id → (sop class, sop instance) of its DRR
    beam_doses_gy: Dict[str, float] = field(default_factory=dict)        # beam_id → dose at the prescription point
    series_number: int = 200
    series_instance_uid: Optional[str] = None
    sop_instance_uid: Optional[str] = None
    approval: str = "UNAPPROVED"
    plan_intent: str = "RESEARCH"
    # ion
    virtual_sad_mm: Tuple[float, float] = (2000.0, 2000.0)
    range_shifter_types: Dict[str, str] = field(default_factory=dict)    # id → BINARY | ANALOG
    scan_spot_tune_id: str = "radiarch"
    spot_size_mm: Optional[Tuple[float, float]] = None
    snout_position_mm: Optional[float] = None


@dataclass
class RTPlanResult:
    path: str
    sop_class_uid: str
    sop_instance_uid: str
    series_instance_uid: str
    beam_numbers: Dict[str, int]
    beam_metersets: Dict[str, float]
    n_fractions: int


# ---------------------------------------------------------------------------
# Shared modules
# ---------------------------------------------------------------------------

def _general_plan(ds: Dataset, ctx: CaseContext, opt: PlanWriteOptions, rtstruct_uid: str, n_fractions: int) -> None:
    ds.RTPlanLabel = opt.label[:16]
    ds.RTPlanName = opt.label[:64]
    ds.RTPlanDescription = research_text(opt.description)
    ds.RTPlanDate = ctx.date
    ds.RTPlanTime = ctx.time
    ds.RTPlanGeometry = "PATIENT"
    ds.PlanIntent = opt.plan_intent
    ds.ReferencedStructureSetSequence = seq([ref(SOP.RTSTRUCT, rtstruct_uid)])
    ds.FrameOfReferenceUID = ctx.frame_of_reference_uid
    ds.PositionReferenceIndicator = ""

    setup = Dataset()
    setup.PatientSetupNumber = 1
    setup.PatientPosition = ctx.patient_position
    setup.SetupTechnique = "ISOCENTRIC"
    ds.PatientSetupSequence = seq([setup])

    if opt.prescription is not None:
        p = opt.prescription
        dr = Dataset()
        dr.DoseReferenceNumber = 1
        dr.DoseReferenceUID = stable_uid(ds.SOPInstanceUID, "dose-reference-1")
        if p.target_roi_number is not None:
            dr.DoseReferenceStructureType = "VOLUME"
            dr.ReferencedROINumber = int(p.target_roi_number)
        else:
            dr.DoseReferenceStructureType = "SITE"
        dr.DoseReferenceDescription = (p.description or p.target_name or "target")[:64]
        dr.DoseReferenceType = "TARGET"
        dr.TargetPrescriptionDose = float(f"{p.dose_gy:.6g}")
        ds.DoseReferenceSequence = seq([dr])
    ds.ApprovalStatus = opt.approval


def _fraction_group(ds: Dataset, metersets: Dict[int, float], n_fractions: int, opt: PlanWriteOptions,
                    beam_ids: Dict[int, str]) -> None:
    fg = Dataset()
    fg.FractionGroupNumber = 1
    fg.NumberOfFractionsPlanned = int(n_fractions)
    fg.NumberOfBeams = len(metersets)
    fg.NumberOfBrachyApplicationSetups = 0
    refs = []
    for number, mu in metersets.items():
        r = Dataset()
        r.ReferencedBeamNumber = number
        r.BeamMeterset = float(f"{mu:.6g}")
        dose = opt.beam_doses_gy.get(beam_ids[number])
        if dose is not None:
            r.BeamDose = float(f"{float(dose):.6g}")
        refs.append(r)
    fg.ReferencedBeamSequence = seq(refs)
    if opt.prescription is not None:
        rd = Dataset()
        rd.ReferencedDoseReferenceNumber = 1
        fg.ReferencedDoseReferenceSequence = seq([rd])
    ds.FractionGroupSequence = seq([fg])


def _angles(cp: Dataset, gantry: float, collimator: float, couch: float, iso: Sequence[float]) -> None:
    cp.GantryAngle = float(f"{gantry % 360.0:.6g}")
    cp.GantryRotationDirection = "NONE"
    cp.BeamLimitingDeviceAngle = float(f"{collimator % 360.0:.6g}")
    cp.BeamLimitingDeviceRotationDirection = "NONE"
    cp.PatientSupportAngle = float(f"{couch % 360.0:.6g}")
    cp.PatientSupportRotationDirection = "NONE"
    cp.TableTopEccentricAngle = 0.0
    cp.TableTopEccentricRotationDirection = "NONE"
    cp.TableTopVerticalPosition = None
    cp.TableTopLongitudinalPosition = None
    cp.TableTopLateralPosition = None
    cp.IsocenterPosition = ds_list(iso)


# ---------------------------------------------------------------------------
# Photon
# ---------------------------------------------------------------------------

def _beam_boundaries(beam: PhotonBeam, machine_boundaries: Optional[Sequence[float]]) -> Optional[List[float]]:
    """The leaf-pair boundaries of a beam's MLC, or None for a jaws-only beam."""
    rows_per_segment = [s.mlc_rows for s in beam.segments]
    if not any(rows_per_segment):
        return None
    if machine_boundaries is not None:
        return [float(v) for v in machine_boundaries]
    edges: set = set()
    for rows in rows_per_segment:
        for r in rows:
            edges.add(round(r.y_min_mm, 4)); edges.add(round(r.y_max_mm, 4))
    bounds = sorted(edges)
    for rows in rows_per_segment:
        for r in rows:
            i = bounds.index(round(r.y_min_mm, 4))
            if bounds[i + 1] != round(r.y_max_mm, 4):
                raise ValueError(f"beam {beam.beam_id}: MLC rows overlap or leave gaps; give the machine's leaf boundaries")
    return bounds


def _leaf_positions(rows: Sequence[MLCRow], bounds: Sequence[float], parked_x: float) -> List[float]:
    n = len(bounds) - 1
    left = [parked_x] * n
    right = [parked_x] * n
    for r in rows:
        key = round(r.y_min_mm, 4)
        i = next((k for k in range(n) if round(bounds[k], 4) == key), None)
        if i is None:
            raise ValueError(f"MLC row at y={r.y_min_mm} is not a leaf pair of the machine")
        left[i] = float(r.x_left_mm)
        right[i] = float(r.x_right_mm)
    return ds_list(left + right)


def _arc_control_points(arc, beam: PhotonBeam, bounds: Optional[Sequence[float]], energy: float, total: float,
                        opt: PlanWriteOptions) -> List[Dataset]:
    """The control points of a DYNAMIC (VMAT) beam: the gantry turns in the arc's direction from one control
    point to the next while the leaves and jaws move linearly and the meterset difference is delivered."""
    cps: List[Dataset] = []
    last = len(arc.control_points) - 1
    for k, c in enumerate(arc.control_points):
        cp = Dataset()
        cp.ControlPointIndex = k
        cp.NominalBeamEnergy = energy
        cp.DoseRateSet = float(opt.dose_rate_mu_min)
        positions = []
        for kind, jaw in (("X", c.x_jaw_mm), ("Y", c.y_jaw_mm)):
            p = Dataset(); p.RTBeamLimitingDeviceType = kind; p.LeafJawPositions = ds_list(jaw); positions.append(p)
        if bounds is not None:
            p = Dataset(); p.RTBeamLimitingDeviceType = "MLCX"
            p.LeafJawPositions = _leaf_positions(c.mlc_rows, bounds, float(c.x_jaw_mm[0]))
            positions.append(p)
        cp.BeamLimitingDevicePositionSequence = seq(positions)
        _angles(cp, c.gantry_deg, arc.collimator_deg, beam.couch_deg, beam.isocenter_mm)
        cp.GantryRotationDirection = arc.direction if k < last else "NONE"
        cp.CumulativeMetersetWeight = float(f"{c.cumulative_mu:.6g}")
        if opt.prescription is not None:
            rd = Dataset(); rd.ReferencedDoseReferenceNumber = 1
            rd.CumulativeDoseReferenceCoefficient = float(f"{c.cumulative_mu / total:.6g}") if total > 0 else 0.0
            cp.ReferencedDoseReferenceSequence = seq([rd])
        cps.append(cp)
    return cps


def build_rtplan(ctx: CaseContext, plan: PhotonPlan, *, rtstruct_uid: str, options: Optional[PlanWriteOptions] = None) -> Dataset:
    opt = options or PlanWriteOptions()
    n_fractions = int(opt.prescription.fractions) if opt.prescription else 1
    ds = new_dataset(ctx, SOP.RTPLAN, "RTPLAN", series_number=opt.series_number, series_instance_uid=opt.series_instance_uid,
                     sop_instance_uid=opt.sop_instance_uid)
    _general_plan(ds, ctx, opt, rtstruct_uid, n_fractions)

    beams: List[Dataset] = []
    metersets: Dict[int, float] = {}
    beam_ids: Dict[int, str] = {}
    for number, beam in enumerate(plan.beams, start=1):
        total = float(sum(s.mu for s in beam.segments))
        if total <= 0.0:
            continue
        bd = Dataset()
        bd.BeamNumber = number
        bd.BeamName = beam.beam_id[:64]
        arc = getattr(beam, "arc", None)
        bd.BeamDescription = research_text(f"arc of {len(arc.control_points)} control points" if arc is not None
                                           else f"{len(beam.segments)} segments")
        bd.BeamType = "DYNAMIC" if arc is not None else "STATIC"
        bd.RadiationType = "PHOTON"
        bd.TreatmentMachineName = opt.machine_name[:16]
        bd.Manufacturer = "Radiarch"
        bd.PrimaryDosimeterUnit = "MU"
        bd.SourceAxisDistance = float(beam.sad_mm)
        bd.ReferencedPatientSetupNumber = 1
        bd.TreatmentDeliveryType = "TREATMENT"
        bd.NumberOfWedges = 0
        bd.NumberOfCompensators = 0
        bd.NumberOfBoli = 0
        bd.NumberOfBlocks = 0
        if beam.beam_id in opt.drr_refs:
            sop_class, sop_uid = opt.drr_refs[beam.beam_id]
            r = ref(sop_class, sop_uid)
            r.ReferenceImageNumber = 1
            bd.ReferencedReferenceImageSequence = seq([r])

        bounds = _beam_boundaries(beam, opt.leaf_boundaries_mm)
        devices = []
        for kind in ("X", "Y"):
            d = Dataset(); d.RTBeamLimitingDeviceType = kind; d.NumberOfLeafJawPairs = 1; devices.append(d)
        if bounds is not None:
            d = Dataset()
            d.RTBeamLimitingDeviceType = "MLCX"
            d.NumberOfLeafJawPairs = len(bounds) - 1
            d.LeafPositionBoundaries = ds_list(bounds)
            devices.append(d)
        bd.BeamLimitingDeviceSequence = seq(devices)

        cps: List[Dataset] = []
        cmw = 0.0
        energy = float(beam.energy_mv) if beam.energy_mv else 6.0
        if arc is not None:
            cps = _arc_control_points(arc, beam, bounds, energy, total, opt)
            cmw = float(arc.total_mu)
        for seg in ([] if arc is not None else beam.segments):
            for phase in (0, 1):
                cp = Dataset()
                cp.ControlPointIndex = len(cps)
                cp.NominalBeamEnergy = energy
                cp.DoseRateSet = float(opt.dose_rate_mu_min)
                positions = []
                for kind, jaw in (("X", seg.x_jaw_mm), ("Y", seg.y_jaw_mm)):
                    p = Dataset(); p.RTBeamLimitingDeviceType = kind; p.LeafJawPositions = ds_list(jaw); positions.append(p)
                if bounds is not None:
                    p = Dataset(); p.RTBeamLimitingDeviceType = "MLCX"
                    p.LeafJawPositions = _leaf_positions(seg.mlc_rows, bounds, float(seg.x_jaw_mm[0]))
                    positions.append(p)
                cp.BeamLimitingDevicePositionSequence = seq(positions)
                _angles(cp, beam.gantry_deg, seg.collimator_deg, beam.couch_deg, beam.isocenter_mm)
                if phase == 1:
                    cmw += float(seg.mu)
                cp.CumulativeMetersetWeight = float(f"{cmw:.6g}")
                if opt.prescription is not None:
                    rd = Dataset(); rd.ReferencedDoseReferenceNumber = 1
                    rd.CumulativeDoseReferenceCoefficient = float(f"{cmw / total:.6g}")
                    cp.ReferencedDoseReferenceSequence = seq([rd])
                cps.append(cp)
        bd.FinalCumulativeMetersetWeight = float(f"{cmw:.6g}")
        bd.NumberOfControlPoints = len(cps)
        bd.ControlPointSequence = seq(cps)
        beams.append(bd)
        metersets[number] = cmw
        beam_ids[number] = beam.beam_id
    if not beams:
        raise ValueError("the plan has no beam with a positive meterset")
    ds.BeamSequence = seq(beams)
    _fraction_group(ds, metersets, n_fractions, opt, beam_ids)
    return ds


# ---------------------------------------------------------------------------
# Ion (proton PBS)
# ---------------------------------------------------------------------------

def _ion_angles(cp: Dataset, beam: ProtonBeam, opt: PlanWriteOptions) -> None:
    cp.GantryAngle = float(f"{beam.gantry_deg % 360.0:.6g}")
    cp.GantryRotationDirection = "NONE"
    cp.GantryPitchAngle = 0.0
    cp.GantryPitchRotationDirection = "NONE"
    cp.BeamLimitingDeviceAngle = 0.0
    cp.BeamLimitingDeviceRotationDirection = "NONE"
    cp.PatientSupportAngle = float(f"{beam.couch_deg % 360.0:.6g}")
    cp.PatientSupportRotationDirection = "NONE"
    cp.TableTopPitchAngle = 0.0
    cp.TableTopPitchRotationDirection = "NONE"
    cp.TableTopRollAngle = 0.0
    cp.TableTopRollRotationDirection = "NONE"
    cp.TableTopVerticalPosition = None
    cp.TableTopLongitudinalPosition = None
    cp.TableTopLateralPosition = None
    cp.SnoutPosition = None if opt.snout_position_mm is None else float(opt.snout_position_mm)
    cp.IsocenterPosition = ds_list(beam.isocenter_mm)


def build_rtionplan(ctx: CaseContext, plan: ProtonPlan, *, rtstruct_uid: str, options: Optional[PlanWriteOptions] = None) -> Dataset:
    opt = options or PlanWriteOptions()
    n_fractions = int(opt.prescription.fractions) if opt.prescription else int(plan.n_fractions)
    ds = new_dataset(ctx, SOP.RTIONPLAN, "RTPLAN", series_number=opt.series_number, series_instance_uid=opt.series_instance_uid,
                     sop_instance_uid=opt.sop_instance_uid)
    _general_plan(ds, ctx, opt, rtstruct_uid, n_fractions)

    beams: List[Dataset] = []
    metersets: Dict[int, float] = {}
    beam_ids: Dict[int, str] = {}
    for number, beam in enumerate(plan.beams, start=1):
        total = float(beam.meterset)
        if total <= 0.0:
            continue
        bd = Dataset()
        bd.BeamNumber = number
        bd.BeamName = (beam.name or beam.beam_id or f"B{number}")[:64]
        bd.BeamDescription = research_text(f"{len(beam.layers)} layers, {beam.n_spots} spots")
        bd.BeamType = "STATIC"
        bd.RadiationType = "PROTON"
        bd.ScanMode = "MODULATED"
        bd.TreatmentMachineName = opt.machine_name[:16]
        bd.Manufacturer = "Radiarch"
        bd.PrimaryDosimeterUnit = "MU"
        bd.VirtualSourceAxisDistances = ds_list(opt.virtual_sad_mm)
        bd.ReferencedPatientSetupNumber = 1
        bd.TreatmentDeliveryType = "TREATMENT"
        bd.NumberOfWedges = 0
        bd.NumberOfCompensators = 0
        bd.NumberOfBoli = 0
        bd.NumberOfBlocks = 0
        bd.NumberOfLateralSpreadingDevices = 0
        bd.NumberOfRangeModulators = 0
        bd.PatientSupportType = "TABLE"
        if beam.range_shifter_id:
            rs = Dataset()
            rs.RangeShifterNumber = 1
            rs.RangeShifterID = str(beam.range_shifter_id)[:16]
            rs.RangeShifterType = opt.range_shifter_types.get(beam.range_shifter_id, "BINARY")
            bd.NumberOfRangeShifters = 1
            bd.RangeShifterSequence = seq([rs])
        else:
            bd.NumberOfRangeShifters = 0
        if beam.beam_id in opt.drr_refs:
            sop_class, sop_uid = opt.drr_refs[beam.beam_id]
            r = ref(sop_class, sop_uid)
            r.ReferenceImageNumber = 1
            bd.ReferencedReferenceImageSequence = seq([r])

        cps: List[Dataset] = []
        cmw = 0.0
        for layer in beam.layers:
            spots = [s for s in layer.spots if s.mu > 0.0]
            if not spots:
                continue
            layer_mu = float(sum(s.mu for s in spots))
            for phase in (0, 1):
                cp = Dataset()
                cp.ControlPointIndex = len(cps)
                cp.NominalBeamEnergy = float(f"{layer.energy_mev:.6g}")
                _ion_angles(cp, beam, opt)
                cp.ScanSpotTuneID = opt.scan_spot_tune_id[:16]
                cp.NumberOfScanSpotPositions = len(spots)
                cp.ScanSpotPositionMap = ds_list([v for s in spots for v in (s.x_mm, s.y_mm)])
                cp.ScanSpotMetersetWeights = ds_list([s.mu if phase == 0 else 0.0 for s in spots])
                if opt.spot_size_mm is not None:
                    cp.ScanningSpotSize = ds_list(opt.spot_size_mm)
                cp.NumberOfPaintings = 1
                if beam.range_shifter_id:
                    st = Dataset()
                    st.ReferencedRangeShifterNumber = 1
                    setting = layer.range_shifter
                    st.RangeShifterSetting = (setting.setting if setting is not None else "IN")[:16]
                    if setting is not None:
                        st.IsocenterToRangeShifterDistance = float(setting.isocenter_to_range_shifter_mm)
                        if setting.water_equivalent_thickness_mm is not None:
                            st.RangeShifterWaterEquivalentThickness = float(setting.water_equivalent_thickness_mm)
                    cp.RangeShifterSettingsSequence = seq([st])
                if phase == 1:
                    cmw += layer_mu
                cp.CumulativeMetersetWeight = float(f"{cmw:.6g}")
                if opt.prescription is not None:
                    rd = Dataset(); rd.ReferencedDoseReferenceNumber = 1
                    rd.CumulativeDoseReferenceCoefficient = float(f"{cmw / total:.6g}")
                    cp.ReferencedDoseReferenceSequence = seq([rd])
                cps.append(cp)
        if not cps:
            continue
        bd.FinalCumulativeMetersetWeight = float(f"{cmw:.6g}")
        bd.NumberOfControlPoints = len(cps)
        bd.IonControlPointSequence = seq(cps)
        beams.append(bd)
        metersets[number] = cmw
        beam_ids[number] = beam.beam_id or bd.BeamName
    if not beams:
        raise ValueError("the ion plan has no beam with a positive meterset")
    ds.IonBeamSequence = seq(beams)
    _fraction_group(ds, metersets, n_fractions, opt, beam_ids)
    return ds


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def _result(ds: Dataset, path: Union[str, Path], plan, n_fractions: int) -> RTPlanResult:
    beams = ds.BeamSequence if hasattr(ds, "BeamSequence") else ds.IonBeamSequence
    numbers = {str(b.BeamName): int(b.BeamNumber) for b in beams}
    mu = {str(b.BeamName): float(b.FinalCumulativeMetersetWeight) for b in beams}
    return RTPlanResult(path=str(path), sop_class_uid=str(ds.SOPClassUID), sop_instance_uid=str(ds.SOPInstanceUID),
                        series_instance_uid=str(ds.SeriesInstanceUID), beam_numbers=numbers, beam_metersets=mu,
                        n_fractions=n_fractions)


def write_rtplan(ctx: CaseContext, plan: Union[PhotonPlan, ProtonPlan], path: Union[str, Path], *, rtstruct_uid: str,
                 options: Optional[PlanWriteOptions] = None) -> RTPlanResult:
    """Write ``plan`` as an RT Plan (photons) or RT Ion Plan (protons)."""
    if isinstance(plan, PhotonPlan):
        ds = build_rtplan(ctx, plan, rtstruct_uid=rtstruct_uid, options=options)
    elif isinstance(plan, ProtonPlan):
        ds = build_rtionplan(ctx, plan, rtstruct_uid=rtstruct_uid, options=options)
    else:
        raise TypeError(f"not a radiarch plan: {type(plan).__name__}")
    save(ds, path)
    return _result(ds, path, plan, int(ds.FractionGroupSequence[0].NumberOfFractionsPlanned))


__all__ = ["Prescription", "PlanWriteOptions", "RTPlanResult", "build_rtplan", "build_rtionplan", "write_rtplan"]
