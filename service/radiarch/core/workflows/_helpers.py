"""Shared helpers for OpenTPS workflow modules.

Extracts repeated patterns (data loading, calibration, BDL, ROI lookup,
objective mapping) into reusable functions to eliminate cross-workflow
code duplication.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from loguru import logger

from ...config import get_settings
from ...models.plan import PlanDetail


class PlannerError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def setup_sim_dir(plan_id: str) -> str:
    """Create and return the simulation output directory for a plan."""
    settings = get_settings()
    sim_dir = os.path.abspath(os.path.join(settings.artifact_dir, "simulations", plan_id))
    os.makedirs(sim_dir, exist_ok=True)
    return sim_dir


def load_ct_and_patient(data_root: Optional[str] = None):
    """Load CT image and patient from the OpenTPS data root.

    Returns:
        (ct, patient, found_rt_structs) tuple
    Raises:
        PlannerError if no CT is found.
    """
    from opentps.core.io import dataLoader
    from opentps.core.data.images import CTImage
    from opentps.core.data._rtStruct import RTStruct

    settings = get_settings()
    root = data_root or settings.opentps_data_root
    data_list = dataLoader.readData(root)
    if not data_list:
        raise PlannerError("No data found in OpenTPS data root")

    ct = None
    patient = None
    found_rt_structs = []

    for item in data_list:
        if isinstance(item, CTImage):
            ct = item
            patient = item.patient
        elif isinstance(item, RTStruct):
            found_rt_structs.append(item)

    if not ct:
        raise PlannerError("No CT found in patient data")

    if not patient:
        from opentps.core.data import Patient
        patient = Patient(name="Unknown")

    # Link any orphan RTStructs to patient
    for rt in found_rt_structs:
        if rt not in patient.rtStructs:
            patient.appendPatientData(rt)

    return ct, patient, found_rt_structs


# ---------------------------------------------------------------------------
# Calibration & BDL
# ---------------------------------------------------------------------------

def setup_calibration():
    """Load the default MCsquare CT calibration.

    Returns:
        (calibration, mcsquare_path) tuple
    """
    import opentps.core.processing.doseCalculation.protons.MCsquare as MCsquareModule
    from opentps.core.data.CTCalibrations.MCsquareCalibration._mcsquareCTCalibration import MCsquareCTCalibration

    mcsquare_path = str(MCsquareModule.__path__[0])
    scanner_path = os.path.join(mcsquare_path, "Scanners", "UCL_Toshiba")
    calibration = MCsquareCTCalibration.fromFiles(
        huDensityFile=os.path.join(scanner_path, "HU_Density_Conversion.txt"),
        huMaterialFile=os.path.join(scanner_path, "HU_Material_Conversion.txt"),
        materialsPath=os.path.join(mcsquare_path, "Materials"),
    )
    return calibration, mcsquare_path


def load_bdl():
    """Load the default Beam Data Library (BDL).

    Returns:
        BDL object from mcsquareIO.readBDL
    """
    import opentps
    import opentps.core.processing.doseCalculation.protons.MCsquare as MCsquareModule
    from opentps.core.io import mcsquareIO

    base_path = os.path.dirname(opentps.__file__)
    bdl_path = os.path.join(
        base_path, "core", "processing", "doseCalculation",
        "protons", "MCsquare", "BDL", "BDL_default_DN_RangeShifter.txt",
    )
    if not os.path.exists(bdl_path):
        bdl_path = os.path.join(
            os.path.dirname(MCsquareModule.__file__),
            "BDL", "BDL_default_DN_RangeShifter.txt",
        )
    return mcsquareIO.readBDL(bdl_path)


# ---------------------------------------------------------------------------
# ROI / Objective helpers
# ---------------------------------------------------------------------------

TARGET_NAMES = {"ptv", "target", "gtv", "ctv", "targetvolume"}


def find_target_roi(patient, fallback_to_first: bool = False):
    """Find the target ROI from the patient's RTStructs.

    Checks contour names against TARGET_NAMES (case-insensitive).
    If ``fallback_to_first`` is True and no named target is found,
    returns the first available contour.
    """
    if not patient or not patient.rtStructs:
        return None

    for rt_struct in patient.rtStructs:
        for contour in rt_struct.contours:
            if contour.name.lower() in TARGET_NAMES:
                return contour

    if fallback_to_first:
        for rt_struct in patient.rtStructs:
            if rt_struct.contours:
                return rt_struct.contours[0]

    return None


def find_body_roi(patient):
    """Find the body/external contour for beamlet calculation."""
    if not patient or not patient.rtStructs:
        return None
    for rt_struct in patient.rtStructs:
        for contour in rt_struct.contours:
            if contour.name.lower() in {"body", "external"}:
                return contour
    return None


def build_gantry_angles(beam_count: int) -> list:
    """Generate evenly-spaced gantry angles for ``beam_count`` beams."""
    if beam_count > 1:
        return [i * (360.0 / beam_count) for i in range(beam_count)]
    return [0.0]


def build_objectives(plan: PlanDetail, patient, target_roi):
    """Map PlanDetail.objectives to an OpenTPS ObjectivesList.

    Falls back to a default DUniform on the target if no objectives
    are specified.
    """
    from opentps.core.data.plan import ObjectivesList
    import opentps.core.processing.planOptimization.objectives.dosimetricObjectives as doseObj

    objectives = ObjectivesList()

    if plan.objectives:
        for obj in plan.objectives:
            roi = next(
                (r for r in patient.rtStructs[0].contours if r.name == obj.structure_name),
                None,
            )
            if not roi:
                logger.warning("Objective ROI %s not found", obj.structure_name)
                continue

            obj_type = obj.objective_type
            if obj_type == "DMin":
                fid = doseObj.DMin(roi=roi, dose=obj.dose_gy, weight=obj.weight)
            elif obj_type == "DMax":
                fid = doseObj.DMax(roi=roi, dose=obj.dose_gy, weight=obj.weight)
            elif obj_type == "DUniform":
                fid = doseObj.DUniform(roi=roi, dose=obj.dose_gy, weight=obj.weight)
            elif obj_type == "DVHMin":
                fid = doseObj.DVHMin(
                    roi=roi, dose=obj.dose_gy,
                    volume=obj.volume_fraction * 100, weight=obj.weight,
                )
            elif obj_type == "DVHMax":
                fid = doseObj.DVHMax(
                    roi=roi, dose=obj.dose_gy,
                    volume=obj.volume_fraction * 100, weight=obj.weight,
                )
            else:
                continue
            objectives.addObjective(fid)
    elif target_roi:
        objectives.addObjective(
            doseObj.DUniform(roi=target_roi, dose=plan.prescription_gy, weight=100.0)
        )

    return objectives


# ---------------------------------------------------------------------------
# MC Calculator factory
# ---------------------------------------------------------------------------

def build_mc_calculator(ct, calibration, nb_primaries: float = 1e4):
    """Create and configure an MCsquare dose calculator."""
    from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import MCsquareDoseCalculator

    mc_calc = MCsquareDoseCalculator()
    mc_calc.nbPrimaries = nb_primaries
    mc_calc.ct = ct
    mc_calc.ctCalibration = calibration
    mc_calc.beamModel = load_bdl()
    return mc_calc


# ---------------------------------------------------------------------------
# DICOM export & DVH (moved from planner)
# ---------------------------------------------------------------------------

def export_rtdose(dose_image, ct, output_path: str):
    """Export a DoseImage as a DICOM RTDOSE file."""
    import pydicom
    from pydicom.dataset import FileDataset
    from pydicom.uid import ExplicitVRLittleEndian
    import pydicom.uid

    file_meta = pydicom.Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.2"
    file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(output_path, {}, file_meta=file_meta, preamble=b"\x00" * 128)

    ds.PatientName = getattr(ct, "patientName", "ANONYMOUS")
    ds.PatientID = getattr(ct, "patientID", "UNKNOWN")
    ds.StudyInstanceUID = getattr(ct, "studyInstanceUID", pydicom.uid.generate_uid())
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.Modality = "RTDOSE"
    ds.Manufacturer = "Radiarch/OpenTPS"
    ds.DoseUnits = "GY"
    ds.DoseType = "PHYSICAL"
    ds.DoseSummationType = "PLAN"

    dose_array = dose_image.imageArray
    ds.Rows = dose_array.shape[1]
    ds.Columns = dose_array.shape[2]
    ds.NumberOfFrames = dose_array.shape[0]
    ds.PixelSpacing = [float(dose_image.spacing[0]), float(dose_image.spacing[1])]
    ds.ImagePositionPatient = [
        float(dose_image.origin[0]),
        float(dose_image.origin[1]),
        float(dose_image.origin[2]),
    ]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.GridFrameOffsetVector = [float(i * dose_image.spacing[2]) for i in range(dose_array.shape[0])]

    dose_max = float(dose_array.max())
    if dose_max > 0:
        dose_grid_scaling = dose_max / (2**31 - 1)
        scaled = (dose_array / dose_grid_scaling).astype(np.uint32)
    else:
        dose_grid_scaling = 1.0
        scaled = np.zeros_like(dose_array, dtype=np.uint32)

    ds.DoseGridScaling = str(dose_grid_scaling)
    ds.BitsAllocated = 32
    ds.BitsStored = 32
    ds.HighBit = 31
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PixelData = scaled.tobytes()
    ds.save_as(output_path)
    logger.info("RTDOSE saved to %s", output_path)


def compute_dvh(dose_image, target_roi, ct) -> Dict[str, Any]:
    """Compute a cumulative DVH for the target ROI."""
    try:
        from opentps.core.data.images import ROIMask

        if isinstance(target_roi, ROIMask):
            mask = target_roi.imageArray.astype(bool)
        else:
            mask_obj = target_roi.getBinaryMask(ct.origin, ct.gridSize, ct.spacing)
            mask = mask_obj.imageArray.astype(bool)

        dose_arr = dose_image.imageArray
        if mask.shape != dose_arr.shape:
            logger.warning("DVH mask shape %s != dose shape %s — skipping", mask.shape, dose_arr.shape)
            return {}

        target_doses = dose_arr[mask]
        if target_doses.size == 0:
            return {}

        max_d = float(target_doses.max())
        n_bins = 100
        bin_edges = np.linspace(0, max_d, n_bins + 1)
        bin_centers = ((bin_edges[:-1] + bin_edges[1:]) / 2).tolist()
        total_voxels = target_doses.size

        volumes = [
            round(float(np.sum(target_doses >= edge)) / total_voxels * 100.0, 2)
            for edge in bin_edges[:-1]
        ]

        return {
            "roiName": getattr(target_roi, "name", "target"),
            "doseGy": [round(d, 4) for d in bin_centers],
            "volumePct": volumes,
            "minDoseGy": round(float(target_doses.min()), 4),
            "maxDoseGy": round(max_d, 4),
            "meanDoseGy": round(float(target_doses.mean()), 4),
        }
    except Exception as exc:
        logger.warning("DVH computation failed: %s", exc)
        return {}
