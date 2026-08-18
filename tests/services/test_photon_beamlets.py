"""Unit tests for radiarch.services.photon_beamlets.

Patches the OpenTPS PhotonPlan / PlanPhotonBeam / PlanPhotonSegment
classes with simple stand-ins so the test exercises the adapter math
(grid dim derivation, jaw resolution) without OpenTPS available.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import List

import pytest

from radiarch.models.beam_model import (
    BeamSetSpec,
    BeamSpec,
    DeliveryParams,
)
from radiarch.services.machine_model import PhotonMachineModel


# ---------------------------------------------------------------------------
# OpenTPS stand-ins
# ---------------------------------------------------------------------------

@dataclass
class _FakeSegment:
    monitorUnits: float = 0.0
    jawOpeningMM: list = field(default_factory=list)


@dataclass
class _FakeBeam:
    gantryAngle: float = 0.0
    couchAngle: float = 0.0
    segments: list = field(default_factory=list)


@dataclass
class _FakePlan:
    beams: list = field(default_factory=list)


@pytest.fixture(autouse=True)
def _patch_opentps_photon(monkeypatch):
    """Insert fake modules at the import paths used by the lazy imports."""
    photon_plan_mod = types.SimpleNamespace(PhotonPlan=_FakePlan)
    plan_beam_mod = types.SimpleNamespace(PlanPhotonBeam=_FakeBeam)
    plan_seg_mod = types.SimpleNamespace(PlanPhotonSegment=_FakeSegment)
    monkeypatch.setitem(sys.modules,
                        "opentps.core.data.plan._photonPlan", photon_plan_mod)
    monkeypatch.setitem(sys.modules,
                        "opentps.core.data.plan._planPhotonBeam", plan_beam_mod)
    monkeypatch.setitem(sys.modules,
                        "opentps.core.data.plan._planPhotonSegment", plan_seg_mod)
    yield


def _beam_set(n: int = 2) -> BeamSetSpec:
    return BeamSetSpec(
        isocenter_mm=(0, 0, 0),
        beams=[BeamSpec(beam_id=f"B{i+1}", gantry_deg=i * 90.0) for i in range(n)],
    )


# ---------------------------------------------------------------------------
# Grid math
# ---------------------------------------------------------------------------

class TestGridMath:
    def test_default_jaw_default_beamlet_yields_expected_grid(self):
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        # 200 mm jaw / 5 mm beamlets = 40×40 = 1600 elements per beam.
        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(),  # default beamlet 5×5
        )
        pb = result.fluence_elements.per_beam[0]
        assert pb.grid_dims == (40, 40)
        assert pb.element_count == 1600
        assert pb.active_beamlets == 1600

    def test_custom_jaw_overrides_machine_default(self):
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        # 100 mm jaw / 10 mm beamlets = 10×10 = 100 per beam.
        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(
                machine_model_id="default", max_jaw_opening_mm=300.0,
            ),
            beam_set=_beam_set(1),
            params=DeliveryParams(
                jaw_opening_mm=(100.0, 100.0),
                beamlet_size_mm=(10.0, 10.0),
            ),
        )
        pb = result.fluence_elements.per_beam[0]
        assert pb.grid_dims == (10, 10)
        assert pb.element_count == 100

    def test_total_count_is_per_beam_sum(self):
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(3),
            params=DeliveryParams(),
        )
        assert result.fluence_elements.total_count == 1600 * 3
        assert len(result.fluence_elements.per_beam) == 3

    def test_non_divisible_jaw_rounds_up(self):
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        # 100 mm / 7 mm = 14.28… → ceil to 15 per axis.
        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(
                jaw_opening_mm=(100.0, 100.0),
                beamlet_size_mm=(7.0, 7.0),
            ),
        )
        pb = result.fluence_elements.per_beam[0]
        assert pb.grid_dims == (15, 15)


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------

class TestPlanConstruction:
    def test_one_beam_per_request(self):
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(3),
            params=DeliveryParams(),
        )
        assert len(result.plan.beams) == 3

    def test_gantry_angles_propagate(self):
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=BeamSetSpec(
                isocenter_mm=(0, 0, 0),
                beams=[
                    BeamSpec(beam_id="B1", gantry_deg=72),
                    BeamSpec(beam_id="B2", gantry_deg=144),
                ],
            ),
            params=DeliveryParams(),
        )
        assert [b.gantryAngle for b in result.plan.beams] == [72.0, 144.0]

    def test_segment_jaw_centered_on_isocenter(self):
        from radiarch.services.photon_beamlets import generate_photon_beamlets

        # Jaw opening 80 mm should produce [-40, +40] mm jaw bounds.
        result = generate_photon_beamlets(
            ct=object(), patient=object(),
            machine_model=PhotonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(jaw_opening_mm=(80.0, 80.0)),
        )
        seg = result.plan.beams[0].segments[0]
        assert seg.jawOpeningMM == [-40.0, 40.0]
