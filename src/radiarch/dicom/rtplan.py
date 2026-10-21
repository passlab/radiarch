"""RT Plan and RT Ion Plan → radiarch plan models (roadmap R2).

Photon plans
------------
Every treatment beam with a non-zero meterset in the fraction group becomes
segments, one per control-point interval: the meterset of the interval is its
share of the cumulative meterset weight times the beam meterset, the aperture
is the jaw and MLC state at the start of the interval (for a static,
step-and-shoot plan) or the mean of its two ends (a sliding-window or VMAT
interval, where the leaves move linearly). A beam whose gantry angle is the
same at every control point is one :class:`PhotonBeam`; an arc is
discretized into one :class:`PhotonBeam` per interval at the interval's
mid-angle, which is the standard approximation for a VMAT dose recalculation
(roadmap R8 builds the arc optimizer on the same representation).

Ion plans
---------
Every treatment ion beam becomes a :class:`ProtonBeam`; every control point
that carries non-zero scan-spot meterset weights becomes an energy layer
whose spot metersets are their share of the final cumulative meterset weight
times the beam meterset. Range-shifter settings are carried per layer.

Attributes that DICOM allows to be omitted at later control points (gantry,
couch, collimator, isocenter, energy, jaws, leaves, range-shifter settings)
keep the value of the last control point that set them.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pydicom
from pydicom.dataset import Dataset

from ..models.common import DicomPlanProvenance
from ..models.photon_plan import MLCRow, PhotonBeam, PhotonPlan, PhotonSegment, open_field_mlc_rows
from ..models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot, RangeShifterSetting
from .uids import PLAN_SOP_CLASSES, SOP

Source = Union[str, Path, Dataset]


class RTPlanError(ValueError):
    """The plan cannot be represented in radiarch's models."""


def _dataset(src: Source) -> Tuple[Dataset, str]:
    if isinstance(src, Dataset):
        return src, ""
    path = Path(src)
    return pydicom.dcmread(str(path)), str(path)


def _provenance(ds: Dataset, sop_class: str, path: str) -> DicomPlanProvenance:
    refs = getattr(ds, "ReferencedStructureSetSequence", None)
    return DicomPlanProvenance(
        sop_class=sop_class,
        sop_instance_uid=str(getattr(ds, "SOPInstanceUID", "")),
        series_instance_uid=str(getattr(ds, "SeriesInstanceUID", "")),
        study_instance_uid=str(getattr(ds, "StudyInstanceUID", "")),
        frame_of_reference_uid=str(getattr(ds, "FrameOfReferenceUID", "")),
        structure_set_uid=str(refs[0].ReferencedSOPInstanceUID) if refs else "",
        plan_label=str(getattr(ds, "RTPlanLabel", "")),
        plan_name=str(getattr(ds, "RTPlanName", "")),
        approval_status=str(getattr(ds, "ApprovalStatus", "")),
        n_fractions=_n_fractions(ds),
        source_path=path,
    )


def _n_fractions(ds: Dataset) -> int:
    fgs = getattr(ds, "FractionGroupSequence", None)
    if not fgs:
        return 1
    try:
        return max(1, int(fgs[0].NumberOfFractionsPlanned))
    except (AttributeError, TypeError, ValueError):
        return 1


def _beam_metersets(ds: Dataset) -> Dict[int, float]:
    """Beam number → beam meterset (MU) from the first fraction group."""
    fgs = getattr(ds, "FractionGroupSequence", None)
    if not fgs:
        raise RTPlanError("plan has no FractionGroupSequence; beam metersets are unknown")
    out: Dict[int, float] = {}
    for rb in getattr(fgs[0], "ReferencedBeamSequence", []):
        mu = getattr(rb, "BeamMeterset", None)
        if mu is not None:
            out[int(rb.ReferencedBeamNumber)] = float(mu)
    return out


def _as_list(value: Any) -> List[float]:
    if value is None:
        return []
    try:
        return [float(v) for v in value]
    except TypeError:
        return [float(value)]


def _couch(angle: float) -> float:
    """DICOM PatientSupportAngle is 0–360; the model wants −180–180."""
    a = float(angle) % 360.0
    return a - 360.0 if a > 180.0 else a


