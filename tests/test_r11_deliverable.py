"""R11.5: a navigation state made deliverable (docs/reports/mco-research-and-design.md, D7, and §5's deliverable tests).

The ``ReferenceDose`` mimicking objective is checked on its own (one-sided: an organ above the reference; a target
above it in its hotter half, below it in its colder half). Then the deliverable step: protons on the stubbed service
(the projected spots are the plan), static photon fields through the SDK on the stub patient (projection, apertures
mimicking the navigated dose, normalisation, the deviation table and its flags, the cache, lineage, export).
"""

from __future__ import annotations

import numpy as np
import pydicom
import pytest

from radiarch.models.mco import DeliverableRequest
from radiarch.models.optimization import HardConstraint, ObjectiveSpec
from radiarch.services.objectives import ReferenceDose

from test_r11_pareto import _mreq, msvc, svc  # noqa: F401  (the stubbed services: a proton beam model, the analytic engine)


class TestReferenceDose:
    def test_one_sided(self):
        ref = np.array([10.0, 10.0, 20.0, 20.0])
        m = np.ones(4)
        organ, target = ReferenceDose("S", ref, "organ"), ReferenceDose("S", ref, "target")
        assert organ(ref, m)[0] == 0.0 and target(ref, m)[0] == 0.0
        assert organ(ref - 3.0, m)[0] == 0.0 and organ(ref + 1.0, m)[0] == pytest.approx(1.0)
        # the target: its colder half (reference 10) is penalized below, its hotter half (20) above
        assert target(ref + np.array([5.0, 5.0, 0.0, 0.0]), m)[0] == 0.0
        assert target(ref + np.array([-2.0, 0.0, 0.0, 0.0]), m)[0] == pytest.approx(1.0)
        assert target(ref + np.array([0.0, 0.0, 2.0, 0.0]), m)[0] == pytest.approx(1.0)
        assert target(ref + np.array([0.0, 0.0, -5.0, 0.0]), m)[0] == 0.0

    def test_gradient_matches_finite_differences(self):
        rng = np.random.default_rng(2)
        ref, d = rng.uniform(5, 15, 30), rng.uniform(5, 15, 30)
        m = (rng.uniform(size=30) > 0.3).astype(float)
        for role in ("organ", "target"):
            obj = ReferenceDose("S", ref, role, 2.0)
            _, g = obj(d, m)
            for i in np.flatnonzero(m)[:10]:
                e = np.zeros(30)
                e[i] = 1e-6
                fd = (obj(d + e, m)[0] - obj(d - e, m)[0]) / 2e-6
                assert g[i] == pytest.approx(fd, rel=1e-4, abs=1e-8)

    def test_spec(self):
        with pytest.raises(ValueError, match="reference_dose_uri and reference_role"):
            ObjectiveSpec(type="ReferenceDose", structure_name="S", dose_gy=0.0, weight=1.0)
        a = ObjectiveSpec(type="ReferenceDose", structure_name="S", dose_gy=0.0, weight=1.0, reference_dose_uri="/x.nii.gz", reference_role="organ")
        assert a.hash() != a.model_copy(update={"reference_role": "target"}).hash()


class TestProtons:
    def test_the_projected_spots_are_the_plan(self, msvc, tmp_path):
        from radiarch.services.mco_deliverable import DeliverableService, target_structures

        res = msvc.run(_mreq(hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=5.0)]))
        assert target_structures(res) == ["PTV"]
        svc_d = DeliverableService(base_dir=tmp_path / "d", mco_service=msvc)
        out = svc_d.run(res.mco_id, DeliverableRequest(project=True))
        assert out.technique == "proton" and out.projected and out.dose_id is None and out.beam_model_id == res.beam_model_id
        assert any("minimum spot meterset" in n for n in out.notes)
        rows = {r.name: r for r in out.deviation}
        assert set(rows) == {"UniformRMS(PTV)", "MeanDose(OAR)"}
        assert all(r.worse_by <= 0.011 and not r.flagged for r in rows.values())       # projected: no trade-off worse
        opt = msvc.optimization.store.get_by_id(out.optimization_id)
        assert opt.cache_key.startswith(f"mco:{res.mco_id}:") and opt.geometry_id == res.geometry_id
        assert svc_d.run(res.mco_id, DeliverableRequest(project=True)).deliverable_id == out.deliverable_id   # cached
        with pytest.raises(ValueError, match="no state"):
            svc_d.run(res.mco_id, DeliverableRequest(state_id="nope"))


