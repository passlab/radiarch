"""
Tests for the MCsquare python_interface (Process/ modules).

Uses sample DICOM data in MCsquare-python_interface/data/ to test
patient data loading, contour extraction, MCsquare simulation,
DVH, DICE, and WET/SPR computation.

Test data: tests/opentps/core/MCsquare-python_interface/data/
"""

import os
import sys
import pytest
import numpy as np


# ---------------------------------------------------------------------------
# 1. Patient data loading
# ---------------------------------------------------------------------------

class TestPatientDataLoading:
    """Test DICOM loading through the MCsquare Process/ modules."""

    def test_patient_data_loading(self, mcsquare_sample_data_dir):
        """Load DICOM using PatientList; verify CT, Plan, RTStruct, RTDose loaded."""
        from Process.PatientData import PatientList

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)

        assert len(patients.list) >= 1, "No patient data loaded"

        patients.list[0].import_patient_data()
        patient = patients.list[0]

        assert len(patient.CTimages) >= 1, "No CT images loaded"
        assert len(patient.Plans) >= 1, "No plans loaded"
        assert len(patient.RTstructs) >= 1, "No RTStruct loaded"
        assert len(patient.RTdoses) >= 1, "No RTDose loaded"

        print(f"Loaded: {len(patient.CTimages)} CT, {len(patient.Plans)} Plan, "
              f"{len(patient.RTstructs)} RTStruct, {len(patient.RTdoses)} RTDose")

    def test_ct_image_properties(self, mcsquare_sample_data_dir):
        """Verify CT image has expected array shape and pixel data."""
        from Process.PatientData import PatientList

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        ct = patients.list[0].CTimages[0]
        assert ct.Image is not None, "CT Image is None"
        assert ct.Image.ndim == 3, f"Expected 3D CT, got {ct.Image.ndim}D"
        assert all(s > 0 for s in ct.Image.shape), "CT dimensions must be positive"

        print(f"CT shape={ct.Image.shape}, dtype={ct.Image.dtype}")


# ---------------------------------------------------------------------------
# 2. Contour extraction
# ---------------------------------------------------------------------------

class TestContourExtraction:
    """Test ROI contour finding and mask generation."""

    def test_find_ptv_contour(self, mcsquare_sample_data_dir):
        """Find PTV contour via find_contour(); verify mask shape."""
        from Process.PatientData import PatientList

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        patient_id, struct_id, contour_id = patients.find_contour('PTV')
        ptv = patients.list[patient_id].RTstructs[struct_id].Contours[contour_id]

        assert ptv.ROIName.upper() == 'PTV' or 'PTV' in ptv.ROIName.upper()
        assert ptv.Mask is not None, "PTV mask is None"
        assert ptv.Mask.ndim == 3, f"Expected 3D mask, got {ptv.Mask.ndim}D"
        assert ptv.Mask.sum() > 0, "PTV mask is empty (all zeros)"

        print(f"PTV '{ptv.ROIName}': mask shape={ptv.Mask.shape}, "
              f"voxels={ptv.Mask.sum()}")

    def test_find_rectum_contour(self, mcsquare_sample_data_dir):
        """Find Rectum contour; verify it exists and has a non-empty mask."""
        from Process.PatientData import PatientList

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        patient_id, struct_id, contour_id = patients.find_contour('Rectum')
        rectum = patients.list[patient_id].RTstructs[struct_id].Contours[contour_id]

        assert rectum.Mask is not None
        assert rectum.Mask.sum() > 0, "Rectum mask is empty"
        print(f"Rectum '{rectum.ROIName}': voxels={rectum.Mask.sum()}")

    def test_list_roi_names(self, mcsquare_sample_data_dir):
        """Print all ROI names from the RTStruct."""
        from Process.PatientData import PatientList

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        rtstruct = patients.list[0].RTstructs[0]
        roi_names = [c.ROIName for c in rtstruct.Contours]
        assert len(roi_names) > 0, "No ROI names found"
        print(f"ROI names: {roi_names}")


# ---------------------------------------------------------------------------
# 3. DICE similarity coefficient
# ---------------------------------------------------------------------------

class TestDICE:
    """Test DICE coefficient computation between contours."""

    def test_dice_coefficient(self, mcsquare_sample_data_dir):
        """Compute DICE between PTV and Prostate; verify DICE in (0, 1]."""
        from Process.PatientData import PatientList
        from scipy.spatial import distance

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        pid, sid, cid = patients.find_contour('PTV')
        ptv = patients.list[pid].RTstructs[sid].Contours[cid]

        pid, sid, cid = patients.find_contour('Prostate')
        prostate = patients.list[pid].RTstructs[sid].Contours[cid]

        dice = 1.0 - distance.dice(ptv.Mask.flatten(), prostate.Mask.flatten())

        assert 0 < dice <= 1.0, f"DICE should be in (0, 1], got {dice}"
        print(f"DICE({ptv.ROIName}, {prostate.ROIName}) = {dice:.4f}")


# ---------------------------------------------------------------------------
# 4. DVH computation
# ---------------------------------------------------------------------------

