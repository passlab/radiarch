from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
from loguru import logger

from ..adapters import OrthancAdapterBase, build_orthanc_adapter
from ..models.plan import PlanDetail
from ..config import get_settings

# Ensure settings are loaded (and sys.path updated) before checking for OpenTPS
_ = get_settings()



def _default_adapter() -> OrthancAdapterBase:
    return build_orthanc_adapter()


class PlannerError(RuntimeError):
    pass


@dataclass
class PlanExecutionResult:
    artifact_bytes: bytes
    artifact_content_type: str
    qa_summary: Dict[str, Any]
    artifact_path: Optional[str] = None


class RadiarchPlanner:
    def __init__(self, adapter: Optional[OrthancAdapterBase] = None, force_synthetic: bool = False):
        self.adapter = adapter or _default_adapter()
        self._force_synthetic = force_synthetic or os.environ.get("RADIARCH_FORCE_SYNTHETIC", "").lower() in ("1", "true", "yes")

    def run(self, plan: PlanDetail) -> PlanExecutionResult:
        logger.info("Running planner for plan %s", plan.id)
        study = self.adapter.get_study(plan.study_instance_uid)
        if not study:
            raise PlannerError(f"Study {plan.study_instance_uid} not found in PACS")

        segmentation = None
        if plan.segmentation_uid:
            segmentation = self.adapter.get_segmentation(plan.segmentation_uid)

        if self._force_synthetic:
            logger.info("force_synthetic enabled — skipping OpenTPS")
            qa_summary = self._run_synthetic(plan, segmentation)
        else:
            # Check availability dynamically to ensure config/paths are loaded
            opentps_available = False
            try:
                import opentps
                opentps_available = True
            except ImportError:
                pass

            if opentps_available:
                qa_summary = self._run_opentps(plan, segmentation)
            else:
                logger.warning("OpenTPS not found; falling back to synthetic planner")
                qa_summary = self._run_synthetic(plan, segmentation)

        artifact_doc = {
            "planId": plan.id,
            "workflowId": plan.workflow_id,
            "studyInstanceUID": plan.study_instance_uid,
            "segmentationUID": plan.segmentation_uid,
            "prescriptionGy": plan.prescription_gy,
            "fractions": plan.fraction_count,
            "qa": qa_summary,
        }
        artifact_bytes = json.dumps(artifact_doc, indent=2).encode("utf-8")

        # Persist JSON summary to disk
        import os
        settings = get_settings()
        summary_dir = os.path.join(settings.artifact_dir, "summaries")
        os.makedirs(summary_dir, exist_ok=True)
        summary_path = os.path.join(summary_dir, f"{plan.id}.json")
        with open(summary_path, "wb") as f:
            f.write(artifact_bytes)

        return PlanExecutionResult(
            artifact_bytes=artifact_bytes,
            artifact_content_type="application/json",
            qa_summary=qa_summary,
            artifact_path=summary_path,
        )

    def _run_synthetic(self, plan: PlanDetail, segmentation: Optional[dict]) -> Dict[str, Any]:
        # Simulate dose coverage metrics using simple Gaussian profile
        beam_count = getattr(plan, 'beam_count', 1) or 1
        spot_count = random.randint(200, 400) * beam_count
        coverage = max(0.7, min(0.99, 0.8 + 0.05 * random.random()))
        hot_spot = max(1.00, 1.10 + 0.05 * random.random())
        dvh_dose = np.linspace(0, plan.prescription_gy * 1.2, 50)
        dvh_volume = np.exp(-((dvh_dose / plan.prescription_gy) ** 2) * 2) * 100

        # Generate per-beam gantry angles
        gantry_angles = [round(i * (360.0 / beam_count), 1) for i in range(beam_count)]

        return {
            "engine": "synthetic",
            "beamCount": beam_count,
            "gantryAngles": gantry_angles,
            "spotCount": spot_count,
            "targetCoverage": round(coverage, 3),
            "maxDoseRatio": round(hot_spot, 3),
            "dvh": {
                "dose": dvh_dose.tolist(),
                "volume": dvh_volume.tolist(),
            },
            "notes": "OpenTPS modules unavailable; generated synthetic QA",
        }

    def _run_opentps(self, plan: PlanDetail, segmentation: Optional[dict]) -> Dict[str, Any]:
        """
        Run the actual OpenTPS planning pipeline:
        1. Load patient data (CT)
        2. Create a ProtonPlanDesign
        3. Configure single beam (simple)
        4. Run MCsquare dose calculation
        5. Return metrics
        """
        logger.info("Initializing OpenTPS workflow for plan %s (Workflow: %s)", plan.id, plan.workflow_id)

        # Import OpenTPS modules here to avoid loading them at module level if not needed
        from opentps.core.io import dataLoader
        from opentps.core.data.plan import ProtonPlanDesign
        from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import MCsquareDoseCalculator
        from opentps.core.data.images import CTImage, DoseImage
        from opentps.core.utils.programSettings import ProgramSettings
        # from opentps.core.data.CTCalibrations.CTCalibration_Schneider2000 import CTCalibration_Schneider2000
        from opentps.core.data.CTCalibrations.MCsquareCalibration._mcsquareCTCalibration import MCsquareCTCalibration
        import opentps.core.processing.doseCalculation.protons.MCsquare as MCsquareModule
        from opentps.core.data.MCsquare._bdl import BDL

        # Configure OpenTPS settings
        ps = ProgramSettings()
        # Ensure simulation folder is in a writable location, e.g., artifact_dir/simulations
        settings = get_settings()
        import os
        # Prepare simulation folder
        sim_dir = os.path.join(settings.artifact_dir, "simulations", plan.id)
        sim_dir = os.path.abspath(sim_dir)
        os.makedirs(sim_dir, exist_ok=True)
        # ProgramSettings singleton doesn't allow setting simulationFolder directly
        # Hack: update the internal config dictionary
        ps._config["dir"]["simulationFolder"] = sim_dir

        # 1. Load data
        data_root = settings.opentps_data_root
        logger.info("Loading patient data from %s", data_root)
        
        # Use dataLoader to read all data in the directory
        data_list = dataLoader.readData(data_root)
        if not data_list:
            raise PlannerError("No data found in OpenTPS data root")
            
        patient = None
        ct = None
        
        # Find CT image and patient
        from opentps.core.data._rtStruct import RTStruct
        
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
            # Fallback
            from opentps.core.data import Patient
            patient = Patient(name="Unknown")
            
        # Ensure RTStructs are linked to patient
        if found_rt_structs:
            logger.info(f"Found {len(found_rt_structs)} RTStructs in data list")
            for rt in found_rt_structs:
                if rt not in patient.rtStructs:
                     logger.info(f"Linking RTStruct {rt.name} to patient")
                     patient.appendPatientData(rt)

        logger.info("Loaded patient: %s", patient.name)

        # 2. Design Plan
        logger.info("Configuring ProtonPlanDesign")
        
        # Default calibration
        # from opentps.core.data.CTCalibrations.CTCalibration_Schneider2000 import CTCalibration_Schneider2000
        plan_design = ProtonPlanDesign()
        if plan_design.calibration is None:
            # calibration = CTCalibration_Schneider2000()
            mcsquare_path = str(MCsquareModule.__path__[0])
            scanner_path = os.path.join(mcsquare_path, 'Scanners', 'UCL_Toshiba')
            calibration = MCsquareCTCalibration.fromFiles(
                huDensityFile=os.path.join(scanner_path, 'HU_Density_Conversion.txt'),
                huMaterialFile=os.path.join(scanner_path, 'HU_Material_Conversion.txt'),
                materialsPath=os.path.join(mcsquare_path, 'Materials')
            )
            plan_design.calibration = calibration
        plan_design.ct = ct
        plan_design.patient = patient
        
        # Simple 1-beam setup
        plan_design.gantryAngles = [0.0]
        plan_design.couchAngles = [0.0]
        
        # Find target ROI
        target_roi = None
        for rt_struct in patient.rtStructs:
            for roi in rt_struct.contours:
                if roi.name.lower() in ["gtv", "ptv", "ctv", "target", "targetvolume"]:
                    target_roi = roi
                    break
            if target_roi:
                break
        
        if not target_roi:
             # Fallback: use the first available ROI if any
            for rt_struct in patient.rtStructs:
                if rt_struct.contours:
                    target_roi = rt_struct.contours[0]
                    break
        
        if target_roi:
           logger.info("Using ROI %s as target", target_roi.name)
           # plan_design.targetMask = target_roi
           plan_design.defineTargetMaskAndPrescription(target_roi, 2000.0)
        else:
           logger.warning("No ROI found at all. Plan building might fail.")

        # Build the plan (Geometry, Spots, Layers)
        logger.info("Building ProtonPlan...")
        proton_plan = plan_design.buildPlan()

        # 3. Calculate Dose
        logger.info("Running MCsquare dose calculation...")
        mc_calc = MCsquareDoseCalculator()
        mc_calc.nbPrimaries = 1e4 
        mc_calc.ct = ct
        mc_calc.ctCalibration = calibration
        
        # Load default beam model
        from opentps.core.io import mcsquareIO
        import opentps.core.processing.doseCalculation.protons.MCsquare as mc2_module
        
        # Construct path to default BDL
        # It seems BDL folder is inside MCsquare module
        bdl_path = os.path.join(os.path.dirname(mc2_module.__file__), "BDL", "BDL_default_DN_RangeShifter.txt")
        if not os.path.exists(bdl_path):
             logger.warning("Default BDL not found at %s, trying to find it deeply", bdl_path)
             # Fallback search if path structure is different
             import opentps
             base_path = os.path.dirname(opentps.__file__)
             bdl_path = os.path.join(base_path, "core", "processing", "doseCalculation", "protons", "MCsquare", "BDL", "BDL_default_DN_RangeShifter.txt")

        logger.info("Loading BDL from %s", bdl_path)
        bdl = mcsquareIO.readBDL(bdl_path)
        mc_calc.beamModel = bdl

        # Use explicit computeDose method
        # computeDose(self, ct: CTImage, plan: ProtonPlan, roi: Optional[Sequence[ROIContour]] = None)
        dose_image = mc_calc.computeDose(ct, proton_plan)
        
        logger.info("Dose computation complete. Max dose: %s", dose_image.imageArray.max())

        # 4. Export RTDOSE DICOM
        logger.info("Exporting RTDOSE DICOM...")
        rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
        self._export_rtdose(dose_image, ct, rtdose_path)
        
        # 5. Compute DVH
        dvh_data = self._compute_dvh(dose_image, target_roi, ct) if target_roi else {}
        
        max_dose = float(dose_image.imageArray.max())
        mean_dose = float(dose_image.imageArray.mean())
        
        return {
            "engine": "opentps",
            "patientName": patient.name,
            "beamCount": len(plan_design.gantryAngles),
            "maxDose": max_dose,
            "meanDose": mean_dose,
            "simDir": sim_dir,
            "rtdosePath": rtdose_path,
            "dvh": dvh_data,
            "notes": "Success: OpenTPS MCsquare execution"
        }

    @staticmethod
    def _export_rtdose(dose_image, ct, output_path: str):
        """Export a DoseImage as a DICOM RTDOSE file."""
        import pydicom
        from pydicom.dataset import Dataset, FileDataset
        from pydicom.uid import ExplicitVRLittleEndian
        import pydicom.uid
        import tempfile

        file_meta = pydicom.Dataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.2"  # RT Dose Storage
        file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = FileDataset(output_path, {}, file_meta=file_meta, preamble=b"\x00" * 128)

        # Patient / Study level (copy from CT if available)
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

        # Grid geometry
        dose_array = dose_image.imageArray  # numpy 3D array (z, y, x) or similar
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

        # Frame offsets (z positions)
        frame_offsets = [float(i * dose_image.spacing[2]) for i in range(dose_array.shape[0])]
        ds.GridFrameOffsetVector = frame_offsets

        # Pixel data: scale to uint32 with DoseGridScaling
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

    @staticmethod
    def _compute_dvh(dose_image, target_roi, ct) -> Dict[str, Any]:
        """Compute a cumulative DVH for the target ROI."""
        try:
            from opentps.core.data.images import ROIMask

            # Get the target mask as a binary array
            if isinstance(target_roi, ROIMask):
                mask = target_roi.imageArray.astype(bool)
            else:
                # ROIContour → need to rasterise on CT grid
                mask_obj = target_roi.getBinaryMask(ct.origin, ct.gridSize, ct.spacing)
                mask = mask_obj.imageArray.astype(bool)

            dose_arr = dose_image.imageArray
            # Ensure shapes match (they should share the CT grid)
            if mask.shape != dose_arr.shape:
                logger.warning(
                    "DVH mask shape %s != dose shape %s — skipping DVH",
                    mask.shape, dose_arr.shape,
                )
                return {}

            target_doses = dose_arr[mask]
            if target_doses.size == 0:
                return {}

            # Cumulative DVH: 100 bins from 0 to max_dose
            max_d = float(target_doses.max())
            n_bins = 100
            bin_edges = np.linspace(0, max_d, n_bins + 1)
            bin_centers = ((bin_edges[:-1] + bin_edges[1:]) / 2).tolist()
            total_voxels = target_doses.size

            volumes = []
            for edge in bin_edges[:-1]:
                frac = float(np.sum(target_doses >= edge)) / total_voxels * 100.0
                volumes.append(round(frac, 2))

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