def _mid_angle(a: float, b: float) -> float:
    """Mid-point of two angles along the shorter arc, in [0, 360)."""
    d = ((b - a + 180.0) % 360.0) - 180.0
    return (a + d / 2.0) % 360.0


def _mean_list(a: Optional[List[float]], b: Optional[List[float]]) -> Optional[List[float]]:
    if a is None:
        return b
    if b is None or len(a) != len(b):
        return a
    return [(x + y) / 2.0 for x, y in zip(a, b)]


# ---------------------------------------------------------------------------
# Photon
# ---------------------------------------------------------------------------

def _mlc_rows(bounds: Sequence[float], positions: Sequence[float]) -> List[MLCRow]:
    n = len(bounds) - 1
    if len(positions) != 2 * n:
        raise RTPlanError(f"MLC has {n} leaf pairs but {len(positions)} leaf positions")
    rows = []
    for i in range(n):
        left, right = float(positions[i]), float(positions[n + i])
        if right < left:                       # crossed leaves: treat as closed at the mid-point
            left = right = (left + right) / 2.0
        rows.append(MLCRow(y_min_mm=float(bounds[i]), y_max_mm=float(bounds[i + 1]), x_left_mm=left, x_right_mm=right))
    return rows


def read_photon_plan(src: Source, beamlet_spacing_mm: Tuple[float, float] = (5.0, 5.0),
                     leaf_width_without_mlc_mm: float = 10.0) -> PhotonPlan:
    ds, path = _dataset(src)
    metersets = _beam_metersets(ds)
    beams: List[PhotonBeam] = []
    for b in getattr(ds, "BeamSequence", []):
        if str(getattr(b, "TreatmentDeliveryType", "TREATMENT")).upper() != "TREATMENT":
            continue
        number = int(b.BeamNumber)
        mu_total = metersets.get(number, 0.0)
        if mu_total <= 0.0:
            continue
        sad = float(getattr(b, "SourceAxisDistance", 1000.0) or 1000.0)
        bounds: Optional[List[float]] = None
        for dev in getattr(b, "BeamLimitingDeviceSequence", []):
            kind = str(dev.RTBeamLimitingDeviceType).upper()
            if kind == "MLCY":
                raise RTPlanError("MLCY (leaves travelling along y) is not supported")
            if kind == "MLCX":
                bounds = _as_list(dev.LeafPositionBoundaries)
        cps = list(getattr(b, "ControlPointSequence", []))
        if len(cps) < 2:
            raise RTPlanError(f"beam {number}: a plan needs at least two control points")
        final_cmw = float(getattr(b, "FinalCumulativeMetersetWeight", cps[-1].CumulativeMetersetWeight))
        if final_cmw <= 0.0:
            raise RTPlanError(f"beam {number}: FinalCumulativeMetersetWeight must be positive")

        state: Dict[str, Any] = {"gantry": 0.0, "couch": 0.0, "coll": 0.0, "iso": (0.0, 0.0, 0.0),
                                 "energy": None, "xj": None, "yj": None, "mlc": None}
        states: List[Tuple[float, Dict[str, Any]]] = []
        for cp in cps:
            if hasattr(cp, "GantryAngle"):
                state["gantry"] = float(cp.GantryAngle) % 360.0
            if hasattr(cp, "PatientSupportAngle"):
                state["couch"] = float(cp.PatientSupportAngle)
            if hasattr(cp, "BeamLimitingDeviceAngle"):
                state["coll"] = float(cp.BeamLimitingDeviceAngle)
            if hasattr(cp, "IsocenterPosition"):
                state["iso"] = tuple(float(v) for v in cp.IsocenterPosition)
            if hasattr(cp, "NominalBeamEnergy"):
                state["energy"] = float(cp.NominalBeamEnergy)
            for pos in getattr(cp, "BeamLimitingDevicePositionSequence", []):
                kind = str(pos.RTBeamLimitingDeviceType).upper()
                values = _as_list(pos.LeafJawPositions)
                if kind in ("X", "ASYMX"):
                    state["xj"] = values[:2]
                elif kind in ("Y", "ASYMY"):
                    state["yj"] = values[:2]
                elif kind == "MLCX":
                    state["mlc"] = values
            states.append((float(cp.CumulativeMetersetWeight), dict(state)))

        segments: List[Tuple[float, PhotonSegment]] = []     # (gantry for the interval, segment)
        for k in range(len(states) - 1):
            w0, s0 = states[k]
            w1, s1 = states[k + 1]
            mu = (w1 - w0) / final_cmw * mu_total
            if mu <= 0.0:
                continue
            static = math.isclose(s0["gantry"], s1["gantry"], abs_tol=1e-6)
            gantry = s0["gantry"] if static else _mid_angle(s0["gantry"], s1["gantry"])
            xj = s0["xj"] if static else _mean_list(s0["xj"], s1["xj"])
            yj = s0["yj"] if static else _mean_list(s0["yj"], s1["yj"])
            mlc = s0["mlc"] if static else _mean_list(s0["mlc"], s1["mlc"])
            if mlc is not None and bounds is not None:
                rows = _mlc_rows(bounds, mlc)
                if xj is None:
                    xj = [min(r.x_left_mm for r in rows), max(r.x_right_mm for r in rows)]
                if yj is None:
                    yj = [bounds[0], bounds[-1]]
            else:
                if xj is None or yj is None:
                    raise RTPlanError(f"beam {number}: control point {k} has neither jaws nor MLC positions")
                rows = open_field_mlc_rows((xj[0], xj[1]), (yj[0], yj[1]), leaf_width_without_mlc_mm)
            segments.append((gantry, PhotonSegment(
                control_point_index=k, mu=mu,
                x_jaw_mm=(float(min(xj)), float(max(xj))), y_jaw_mm=(float(min(yj)), float(max(yj))),
                collimator_deg=float(s0["coll"]), mlc_rows=rows,
                beamlet_spacing_mm=(float(beamlet_spacing_mm[0]), float(beamlet_spacing_mm[1])),
            )))
        if not segments:
            continue
        iso = states[0][1]["iso"]
        couch = _couch(states[0][1]["couch"])
        energy = states[0][1]["energy"]
        name = str(getattr(b, "BeamName", "") or number)
        gantries = {round(g, 6) for g, _ in segments}
        if len(gantries) == 1:
            beams.append(PhotonBeam(beam_id=name, gantry_deg=segments[0][0], couch_deg=couch, isocenter_mm=iso,
                                    sad_mm=sad, energy_mv=energy, segments=[s for _, s in segments]))
        else:   # an arc: one beam per control-point interval at its mid-angle
            for g, seg in segments:
                beams.append(PhotonBeam(beam_id=f"{name}:{seg.control_point_index}", gantry_deg=g, couch_deg=couch,
                                        isocenter_mm=iso, sad_mm=sad, energy_mv=energy, segments=[seg]))
    if not beams:
        raise RTPlanError("plan has no treatment beam with a positive meterset")
    return PhotonPlan(name=str(getattr(ds, "RTPlanLabel", "") or "RTPLAN"), beams=beams,
                      dicom=_provenance(ds, "RTPLAN", path))


