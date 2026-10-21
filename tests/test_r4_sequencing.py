"""R4, part C: leaf sequencing of optimized fluence into deliverable apertures."""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from radiarch.models.photon_plan import PhotonPlan
from radiarch.services import sequencing as S
from radiarch.services.machine_model import load_photon_spec
from radiarch.services.photon_beamlets import build_photon_plan


def _plan(beams=((0.0, 0.0),), field=40.0, leaf=5.0, beamlet=5.0) -> PhotonPlan:
    h = field / 2.0
    return build_photon_plan(list(beams), (-h, h), (-h, h), leaf, 1.0, (beamlet, beamlet), name="seq")


class TestRows:
    def test_sequence_row_rising_and_falling_edges(self):
        x = np.arange(7, dtype=float)             # 6 columns, edges 0..6
        # the i-th segment opens at the i-th rising edge and closes at the i-th falling edge
        assert S.sequence_row(np.array([0, 2, 2, 1, 0, 0]), x) == [(1.0, 3.0), (1.0, 4.0)]
        segs = S.sequence_row(np.array([1, 2, 1, 2, 1, 0]), x)
        assert segs == [(0.0, 2.0), (1.0, 4.0), (3.0, 5.0)]
        rebuilt = np.zeros(6)
        for a, b in segs:
            rebuilt[int(a):int(b)] += 1
        assert np.array_equal(rebuilt, [1, 2, 1, 2, 1, 0])
        assert S.sequence_row(np.zeros(6, int), x) == []

    def test_fluence_map_bins_beamlets_onto_leaf_pairs(self):
        machine = load_photon_spec("synthetic-120")
        plan = _plan(field=40.0, leaf=5.0, beamlet=5.0)
        w = np.arange(plan.n_beamlets, dtype=float)
        maps = S.fluence_maps(plan, w, machine.mlc)
        assert len(maps) == 1 and maps[0].values.shape == (8, 8)
        assert set(maps[0].pair_indices) == set(range(26, 34))          # pairs covering y in [-20, 20) of the 5 mm central region
        # each cell holds exactly one beamlet's weight
        assert np.allclose(np.sort(maps[0].values.ravel()), np.sort(w))

    def test_ten_mm_leaves_average_two_beamlet_rows(self):
        machine = load_photon_spec("synthetic-120")
        # a field reaching y = ±150 mm covers 10 mm outer leaves (|y| > 100)
        plan = _plan(field=300.0, leaf=5.0, beamlet=5.0)
        bl = plan.beamlets()
        w = np.where(bl[:, 1] > 100, 2.0, 0.0)
        w[(bl[:, 1] > 100) & (bl[:, 1] < 105)] = 4.0                    # one of the two rows of pair (100, 110) is 4, the other 2
        maps = S.fluence_maps(plan, w, machine.mlc)
        m = maps[0]
        pair_100 = m.pair_indices.index(machine.mlc.pair_index(102.0))
        assert np.allclose(m.values[pair_100], 3.0)


class TestApertures:
    def test_decomposition_reproduces_the_quantized_map(self):
        machine = load_photon_spec("synthetic-160")
        plan = _plan(field=40.0)
        rng = np.random.default_rng(3)
        w = rng.random(plan.n_beamlets) * 10
        maps = S.fluence_maps(plan, w, machine.mlc)
        aps = S.sequence_map(maps[0], levels=5)
        assert aps and all(a.level_weight == pytest.approx(w.max() / 5) for a in aps)
        # summing the apertures' coverage × level weight gives back the quantized map
        cov = S.coverage_matrix(plan, maps, aps, machine.mlc)
        rebuilt = np.asarray(cov @ np.full(len(aps), aps[0].level_weight)).ravel()
        quantized = np.rint(w / (w.max() / 5)) * (w.max() / 5)
        assert np.allclose(rebuilt, quantized, atol=1e-9)

    def test_machine_limits_and_interdigitation_report(self):
        machine = load_photon_spec("synthetic-120")
        mlc = machine.mlc.model_copy(update={"interdigitation": False, "max_overtravel_mm": 10.0})
        ap = S.Aperture(0, np.array([-30.0, 15.0]), np.array([-20.0, 30.0]), 1.0)
        out = S.apply_machine_limits(ap, mlc, [30, 31])
        assert out.right_mm[0] == -10.0 and out.left_mm[1] == 10.0            # both tips clipped to 10 mm overtravel
        assert any("interdigitation" in i for i in out.issues)
        narrow = S.apply_machine_limits(S.Aperture(0, np.array([0.0]), np.array([0.3]), 1.0), machine.mlc, [30])
        assert narrow.right_mm[0] == narrow.left_mm[0]

    def test_segment_weights_fit_a_target_dose(self):
        """Two apertures, two voxels: the weights that give the wanted dose are found."""
        S_mat = sp.csr_matrix(np.array([[1.0, 0.0], [0.0, 2.0], [0.5, 0.5]]))
        target = np.array([2.0, 4.0, 2.0])

        def terms(dose):
            d = dose.ravel()
            return float(np.sum((d - target) ** 2)), (2 * (d - target)).reshape(dose.shape)

        w, conv = S.optimize_segment_weights(S_mat, (3, 1, 1), terms, np.ones(2))
        assert np.allclose(w, [2.0, 2.0], atol=1e-4) and conv.success


