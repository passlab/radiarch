"""RT Plan / RT Ion Plan / RT Dose / Registration readers (roadmap R2)."""

from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pydicom
import pytest

from radiarch.dicom import read_registration, read_rtdose, read_rtplan, resample_dose_to_grid
from radiarch.dicom.rtplan import RTPlanError, read_ion_plan, read_photon_plan
from radiarch.models.photon_plan import PhotonPlan
from radiarch.models.proton_plan import ProtonPlan
import dicom_fixtures as F

BOUNDS = [-20.0, -10.0, 0.0, 10.0, 20.0]        # 4 leaf pairs along y


def _static_plan(**kw):
    cps = [
        {"cmw": 0.0, "gantry": 30.0, "couch": 350.0, "coll": 5.0, "iso": [1.0, 2.0, 3.0], "energy": 6.0,
         "xj": [-30.0, 30.0], "yj": [-20.0, 20.0], "mlc": [-25, -15, -15, -25, 25, 15, 15, 25]},
        {"cmw": 1.0},
    ]
    return F.photon_rtplan([{"number": 1, "name": "AP", "cps": cps}], {1: 100.0}, bounds=BOUNDS, **kw)


# ---------------------------------------------------------------------------
# Photon plans
# ---------------------------------------------------------------------------

class TestPhotonPlan:
    def test_static_beam_one_segment(self):
        plan = read_photon_plan(_static_plan())
        assert isinstance(plan, PhotonPlan) and len(plan.beams) == 1
        b = plan.beams[0]
        assert b.beam_id == "AP" and b.gantry_deg == 30.0 and b.couch_deg == -10.0
        assert b.isocenter_mm == (1.0, 2.0, 3.0) and b.energy_mv == 6.0 and b.sad_mm == 1000.0
        assert len(b.segments) == 1
        s = b.segments[0]
        assert s.mu == pytest.approx(100.0) and s.collimator_deg == 5.0
        assert s.x_jaw_mm == (-30.0, 30.0) and s.y_jaw_mm == (-20.0, 20.0)
        assert [(r.y_min_mm, r.y_max_mm, r.x_left_mm, r.x_right_mm) for r in s.mlc_rows] == [
            (-20.0, -10.0, -25.0, 25.0), (-10.0, 0.0, -15.0, 15.0), (0.0, 10.0, -15.0, 15.0), (10.0, 20.0, -25.0, 25.0)]
        assert plan.dicom is not None and plan.dicom.sop_class == "RTPLAN" and plan.dicom.frame_of_reference_uid.endswith(".1")
        assert plan.dicom.structure_set_uid.endswith(".77") and plan.dicom.plan_label == "TestPlan"
        assert plan.n_beamlets > 0 and plan.beamlet_mu().shape == (plan.n_beamlets,)

    def test_step_and_shoot_segments_take_the_start_aperture(self):
        cps = [
            {"cmw": 0.0, "gantry": 0.0, "iso": [0, 0, 0], "xj": [-10, 10], "yj": [-20, 20], "mlc": [-10, -10, -10, -10, 10, 10, 10, 10]},
            {"cmw": 0.4, "mlc": [-5, -5, -5, -5, 5, 5, 5, 5]},
            {"cmw": 1.0},
        ]
        ds = F.photon_rtplan([{"number": 2, "cps": cps}], {2: 50.0}, bounds=BOUNDS)
        plan = read_photon_plan(ds)
        segs = plan.beams[0].segments
        assert [round(s.mu, 6) for s in segs] == [20.0, 30.0]
        assert segs[0].mlc_rows[0].x_right_mm == 10.0 and segs[1].mlc_rows[0].x_right_mm == 5.0
        assert [s.control_point_index for s in segs] == [0, 1]

    def test_arc_is_discretized_per_interval_at_mid_angles(self):
        cps = [
            {"cmw": 0.0, "gantry": 350.0, "iso": [0, 0, 0], "xj": [-10, 10], "yj": [-20, 20], "mlc": [-10, -10, -10, -10, 10, 10, 10, 10]},
            {"cmw": 0.5, "gantry": 10.0, "mlc": [-10, -10, -10, -10, 20, 20, 20, 20]},
            {"cmw": 1.0, "gantry": 30.0},
        ]
        plan = read_photon_plan(F.photon_rtplan([{"number": 3, "name": "Arc", "cps": cps}], {3: 200.0}, bounds=BOUNDS))
        assert [b.beam_id for b in plan.beams] == ["Arc:0", "Arc:1"]
        assert [b.gantry_deg for b in plan.beams] == [0.0, 20.0]          # mid-angles, wrap handled
        assert [b.segments[0].mu for b in plan.beams] == [100.0, 100.0]
        assert plan.beams[0].segments[0].mlc_rows[0].x_right_mm == 15.0   # mean of 10 and 20 over the interval

    def test_crossed_leaves_close_and_missing_jaws_come_from_the_mlc(self):
        cps = [{"cmw": 0.0, "gantry": 0.0, "iso": [0, 0, 0], "mlc": [-10, 3, -10, -10, 10, 1, 10, 10]}, {"cmw": 1.0}]
        plan = read_photon_plan(F.photon_rtplan([{"number": 1, "cps": cps}], {1: 10.0}, bounds=BOUNDS))
        s = plan.beams[0].segments[0]
        assert s.mlc_rows[1].x_left_mm == s.mlc_rows[1].x_right_mm == 2.0
        assert s.x_jaw_mm == (-10.0, 10.0) and s.y_jaw_mm == (-20.0, 20.0)

    def test_setup_and_zero_meterset_beams_are_skipped(self):
        cps = [{"cmw": 0.0, "gantry": 0.0, "iso": [0, 0, 0], "xj": [-10, 10], "yj": [-10, 10]}, {"cmw": 1.0}]
        ds = F.photon_rtplan([
            {"number": 1, "name": "Setup", "delivery": "SETUP", "cps": cps},
            {"number": 2, "name": "Zero", "cps": cps},
            {"number": 3, "name": "Real", "cps": cps},
        ], {1: 1.0, 2: 0.0, 3: 42.0})
        plan = read_photon_plan(ds)
        assert [b.beam_id for b in plan.beams] == ["Real"] and plan.beams[0].meterset == 42.0
        assert len(plan.beams[0].segments[0].mlc_rows) == 2          # open field at 10 mm leaves

    def test_dispatch_and_errors(self):
        assert isinstance(read_rtplan(_static_plan()), PhotonPlan)
        with pytest.raises(RTPlanError):
            read_photon_plan(F.photon_rtplan([{"number": 1, "cps": [{"cmw": 0.0, "gantry": 0.0}, {"cmw": 1.0}]}], {1: 10.0}))
        with pytest.raises(RTPlanError):
            read_rtplan(pydicom.Dataset())