# ---------------------------------------------------------------------------
# Static photon fields through the SDK on the stub patient
# ---------------------------------------------------------------------------

from test_r11_navigation import rx  # noqa: E402,F401
from test_r6_rt_export_service import env  # noqa: E402,F401


def test_a_deliverable_photon_plan_through_the_sdk(rx, tmp_path):
    from radiarch.sdk import MCOPlan, RadiarchError, ops

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=6,
                hard_constraints=[ops.hard("PTV", "Dmin", ">=", 1.0)])
    st = ps.navigate(move={"MeanDose(OAR)": 0.9 * ps.states()[0].values_gy[1]})
    goals = {"goals": [{"structure": "PTV", "metric": "D95%[Gy]", "op": ">=", "value": 1.5, "priority": 1},
                       {"structure": "OAR", "metric": "Dmean[Gy]", "op": "<=", "value": 1.0, "priority": 2}]}
    plan = ps.deliverable(st, levels=5, max_iterations=60, goals=goals, normalise={"structure": "PTV", "metric": "D95", "gy": 1.8},
                          tolerance_gy=0.05, project=True)
    assert isinstance(plan, MCOPlan) and plan.technique == "imrt" and plan.sequence_id and plan.state_id == st.state_id
    assert plan.projected and plan.normalisation > 0 and plan.dose_id
    names = [r["name"] for r in plan.deviation_table()]
    assert names[:2] == ["UniformRMS(PTV)", "MeanDose(OAR)"] and any(n.startswith("PTV D95%[Gy]") for n in names)
    assert plan.flagged == sum(r["flagged"] for r in plan.deviation_table())
    for r in plan.deviation_table():
        assert r["flagged"] == (r["worse_by"] > (0.05 if r["unit"] == "Gy" else 1.0))
    # normalised: the plan's PTV D95 is the goal
    dose = plan.dose()
    assert dose.id == plan.dose_id
    assert ps.deliverable(st, levels=5, max_iterations=60, goals=goals, normalise={"structure": "PTV", "metric": "D95", "gy": 1.8},
                          tolerance_gy=0.05, project=True).id == plan.id                                       # cached
    blend = ps.deliverable(st, levels=5, max_iterations=60, goals=goals, normalise={"structure": "PTV", "metric": "D95", "gy": 1.8},
                          tolerance_gy=0.05)
    assert not blend.projected and blend.id != plan.id and all(r["projected"] is None for r in blend.deviation_table())   # the default: the blend
    graph = rx.get(f"/lineage/optimization/{plan.optimization_id}")
    assert {n["ref"]["kind"] for n in graph["nodes"]} >= {"optimization", "mco", "beam_model", "geometry"}
    exp = plan.export(label="MCO", prescription={"dose_gy": 2.0, "fractions": 2})
    files = exp.download(tmp_path / "rt")
    assert pydicom.dcmread(next(p for p in files if p.name == "RP.dcm")).RTPlanLabel == "MCO"

    with pytest.raises(RadiarchError) as e:
        ps.deliverable("no-such-state")
    assert e.value.status_code == 404
    with pytest.raises(RadiarchError) as e:
        rx.get("/mco/deliverables/no-such-plan")
    assert e.value.status_code == 404


def test_planning_goals_from_a_clinical_goal_set():
    from radiarch.models.evaluation import GoalSetSpec
    from radiarch.services.mco_deliverable import planning_goals

    gs = GoalSetSpec(goals=[{"structure": "PTV", "metric": "D95%[Gy]", "op": ">=", "value": 60.0, "priority": 1},
                            {"structure": "Cord", "metric": "Dmax[Gy]", "op": "<=", "value": 45.0, "priority": 2},
                            {"structure": "Eso", "metric": "Dmean[Gy]", "op": "<=", "value": 34.0, "priority": 2},
                            {"structure": "Heart", "metric": "D33%[Gy]", "op": "<=", "value": 60.0, "priority": 2},
                            {"structure": "Lungs", "metric": "V20Gy[%]", "op": "<=", "value": 37.0, "priority": 2},
                            {"structure": "PTV", "metric": "D0.03cc[Gy]", "op": "<=", "value": 72.0, "priority": 2}])
    assert planning_goals(gs) == [{"structure": "PTV", "metric": "D95", "op": ">=", "gy": 60.0},
                                  {"structure": "Cord", "metric": "Dmax", "op": "<=", "gy": 45.0},
                                  {"structure": "Eso", "metric": "Dmean", "op": "<=", "gy": 34.0},
                                  {"structure": "Heart", "metric": "D33", "op": "<=", "gy": 60.0}]
    assert planning_goals(None) == []


