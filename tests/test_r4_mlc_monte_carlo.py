"""Roadmap R4: the leaf model against Monte Carlo through the Versa's Agility MLC (``docs/reports/mlc-leaf-model.md``):
the MLC fields of ``validation/mc_reference.py``, their plans in the harness, the fit of the transmission and leaf gap,
and the primaries of the references."""

from __future__ import annotations

import json

import numpy as np
import pytest

from radiarch.models.photon_plan import LeafModel
from radiarch.validation import cases_r7, cases_r8
from radiarch.validation import mc_reference as mr

C = (349.3 - 7.5) / 1000.0                       # the Versa MLC's projection (mc_reference.set_mlc_field)
CENTRES = (np.arange(80) - 39.5) * 5.1262        # leaf-pair centres at isocenter, a boundary on the axis


def f(x):
    """An even calibration offset like the Versa's (0.25 mm on the axis, less off the axis)."""
    return 0.25 - 2.3e-4 * np.asarray(x, dtype=float) ** 2


class TestLeafPositions:
    def test_an_open_band_puts_each_tip_where_the_versa_puts_a_rectangular_field(self):
        left, right, rows = mr.mlc_leaf_positions(CENTRES, [(-50.0, 50.0, -20.0, 30.0)], f, C)
        k = int(np.argmin(np.abs(CENTRES - 2.56)))
        assert left[k] == pytest.approx(C * (-20.0 + f(20.0)))
        assert right[k] == pytest.approx(C * (30.0 - f(30.0)))
        assert all(r[2:] == [-20.0, 30.0] for r in rows)

    def test_rows_cover_the_pairs_the_jaws_leave_open(self):
        _, _, rows = mr.mlc_leaf_positions(CENTRES, [], f, C)
        assert len(rows) == 20 and rows[0][0] < -50.0 < rows[0][1] and rows[-1][0] < 50.0 < rows[-1][1]
        assert all(b == pytest.approx(a) for (_, a, _, _), (b, _, _, _) in zip(rows, rows[1:]))

    def test_a_closed_pair_touches_and_states_the_gap_its_rounded_ends_pass(self):
        bands = [(-50.0, -10.0, -40.0, 40.0), (-10.0, 10.0, 20.0, 20.0), (10.0, 50.0, -40.0, 40.0)]
        left, right, rows = mr.mlc_leaf_positions(CENTRES, bands, f, C)
        assert np.allclose(left[38:42], C * 20.0) and np.allclose(right[38:42], C * 20.0)
        assert rows[10][2:] == [round(20.0 - float(f(-20.0)), 3), round(20.0 + float(f(20.0)), 3)]

    def test_pairs_outside_every_band_close_on_the_axis(self):
        left, right, _ = mr.mlc_leaf_positions(CENTRES, [(-10.0, 10.0, -30.0, 30.0)], f, C)
        assert left[0] == right[0] == 0.0 and left[-1] == right[-1] == 0.0

    def test_interdigitating_pairs_are_refused(self):
        with pytest.raises(ValueError, match="interdigitate"):
            mr.mlc_leaf_positions(CENTRES, [(-20.0, 0.0, -40.0, -30.0), (0.0, 20.0, 30.0, 40.0)], f, C)

    def test_a_gap_narrower_than_the_rounded_ends_is_refused(self):
        with pytest.raises(ValueError, match="past touching"):
            mr.mlc_leaf_positions(CENTRES, [(-50.0, 50.0, -0.1, 0.1)], f, C)

    @pytest.mark.parametrize("case", sorted(mr.MLC_BANDS))
    def test_the_shipped_mlc_fields_are_valid(self, case):
        left, right, rows = mr.mlc_leaf_positions(CENTRES, mr.MLC_BANDS[case], f, C)
        assert len(rows) == 20 and np.all(right >= left)