# ---------------------------------------------------------------------------
# Ion plans
# ---------------------------------------------------------------------------

class TestIonPlan:
    def test_layers_spots_and_metersets(self):
        ds = F.ion_rtplan([{
            "number": 1, "name": "G90", "gantry": 90.0, "couch": 270.0, "iso": (5.0, -5.0, 0.0),
            "layers": [(150.0, [(0, 0, 0.3), (10, 0, 0.2)], None), (120.0, [(0, 10, 0.5)], None)],
        }], {1: 200.0}, n_fractions=3)
        plan = read_ion_plan(ds)
        assert isinstance(plan, ProtonPlan) and plan.n_fractions == 3 and len(plan.beams) == 1
        b = plan.beams[0]
        assert b.gantry_deg == 90.0 and b.couch_deg == -90.0 and b.isocenter_mm == (5.0, -5.0, 0.0) and b.range_shifter_id is None
        assert [l.energy_mev for l in b.layers] == [150.0, 120.0]
        assert [round(s.mu, 6) for s in b.layers[0].spots] == [60.0, 40.0] and b.layers[1].spots[0].mu == pytest.approx(100.0)
        assert plan.meterset == pytest.approx(200.0) and plan.spot_mus.tolist() == pytest.approx([60.0, 40.0, 100.0])
        assert plan.dicom.sop_class == "RTIONPLAN"

    def test_range_shifter_settings_are_carried(self):
        ds = F.ion_rtplan([{
            "number": 2, "range_shifter_id": "RS_Block",
            "layers": [(100.0, [(0, 0, 1.0)], {"setting": "IN", "distance": 300.0, "wet": 74.1})],
        }], {2: 10.0})
        plan = read_rtplan(ds)
        assert isinstance(plan, ProtonPlan)
        layer = plan.beams[0].layers[0]
        assert plan.beams[0].range_shifter_id == "RS_Block"
        assert layer.range_shifter.setting == "IN" and layer.range_shifter.isocenter_to_range_shifter_mm == 300.0
        assert layer.range_shifter.water_equivalent_thickness_mm == 74.1

    def test_round_trip_through_the_mcsquare_plan_writer(self, tmp_path):
        """An ion plan read from DICOM writes the same MCsquare plan file as the model built by hand."""
        from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonSpot
        from radiarch.services.dose_engines.mcsquare_driver import write_plan_pencil

        ds = F.ion_rtplan([{"number": 1, "gantry": 45.0, "iso": (0, 0, 0),
                            "layers": [(150.0, [(1.0, 2.0, 0.25), (3.0, 4.0, 0.75)], None)]}], {1: 8.0})
        read = read_ion_plan(ds)
        built = ProtonPlan(beams=[ProtonBeam(beam_id="1", gantry_deg=45.0, isocenter_mm=(0, 0, 0),
                                             layers=[ProtonLayer(energy_mev=150.0, spots=[ProtonSpot(x_mm=1, y_mm=2, mu=2.0), ProtonSpot(x_mm=3, y_mm=4, mu=6.0)])])])
        a = write_plan_pencil(read, tmp_path / "a.txt", (0, 0, 0), (1, 1, 1), (10, 10, 10)).read_text()
        b = write_plan_pencil(built, tmp_path / "b.txt", (0, 0, 0), (1, 1, 1), (10, 10, 10)).read_text()
        assert a.replace("#PlanName\na\n", "") == b.replace("#PlanName\nb\n", "")