def test_the_deliverable_metersets_are_driven_by_the_goals_in_rounds(rx, monkeypatch):
    """R11.9: the meterset optimization takes, with the mimic, each target's hot-spot term (no hotter than the navigated
    plan past the tolerance) and the goals' objectives; a goal that fails after normalisation triples its weight (an
    organ limit 5 % lower) and the metersets are optimized again, up to ``rounds`` times."""
    from radiarch.services.apertures import ApertureService
    from radiarch.sdk import ops

    seen = []
    real = ApertureService.sequence

    def capture(self, optimization_id, request):
        seen.append(request)
        return real(self, optimization_id, request)

    monkeypatch.setattr(ApertureService, "sequence", capture)
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=6,
                hard_constraints=[ops.hard("PTV", "Dmin", ">=", 1.0)])
    goals = {"goals": [{"structure": "PTV", "metric": "D95%[Gy]", "op": ">=", "value": 1.5, "priority": 1},
                       {"structure": "OAR", "metric": "Dmean[Gy]", "op": "<=", "value": 0.001, "priority": 2}]}   # the OAR goal cannot hold
    plan = ps.deliverable("balance", levels=5, max_iterations=60, goals=goals, prescription_gy=2.0, rounds=2,
                          normalise={"structure": "PTV", "metric": "D95", "gy": 1.8}, tolerance_gy=0.05)
    assert len(seen) == 2 and len(plan.rounds) == 2, plan.rounds
    assert plan.rounds[0]["failed"] == ["OAR Dmean"] and plan.rounds[1]["failed"] == ["OAR Dmean"]
    assert all(r["normalisation"] > 0 for r in plan.rounds)
    first, second = seen
    kinds = [(o.type, o.structure_name) for o in first.objectives]
    assert ("ReferenceDose", "PTV") in kinds and ("ReferenceDose", "OAR") in kinds       # the mimic
    hot = [o for o in first.objectives if o.type == "DMax" and o.structure_name == "PTV"]
    assert len(hot) == 1 and hot[0].dose_gy > 1.0                                          # the hot-spot term: navigated max + tolerance
    assert ("DUniform", "PTV") in kinds and ("DVHMin", "PTV") in kinds                     # the goals' objectives
    oar1 = [o for o in first.objectives if o.type == "DVHMax" and o.structure_name == "OAR"][0]
    oar2 = [o for o in second.objectives if o.type == "DVHMax" and o.structure_name == "OAR"][0]
    assert oar2.weight == pytest.approx(3.0 * oar1.weight) and oar2.dose_gy == pytest.approx(0.95 * oar1.dose_gy)
    assert plan.request.rounds == 2 and plan.request.hot_spot_gy is None
    hard = {(c.metric, c.op): c for c in first.hard_constraints}                          # R11.9 (A): coverage and the hot spot, hard
    assert set(hard) == {("gEUD", ">="), ("Dmax", "<=")} and hard[("gEUD", ">=")].value_gy == 1.8 and hard[("gEUD", ">=")].eud_a == -10.0
    assert hard[("Dmax", "<=")].value_gy == pytest.approx(1.2 * 2.0) and "hard_constraints" in plan.rounds[0]
    assert first.levels == 5 == second.levels                                              # no peak capped: the request's levels

    # a goal set that holds in the first round stops there (without the coverage constraints, whose level rounds of their
    # own calibrate); no goals: the mimic and the hot-spot term alone, one round
    seen.clear()
    easy = ps.deliverable("balance", levels=5, max_iterations=60, goals={"goals": goals["goals"][:1]}, prescription_gy=2.0, rounds=3,
                          normalise={"structure": "PTV", "metric": "D95", "gy": 1.8}, hard_coverage=False)
    assert len(easy.rounds) == 1 and easy.rounds[0]["failed"] == [] and len(seen) == 1
    seen.clear()
    bare = ps.deliverable("balance", levels=5, max_iterations=60, rounds=3, hot_spot_gy=2.5)
    assert len(bare.rounds) == 1 and len(seen) == 1 and seen[0].hard_constraints == []            # no normalise: no limits
    types = {(o.type, o.structure_name): o for o in seen[0].objectives}
    assert set(types) == {("ReferenceDose", "PTV"), ("ReferenceDose", "OAR"), ("DMax", "PTV")} and types[("DMax", "PTV")].dose_gy == 2.5
    seen.clear()
    off = ps.deliverable("balance", levels=5, max_iterations=60, rounds=1, normalise={"structure": "PTV", "metric": "D95", "gy": 1.8},
                         hard_coverage=False)
    assert seen[0].hard_constraints == [] and "hard_constraints" not in off.rounds[0]


