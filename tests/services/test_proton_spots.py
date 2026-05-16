"""Unit tests for radiarch.services.proton_spots.

We bypass OpenTPS by patching ``ProtonPlanDesign`` to return a hand-built
plan stub. The function-under-test is the *adapter* that maps
``BeamSetSpec`` + ``DeliveryParams`` onto OpenTPS conventions and walks
the resulting plan into a ``FluenceElementSet`` — that's what we cover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from unittest.mock import patch

import pytest

from radiarch.models.beam_model import (
    BeamSetSpec,
    BeamSpec,
    DeliveryParams,
    Modality,
)
from radiarch.services.machine_model import ProtonMachineModel


# ---------------------------------------------------------------------------
# Test doubles for the OpenTPS plan structure walked by _summarize_proton_plan
# ---------------------------------------------------------------------------

@dataclass
class _FakeLayer:
    nominalEnergy: float
    spots: List[int]  # Just a list whose len() is the spot count


@dataclass
class _FakeBeam:
    layers: List[_FakeLayer] = field(default_factory=list)


@dataclass
class _FakePlan:
    beams: List[_FakeBeam] = field(default_factory=list)


class _FakeProtonPlanDesign:
    """Stand-in for OpenTPS's ``ProtonPlanDesign``.

    Records the inputs it receives (so tests can assert mapping logic)
    and returns a deterministic plan from ``buildPlan``.
    """

    instances: List["_FakeProtonPlanDesign"] = []

    def __init__(self):
        self.ct = None
        self.patient = None
        self.calibration = None
        self.gantryAngles = None
        self.couchAngles = None
        self.spotSpacing = None
        self.layerSpacing = None
        self.target_call = None
        # Build-time return shape — set by the test before buildPlan is called.
        self._plan = None
        _FakeProtonPlanDesign.instances.append(self)

    def defineTargetMaskAndPrescription(self, contour, prescription_gy):
        self.target_call = (contour, prescription_gy)

    def buildPlan(self):
        # Default plan: two energy layers per beam, 5 spots each.
        if self._plan is not None:
            return self._plan
        beams = []
        for _ in (self.gantryAngles or []):
            beams.append(_FakeBeam(layers=[
                _FakeLayer(nominalEnergy=100.0, spots=list(range(5))),
                _FakeLayer(nominalEnergy=110.0, spots=list(range(5))),
            ]))
        return _FakePlan(beams=beams)


@pytest.fixture(autouse=True)
def _reset_design_instances():
    _FakeProtonPlanDesign.instances.clear()


@pytest.fixture
def patched_proton_plan_design(monkeypatch):
    """Patch the OpenTPS ProtonPlanDesign import inside the generator."""
    import radiarch.services.proton_spots as ps

    # Insert a fake into the import path used by the lazy import inside
    # generate_proton_spots. We patch sys.modules so the lazy
    # ``from opentps.core.data.plan import ProtonPlanDesign`` returns
    # our fake.
    import sys
    import types

    fake_mod = types.SimpleNamespace(ProtonPlanDesign=_FakeProtonPlanDesign)
    monkeypatch.setitem(sys.modules, "opentps.core.data.plan", fake_mod)
    yield


def _beam_set(n_beams: int = 2) -> BeamSetSpec:
    return BeamSetSpec(
        isocenter_mm=(0, 0, 0),
        beams=[
            BeamSpec(beam_id=f"B{i+1}", gantry_deg=i * 90.0)
            for i in range(n_beams)
        ],
    )


# ---------------------------------------------------------------------------
# Mapping: request → ProtonPlanDesign attributes
# ---------------------------------------------------------------------------

class TestRequestMapping:
    def test_gantry_couch_passed_through_in_order(self, patched_proton_plan_design):
        from radiarch.services.proton_spots import generate_proton_spots

        beam_set = BeamSetSpec(
            isocenter_mm=(0, 0, 0),
            beams=[
                BeamSpec(beam_id="A", gantry_deg=0, couch_deg=10),
                BeamSpec(beam_id="B", gantry_deg=90, couch_deg=-5),
            ],
        )
        result = generate_proton_spots(
            ct=object(), patient=object(), target_contour=object(),
            machine_model=ProtonMachineModel(machine_model_id="default"),
            beam_set=beam_set,
            params=DeliveryParams(),
        )
        design = _FakeProtonPlanDesign.instances[0]
        assert design.gantryAngles == [0.0, 90.0]
        assert design.couchAngles == [10.0, -5.0]

    def test_spot_and_layer_spacing_applied(self, patched_proton_plan_design):
        from radiarch.services.proton_spots import generate_proton_spots

        params = DeliveryParams(spot_spacing_mm=3.5, layer_spacing_mm=2.5)
        generate_proton_spots(
            ct=object(), patient=object(), target_contour=object(),
            machine_model=ProtonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(),
            params=params,
        )
        design = _FakeProtonPlanDesign.instances[0]
        assert design.spotSpacing == 3.5
        assert design.layerSpacing == 2.5

    def test_target_contour_supplied_to_design(self, patched_proton_plan_design):
        from radiarch.services.proton_spots import generate_proton_spots

        sentinel = object()
        generate_proton_spots(
            ct=object(), patient=object(), target_contour=sentinel,
            machine_model=ProtonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(),
            prescription_gy=4.0,
        )
        design = _FakeProtonPlanDesign.instances[0]
        assert design.target_call == (sentinel, 4.0)

    def test_no_target_skips_define(self, patched_proton_plan_design):
        from radiarch.services.proton_spots import generate_proton_spots

        generate_proton_spots(
            ct=object(), patient=object(), target_contour=None,
            machine_model=ProtonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(),
        )
        design = _FakeProtonPlanDesign.instances[0]
        assert design.target_call is None


# ---------------------------------------------------------------------------
# Result: built plan → FluenceElementSet
# ---------------------------------------------------------------------------

class TestPlanSummarization:
    def test_per_beam_layout_matches_request(self, patched_proton_plan_design):
        from radiarch.services.proton_spots import generate_proton_spots

        beam_set = _beam_set(2)
        result = generate_proton_spots(
            ct=object(), patient=object(), target_contour=object(),
            machine_model=ProtonMachineModel(machine_model_id="default"),
            beam_set=beam_set,
            params=DeliveryParams(),
        )
        # Default fake plan: 2 layers × 5 spots per beam, 2 beams = 20 spots.
        assert result.fluence_elements.total_count == 20
        assert [pb.beam_id for pb in result.fluence_elements.per_beam] == ["B1", "B2"]
        for pb in result.fluence_elements.per_beam:
            assert pb.element_count == 10
            assert pb.energy_layers == [100.0, 110.0]
            assert pb.spots_per_layer == [5, 5]

    def test_plan_object_is_returned(self, patched_proton_plan_design):
        from radiarch.services.proton_spots import generate_proton_spots

        result = generate_proton_spots(
            ct=object(), patient=object(), target_contour=object(),
            machine_model=ProtonMachineModel(machine_model_id="default"),
            beam_set=_beam_set(1),
            params=DeliveryParams(),
        )
        assert isinstance(result.plan, _FakePlan)
        assert len(result.plan.beams) == 1
