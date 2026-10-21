"""Photon beam-model builder on radiarch's own plan model (R1).

No OpenTPS involved: ``build_photon_plan`` returns a ``PhotonPlan`` whose
beamlets follow the half-pixel grid, so the counts are the ones the
vendored OpenTPS copy produced (a 200 mm field at 5 mm → 1600)."""

from __future__ import annotations

import pytest

from radiarch.models.beam_model import BeamSetSpec, BeamSpec, DeliveryParams
from radiarch.models.photon_plan import PhotonPlan
from radiarch.services.machine_model import PhotonMachineModel
from radiarch.services.photon_beamlets import build_photon_plan, generate_photon_beamlets


def _beam_set(n: int = 2) -> BeamSetSpec:
    return BeamSetSpec(
        isocenter_mm=(0, 0, 0),
        beams=[BeamSpec(beam_id=f"B{i+1}", gantry_deg=i * 90.0) for i in range(n)],
    )


class TestGridMath:
    def test_default_jaw_default_beamlet_yields_expected_grid(self):
        result = generate_photon_beamlets(
            geometry=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(),  # default beamlet 5×5, 200 mm jaws, 10 mm leaves
        )
        pb = result.fluence_elements.per_beam[0]
        assert pb.grid_dims == (40, 40)
        assert pb.element_count == 1600
        assert pb.active_beamlets == 1600

    def test_custom_jaw_overrides_machine_default(self):
        result = generate_photon_beamlets(
            geometry=object(),
            machine_model=PhotonMachineModel(machine_model_id="default", max_jaw_opening_mm=300.0),
            beam_set=_beam_set(1),
            params=DeliveryParams(jaw_opening_mm=(100.0, 100.0), beamlet_size_mm=(10.0, 10.0)),
        )
        pb = result.fluence_elements.per_beam[0]
        assert pb.grid_dims == (10, 10)
        assert pb.element_count == 100

    def test_total_count_is_per_beam_sum(self):
        result = generate_photon_beamlets(
            geometry=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(3),
            params=DeliveryParams(),
        )
        assert result.fluence_elements.total_count == 1600 * 3
        assert len(result.fluence_elements.per_beam) == 3
        assert result.plan.n_beamlets == 1600 * 3

    def test_leaf_width_from_request_overrides_machine(self):
        result = generate_photon_beamlets(
            geometry=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(mlc_leaf_width_mm=5.0),
        )
        assert len(result.plan.beams[0].segments[0].mlc_rows) == 40   # 200 mm / 5 mm


class TestPlanAssembly:
    def test_one_beam_per_request_with_ids_and_angles(self):
        beam_set = BeamSetSpec(
            isocenter_mm=(1.0, 2.0, 3.0),
            beams=[BeamSpec(beam_id="A", gantry_deg=72.0), BeamSpec(beam_id="B", gantry_deg=144.0, couch_deg=10.0)],
        )
        result = generate_photon_beamlets(
            geometry=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=beam_set, params=DeliveryParams(),
        )
        plan = result.plan
        assert isinstance(plan, PhotonPlan)
        assert [b.beam_id for b in plan.beams] == ["A", "B"]
        assert [b.gantry_deg for b in plan.beams] == [72.0, 144.0]
        assert plan.beams[1].couch_deg == 10.0
        assert plan.isocenter_mm == (1.0, 2.0, 3.0)

    def test_segment_jaws_centred_on_isocenter(self):
        plan = build_photon_plan([(0.0, 0.0)], (-40.0, 40.0), (-40.0, 40.0), 10.0, 5000.0)
        seg = plan.beams[0].segments[0]
        assert seg.x_jaw_mm == (-40.0, 40.0)
        assert seg.y_jaw_mm == (-40.0, 40.0)
        assert seg.mu == 5000.0
        assert len(seg.mlc_rows) == 8

    def test_plan_round_trips_through_json(self):
        plan = build_photon_plan([(0.0, 0.0), (180.0, 0.0)], (-50.0, 50.0), (-50.0, 50.0), 10.0, 100.0)
        again = PhotonPlan.from_json(plan.to_json())
        assert again == plan
        assert again.n_beamlets == 2 * 400

    def test_gantry_wraps_to_dicom_range(self):
        plan = build_photon_plan([(360.0, 0.0)], (-50.0, 50.0), (-50.0, 50.0), 10.0, 1.0)
        assert plan.beams[0].gantry_deg == 0.0

    def test_beam_id_count_mismatch_rejected(self):
        with pytest.raises(ValueError):
            build_photon_plan([(0.0, 0.0)], (-50.0, 50.0), (-50.0, 50.0), 10.0, 1.0, beam_ids=["a", "b"])