class TestPrimaries:
    def test_the_total_is_split_over_the_threads(self):
        assert mr.per_thread(5e7, 18) == 2777778
        assert mr.per_thread(10, 64) == 1

    @pytest.mark.parametrize("per_event, factor", [(False, 18), (True, 1)])
    def test_references_made_per_thread_are_read_per_simulated_primary(self, tmp_path, monkeypatch, per_event, factor):
        dose = np.full((4, 4, 4), 3.6e-13, dtype=np.float32)
        mr.save_reference(tmp_path / "water_x.npz", dose, np.zeros_like(dose), 2.5, (0.0, 1.25, 0.0), 1000)
        prov = {"threads": 18, "primaries": 1000, **({"dose_per": "event"} if per_event else {})}
        (tmp_path / "water_x.json").write_text(json.dumps(prov), encoding="utf-8")
        monkeypatch.setattr(cases_r7, "MC_DIR", tmp_path)
        ref = cases_r7._mc_reference("water_x")
        assert float(ref["dose"].max()) == pytest.approx(3.6e-13 / factor, rel=1e-3)
        assert ref["primaries"] == 1000 * factor

    def test_runs_with_different_seeds_merge_weighted_by_their_primaries(self, tmp_path):
        for name, seed, n, value, unc in (("a", 1, 1000, 2.0e-13, 0.02), ("b", 2, 3000, 4.0e-13, 0.01)):
            d = tmp_path / name
            d.mkdir()
            dose = np.full((4, 4, 4), value, dtype=np.float32)
            mr.save_reference(d / "mlc_x.npz", dose, np.full_like(dose, unc), 2.5, (0.0, 1.25, 0.0), n)
            (d / "mlc_x.json").write_text(json.dumps({"case": "mlc_x", "seed": seed, "primaries": n, "dose_per": "event",
                                                      "elapsed_s": 10.0, "date": f"2026-11-0{seed}"}), encoding="utf-8")
        prov = mr.merge_runs("mlc_x", [tmp_path / "a", tmp_path / "b"], tmp_path / "out")
        dose, unc, _, _, n = mr.load_reference_arrays(tmp_path / "out" / "mlc_x.npz")
        assert n == 4000 and prov["seed"] == [1, 2] and prov["runs"] == 2 and prov["elapsed_s"] == 20.0
        assert float(dose.max()) == pytest.approx(3.5e-13, rel=1e-3)
        sd = np.hypot(1000 * 0.02 * 2.0e-13, 3000 * 0.01 * 4.0e-13) / 4000
        assert float(unc.max()) == pytest.approx(sd / 3.5e-13, abs=1e-3)

    def test_runs_sharing_a_seed_are_refused(self, tmp_path):
        for name in ("a", "b"):
            d = tmp_path / name
            d.mkdir()
            mr.save_reference(d / "mlc_x.npz", np.ones((2, 2, 2)), np.zeros((2, 2, 2)), 2.5, (0.0, 1.25, 0.0), 10)
            (d / "mlc_x.json").write_text(json.dumps({"seed": 7, "primaries": 10, "dose_per": "event"}), encoding="utf-8")
        with pytest.raises(ValueError, match="share a seed"):
            mr.merge_runs("mlc_x", [tmp_path / "a", tmp_path / "b"], tmp_path / "out")


def _prov(case, bands):
    _, _, rows = mr.mlc_leaf_positions(CENTRES, bands, f, C)
    return {"case": case, "mlc": {"jaw_y_mm": [-50.0, 50.0], "block_x_mm": [-100.0, 100.0], "rows": rows, "bands": bands}}


class TestHarness:
    def test_the_plan_states_the_jaws_blocks_rows_and_model(self):
        model = LeafModel(leaf_transmission=0.004, dosimetric_leaf_gap_mm=0.3)
        plan = cases_r8._mlc_plan(_prov("mlc_gap10", mr.MLC_BANDS["mlc_gap10"]), model)
        seg = plan.beams[0].segments[0]
        assert seg.x_jaw_mm == (-100.0, 100.0) and seg.y_jaw_mm == (-50.0, 50.0)
        assert len(seg.mlc_rows) == 20 and seg.mlc_rows[0].x_left_mm == -5.0 and plan.leaf_model == model

    def test_the_fit_recovers_the_transmission_and_leaf_gap_of_a_known_model(self):
        """'Monte Carlo' made by the pencil beam with a known leaf model: the fit gives that model back."""
        from radiarch.services.dose_engines.pb import PencilBeamEngine
        from radiarch.validation import phantoms as ph
        ok, reason = PencilBeamEngine().availability()
        if not ok:
            pytest.skip(reason)
        eng = PencilBeamEngine()
        phantom = ph.water_box(120.0, 150.0, 5.0)
        provs = {c: _prov(c, mr.MLC_BANDS[c]) for c in ("mlc_open", "mlc_closed", "mlc_gap10")}

        def dose(case, model):
            plan = cases_r8._mlc_plan(provs[case], model)
            return eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params={"fluence": "apertures"})

        norm = cases_r8._region(phantom, (-10.0, 10.0), (-10.0, 10.0))
        open_norm = float(dose("mlc_open", None)[norm].mean())
        truth = LeafModel(leaf_transmission=0.004, dosimetric_leaf_gap_mm=0.8, tongue_and_groove_mm=0.5)
        t_region = cases_r8._region(phantom, (25.0, 75.0), (-35.0, 35.0)) | cases_r8._region(phantom, (-75.0, -25.0), (-35.0, 35.0))
        gap_region = cases_r8._sweep_region(phantom)
        mc_t = float(dose("mlc_closed", truth)[t_region].mean()) / open_norm
        mc_gap = float(dose("mlc_gap10", truth)[gap_region].mean()) / open_norm
        t, g = cases_r8._fit_leaf_model(lambda c, m: dose(c, m) / open_norm, mc_t, mc_gap, t_region, gap_region, 0.5)
        assert t == pytest.approx(0.004, abs=1e-4)
        assert g == pytest.approx(0.8, abs=0.05)