def test_the_coverage_constraint_is_calibrated_until_the_normalisation_is_near_1(rx, monkeypatch):
    """R11.9: a gEUD at the coverage dose is not the coverage goal (the 4 mm lung case met it and still needed 1.11).
    While a round's normalisation is outside normalise_band, the next round's gEUD level is scaled by it, never above
    0.95 times the maximum's limit; the round nearest 1 is the plan."""
    import radiarch.services.autoplan as autoplan
    from radiarch.services.apertures import ApertureService
    from radiarch.sdk import ops

    seen, made = [], []
    real_sequence, real_normalise = ApertureService.sequence, autoplan.normalise_to_goal

    def capture(self, optimization_id, request):
        seen.append(request)
        made.append(real_sequence(self, optimization_id, request))
        return made[-1]

    factors: list = []

    def scripted(dose, target, metric, gy):                # each round's normalisation as scripted, then the real one
        if factors:
            k = factors.pop(0)
            return dose * k, k
        return real_normalise(dose, target, metric, gy)

    monkeypatch.setattr(ApertureService, "sequence", capture)
    monkeypatch.setattr(autoplan, "normalise_to_goal", scripted)
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=6,
                hard_constraints=[ops.hard("PTV", "Dmin", ">=", 1.0)])
    normalise = {"structure": "PTV", "metric": "D95", "gy": 1.8}

    factors[:] = [1.2, 1.1, 1.01]
    plan = ps.deliverable("balance", levels=5, max_iterations=60, prescription_gy=2.0, rounds=4, normalise=normalise)
    levels = [next(c.value_gy for c in q.hard_constraints if c.metric == "gEUD") for q in seen]
    assert levels == [1.8, pytest.approx(1.8 * 1.2), pytest.approx(0.95 * 2.4)]       # 1.8 x 1.2 x 1.1 is past 0.95 x 2.4
    assert [r["coverage_gy"] for r in plan.rounds] == levels and len(plan.rounds) == 3  # 1.01: within the band, stop
    assert [r.get("kept", False) for r in plan.rounds] == [False, False, True] and plan.sequence_id == made[2].sequence_id

    seen.clear(); made.clear()
    factors[:] = [1.2, 1.3, 1.25]                          # never within the band: the nearest round is kept
    plan = ps.deliverable("balance", levels=5, max_iterations=60, prescription_gy=2.0, rounds=3, normalise=normalise, normalise_band=0.02)
    assert len(seen) == 3 and [r.get("kept", False) for r in plan.rounds] == [True, False, False]
    assert plan.sequence_id == made[0].sequence_id

    seen.clear()
    factors[:] = [1.02]                                    # within the default band (0.03): one round
    plan = ps.deliverable("balance", levels=5, max_iterations=60, prescription_gy=2.0, rounds=3, normalise=normalise, normalise_band=0.03,
                          tolerance_gy=0.07)
    assert len(seen) == 1 and plan.rounds[0]["kept"] is True


def test_a_maximum_past_its_limit_once_normalised_divides_the_limit_by_the_normalisation(rx, monkeypatch):
    """R11.11: the 4 mm lung arcs' kept round was within the band (1.029), and its normalisation took the PTV's maximum
    to 74.3 Gy against 72. A round within the band whose maximum, once normalised, passes the limit is not calibrated:
    the next round keeps the coverage level and takes the limit divided by the normalisation. Every round records its
    limits and what the metersets reached."""
    import radiarch.services.autoplan as autoplan
    from radiarch.services.apertures import ApertureService
    from radiarch.sdk import ops

    seen = []
    real_sequence = ApertureService.sequence

    def capture(self, optimization_id, request):
        seen.append(request)
        return real_sequence(self, optimization_id, request)

    monkeypatch.setattr(ApertureService, "sequence", capture)
    monkeypatch.setattr(autoplan, "normalise_to_goal", lambda dose, target, metric, gy: (dose * 1.02, 1.02))   # within the band
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=6,
                hard_constraints=[ops.hard("PTV", "Dmin", ">=", 1.0)])
    # a 1.01 Gy limit (1.01 x 1.0) under a 1.8 Gy coverage level: the maximum cannot hold once normalised
    plan = ps.deliverable("balance", levels=5, max_iterations=60, prescription_gy=1.0, max_dose_factor=1.01, rounds=2,
                          normalise={"structure": "PTV", "metric": "D95", "gy": 1.8})
    assert len(seen) == 2 and len(plan.rounds) == 2, plan.rounds
    limits = [{c.metric: c.value_gy for c in q.hard_constraints} for q in seen]
    assert limits[0] == {"gEUD": 1.8, "Dmax": 1.01}
    assert limits[1] == {"gEUD": 1.8, "Dmax": pytest.approx(round(1.01 / 1.02, 3))}                      # coverage kept, limit / k
    for r, lim in zip(plan.rounds, limits):
        assert r["coverage_gy"] == lim["gEUD"] and r["max_gy"] == pytest.approx(lim["Dmax"])
        assert r["dmax_normalised_gy"] == pytest.approx(1.02 * r["dmax_gy"], abs=2e-3) and r["dmax_normalised_gy"] > 1.01 + 0.5
        assert r["geud_gy"] > 0 and set(r["hard_constraints"]) and r["normalisation"] == 1.02