# ---------------------------------------------------------------------------
# Ion (proton PBS)
# ---------------------------------------------------------------------------

def read_ion_plan(src: Source) -> ProtonPlan:
    ds, path = _dataset(src)
    metersets = _beam_metersets(ds)
    beams: List[ProtonBeam] = []
    for b in getattr(ds, "IonBeamSequence", []):
        if str(getattr(b, "TreatmentDeliveryType", "TREATMENT")).upper() != "TREATMENT":
            continue
        number = int(b.BeamNumber)
        mu_total = metersets.get(number, 0.0)
        if mu_total <= 0.0:
            continue
        scan_mode = str(getattr(b, "ScanMode", "MODULATED")).upper()
        if scan_mode != "MODULATED":
            raise RTPlanError(f"ion beam {number}: scan mode {scan_mode} is not pencil-beam scanning")
        rs_seq = getattr(b, "RangeShifterSequence", None)
        rs_id = str(rs_seq[0].RangeShifterID) if rs_seq else None
        cps = list(getattr(b, "IonControlPointSequence", []))
        if not cps:
            raise RTPlanError(f"ion beam {number}: no control points")
        final_cmw = float(getattr(b, "FinalCumulativeMetersetWeight", 0.0) or 0.0)
        if final_cmw <= 0.0:
            final_cmw = float(cps[-1].CumulativeMetersetWeight)
        if final_cmw <= 0.0:
            raise RTPlanError(f"ion beam {number}: FinalCumulativeMetersetWeight must be positive")

        state: Dict[str, Any] = {"gantry": 0.0, "couch": 0.0, "iso": (0.0, 0.0, 0.0), "energy": None, "rs": None}
        layers: List[ProtonLayer] = []
        for cp in cps:
            if hasattr(cp, "GantryAngle"):
                state["gantry"] = float(cp.GantryAngle) % 360.0
            if hasattr(cp, "PatientSupportAngle"):
                state["couch"] = float(cp.PatientSupportAngle)
            if hasattr(cp, "IsocenterPosition"):
                state["iso"] = tuple(float(v) for v in cp.IsocenterPosition)
            if hasattr(cp, "NominalBeamEnergy"):
                state["energy"] = float(cp.NominalBeamEnergy)
            rss = getattr(cp, "RangeShifterSettingsSequence", None)
            if rss:
                r = rss[0]
                wet = getattr(r, "RangeShifterWaterEquivalentThickness", None)
                state["rs"] = RangeShifterSetting(
                    setting=str(getattr(r, "RangeShifterSetting", "IN")),
                    isocenter_to_range_shifter_mm=float(getattr(r, "IsocenterToRangeShifterDistance", 0.0) or 0.0),
                    water_equivalent_thickness_mm=(None if wet is None else float(wet)),
                )
            weights = _as_list(getattr(cp, "ScanSpotMetersetWeights", None))
            if not weights or sum(weights) <= 0.0:
                continue
            xy = _as_list(getattr(cp, "ScanSpotPositionMap", None))
            if len(xy) != 2 * len(weights):
                raise RTPlanError(f"ion beam {number}: {len(weights)} spot weights but {len(xy) // 2} positions")
            if state["energy"] is None:
                raise RTPlanError(f"ion beam {number}: control point without NominalBeamEnergy")
            spots = [ProtonSpot(x_mm=xy[2 * i], y_mm=xy[2 * i + 1], mu=w / final_cmw * mu_total)
                     for i, w in enumerate(weights) if w > 0.0]
            layers.append(ProtonLayer(energy_mev=float(state["energy"]), spots=spots,
                                      range_shifter=(state["rs"] if rs_id is not None else None)))
        if not layers:
            continue
        beams.append(ProtonBeam(beam_id=str(number), name=str(getattr(b, "BeamName", "") or ""),
                                gantry_deg=state["gantry"] if len(cps) == 1 else float(getattr(cps[0], "GantryAngle", state["gantry"])) % 360.0,
                                couch_deg=_couch(float(getattr(cps[0], "PatientSupportAngle", state["couch"]))),
                                isocenter_mm=tuple(float(v) for v in getattr(cps[0], "IsocenterPosition", state["iso"])),
                                range_shifter_id=rs_id, layers=layers))
    if not beams:
        raise RTPlanError("ion plan has no treatment beam with a positive meterset")
    return ProtonPlan(name=str(getattr(ds, "RTPlanLabel", "") or "RTIONPLAN"), n_fractions=_n_fractions(ds),
                      beams=beams, dicom=_provenance(ds, "RTIONPLAN", path))


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def read_rtplan(src: Source, beamlet_spacing_mm: Tuple[float, float] = (5.0, 5.0)) -> Union[PhotonPlan, ProtonPlan]:
    """Read an RT Plan or RT Ion Plan into the matching radiarch model."""
    ds, _ = _dataset(src)
    sop = str(getattr(ds, "SOPClassUID", ""))
    if sop == SOP.RTIONPLAN or (sop not in PLAN_SOP_CLASSES and hasattr(ds, "IonBeamSequence")):
        return read_ion_plan(ds if isinstance(src, Dataset) else src)
    if sop == SOP.RTPLAN or hasattr(ds, "BeamSequence"):
        return read_photon_plan(ds if isinstance(src, Dataset) else src, beamlet_spacing_mm)
    raise RTPlanError(f"not an RT Plan or RT Ion Plan (SOP class {sop or 'missing'})")


__all__ = ["RTPlanError", "read_rtplan", "read_photon_plan", "read_ion_plan"]
