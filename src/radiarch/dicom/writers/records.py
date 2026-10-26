"""RT Beams Treatment Record, RT Ion Beams Treatment Record and RT Treatment
Summary Record writers (roadmap R6).

A treatment record is what a delivery system writes after a session: the
plan it delivered, the fraction number, the date, and per beam what was
specified and what was delivered at every control point. Radiarch writes
them from the plan it wrote, for a treatment machine's record keeping
and for its own end-to-end tests: ``delivered`` scales the
specified metersets (1.0 = the whole fraction; less for an interrupted
session, which then terminates OPERATOR or MACHINE). The summary record
closes a course: fractions delivered, first and last dates, the cumulative
dose to the plan's dose reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from pydicom.dataset import Dataset

from ...models.photon_plan import PhotonPlan
from ...models.proton_plan import ProtonPlan
from ..uids import SOP
from .common import CaseContext, ds_list, new_dataset, per_fraction, ref, research_text, save, seq
from .rtplan import PlanWriteOptions, _beam_boundaries, _leaf_positions


@dataclass
class Session:
    """One delivered fraction."""

    fraction_number: int
    treatment_date: Union[str, date, datetime]
    treatment_time: str = "120000"
    delivered: float = 1.0                      # fraction of every specified meterset delivered
    termination: str = "NORMAL"                 # NORMAL | OPERATOR | MACHINE | UNKNOWN
    verification: str = "VERIFIED"              # VERIFIED | VERIFIED_OVR | NOT_VERIFIED
    machine_name: str = "RADIARCH"
    beam_delivered: Dict[str, float] = field(default_factory=dict)   # beam name → delivered fraction, overrides `delivered`
    couch_vertical_mm: Optional[float] = None
    couch_longitudinal_mm: Optional[float] = None
    couch_lateral_mm: Optional[float] = None
    referenced_record_uids: List[str] = field(default_factory=list)  # earlier records of the course

    @property
    def date_str(self) -> str:
        d = self.treatment_date
        if isinstance(d, (date, datetime)):
            return d.strftime("%Y%m%d")
        return str(d)


@dataclass
class RecordResult:
    path: str
    sop_class_uid: str
    sop_instance_uid: str
    series_instance_uid: str
    fraction_number: Optional[int]
    delivered_metersets: Dict[str, float]


def _general_record(ds: Dataset, ctx: CaseContext, session: Optional[Session], plan_sop_class: str, plan_sop_instance: str,
                    machine_name: str, setup_and_machine: bool = True) -> None:
    ds.TreatmentDate = session.date_str if session else ctx.date
    ds.TreatmentTime = session.treatment_time if session else ctx.time
    ds.ReferencedRTPlanSequence = seq([ref(plan_sop_class, plan_sop_instance)])
    if session and session.referenced_record_uids:
        cls = SOP.RTBEAMS_TREATMENT_RECORD if plan_sop_class == SOP.RTPLAN else SOP.RTION_BEAMS_TREATMENT_RECORD
        ds.ReferencedTreatmentRecordSequence = seq([ref(cls, uid) for uid in session.referenced_record_uids])
    if not setup_and_machine:
        return
    setup = Dataset()
    setup.PatientSetupNumber = 1
    setup.PatientPosition = ctx.patient_position
    setup.SetupTechnique = "ISOCENTRIC"
    ds.PatientSetupSequence = seq([setup])
    machine = Dataset()
    machine.TreatmentMachineName = machine_name[:16]
    machine.Manufacturer = "Radiarch"
    machine.InstitutionName = ctx.institution_name
    machine.InstitutionAddress = ""
    machine.ManufacturerModelName = "emulated delivery"
    machine.DeviceSerialNumber = "0"
    ds.TreatmentMachineSequence = seq([machine])


def _couch(cp: Dataset, session: Session) -> None:
    cp.TableTopVerticalPosition = session.couch_vertical_mm
    cp.TableTopLongitudinalPosition = session.couch_longitudinal_mm
    cp.TableTopLateralPosition = session.couch_lateral_mm


# ---------------------------------------------------------------------------
# RT Beams Treatment Record (photons)
# ---------------------------------------------------------------------------

def build_beams_record(ctx: CaseContext, plan: PhotonPlan, session: Session, *, plan_sop_instance: str,
                       options: Optional[PlanWriteOptions] = None, series_number: int = 500,
                       series_instance_uid: Optional[str] = None, sop_instance_uid: Optional[str] = None) -> Dataset:
    opt = options or PlanWriteOptions()
    ds = new_dataset(ctx, SOP.RTBEAMS_TREATMENT_RECORD, "RTRECORD", series_number=series_number,
                     series_instance_uid=series_instance_uid, sop_instance_uid=sop_instance_uid,
                     instance_number=session.fraction_number)
    _general_record(ds, ctx, session, SOP.RTPLAN, plan_sop_instance, session.machine_name)
    plan = per_fraction(plan, int(opt.prescription.fractions) if opt.prescription else 1)     # a session delivers one fraction

    items = []
    for number, beam in enumerate(plan.beams, start=1):
        specified = float(sum(s.mu for s in beam.segments))
        if specified <= 0.0:
            continue
        frac = float(session.beam_delivered.get(beam.beam_id, session.delivered))
        tb = Dataset()
        tb.ReferencedBeamNumber = number
        tb.BeamName = beam.beam_id[:64]
        tb.BeamType = "STATIC"
        tb.RadiationType = "PHOTON"
        tb.TreatmentDeliveryType = "TREATMENT"
        tb.SourceAxisDistance = float(beam.sad_mm)
        tb.NumberOfWedges = 0
        tb.NumberOfCompensators = 0
        tb.NumberOfBoli = 0
        tb.NumberOfBlocks = 0
        tb.CurrentFractionNumber = int(session.fraction_number)
        tb.TreatmentTerminationStatus = session.termination
        tb.TreatmentVerificationStatus = session.verification
        tb.ReferencedPatientSetupNumber = 1
        tb.SpecifiedPrimaryMeterset = float(f"{specified:.10g}")
        tb.DeliveredPrimaryMeterset = float(f"{specified * frac:.10g}")
        tb.SpecifiedTreatmentTime = float(f"{specified / opt.dose_rate_mu_min * 60.0:.6g}")
        tb.DeliveredTreatmentTime = float(f"{specified * frac / opt.dose_rate_mu_min * 60.0:.6g}")

        bounds = _beam_boundaries(beam, opt.leaf_boundaries_mm)
        pairs = []
        for kind in ("X", "Y"):
            d = Dataset(); d.RTBeamLimitingDeviceType = kind; d.NumberOfLeafJawPairs = 1; pairs.append(d)
        if bounds is not None:
            d = Dataset(); d.RTBeamLimitingDeviceType = "MLCX"; d.NumberOfLeafJawPairs = len(bounds) - 1; pairs.append(d)
        tb.BeamLimitingDeviceLeafPairsSequence = seq(pairs)

        cps = []
        cmw = 0.0
        for seg in beam.segments:
            for phase in (0, 1):
                cp = Dataset()
                cp.ReferencedControlPointIndex = len(cps)
                cp.TreatmentControlPointDate = session.date_str
                cp.TreatmentControlPointTime = session.treatment_time
                if phase == 1:
                    cmw += float(seg.mu)
                cp.SpecifiedMeterset = float(f"{cmw:.10g}")
                cp.DeliveredMeterset = float(f"{cmw * frac:.10g}")
                cp.DoseRateSet = float(opt.dose_rate_mu_min)
                cp.DoseRateDelivered = float(opt.dose_rate_mu_min)
                positions = []
                for kind, jaw in (("X", seg.x_jaw_mm), ("Y", seg.y_jaw_mm)):
                    p = Dataset(); p.RTBeamLimitingDeviceType = kind; p.LeafJawPositions = ds_list(jaw); positions.append(p)
                if bounds is not None:
                    p = Dataset(); p.RTBeamLimitingDeviceType = "MLCX"
                    p.LeafJawPositions = _leaf_positions(seg.mlc_rows, bounds, float(seg.x_jaw_mm[0])); positions.append(p)
                cp.BeamLimitingDevicePositionSequence = seq(positions)
                cp.GantryAngle = float(f"{beam.gantry_deg % 360.0:.6g}")
                cp.GantryRotationDirection = "NONE"
                cp.BeamLimitingDeviceAngle = float(f"{seg.collimator_deg % 360.0:.6g}")
                cp.BeamLimitingDeviceRotationDirection = "NONE"
                cp.PatientSupportAngle = float(f"{beam.couch_deg % 360.0:.6g}")
                cp.PatientSupportRotationDirection = "NONE"
                cp.TableTopEccentricAngle = 0.0
                cp.TableTopEccentricRotationDirection = "NONE"
                _couch(cp, session)
                cps.append(cp)
        tb.NumberOfControlPoints = len(cps)
        tb.ControlPointDeliverySequence = seq(cps)
        items.append(tb)
    if not items:
        raise ValueError("the plan has no beam with a positive meterset")
    ds.TreatmentSessionBeamSequence = seq(items)
    ds.NumberOfFractionsPlanned = int(opt.prescription.fractions) if opt.prescription else 1
    ds.PrimaryDosimeterUnit = "MU"
    return ds


# ---------------------------------------------------------------------------
# RT Ion Beams Treatment Record (protons)
# ---------------------------------------------------------------------------

def build_ion_beams_record(ctx: CaseContext, plan: ProtonPlan, session: Session, *, plan_sop_instance: str,
                           options: Optional[PlanWriteOptions] = None, series_number: int = 500,
                           series_instance_uid: Optional[str] = None, sop_instance_uid: Optional[str] = None) -> Dataset:
    opt = options or PlanWriteOptions()
    ds = new_dataset(ctx, SOP.RTION_BEAMS_TREATMENT_RECORD, "RTRECORD", series_number=series_number,
                     series_instance_uid=series_instance_uid, sop_instance_uid=sop_instance_uid,
                     instance_number=session.fraction_number)
    _general_record(ds, ctx, session, SOP.RTIONPLAN, plan_sop_instance, session.machine_name)
    plan = per_fraction(plan, int(opt.prescription.fractions) if opt.prescription else int(plan.n_fractions))

    items = []
    for number, beam in enumerate(plan.beams, start=1):
        specified = float(beam.meterset)
        if specified <= 0.0:
            continue
        frac = float(session.beam_delivered.get(beam.beam_id or beam.name, session.delivered))
        tb = Dataset()
        tb.ReferencedBeamNumber = number
        tb.BeamName = (beam.name or beam.beam_id or f"B{number}")[:64]
        tb.BeamType = "STATIC"
        tb.RadiationType = "PROTON"
        tb.ScanMode = "MODULATED"
        tb.TreatmentDeliveryType = "TREATMENT"
        tb.NumberOfWedges = 0
        tb.NumberOfCompensators = 0
        tb.NumberOfBoli = 0
        tb.NumberOfBlocks = 0
        tb.NumberOfRangeShifters = 1 if beam.range_shifter_id else 0
        tb.NumberOfLateralSpreadingDevices = 0
        tb.NumberOfRangeModulators = 0
        tb.PatientSupportType = "TABLE"
        tb.CurrentFractionNumber = int(session.fraction_number)
        tb.TreatmentTerminationStatus = session.termination
        tb.TreatmentVerificationStatus = session.verification
        tb.ReferencedPatientSetupNumber = 1
        tb.SpecifiedPrimaryMeterset = float(f"{specified:.10g}")
        tb.DeliveredPrimaryMeterset = float(f"{specified * frac:.10g}")
        if beam.range_shifter_id:
            rs = Dataset(); rs.ReferencedRangeShifterNumber = 1; rs.RangeShifterID = str(beam.range_shifter_id)[:16]
            tb.RecordedRangeShifterSequence = seq([rs])

        cps = []
        cmw = 0.0
        for layer in beam.layers:
            spots = [s for s in layer.spots if s.mu > 0.0]
            if not spots:
                continue
            layer_mu = float(sum(s.mu for s in spots))
            for phase in (0, 1):
                cp = Dataset()
                cp.ReferencedControlPointIndex = len(cps)
                cp.TreatmentControlPointDate = session.date_str
                cp.TreatmentControlPointTime = session.treatment_time
                if phase == 1:
                    cmw += layer_mu
                cp.SpecifiedMeterset = float(f"{cmw:.10g}")
                cp.DeliveredMeterset = float(f"{cmw * frac:.10g}")
                cp.NominalBeamEnergy = float(f"{layer.energy_mev:.6g}")
                cp.ScanSpotTuneID = opt.scan_spot_tune_id[:16]
                cp.NumberOfScanSpotPositions = len(spots)
                cp.ScanSpotPositionMap = ds_list([v for s in spots for v in (s.x_mm, s.y_mm)])
                cp.ScanSpotMetersetsDelivered = ds_list([(s.mu if phase == 0 else 0.0) * frac for s in spots])
                cp.NumberOfPaintings = 1
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
                _couch(cp, session)
                if beam.range_shifter_id:
                    st = Dataset(); st.ReferencedRangeShifterNumber = 1
                    setting = layer.range_shifter
                    st.RangeShifterSetting = (setting.setting if setting is not None else "IN")[:16]
                    cp.RangeShifterSettingsSequence = seq([st])
                cps.append(cp)
        if not cps:
            continue
        tb.NumberOfControlPoints = len(cps)
        tb.IonControlPointDeliverySequence = seq(cps)
        items.append(tb)
    if not items:
        raise ValueError("the ion plan has no beam with a positive meterset")
    ds.TreatmentSessionIonBeamSequence = seq(items)
    ds.NumberOfFractionsPlanned = int(opt.prescription.fractions) if opt.prescription else int(plan.n_fractions)
    ds.PrimaryDosimeterUnit = "MU"
    return ds


# ---------------------------------------------------------------------------
# RT Treatment Summary Record
# ---------------------------------------------------------------------------

@dataclass
class CourseSummary:
    sessions: List[Session]
    fractions_planned: int
    status: str = "COMPLETED"                 # NOT_STARTED | ON_TREATMENT | ON_BREAK | SUSPENDED | STOPPED | COMPLETED
    comment: str = ""
    prescription_dose_gy: Optional[float] = None     # total; the cumulative dose is its delivered share
    dose_reference_description: str = "target"


def build_summary_record(ctx: CaseContext, course: CourseSummary, *, plan_sop_class: str, plan_sop_instance: str,
                         machine_name: str = "RADIARCH", series_number: int = 600,
                         series_instance_uid: Optional[str] = None, sop_instance_uid: Optional[str] = None) -> Dataset:
    ds = new_dataset(ctx, SOP.RT_TREATMENT_SUMMARY_RECORD, "RTRECORD", series_number=series_number, series_instance_uid=series_instance_uid,
                     sop_instance_uid=sop_instance_uid)
    sessions = sorted(course.sessions, key=lambda s: s.fraction_number)
    last = sessions[-1] if sessions else None
    _general_record(ds, ctx, last, plan_sop_class, plan_sop_instance, machine_name, setup_and_machine=False)

    ds.CurrentTreatmentStatus = course.status
    ds.TreatmentStatusComment = research_text(course.comment)
    if sessions:
        ds.FirstTreatmentDate = sessions[0].date_str
        ds.MostRecentTreatmentDate = sessions[-1].date_str
    else:
        ds.FirstTreatmentDate = None
        ds.MostRecentTreatmentDate = None
    delivered = float(sum(s.delivered for s in sessions))
    if course.prescription_dose_gy is not None and course.fractions_planned > 0:
        cd = Dataset()
        cd.ReferencedDoseReferenceNumber = 1
        cd.DoseReferenceDescription = course.dose_reference_description[:64]
        cd.CumulativeDoseToDoseReference = float(f"{course.prescription_dose_gy * delivered / course.fractions_planned:.6g}")
        ds.TreatmentSummaryCalculatedDoseReferenceSequence = seq([cd])
    fg = Dataset()
    fg.ReferencedFractionGroupNumber = 1
    fg.FractionGroupType = "EXTERNAL_BEAM"
    fg.NumberOfFractionsPlanned = int(course.fractions_planned)
    fg.NumberOfFractionsDelivered = len(sessions)
    fs = []
    for s in sessions:
        f = Dataset()
        f.ReferencedFractionNumber = int(s.fraction_number)
        f.TreatmentDate = s.date_str
        f.TreatmentTime = s.treatment_time
        f.TreatmentTerminationStatus = s.termination
        fs.append(f)
    if fs:
        fg.FractionStatusSummarySequence = seq(fs)
    ds.FractionGroupSummarySequence = seq([fg])
    return ds


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def write_treatment_record(ctx: CaseContext, plan: Union[PhotonPlan, ProtonPlan], session: Session, path: Union[str, Path], *,
                           plan_sop_instance: str, options: Optional[PlanWriteOptions] = None, **kw) -> RecordResult:
    """Write the RT (Ion) Beams Treatment Record of one session of ``plan``."""
    if isinstance(plan, PhotonPlan):
        ds = build_beams_record(ctx, plan, session, plan_sop_instance=plan_sop_instance, options=options, **kw)
        beams = ds.TreatmentSessionBeamSequence
    elif isinstance(plan, ProtonPlan):
        ds = build_ion_beams_record(ctx, plan, session, plan_sop_instance=plan_sop_instance, options=options, **kw)
        beams = ds.TreatmentSessionIonBeamSequence
    else:
        raise TypeError(f"not a radiarch plan: {type(plan).__name__}")
    save(ds, path)
    return RecordResult(path=str(path), sop_class_uid=str(ds.SOPClassUID), sop_instance_uid=str(ds.SOPInstanceUID),
                        series_instance_uid=str(ds.SeriesInstanceUID), fraction_number=session.fraction_number,
                        delivered_metersets={str(b.BeamName): float(b.DeliveredPrimaryMeterset) for b in beams})


def write_summary_record(ctx: CaseContext, course: CourseSummary, path: Union[str, Path], **kw) -> RecordResult:
    ds = build_summary_record(ctx, course, **kw)
    save(ds, path)
    return RecordResult(path=str(path), sop_class_uid=str(ds.SOPClassUID), sop_instance_uid=str(ds.SOPInstanceUID),
                        series_instance_uid=str(ds.SeriesInstanceUID), fraction_number=None, delivered_metersets={})


__all__ = ["Session", "CourseSummary", "RecordResult", "build_beams_record", "build_ion_beams_record",
           "build_summary_record", "write_treatment_record", "write_summary_record"]
