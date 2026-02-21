"""
Tests for the vendored OpenTPS core library.

Uses SimpleFantomWithStruct test data (200 CT slices + RTStruct) to test
data loading, plan construction, MCsquare dose calculation, and DVH computation.

Requires: vendored opentps.core at service/opentps/core/
Test data: tests/opentps/core/opentps-testData/SimpleFantomWithStruct/
"""

import os
import pytest
import numpy as np


# ---------------------------------------------------------------------------
# 1. Data loading
# ---------------------------------------------------------------------------

class TestDataLoading:
    """Test DICOM data loading through the vendored OpenTPS I/O layer."""

    def test_load_ct_image(self, simple_fantom_dir):
        """Load CT from DICOM directory; verify shape, spacing, HU range."""
        from opentps.core.io.dataLoader import readData
        from opentps.core.data.images._ctImage import CTImage

        data = readData(simple_fantom_dir)
        ct_images = [d for d in data if isinstance(d, CTImage)]

        assert len(ct_images) >= 1, "No CT image loaded from SimpleFantomWithStruct"
        ct = ct_images[0]

        # Verify 3D volume
        assert ct.imageArray is not None, "CT imageArray is None"
        assert ct.imageArray.ndim == 3, f"Expected 3D array, got {ct.imageArray.ndim}D"
        assert all(s > 0 for s in ct.imageArray.shape), "CT dimensions must be positive"

        # Spacing should be positive
        assert ct.spacing is not None, "CT spacing is None"
        assert all(s > 0 for s in ct.spacing), f"CT spacing must be positive: {ct.spacing}"

        # HU range sanity check
        min_hu = ct.imageArray.min()
        max_hu = ct.imageArray.max()
        assert min_hu >= -1100, f"HU min out of range: {min_hu}"
        assert max_hu > min_hu, "Max HU should be greater than min HU"
        print(f"CT shape={ct.imageArray.shape}, spacing={ct.spacing}, HU=[{min_hu}, {max_hu}]")

    def test_load_rtstruct(self, simple_fantom_dir):
        """Load RTStruct and verify ROI names are extracted."""
        from opentps.core.io.dataLoader import readData
        from opentps.core.data._rtStruct import RTStruct

        data = readData(simple_fantom_dir)
        structs = [d for d in data if isinstance(d, RTStruct)]

        assert len(structs) >= 1, "No RTStruct loaded from SimpleFantomWithStruct"
        struct = structs[0]

        # Verify ROIs exist
        assert hasattr(struct, 'ROIs') or hasattr(struct, 'contours'), \
            "RTStruct has no ROIs/contours attribute"

        rois = struct.ROIs if hasattr(struct, 'ROIs') else struct.contours
        assert len(rois) > 0, "RTStruct has no ROI contours"

        # Print ROI names for debugging
        roi_names = [r.ROIName if hasattr(r, 'ROIName') else str(r) for r in rois]
        print(f"Loaded {len(rois)} ROIs: {roi_names}")

    def test_readdata_returns_multiple_types(self, simple_fantom_dir):
        """Verify readData returns both CT and struct objects."""
        from opentps.core.io.dataLoader import readData

        data = readData(simple_fantom_dir)
        assert len(data) >= 2, f"Expected at least CT + RTStruct, got {len(data)} objects"

        type_names = [type(d).__name__ for d in data]
        print(f"Loaded types: {type_names}")


# ---------------------------------------------------------------------------
# 2. Plan design construction
# ---------------------------------------------------------------------------

class TestPlanDesign:
    """Test treatment plan construction using OpenTPS API."""

    def test_proton_plan_design_construction(self, simple_fantom_dir):
        """Build a ProtonPlanDesign with gantry angles, verify beam config."""
        from opentps.core.io.dataLoader import readData
        from opentps.core.data.images._ctImage import CTImage
        from opentps.core.data.plan._protonPlanDesign import ProtonPlanDesign

        data = readData(simple_fantom_dir)
        ct = next(d for d in data if isinstance(d, CTImage))

        # Create plan design
        plan_design = ProtonPlanDesign()
        plan_design.ct = ct
        plan_design.gantryAngles = [0.0, 90.0]
        plan_design.couchAngle = 0.0
        plan_design.targetMargin = 5.0  # mm
        plan_design.proximalMargin = 5.0
        plan_design.distalMargin = 5.0

        assert plan_design.ct is not None
        assert len(plan_design.gantryAngles) == 2
        assert plan_design.gantryAngles[0] == 0.0
        assert plan_design.gantryAngles[1] == 90.0
        print(f"ProtonPlanDesign: gantry={plan_design.gantryAngles}, "
              f"target_margin={plan_design.targetMargin}mm")


