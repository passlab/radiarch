"""Unit tests for radiarch.services.proton_spots and spot_placement.

``generate_proton_spots`` maps a ``BeamSetSpec`` + ``DeliveryParams`` onto
``place_spots`` and walks the resulting plan into a ``FluenceElementSet``.
The geometry is a small water cube with a spherical target so the tests run
in well under a second and need no DICOM.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from radiarch.models.beam_model import BeamSetSpec, BeamSpec, DeliveryParams
from radiarch.models.proton_plan import ProtonPlan
from radiarch.services import spot_placement as S
from radiarch.services.geometry_bundle import GeometryArrays
from radiarch.services.machine_model import ProtonMachineModel
from radiarch.services.proton_spots import generate_proton_spots, summarize_proton_plan


def _water_sphere(n: int = 30, spacing: float = 2.0, radius_mm: float = 12.0, extra=None) -> GeometryArrays:
    c = (n - 1) / 2.0
    zz, yy, xx = np.mgrid[:n, :n, :n]
    sphere = ((xx - c) ** 2 + (yy - c) ** 2 + (zz - c) ** 2) * spacing ** 2 <= radius_mm ** 2
    ct = np.full((n, n, n), -1000, dtype=np.int16)
    ct[2:-2, 2:-2, 2:-2] = 0
    masks = np.where(sphere, 1, 0).astype(np.uint16)
    index = {"PTV": 1}
    if extra:
        index.update(extra)
    return GeometryArrays(
        geometry_id="g-sphere", ct_hu=ct, masks=masks, structure_index=index,
        origin_mm=(-c * spacing,) * 3, spacing_mm=(spacing,) * 3, patient_name="WATER",
    )


def _beam_set(n_beams: int = 2) -> BeamSetSpec:
    return BeamSetSpec(isocenter_mm=(0, 0, 0),
                       beams=[BeamSpec(beam_id=f"B{i + 1}", gantry_deg=i * 90.0) for i in range(n_beams)])


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class TestRangeEnergy:
    def test_round_trip(self):
        for e in (70.0, 100.0, 150.0, 226.0):
            assert S.range_to_energy_mev(S.energy_to_range_cm(e)) == pytest.approx(e, rel=2e-3)

    def test_known_values(self):
        # Grevillot fit: 100 MeV ≈ 7.7 cm in water, 200 MeV ≈ 26 cm
        assert S.energy_to_range_cm(100.0) == pytest.approx(7.72, abs=0.1)
        assert S.energy_to_range_cm(200.0) == pytest.approx(25.9, abs=0.3)
        assert S.range_to_energy_mev(0.0) == 0.0 and S.energy_to_range_cm(0.0) == 0.0


class TestGridAndDirection:
    def test_direction_is_unit_and_follows_gantry(self):
        assert np.allclose(S.beam_direction(0.0, 0.0), [0, 1, 0], atol=1e-9)
        assert np.allclose(S.beam_direction(90.0, 0.0), [-1, 0, 0], atol=1e-9)
        assert np.allclose(S.beam_direction(270.0, 0.0), [1, 0, 0], atol=1e-9)
        for g, c in [(37.0, 12.0), (200.0, -40.0)]:
            assert np.linalg.norm(S.beam_direction(g, c)) == pytest.approx(1.0)

    def test_hexagonal_grid_covers_the_field_of_view(self):
        bev, xyz = S.hexagonal_spot_grid(5.0, (1.0, 2.0, 3.0), 0.0, 0.0)
        assert bev.shape[0] == 80 * 93
        assert bev[:, 0].min() <= -195 and bev[:, 0].max() >= 195
        assert abs(bev[:, 1].max() + bev[:, 1].min()) < 5.0
        # odd rows are shifted by half a spacing (hexagonal packing)
        rows = {round(y, 6) for y in bev[:, 1]}
        assert len(rows) == 93
        # at gantry 0 the BEV x is the patient x and BEV y the patient z, around the isocenter
        assert np.allclose(xyz[:, 0] - 1.0, bev[:, 0]) and np.allclose(xyz[:, 2] - 3.0, bev[:, 1])
        assert np.allclose(xyz[:, 1], 2.0)

    def test_dilation_grows_the_mask(self):
        g = _water_sphere()
        m = g.mask_xyz(1)
        d = S.dilate_mask(m, g.spacing_mm, 5.0)
        assert d.sum() > m.sum() and d[m].all()
        assert S.dilate_mask(m, g.spacing_mm, 0.0).sum() == m.sum()

    def test_center_of_mass(self):
        g = _water_sphere()
        assert np.allclose(S.center_of_mass_mm(g.mask_xyz(1), g.origin_mm, g.spacing_mm), [0, 0, 0], atol=1e-6)


class TestPlacement:
    @pytest.fixture(scope="class")
    def rsp(self):
        g = _water_sphere()
        return g, ProtonMachineModel.from_default().rsp_model.rsp(g.ct_hu_xyz(), 100.0)

    def test_spots_land_on_the_target(self, rsp):
        g, r = rsp
        plan = S.place_spots(r, g.mask_xyz(1), g.origin_mm, g.spacing_mm, [S.BeamGeometry("B1", 0.0)])
        assert isinstance(plan, ProtonPlan) and plan.n_spots > 0
        beam = plan.beams[0]
        assert beam.isocenter_mm == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
        xy = np.array([(s.x_mm, s.y_mm) for layer in beam.layers for s in layer.spots])
        # target radius 12 mm + 5 mm margin, spots on a 5 mm hexagonal grid
        assert np.hypot(xy[:, 0], xy[:, 1]).max() <= 17.0 + 2.5
        assert np.hypot(xy[:, 0], xy[:, 1]).min() < 3.0
        energies = [l.energy_mev for l in beam.layers]
        assert energies == sorted(energies, reverse=True)
        # the distal edge of a 24 mm sphere (+5 mm margin) ~4.7 cm deep in water: ~75 MeV;
        # the shallowest layers belong to edge spots that graze the dilated target
        assert 70.0 < max(energies) < 80.0 and 0.0 < min(energies) < max(energies)
        assert all(s.mu == 1.0 for s in plan.beams[0].layers[0].spots)

    def test_every_gantry_angle_reaches_the_target(self, rsp):
        g, r = rsp
        beams = [S.BeamGeometry(f"B{i}", gantry, couch) for i, (gantry, couch) in
                 enumerate([(0.0, 0.0), (90.0, 0.0), (180.0, 0.0), (270.0, 0.0), (45.0, 20.0), (300.0, -30.0)])]
        plan = S.place_spots(r, g.mask_xyz(1), g.origin_mm, g.spacing_mm, beams)
        counts = [b.n_spots for b in plan.beams]
        assert min(counts) > 0 and max(counts) / min(counts) < 1.5
        for b in plan.beams:
            assert all(abs(b.layers[i].energy_mev - b.layers[j].energy_mev) >= S.LAYER_ENERGY_TOLERANCE_MEV
                       for i in range(len(b.layers)) for j in range(i))

    def test_explicit_isocenter_and_params(self, rsp):
        g, r = rsp
        p = S.PlacementParams(spot_spacing_mm=4.0, layer_spacing_mm=3.0, target_margin_mm=0.0, proximal_layers=0, distal_layers=0)
        plan = S.place_spots(r, g.mask_xyz(1), g.origin_mm, g.spacing_mm, [S.BeamGeometry("B", 0.0)], p, isocenter_mm=(1.0, 2.0, 3.0))
        assert plan.beams[0].isocenter_mm == (1.0, 2.0, 3.0)
        xy = np.array([(s.x_mm, s.y_mm) for layer in plan.beams[0].layers for s in layer.spots])
        assert np.hypot(xy[:, 0] + 1.0, xy[:, 1] + 3.0).max() <= 12.0 + 2.0
        e = [l.energy_mev for l in plan.beams[0].layers]
        assert len(e) >= 6 and all(S.energy_to_range_cm(a) * 10 - S.energy_to_range_cm(b) * 10 == pytest.approx(3.0, abs=0.05)
                                   for a, b in zip(e, e[1:]))

    def test_empty_target_is_an_error(self, rsp):
        g, r = rsp
        with pytest.raises(ValueError, match="empty"):
            S.place_spots(r, np.zeros_like(g.mask_xyz(1)), g.origin_mm, g.spacing_mm, [S.BeamGeometry("B", 0.0)])

    def test_marching_depth_in_water(self, rsp):
        """A spot through the centre of the cube: the water-equivalent depth to the dilated
        target is the geometric distance (RSP of water 1)."""
        g, r = rsp
        grid = np.asarray(r.shape, dtype=np.int32)
        off, sp = np.asarray(g.origin_mm, np.float32), np.asarray(g.spacing_mm, np.float32)
        mask = g.mask_xyz(1)
        d = np.asarray(S.beam_direction(0.0, 0.0), np.float32)
        start = np.array([[0.0, float(g.origin_mm[1]), 0.0]], np.float32)
        pos, wet = S.march_to_target(np.ascontiguousarray(r, np.float32).ravel(), mask.ravel(), off, sp, grid, start, d)
        assert wet[0] > 0
        # air shell of 2 voxels (RSP ~0.001) then water up to the sphere surface at y = -12
        expected = (-12.0 - float(g.origin_mm[1])) - 4.0
        assert wet[0] == pytest.approx(expected, abs=2.5)


# ---------------------------------------------------------------------------
# The adapter: request → plan → FluenceElementSet
# ---------------------------------------------------------------------------

class TestGenerateProtonSpots:
    def test_per_beam_layout_matches_request(self):
        g = _water_sphere()
        result = generate_proton_spots(g, ProtonMachineModel.from_default(), _beam_set(2), DeliveryParams())
        fe = result.fluence_elements
        assert [pb.beam_id for pb in fe.per_beam] == ["B1", "B2"]
        assert fe.total_count == result.plan.n_spots > 0
        for pb, beam in zip(fe.per_beam, result.plan.beams):
            assert pb.element_count == beam.n_spots
            assert pb.energy_layers == [l.energy_mev for l in beam.layers]
            assert pb.spots_per_layer == [l.n_spots for l in beam.layers]

    def test_spacing_parameters_are_honoured(self):
        g = _water_sphere()
        coarse = generate_proton_spots(g, ProtonMachineModel.from_default(), _beam_set(1), DeliveryParams(spot_spacing_mm=6.0, layer_spacing_mm=6.0))
        fine = generate_proton_spots(g, ProtonMachineModel.from_default(), _beam_set(1), DeliveryParams(spot_spacing_mm=3.0, layer_spacing_mm=3.0))
        assert fine.plan.n_spots > 2 * coarse.plan.n_spots
        assert len(fine.plan.beams[0].layers) > len(coarse.plan.beams[0].layers)

    def test_target_is_picked_from_the_structure_index(self):
        g = _water_sphere(extra={"SpinalCord": 2})
        result = generate_proton_spots(g, ProtonMachineModel.from_default(), _beam_set(1), DeliveryParams())
        assert result.plan.n_spots > 0
        no_target = GeometryArrays("g", g.ct_hu, g.masks, {"Lung_L": 1}, g.origin_mm, g.spacing_mm)
        with pytest.raises(ValueError, match="no target structure"):
            generate_proton_spots(no_target, ProtonMachineModel.from_default(), _beam_set(1), DeliveryParams())
        explicit = generate_proton_spots(no_target, ProtonMachineModel.from_default(), _beam_set(1), DeliveryParams(), target_label=1)
        assert explicit.plan.n_spots == result.plan.n_spots

    def test_summary_falls_back_to_request_beams_for_an_empty_plan(self):
        fe = summarize_proton_plan(ProtonPlan(name="empty"), _beam_set(2))
        assert [pb.beam_id for pb in fe.per_beam] == ["B1", "B2"] and fe.total_count == 0