def test_the_navigated_fluence_is_capped_before_sequencing():
    """A few high beamlets would close most of a beam's field at the sequencer's fluence steps; each beam's peaks are
    capped at peak_ratio times its median nonzero weight, and a note says how much fluence that was."""
    from radiarch.services.mco_deliverable import capped_fluence

    class _Beam:
        def __init__(self, beam_id, n):
            self.beam_id, self.n = beam_id, n

        def beamlets(self):
            return np.zeros((self.n, 4))

    class _Plan:
        beams = [_Beam("B1", 10), _Beam("B2", 5)]

    w = np.array([1.0] * 8 + [30.0, 0.0] + [2.0, 2.0, 2.0, 0.0, 50.0])
    capped, notes = capped_fluence(_Plan(), w, 6.0)
    assert capped[:10].tolist() == [1.0] * 8 + [6.0, 0.0] and capped[10:].tolist() == [2.0, 2.0, 2.0, 0.0, 12.0]
    assert len(notes) == 2 and notes[0].startswith("beam B1: 1 of 10 beamlets capped at 6 x the median (6)") and "B2" in notes[1]
    same, none = capped_fluence(_Plan(), w, None)
    assert same.tolist() == w.tolist() and none == []
    smooth, no_notes = capped_fluence(_Plan(), np.ones(15), 6.0)
    assert smooth.tolist() == [1.0] * 15 and no_notes == []


def _two_segment_problem():
    import scipy.sparse as sp

    S = sp.csr_matrix(np.array([[1.0, 0.2], [0.8, 0.3], [0.9, 0.0], [0.0, 0.1]]))      # 4 voxels, 2 segments
    grid = (1, 2, 2)
    organ = np.zeros(grid); organ.flat[2:] = 1.0
    target = np.zeros(grid); target.flat[:2] = 1.0

    def cost(d):                                                                          # the organ's dose pulls everything down
        s = float((d * organ).sum())
        return s * s, 2.0 * s * organ
    return S, grid, cost, target


def test_the_meterset_solves_meet_hard_constraints():
    """R11.9 (A): the segment and the arc-interval meterset solves hold a coverage limit the objectives alone would give up."""
    from radiarch.models.optimization import HardConstraint
    from radiarch.services.hard_constraints import HardConstraintTerm
    from radiarch.services.sequencing import optimize_segment_weights
    from radiarch.services.vmat import optimize_interval_mu

    S, grid, cost, target = _two_segment_problem()
    spec = HardConstraint(structure_name="T", metric="Dmin", op=">=", value_gy=1.0, tolerance_gy=0.01)
    free, _ = optimize_segment_weights(S, grid, cost, np.ones(2), max_iterations=200)
    assert float((S @ free)[:2].min()) < 0.5                                              # unconstrained: the target is given up
    held, conv = optimize_segment_weights(S, grid, cost, np.ones(2), max_iterations=200, hard_terms=[HardConstraintTerm(spec, target)])
    assert float((S @ held)[:2].min()) >= 1.0 - 0.02 and conv.success and list(conv.constraint_violations.values()) == [0.0]
    mu_min = np.array([0.05, 0.05])
    mu, conv = optimize_interval_mu(S, grid, cost, np.ones(2), mu_min, max_iterations=200, hard_terms=[HardConstraintTerm(spec, target)])
    assert np.all(mu >= mu_min - 1e-12) and float((S @ mu)[:2].min()) >= 1.0 - 0.02 and conv.success