class TestDVHComputation:
    """Test Dose-Volume Histogram computation."""

    def test_dvh_metrics(self, mcsquare_sample_data_dir):
        """Compute DVH for PTV; verify D95, D5, Dmean are positive."""
        from Process.PatientData import PatientList
        from Process.DVH import DVH

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        dose = patients.list[0].RTdoses[0]
        pid, sid, cid = patients.find_contour('PTV')
        ptv = patients.list[pid].RTstructs[sid].Contours[cid]

        dvh = DVH(dose, ptv)

        assert dvh.D95 >= 0, f"D95 should be >= 0, got {dvh.D95}"
        assert dvh.D5 >= 0, f"D5 should be >= 0, got {dvh.D5}"
        assert dvh.Dmean >= 0, f"Dmean should be >= 0, got {dvh.Dmean}"
        assert dvh.D5 >= dvh.D95, f"D5 should be >= D95"

        print(f"DVH PTV: D95={dvh.D95:.2f} Gy, D5={dvh.D5:.2f} Gy, "
              f"Dmean={dvh.Dmean:.2f} Gy")

    def test_dvh_oar(self, mcsquare_sample_data_dir):
        """Compute DVH for Rectum (OAR); verify Dmean is reasonable."""
        from Process.PatientData import PatientList
        from Process.DVH import DVH

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        dose = patients.list[0].RTdoses[0]
        pid, sid, cid = patients.find_contour('Rectum')
        rectum = patients.list[pid].RTstructs[sid].Contours[cid]

        dvh = DVH(dose, rectum)

        assert dvh.Dmean >= 0, f"Rectum Dmean should be >= 0"
        print(f"DVH Rectum: Dmean={dvh.Dmean:.2f} Gy, D95={dvh.D95:.2f} Gy")


# ---------------------------------------------------------------------------
# 5. MCsquare simulation (slow — requires binary)
# ---------------------------------------------------------------------------

class TestMCsquareSimulation:
    """Test MCsquare dose calculation through the python_interface."""

    @pytest.mark.slow
    def test_mcsquare_simulation(self, mcsquare_sample_data_dir, mcsquare_interface_dir, tmp_path):
        """Run MCsquare simulation; verify dose output exists.

        This test takes ~30-60 seconds depending on hardware.
        Must run from MCsquare-python_interface directory since several
        Process modules use hardcoded relative paths (e.g. MCsquare/BDL).
        """
        # chdir so that hardcoded relative paths resolve correctly
        saved_cwd = os.getcwd()
        try:
            os.chdir(mcsquare_interface_dir)

            from Process.PatientData import PatientList
            from Process.MCsquare import MCsquare

            patients = PatientList()
            patients.list_dicom_files(mcsquare_sample_data_dir, 1)
            patients.list[0].import_patient_data()

            ct = patients.list[0].CTimages[0]
            plan = patients.list[0].Plans[0]

            # Configure MCsquare — use the binaries from the core folder,
            # not the python_interface test folder (which only has the shell wrapper)
            import opentps.core.processing.doseCalculation.protons.MCsquare as MCsquareModule
            core_mcsquare_path = str(MCsquareModule.__path__[0])

            mc2 = MCsquare()
            mc2.Path_MCsquareLib = core_mcsquare_path
            mc2.WorkDir = str(tmp_path)
            mc2.NumProtons = 1e5  # low for speed
            mc2.MaxUncertainty = 5.0  # allow high uncertainty for speed
            mc2.dose2water = True
            # Update BDL and Scanner paths (they resolve ./MCsquare at construction time)
            mc2.BDL.Path_MCsquareLib = core_mcsquare_path
            mc2.BDL.BDL_folder = os.path.join(core_mcsquare_path, "BDL")
            mc2.BDL.selected_BDL = "BDL_default_DN_RangeShifter"
            mc2.Scanner.Path_MCsquareLib = core_mcsquare_path
            mc2.Scanner.Scanner_folder = os.path.join(core_mcsquare_path, "Scanners")
            mc2.Scanner.selected_Scanner = "UCL_Toshiba"

            # Run simulation
            mhd_dose = mc2.MCsquare_simulation(ct, plan)

            assert mhd_dose is not None, "MCsquare simulation returned None"
            # MCsquare writes dose output to WorkDir/Outputs/
            outputs_dir = os.path.join(mc2.WorkDir, "Outputs")
            assert os.path.exists(os.path.join(outputs_dir, "Dose.mhd")), \
                "Dose MHD file not found in output directory"

            print(f"MCsquare simulation complete. Dose output in {mc2.WorkDir}")
        finally:
            os.chdir(saved_cwd)


# ---------------------------------------------------------------------------
# 6. WET / SPR computation
# ---------------------------------------------------------------------------

class TestSPRandWET:
    """Test stopping power ratio and water-equivalent thickness computation."""

    def test_spr_conversion(self, mcsquare_sample_data_dir, mcsquare_interface_dir):
        """Convert CT to SPR; verify dimensions and SPR range.

        Must run from MCsquare-python_interface directory since SPRimage
        hardcodes relative path './MCsquare' for scanner calibration.
        """
        import os
        from Process.PatientData import PatientList

        patients = PatientList()
        patients.list_dicom_files(mcsquare_sample_data_dir, 1)
        patients.list[0].import_patient_data()

        ct = patients.list[0].CTimages[0]

        # SPRimage expects ./MCsquare/ relative to cwd
        saved_cwd = os.getcwd()
        try:
            os.chdir(mcsquare_interface_dir)
            from Process.SPRimage import SPRimage
            spr = SPRimage()
            spr.convert_CT_to_SPR(ct, "default")
        finally:
            os.chdir(saved_cwd)

        assert spr.Image is not None, "SPR image is None"
        assert spr.Image.shape == ct.Image.shape, \
            f"SPR shape {spr.Image.shape} != CT shape {ct.Image.shape}"
        assert spr.Image.min() >= 0, f"SPR should be non-negative, got min={spr.Image.min()}"
        assert spr.Image.max() > 0, "SPR is all zeros"

        print(f"SPR shape={spr.Image.shape}, range=[{spr.Image.min():.4f}, {spr.Image.max():.4f}]")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