# ---------------------------------------------------------------------------
# RT Dose
# ---------------------------------------------------------------------------

class TestRTDose:
    def _ramp(self):
        z, y, x = np.indices((3, 4, 5))
        return (10.0 * z + 1.0 * y + 0.1 * x).astype(np.float32)

    def test_grid_and_values(self):
        dose = self._ramp()
        vol = read_rtdose(F.rtdose(dose, (2.0, 2.5, 3.0), (-4.0, -5.0, 10.0)))
        assert vol.shape_zyx == (3, 4, 5) and vol.spacing_mm == (2.0, 2.5, 3.0) and vol.origin_mm == (-4.0, -5.0, 10.0)
        np.testing.assert_allclose(vol.dose_zyx, dose, atol=dose.max() / 65000.0)
        assert vol.summation_type == "PLAN" and vol.referenced_plan_uid.endswith(".55") and vol.dose_units == "GY"
        assert vol.axis_mm("z").tolist() == [10.0, 13.0, 16.0]

    @pytest.mark.parametrize("absolute", [False, True])
    def test_descending_frames_come_back_ascending(self, absolute):
        dose = self._ramp()
        vol = read_rtdose(F.rtdose(dose, (1.0, 1.0, 2.0), (0.0, 0.0, 5.0), descending=True, absolute_offsets=absolute))
        assert vol.origin_mm[2] == 5.0 and vol.spacing_mm[2] == 2.0
        np.testing.assert_allclose(vol.dose_zyx, dose, atol=dose.max() / 65000.0)

    def test_resampling_onto_a_shifted_grid(self):
        dose = self._ramp()
        vol = read_rtdose(F.rtdose(dose, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)))
        same = resample_dose_to_grid(vol, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (3, 4, 5))
        np.testing.assert_allclose(same, vol.dose_zyx, atol=1e-5)
        half = resample_dose_to_grid(vol, (0.5, 0.0, 0.0), (1.0, 1.0, 1.0), (3, 4, 4))
        np.testing.assert_allclose(half[0, 0, :], vol.dose_zyx[0, 0, :4] + 0.05, atol=5e-4)   # 16-bit quantization of the fixture
        outside = resample_dose_to_grid(vol, (0.0, 0.0, 100.0), (1.0, 1.0, 1.0), (2, 2, 2), fill=-1.0)
        assert np.all(outside == -1.0)

    def test_real_eclipse_dose_if_present(self):
        files = sorted(glob.glob("/home/yyan7/SMIS/smis/data/public/pancreatic-ct-cbct-seg/Pancreas-CT-CB_001/RTDOSE_*/*.dcm"))
        if not files:
            pytest.skip("public RTDOSE not on this machine")
        ds = pydicom.dcmread(files[0])
        vol = read_rtdose(files[0])
        assert vol.shape_zyx == (int(ds.NumberOfFrames), int(ds.Rows), int(ds.Columns))
        assert vol.spacing_mm[:2] == (float(ds.PixelSpacing[1]), float(ds.PixelSpacing[0]))
        assert vol.dose_zyx.max() == pytest.approx(float(ds.pixel_array.max()) * float(ds.DoseGridScaling), rel=1e-6)
        assert vol.frame_of_reference_uid == str(ds.FrameOfReferenceUID) and vol.referenced_plan_uid


# ---------------------------------------------------------------------------
# Registrations
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_spatial(self):
        t = np.eye(4); t[:3, 3] = [10.0, -5.0, 2.0]
        reg = read_registration(F.spatial_registration("FOR-A", {"FOR-A": np.eye(4), "FOR-B": t}))
        assert reg.frame_of_reference_uid == "FOR-A" and set(reg.matrices) == {"FOR-A", "FOR-B"}
        np.testing.assert_allclose(reg.transform_points("FOR-B", [[0, 0, 0], [1, 1, 1]]), [[10, -5, 2], [11, -4, 3]])
        assert reg.matrix_types["FOR-B"] == "RIGID"

    def test_deformable(self):
        disp = np.zeros((2, 3, 4, 3), dtype=np.float32); disp[..., 0] = 1.5; disp[1, 2, 3] = [0, 0, -2.0]
        regs = read_registration(F.deformable_registration("FOR-A", "FOR-B", disp, (1.0, 2.0, 3.0), (5.0, 5.0, 5.0)))
        assert len(regs) == 1
        d = regs[0]
        assert d.source_frame_of_reference_uid == "FOR-B" and d.grid_shape_zyx == (2, 3, 4)
        assert d.grid_origin_mm == (1.0, 2.0, 3.0) and d.grid_spacing_mm == (5.0, 5.0, 5.0)
        np.testing.assert_array_equal(d.displacement_zyx, disp)
        np.testing.assert_array_equal(d.pre_matrix, np.eye(4))
