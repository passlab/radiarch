"""Roadmap R8: arcs in the photon plan model, their sectors, and their DICOM round trip."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from radiarch.dicom import read_rtplan
from radiarch.dicom.writers import CaseContext, write_rtplan
from radiarch.models.photon_plan import (
    ArcControlPoint, MLCRow, PhotonArc, PhotonBeam, PhotonPlan, PhotonSegment, arc_step_deg, mid_angle_deg,
)


def _rows(left: float, right: float):
    return [MLCRow(y_min_mm=y, y_max_mm=y + 5, x_left_mm=left, x_right_mm=right) for y in range(-15, 15, 5)]


def _arc(direction="CW", angles=(350.0, 352.0, 354.0, 356.0), mus=(0.0, 4.0, 10.0, 12.0)):
    cps = [ArcControlPoint(gantry_deg=g, cumulative_mu=m, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows(-10 + 2 * k, 10 + 2 * k))
           for k, (g, m) in enumerate(zip(angles, mus))]
    return PhotonArc(direction=direction, control_points=cps)


class TestArcModel:
    def test_steps_and_mid_angles_wrap(self):
        assert arc_step_deg(358, 2, "CW") == pytest.approx(4.0)
        assert arc_step_deg(2, 358, "CC") == pytest.approx(-4.0)
        assert mid_angle_deg(358, 2, "CW") == pytest.approx(0.0)
        assert mid_angle_deg(2, 358, "CC") == pytest.approx(0.0)
        assert mid_angle_deg(10, 20, "CW") == pytest.approx(15.0)

    def test_sectors_are_mid_angle_mean_aperture_interval_mu(self):
        arc = _arc(angles=(358.0, 0.0, 2.0, 4.0))
        sec = arc.sectors()
        assert [s.gantry_deg for s in sec] == pytest.approx([359.0, 1.0, 3.0])
        assert [s.mu for s in sec] == pytest.approx([4.0, 6.0, 2.0])
        assert sec[0].mlc_rows[0].x_left_mm == pytest.approx(-9.0) and sec[0].mlc_rows[0].x_right_mm == pytest.approx(11.0)
        assert arc.total_mu == pytest.approx(12.0) and arc.length_deg == pytest.approx(6.0)

    def test_counter_clockwise_arc(self):
        arc = _arc("CC", angles=(10.0, 7.0, 4.0, 1.0))
        assert [s.gantry_deg for s in arc.sectors()] == pytest.approx([8.5, 5.5, 2.5])
        assert arc.length_deg == pytest.approx(9.0)

    @pytest.mark.parametrize("angles,mus,why", [
        ((0.0, 2.0, 2.0, 4.0), (0, 1, 2, 3), "does not turn"),
        ((0.0, 2.0, 40.0, 42.0), (0, 1, 2, 3), "more than 30"),
        ((0.0, 2.0, 4.0, 6.0), (0, 2, 1, 3), "decrease"),
        ((0.0, 2.0, 4.0, 6.0), (1, 2, 3, 4), "first control point"),
    ])
    def test_invalid_arcs_are_rejected(self, angles, mus, why):
        with pytest.raises(ValueError):
            _arc(angles=angles, mus=mus)

    def test_the_wrong_direction_is_a_long_way_round(self):
        # 0 -> 2 counter-clockwise is a 358 degree interval: rejected
        with pytest.raises(ValueError):
            _arc("CC", angles=(0.0, 2.0, 4.0, 6.0))

    def test_beam_from_arc_and_json_round_trip(self):
        beam = PhotonBeam.from_arc("ARC1", _arc(), couch_deg=5.0, energy_mv=6.0)
        plan = PhotonPlan(name="vmat", beams=[beam])
        back = PhotonPlan.from_json(plan.to_json())
        assert back.beams[0].arc is not None and len(back.beams[0].segments) == 3
        assert back.beams[0].gantry_deg == pytest.approx(350.0)
        assert [beam.segment_gantry_deg(s) for s in back.beams[0].segments] == pytest.approx([351.0, 353.0, 355.0])
        # columns: beamlets of every sector, sector by sector
        assert plan.n_beamlets == sum(s.n_beamlets for s in beam.segments)

    def test_an_arc_beam_needs_its_sectors(self):
        arc = _arc()
        with pytest.raises(ValueError):
            PhotonBeam(beam_id="X", gantry_deg=350, segments=[PhotonSegment(mu=1, x_jaw_mm=(-5, 5), y_jaw_mm=(-5, 5))], arc=arc)


class TestEnginesSeeSectorAngles:
    def test_ccc_beamlets_carry_the_sector_angle(self):
        from radiarch.services.dose_engines.ccc_driver import beamlet_geometry_from_plan
        plan = PhotonPlan(beams=[PhotonBeam.from_arc("A", _arc())])
        geo = beamlet_geometry_from_plan(plan)
        assert set(np.round(geo.angles_deg[:, 0], 6)) == {351.0, 353.0, 355.0}

    def test_pb_directions_one_per_sector(self):
        from radiarch.services.dose_engines.pb import plan_directions
        plan = PhotonPlan(beams=[PhotonBeam.from_arc("A", _arc()),
                                 PhotonBeam(beam_id="S", gantry_deg=90, segments=[PhotonSegment(mu=1, x_jaw_mm=(-5, 5), y_jaw_mm=(-5, 5))])])
        dirs = plan_directions(plan)
        assert [round(d.gantry_deg, 6) for d in dirs] == [351.0, 353.0, 355.0, 90.0]
        cols = [s.first_column for d in dirs for s in d.segments]
        assert cols == sorted(cols) and cols[0] == 0


class TestArcDicom:
    def test_dynamic_beam_round_trip(self, tmp_path):
        n = 8
        ctx = CaseContext(patient_name="R8^Arc", patient_id="R8-1", patient_sex="O", ct_series_instance_uid="1.2.826.0.1.3680043.8.498.8888",
                          ct_sop_instance_uids=[f"1.2.826.0.1.3680043.8.498.8888.{k}" for k in range(n)], now=datetime(2026, 10, 22, 12, 0, 0))
        arc = _arc("CW", angles=(358.0, 0.0, 2.0, 4.0))
        plan = PhotonPlan(name="vmat", beams=[PhotonBeam.from_arc("ARC1", arc, energy_mv=6.0),
                                              PhotonBeam(beam_id="AP", gantry_deg=0, energy_mv=6.0,
                                                         segments=[PhotonSegment(mu=20, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows(-10, 10))])])
        res = write_rtplan(ctx, plan, tmp_path / "RP.dcm", rtstruct_uid="1.2.826.0.1.3680043.8.498.9999")
        import pydicom
        ds = pydicom.dcmread(res.path)
        b = ds.BeamSequence[0]
        assert b.BeamType == "DYNAMIC" and int(b.NumberOfControlPoints) == 4
        assert [cp.GantryRotationDirection for cp in b.ControlPointSequence] == ["CW", "CW", "CW", "NONE"]
        assert [float(cp.CumulativeMetersetWeight) for cp in b.ControlPointSequence] == pytest.approx([0, 4, 10, 12])
        assert ds.BeamSequence[1].BeamType == "STATIC"
        back = read_rtplan(res.path)
        assert len(back.beams) == 2
        a2 = back.beams[0].arc
        assert a2 is not None and a2.direction == "CW"
        assert [c.gantry_deg for c in a2.control_points] == pytest.approx([358.0, 0.0, 2.0, 4.0])
        assert [c.cumulative_mu for c in a2.control_points] == pytest.approx([0, 4, 10, 12])
        for c1, c2 in zip(arc.control_points, a2.control_points):
            assert [r.x_left_mm for r in c2.mlc_rows] == pytest.approx([r.x_left_mm for r in c1.mlc_rows])
        assert back.beams[1].arc is None and back.beams[1].gantry_deg == pytest.approx(0.0)


class TestCoverageBeamlets:
    """Recomputing a delivered plan: every aperture cell, weighted by its open fraction."""

    def test_narrow_window_is_covered(self):
        seg = PhotonSegment(mu=2.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows(1.0, 5.0))
        assert seg.beamlets().shape[0] == 0                       # the optimizer's cut drops a 4 mm opening
        cov = seg.coverage_beamlets()
        assert (cov[:, 2] * cov[:, 3] * cov[:, 4]).sum() == pytest.approx(4.0 * 30.0)
        assert np.all((cov[:, 4] > 0) & (cov[:, 4] <= 1.0))

    def test_open_field_matches_the_beamlet_cut(self):
        seg = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows(-10.0, 10.0))
        cov, cut = seg.coverage_beamlets(), seg.beamlets()
        assert np.allclose(cov[:, 4], 1.0)
        assert sorted(map(tuple, cov[:, :2].round(6))) == sorted(map(tuple, cut[:, :2].round(6)))

    def test_jaws_clip_the_leaves(self):
        seg = PhotonSegment(mu=1.0, x_jaw_mm=(-3, 7), y_jaw_mm=(-12, 12), mlc_rows=_rows(-10.0, 10.0))
        cov = seg.coverage_beamlets()
        assert (cov[:, 2] * cov[:, 3] * cov[:, 4]).sum() == pytest.approx(10.0 * 24.0)

    def test_delivered_geometry_weights_by_mu(self):
        from radiarch.services.dose_engines.ccc_driver import delivered_beamlet_geometry
        seg = PhotonSegment(mu=3.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows(1.0, 5.0), gantry_deg=40.0)
        geo, mu = delivered_beamlet_geometry(PhotonPlan(beams=[PhotonBeam(beam_id="A", gantry_deg=0.0, segments=[seg])]))
        assert len(geo) == mu.shape[0] > 0
        assert np.allclose(geo.angles_deg[:, 0], 40.0)
        assert (mu * 25.0).sum() == pytest.approx(3.0 * 4.0 * 30.0)