class TestSequencePlan:
    @staticmethod
    def _problem():
        """A 20³ water box, a central target, two opposed beams with 10 mm beamlets and a simple Dij:
        every beamlet deposits a column of dose along its beam through the grid."""
        n, sp_mm = 20, 5.0
        plan = _plan(beams=((0.0, 0.0), (180.0, 0.0)), field=60.0, leaf=5.0, beamlet=10.0)
        grid = (n, n, n)
        bl = plan.beamlets()
        beam_of = plan.beamlet_beam_index()
        rows, cols, vals = [], [], []
        zz, yy, xx = np.indices(grid)
        coords = {"x": (xx - (n - 1) / 2) * sp_mm, "z": (zz - (n - 1) / 2) * sp_mm, "y": (yy - (n - 1) / 2) * sp_mm}
        for j in range(bl.shape[0]):
            x, y, dx, dy = bl[j]
            inside = (np.abs(coords["x"] - x) <= dx / 2) & (np.abs(coords["z"] - y) <= dy / 2)
            depth = coords["y"] if beam_of[j] == 0 else -coords["y"]
            d = np.exp(-(depth + 50) / 150.0) * inside
            idx = np.flatnonzero(d.ravel())
            rows.append(idx); cols.append(np.full(idx.size, j)); vals.append(d.ravel()[idx])
        dij = sp.csr_matrix((0.01 * np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n ** 3, bl.shape[0]))   # ~1 cGy per MU
        ptv = (np.abs(coords["x"]) <= 15) & (np.abs(coords["y"]) <= 15) & (np.abs(coords["z"]) <= 15)
        oar = (np.abs(coords["x"]) <= 40) & (coords["y"] > 25) & (coords["y"] <= 35) & (np.abs(coords["z"]) <= 10)

        def terms(dose):
            d = np.asarray(dose, dtype=float)
            g = np.zeros_like(d)
            loss = 0.0
            diff = (d - 2.0) * ptv
            loss += float(np.sum(diff ** 2)); g += 2 * diff
            over = np.maximum(d - 0.5, 0) * oar
            loss += 4 * float(np.sum(over ** 2)); g += 8 * over
            return loss, g
        return plan, dij, grid, terms, ptv, oar

    def test_end_to_end_on_a_water_box(self):
        plan, dij, grid, terms, ptv, oar = self._problem()
        machine = load_photon_spec("synthetic-120")
        # an "optimized" fluence: a round-ish target at 2 Gy from two beams, nothing elsewhere
        bl = plan.beamlets()
        w = np.where(np.hypot(bl[:, 0], bl[:, 1]) <= 16, 1.0, 0.0) * 110.0
        w[(bl[:, 1] > 5)] *= 0.6                                     # less through the upper rows (OAR side)
        res = S.sequence_plan(plan, w, dij, grid, terms, machine, levels=4, max_iterations=100)
        # a beam whose segments all fall under the minimum MU is left out (the optimizer may favour one side)
        assert res.plan.n_beamlets > 0 and 1 <= len(res.plan.beams) <= 2
        assert res.segment_mu.shape[0] == sum(len(b.segments) for b in res.plan.beams)
        assert all(s.mu >= machine.min_mu_per_segment for b in res.plan.beams for s in b.segments)
        assert all(len(s.mlc_rows) >= 1 and s.x_jaw_mm[1] > s.x_jaw_mm[0] for b in res.plan.beams for s in b.segments)
        for rep in res.deliverability:
            assert rep.n_segments >= 1 and rep.total_mu > 0 and rep.beam_on_time_s > 0 and not rep.issues
        # the segment dose covers the target and the apertures stay inside the field
        assert res.dose[ptv].mean() > 1.0 and res.dose.shape == grid
        for b in res.plan.beams:
            for seg in b.segments:
                for r in seg.mlc_rows:
                    assert -30.0 - 1e-6 <= r.x_left_mm <= r.x_right_mm <= 30.0 + 1e-6
        # the re-optimized segment weights do at least as well as the uniform level weights
        assert res.convergence.final_cost <= terms(np.asarray(dij @ (res.coverage @ np.full(res.coverage.shape[1], w.max() / 4))).reshape(grid))[0] + 1e-6

    def test_min_area_drops_tiny_apertures(self):
        plan, dij, grid, terms, ptv, oar = self._problem()
        machine = load_photon_spec("synthetic-120").model_copy(update={"min_segment_area_mm2": 1e9})
        bl = plan.beamlets()
        w = np.where(np.hypot(bl[:, 0], bl[:, 1]) <= 16, 1.0, 0.0)
        with pytest.raises(ValueError, match="minimum area"):
            S.sequence_plan(plan, w, dij, grid, terms, machine, levels=3)
