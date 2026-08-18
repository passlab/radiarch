"""Unit tests for the Pydantic schemas in radiarch.models.beam_model."""

from __future__ import annotations

import pytest

from radiarch.models.beam_model import (
    BeamModelBuildRequest,
    BeamSetSpec,
    BeamSpec,
    DeliveryParams,
    FluenceElementSet,
    Modality,
    PerBeamElements,
)


# ---------------------------------------------------------------------------
# BeamSpec / BeamSetSpec validation
# ---------------------------------------------------------------------------

class TestBeamSpec:
    def test_rejects_gantry_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            BeamSpec(beam_id="B0", gantry_deg=361.0)

    def test_rejects_gantry_at_360(self) -> None:
        # IEC 61217: gantry is [0, 360), 360 wraps to 0.
        with pytest.raises(ValueError):
            BeamSpec(beam_id="B0", gantry_deg=360.0)

    def test_rejects_couch_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            BeamSpec(beam_id="B0", gantry_deg=0.0, couch_deg=200.0)

    def test_defaults_couch_and_collimator_to_zero(self) -> None:
        b = BeamSpec(beam_id="B0", gantry_deg=90.0)
        assert b.couch_deg == 0.0
        assert b.collimator_deg == 0.0


class TestBeamSetSpec:
    def test_unique_beam_ids_enforced(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            BeamSetSpec(
                isocenter_mm=(0, 0, 0),
                beams=[
                    BeamSpec(beam_id="A", gantry_deg=0),
                    BeamSpec(beam_id="A", gantry_deg=90),
                ],
            )

    def test_minimum_one_beam(self) -> None:
        with pytest.raises(ValueError):
            BeamSetSpec(isocenter_mm=(0, 0, 0), beams=[])

    def test_max_nine_beams(self) -> None:
        beams = [BeamSpec(beam_id=f"B{i}", gantry_deg=0) for i in range(10)]
        with pytest.raises(ValueError):
            BeamSetSpec(isocenter_mm=(0, 0, 0), beams=beams)


# ---------------------------------------------------------------------------
# DeliveryParams modality filtering
# ---------------------------------------------------------------------------

class TestDeliveryParams:
    def test_proton_filter_keeps_only_proton_fields(self) -> None:
        p = DeliveryParams(
            spot_spacing_mm=4.0,
            layer_spacing_mm=3.0,
            beamlet_size_mm=(7, 7),  # photon — should be filtered out
            mlc_leaf_width_mm=2.5,    # photon — should be filtered out
        )
        out = p.for_modality(Modality.proton_pbs)
        assert "spot_spacing_mm" in out
        assert out["spot_spacing_mm"] == 4.0
        assert "beamlet_size_mm" not in out
        assert "mlc_leaf_width_mm" not in out

    def test_photon_filter_keeps_only_photon_fields(self) -> None:
        p = DeliveryParams(
            spot_spacing_mm=4.0,      # proton — filtered
            beamlet_size_mm=(7, 7),
            mlc_leaf_width_mm=2.5,
        )
        out = p.for_modality(Modality.photon_imrt)
        assert "beamlet_size_mm" in out
        assert "spot_spacing_mm" not in out

    def test_tuple_normalized_to_list(self) -> None:
        # Tuples and lists hash differently in JSON but are semantically
        # equivalent — for_modality should normalize.
        p = DeliveryParams(beamlet_size_mm=(5.0, 5.0))
        out = p.for_modality(Modality.photon_imrt)
        assert out["beamlet_size_mm"] == [5.0, 5.0]


# ---------------------------------------------------------------------------
# Cache key behaviour — the centerpiece
# ---------------------------------------------------------------------------

def _request(**overrides) -> BeamModelBuildRequest:
    base = dict(
        geometry_id="g-1",
        modality=Modality.proton_pbs,
        machine_model_id=None,
        beam_set=BeamSetSpec(
            isocenter_mm=(0, 0, 0),
            beams=[BeamSpec(beam_id="B1", gantry_deg=0)],
        ),
        delivery_params=DeliveryParams(),
    )
    base.update(overrides)
    return BeamModelBuildRequest(**base)


class TestCacheKey:
    def test_deterministic(self) -> None:
        assert _request().compute_cache_key() == _request().compute_cache_key()

    def test_changes_with_geometry_id(self) -> None:
        a = _request(geometry_id="g-1").compute_cache_key()
        b = _request(geometry_id="g-2").compute_cache_key()
        assert a != b

    def test_changes_with_modality(self) -> None:
        a = _request(modality=Modality.proton_pbs).compute_cache_key()
        b = _request(modality=Modality.photon_imrt).compute_cache_key()
        assert a != b

    def test_invariant_to_beam_order(self) -> None:
        beams_a = [
            BeamSpec(beam_id="B1", gantry_deg=0),
            BeamSpec(beam_id="B2", gantry_deg=90),
        ]
        beams_b = list(reversed(beams_a))
        a = _request(beam_set=BeamSetSpec(isocenter_mm=(0, 0, 0), beams=beams_a)).compute_cache_key()
        b = _request(beam_set=BeamSetSpec(isocenter_mm=(0, 0, 0), beams=beams_b)).compute_cache_key()
        assert a == b

    def test_proton_param_change_does_not_bust_photon_cache(self) -> None:
        """The headline invariant — modality filter actually filters."""
        photon_a = _request(
            modality=Modality.photon_imrt,
            delivery_params=DeliveryParams(spot_spacing_mm=4.0, beamlet_size_mm=(5, 5)),
        ).compute_cache_key()
        photon_b = _request(
            modality=Modality.photon_imrt,
            delivery_params=DeliveryParams(spot_spacing_mm=8.0, beamlet_size_mm=(5, 5)),
        ).compute_cache_key()
        assert photon_a == photon_b, "spot_spacing change must not affect photon hash"

    def test_photon_param_change_does_not_bust_proton_cache(self) -> None:
        proton_a = _request(
            modality=Modality.proton_pbs,
            delivery_params=DeliveryParams(spot_spacing_mm=5.0, beamlet_size_mm=(5, 5)),
        ).compute_cache_key()
        proton_b = _request(
            modality=Modality.proton_pbs,
            delivery_params=DeliveryParams(spot_spacing_mm=5.0, beamlet_size_mm=(8, 8)),
        ).compute_cache_key()
        assert proton_a == proton_b

    def test_changes_with_relevant_param(self) -> None:
        proton_a = _request(
            delivery_params=DeliveryParams(spot_spacing_mm=4.0)
        ).compute_cache_key()
        proton_b = _request(
            delivery_params=DeliveryParams(spot_spacing_mm=8.0)
        ).compute_cache_key()
        assert proton_a != proton_b

    def test_excludes_plan_id(self) -> None:
        a = _request(plan_id="plan-A").compute_cache_key()
        b = _request(plan_id="plan-B").compute_cache_key()
        assert a == b, "plan_id is a downstream reference, not a build input"


# ---------------------------------------------------------------------------
# FluenceElementSet totals invariant
# ---------------------------------------------------------------------------

class TestFluenceElementSet:
    def test_totals_must_match(self) -> None:
        with pytest.raises(ValueError, match="total_count"):
            FluenceElementSet(
                total_count=10,
                per_beam=[
                    PerBeamElements(beam_id="B1", element_count=3),
                    PerBeamElements(beam_id="B2", element_count=4),
                ],
            )

    def test_happy_path(self) -> None:
        fe = FluenceElementSet(
            total_count=7,
            per_beam=[
                PerBeamElements(beam_id="B1", element_count=3),
                PerBeamElements(beam_id="B2", element_count=4),
            ],
        )
        assert fe.total_count == 7

    def test_proton_layer_arrays_must_align(self) -> None:
        with pytest.raises(ValueError, match="length"):
            PerBeamElements(
                beam_id="B1",
                element_count=10,
                energy_layers=[100.0, 110.0],
                spots_per_layer=[5],
            )

    def test_proton_layer_arrays_aligned_ok(self) -> None:
        pbe = PerBeamElements(
            beam_id="B1",
            element_count=12,
            energy_layers=[100.0, 110.0, 120.0],
            spots_per_layer=[4, 4, 4],
        )
        assert sum(pbe.spots_per_layer) == pbe.element_count