# ---------------------------------------------------------------------------
# 3. MCsquare dose calculation (slow — requires binary)
# ---------------------------------------------------------------------------

class TestMCsquareDoseCalculation:
    """Test MCsquare dose calculation through the vendored OpenTPS wrapper."""

    @pytest.mark.slow
    def test_mcsquare_dose_calculator_setup(self):
        """Configure MCsquareDoseCalculator and verify settings."""
        from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import (
            MCsquareDoseCalculator,
        )

        calc = MCsquareDoseCalculator()
        calc.nbPrimaries = 1e4
        calc.statUncertainty = 0.0  # disable uncertainty stopping

        assert calc.nbPrimaries == 1e4
        assert calc.statUncertainty == 0.0
        print("MCsquareDoseCalculator configured successfully")

    @pytest.mark.slow
    def test_dose_computation_basic(self, simple_fantom_dir):
        """Run MCsquare dose calc with low primaries; verify dose is non-zero.

        This test takes ~10-30 seconds depending on hardware.
        """
        from opentps.core.io.dataLoader import readData
        from opentps.core.data.images._ctImage import CTImage
        from opentps.core.data._rtStruct import RTStruct
        from opentps.core.data.plan._protonPlanDesign import ProtonPlanDesign
        from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import (
            MCsquareDoseCalculator,
        )

        # Load data
        data = readData(simple_fantom_dir)
        ct = next(d for d in data if isinstance(d, CTImage))
        structs = [d for d in data if isinstance(d, RTStruct)]
        assert len(structs) >= 1, "Need RTStruct for dose calculation"

        struct = structs[0]
        rois = struct.ROIs if hasattr(struct, 'ROIs') else struct.contours

        # Find a target-like ROI
        target_roi = None
        for roi in rois:
            name = roi.ROIName if hasattr(roi, 'ROIName') else ""
            if "ptv" in name.lower() or "target" in name.lower() or "gtv" in name.lower():
                target_roi = roi
                break
        if target_roi is None and len(rois) > 0:
            target_roi = rois[0]  # fallback to first ROI

        assert target_roi is not None, "No ROI found in RTStruct"

        # Create plan design
        plan_design = ProtonPlanDesign()
        plan_design.ct = ct
        plan_design.gantryAngles = [0.0]
        plan_design.couchAngles = [0.0]
        plan_design.targetMargin = 5.0
        plan_design.proximalMargin = 5.0
        plan_design.distalMargin = 5.0

        # Use defineTargetMaskAndPrescription to properly create the binary
        # target mask from the ROIContour — buildPlan() needs targetMask,
        # not targetStructure.
        plan_design.defineTargetMaskAndPrescription(target_roi, 2.0)

        # Set up calibration and BDL BEFORE buildPlan() — initializeBeams()
        # calls PlanInitializer.placeSpots() which needs calibration for
        # RSPImage.fromCT() to convert HU to RSP.
        import opentps.core.processing.doseCalculation.protons.MCsquare as MCsquareModule
        from opentps.core.data.CTCalibrations.MCsquareCalibration._mcsquareCTCalibration import MCsquareCTCalibration
        from opentps.core.io import mcsquareIO

        mcsquare_path = str(MCsquareModule.__path__[0])
        scanner_path = os.path.join(mcsquare_path, "Scanners", "UCL_Toshiba")
        calibration = MCsquareCTCalibration.fromFiles(
            huDensityFile=os.path.join(scanner_path, "HU_Density_Conversion.txt"),
            huMaterialFile=os.path.join(scanner_path, "HU_Material_Conversion.txt"),
            materialsPath=os.path.join(mcsquare_path, "Materials"),
        )
        bdl_path = os.path.join(mcsquare_path, "BDL", "BDL_default_DN_RangeShifter.txt")
        bdl = mcsquareIO.readBDL(bdl_path)

        plan_design.calibration = calibration

        # Build spot-scanning plan from design
        plan = plan_design.buildPlan()
        assert plan is not None, "Failed to build proton plan"

        # Configure MCsquare dose calculator
        calc = MCsquareDoseCalculator()
        calc.nbPrimaries = 1e4  # low for speed
        calc.statUncertainty = 0.0
        calc.ctCalibration = calibration
        calc.beamModel = bdl

        # Compute dose
        dose = calc.computeDose(ct, plan)
        assert dose is not None, "Dose computation returned None"
        assert dose.imageArray is not None, "Dose imageArray is None"
        assert dose.imageArray.max() > 0, "Dose is all zeros — MCsquare may have failed"

        print(f"Dose shape={dose.imageArray.shape}, "
              f"max={dose.imageArray.max():.4f} Gy, "
              f"mean={dose.imageArray.mean():.6f} Gy")


# ---------------------------------------------------------------------------
# 4. DVH computation
# ---------------------------------------------------------------------------

class TestDVH:
    """Test Dose-Volume Histogram computation."""

    @pytest.mark.slow
    def test_dvh_from_dose(self, simple_fantom_dir):
        """Compute DVH from dose + contour; verify dose stats are positive.

        Depends on successful dose calculation.
        """
        from opentps.core.io.dataLoader import readData
        from opentps.core.data.images._ctImage import CTImage
        from opentps.core.data._rtStruct import RTStruct
        from opentps.core.data._dvh import DVH
        from opentps.core.data.plan._protonPlanDesign import ProtonPlanDesign
        from opentps.core.processing.doseCalculation.protons.mcsquareDoseCalculator import (
            MCsquareDoseCalculator,
        )

        # Load data
        data = readData(simple_fantom_dir)
        ct = next(d for d in data if isinstance(d, CTImage))
        struct = next(d for d in data if isinstance(d, RTStruct))
        rois = struct.ROIs if hasattr(struct, 'ROIs') else struct.contours
        target_roi = rois[0]

        # Build plan and compute dose
        plan_design = ProtonPlanDesign()
        plan_design.ct = ct
        plan_design.gantryAngles = [0.0]
        plan_design.couchAngles = [0.0]
        plan_design.targetMargin = 5.0
        plan_design.proximalMargin = 5.0
        plan_design.distalMargin = 5.0

        # Properly create target mask from ROIContour
        plan_design.defineTargetMaskAndPrescription(target_roi, 2.0)

        # Set up calibration and BDL BEFORE buildPlan()
        import opentps.core.processing.doseCalculation.protons.MCsquare as MCsquareModule
        from opentps.core.data.CTCalibrations.MCsquareCalibration._mcsquareCTCalibration import MCsquareCTCalibration
        from opentps.core.io import mcsquareIO

        mcsquare_path = str(MCsquareModule.__path__[0])
        scanner_path = os.path.join(mcsquare_path, "Scanners", "UCL_Toshiba")
        calibration = MCsquareCTCalibration.fromFiles(
            huDensityFile=os.path.join(scanner_path, "HU_Density_Conversion.txt"),
            huMaterialFile=os.path.join(scanner_path, "HU_Material_Conversion.txt"),
            materialsPath=os.path.join(mcsquare_path, "Materials"),
        )
        bdl_path = os.path.join(mcsquare_path, "BDL", "BDL_default_DN_RangeShifter.txt")
        bdl = mcsquareIO.readBDL(bdl_path)

        plan_design.calibration = calibration

        plan = plan_design.buildPlan()
        calc = MCsquareDoseCalculator()
        calc.nbPrimaries = 1e4
        calc.statUncertainty = 0.0
        calc.ctCalibration = calibration
        calc.beamModel = bdl
        dose = calc.computeDose(ct, plan)

        # Compute DVH (DVH signature: roiMask first, dose second)
        dvh = DVH(target_roi, dose)

        assert dvh is not None
        assert hasattr(dvh, 'D95') or hasattr(dvh, 'meanDose'), \
            "DVH object missing expected dose metrics"

        # Check basic metrics
        if hasattr(dvh, 'D95'):
            assert dvh.D95 >= 0, f"D95 should be non-negative, got {dvh.D95}"
            print(f"DVH D95={dvh.D95:.4f} Gy")
        if hasattr(dvh, 'meanDose'):
            assert dvh.meanDose >= 0, f"meanDose should be non-negative"
            print(f"DVH meanDose={dvh.meanDose:.4f} Gy")
        if hasattr(dvh, 'D5'):
            print(f"DVH D5={dvh.D5:.4f} Gy")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
