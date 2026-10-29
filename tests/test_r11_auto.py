"""R11.4: automatic navigation by goal priority and projection onto the Pareto set (docs/reports/mco-research-and-design.md,
D6, and §5's tests).

A three-plan, three-voxel problem solved by hand checks the lexicographic order: each level reaches what it can, a
lower level never undoes a higher one beyond the slip. The projection is checked on a synthetic dose-matrix problem
(the projected plan is at least as good in every trade-off and better in their sum) and through the service; the
route and the SDK on the stub patient.
"""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.models.evaluation import ClinicalGoal, GoalSetSpec
from radiarch.models.mco import AutoNavigateRequest, MCOResult, ParetoPlan
from radiarch.models.optimization import HardConstraint, ObjectiveSpec
from radiarch.services.navigation import NavigationError, Navigator
from radiarch.services.optimization import _objective_from_spec

TRADEOFFS = [ObjectiveSpec(type="UniformRMS", structure_name="P", dose_gy=10.0, weight=1.0),
             ObjectiveSpec(type="MeanDose", structure_name="A", dose_gy=0.0, weight=1.0),
             ObjectiveSpec(type="MeanDose", structure_name="B", dose_gy=0.0, weight=1.0)]


@pytest.fixture(scope="module")
def toy() -> Navigator:
    """Voxels P, A, B; plan 0 treats P and A, plan 1 P and B, plan 2 only a little of P (the balance plan)."""
    doses = np.array([[10.0, 10.0, 0.0], [10.0, 0.0, 10.0], [4.0, 0.0, 0.0]])
    masks = {"P": np.array([True, False, False]), "A": np.array([False, True, False]), "B": np.array([False, False, True])}
    objs = [_objective_from_spec(o) for o in TRADEOFFS]
    F = np.array([[o.value(d, masks[t.structure_name].astype(float)) for o, t in zip(objs, TRADEOFFS)] for d in doses])
    ideal, nadir = F.min(axis=0), F.max(axis=0)
    result = MCOResult(
        mco_id="toy", cache_key="k", geometry_id="g", beam_model_id="b", engine_name="toy", engine_version="1", tradeoffs=TRADEOFFS,
        ideal_gy=list(ideal), nadir_gy=list(nadir),
        plans=[ParetoPlan(index=k, kind=("anchor", "anchor", "balance")[k], weights=[1, 1, 1], values_gy=list(F[k]),
                          normalized=list((F[k] - ideal) / np.where(nadir > ideal, nadir - ideal, 1))) for k in range(3)],
        error_bound=0.0, converged=True, navigation_structures=["P", "A", "B"], navigation_voxels=3, voxel_cc=1.0, weights_uri="-",
        navigation_dose_uri="-")
    return Navigator(result, doses, masks)


def _goals(*triples):
    return GoalSetSpec(goals=[ClinicalGoal(structure=s, metric=m, op=op, value=v, priority=p) for s, m, op, v, p in triples])


def _auto(nav, goals, **kw):
    req = AutoNavigateRequest(goals=goals, **kw)
    return nav.auto_navigate(req, nav.balance_blend())


class TestLexicographic:
    def test_a_three_level_problem_solved_by_hand(self, toy):
        # P = 10 l0 + 10 l1 + 4 l2, A = 10 l0, B = 10 l1.  Level 1: P >= 8 (l2 <= 1/3).  Level 2: A <= 3 (l0 <= 0.3).
        # Both are met and stay met, so level 3, B <= 3, cannot hold as well: l1 >= 1 - 1/3 - 0.3 = 0.367 and
        # B >= 3.67, a shortfall of 0.222.
        goals = _goals(("P", "Dmean[Gy]", ">=", 8.0, 1), ("A", "Dmax[Gy]", "<=", 3.0, 2), ("B", "Dmax[Gy]", "<=", 3.0, 3))
        lam, _, notes, levels = _auto(toy, goals)
        d = toy.dose(lam)
        assert [lv.priority for lv in levels] == [1, 2, 3] and not notes
        assert levels[0].shortfall_before > 0 and levels[0].shortfall == pytest.approx(0.0, abs=1e-6)
        assert d[0] >= 8.0 - 1e-4 and d[1] <= 3.0 + 1e-4
        assert d[2] == pytest.approx(3.667, abs=0.02) and levels[2].shortfall == pytest.approx(0.222, abs=0.01)
        assert levels[2].passed == 0

    def test_the_order_decides(self, toy):
        # the same goals with B first: B passes, A pays
        goals = _goals(("P", "Dmean[Gy]", ">=", 8.0, 1), ("B", "Dmax[Gy]", "<=", 3.0, 2), ("A", "Dmax[Gy]", "<=", 3.0, 3))
        lam, _, _, levels = _auto(toy, goals)
        d = toy.dose(lam)
        assert d[2] <= 3.0 + 1e-4 and d[1] == pytest.approx(3.667, abs=0.02)

    def test_a_lower_level_never_undoes_a_higher_one(self, toy):
        goals = _goals(("A", "Dmax[Gy]", "<=", 1.0, 1), ("P", "Dmean[Gy]", ">=", 9.5, 2))
        lam, _, _, levels = _auto(toy, goals)
        assert toy.dose(lam)[1] <= 1.0 + 1e-4 and levels[0].shortfall == pytest.approx(0.0, abs=1e-6)

    def test_a_missed_goal_may_slip_for_the_levels_below(self, toy):
        # P >= 11 cannot be met (best 10: a shortfall of 1/11); level 2 may cost it at most the 1 % slip
        goals = _goals(("P", "Dmean[Gy]", ">=", 11.0, 1), ("A", "Dmax[Gy]", "<=", 0.0, 2))
        lam, _, _, levels = _auto(toy, goals)
        d = toy.dose(lam)
        assert levels[0].shortfall == pytest.approx(1 / 11, abs=1e-4)
        assert d[0] >= 10.0 - 0.11 - 1e-3 and d[0] < 10.0 - 0.05            # it used the slip to lower A

    def test_clamps_hold_and_refusals(self, toy):
        goals = _goals(("P", "Dmean[Gy]", ">=", 9.9, 1))
        lam, clamps, _, _ = _auto(toy, goals, clamps={"MeanDose(A)": 2.0})
        assert lam @ toy.F[:, 1] <= 2.0 + 1e-6 and clamps == {"MeanDose(A)": 2.0}
        lam, _, notes, levels = _auto(toy, _goals(("Liver", "Dmean[Gy]", "<=", 1.0, 1), ("P", "Dmean[Gy]", ">=", 8.0, 1)))
        assert any("Liver" in n for n in notes) and levels[0].goals == 1
        with pytest.raises(NavigationError, match="fractions"):
            _auto(toy, GoalSetSpec(goals=goals.goals, dose_basis="EQD2"))
        with pytest.raises(NavigationError, match="prescription"):
            _auto(toy, _goals(("P", "D95%[%]", ">=", 95.0, 1)))

    def test_the_state_reports_the_levels_and_goals(self, toy):
        goals = _goals(("P", "Dmean[Gy]", ">=", 8.0, 1), ("A", "Dmax[Gy]", "<=", 3.0, 2))
        req = AutoNavigateRequest(goals=goals, name="auto")
        lam, clamps, notes, levels = toy.auto_navigate(req, toy.balance_blend())
        st = toy.state(lam, req, "s", clamps, notes, "balance", levels)
        assert st.name == "auto" and [lv.priority for lv in st.levels] == [1, 2]
        assert st.goals.n_goals == 2 and st.goals.all_priority1_passed


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

class TestProjection:
    def test_a_blend_off_the_front_is_moved_onto_it(self):
        from radiarch.services.mco import project_blend
        from radiarch.services.optimization_solvers import get_solver
        from radiarch.services.pareto import Solved, sandwich

        rng = np.random.default_rng(5)
        dij = rng.uniform(0.0, 1.0, (30, 8))
        dij[10:20, :4] += 1.5
        dij[20:30, 4:] += 1.5
        masks = {"PTV": np.arange(30) < 10, "A": (np.arange(30) >= 10) & (np.arange(30) < 20), "B": np.arange(30) >= 20}
        tradeoffs = [ObjectiveSpec(type="UniformRMS", structure_name="PTV", dose_gy=10.0, weight=1.0),
                     ObjectiveSpec(type="MeanDose", structure_name="A", dose_gy=0.0, weight=1.0),
                     ObjectiveSpec(type="MeanDose", structure_name="B", dose_gy=0.0, weight=1.0)]
        objs = [_objective_from_spec(o) for o in tradeoffs]
        fm = [masks[o.structure_name].astype(float) for o in tradeoffs]
        solver = get_solver("L-BFGS-B")
        fwd, back = (lambda w: dij @ w), (lambda g: dij.T @ g)

        def solve(w, warm):
            def fg(x):
                d = dij @ x
                v, g = 0.0, np.zeros(30)
                for wi, o, m in zip(w, objs, fm):
                    a, b = o.value_and_grad(d, m)
                    v, g = v + wi * a, g + wi * b
                return v, dij.T @ g
            x, _ = solver.run(fg, np.ones(8), 2000, 1e-14)
            d = dij @ x
            return Solved(np.asarray(x), np.array([o.value(d, m) for o, m in zip(objs, fm)]))

        res = sandwich(solve, 3, budget=4, tol=0.0)              # three anchors and the balance plan: a coarse set
        span = res.nadir - res.ideal
        x0 = 0.5 * res.plans[0].solved.x + 0.5 * res.plans[1].solved.x
        f0 = np.array([o.value(dij @ x0, m) for o, m in zip(objs, fm)])
        x, dose, notes = project_blend(objs, fm, fwd, back, [], x0, span, solver, 2000, 1e-12, ["PTV", "A", "B"])
        f = np.array([o.value(dose, m) for o, m in zip(objs, fm)])
        assert not notes
        assert np.all(f <= f0 + 0.01 + 1e-9)                                  # no trade-off worse (cap tolerance 0.01 Gy)
        assert (f / span).sum() < (f0 / span).sum() - 0.01                    # and their sum better

    def test_through_the_service(self, msvc):
        from test_r11_pareto import _mreq

        res = msvc.run(_mreq(hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=5.0)]))
        lam = np.zeros(len(res.plans))
        lam[0], lam[1] = 0.5, 0.5
        x, nav_dose, notes = msvc.project(res.mco_id, lam)
        index, doses, masks = msvc.store.load_navigation(res.mco_id)
        assert x.shape[0] == msvc.store.load_weights(res.mco_id).shape[1] and nav_dose.shape == index.shape
        blend = lam @ doses
        from radiarch.services.objectives import MeanDose, UniformRMS

        for obj, name, k in ((UniformRMS("PTV", 10.0), "PTV", 0), (MeanDose("OAR", 0.0), "OAR", 1)):
            assert obj.value(nav_dose, masks[name].astype(float)) <= obj.value(blend, masks[name].astype(float)) + 0.011
        assert float(nav_dose[masks["PTV"]].min()) >= 5.0 - 0.1                                   # the hard constraint holds


from test_r11_pareto import msvc, svc  # noqa: E402,F401  (the stubbed services)


# ---------------------------------------------------------------------------
# Route and SDK on the stub patient
# ---------------------------------------------------------------------------

from test_r11_navigation import rx  # noqa: E402,F401
from test_r6_rt_export_service import env  # noqa: E402,F401


def test_automatic_navigation_through_the_sdk(rx):
    from radiarch.sdk import RadiarchError, ops

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=6,
                hard_constraints=[ops.hard("PTV", "Dmin", ">=", 0.5)])
    bal = ps.states()[0]
    goals = {"goals": [{"structure": "PTV", "metric": "Dmean[Gy]", "op": ">=", "value": 1.8, "priority": 1},
                       {"structure": "OAR", "metric": "Dmean[Gy]", "op": "<=", "value": 0.0, "priority": 2}]}
    st = ps.auto_navigate(goals, name="auto")
    assert [lv.priority for lv in st.levels] == [1, 2] and st.name == "auto" and st.from_state == "balance"
    assert st.goals.n_goals == 2 and st.state_id in [s.state_id for s in ps.states()]
    assert st.values_gy != bal.values_gy
    with pytest.raises(RadiarchError) as e:
        ps.auto_navigate({"goals": [{"structure": "PTV", "metric": "D95%[%]", "op": ">=", "value": 95, "priority": 1}]})
    assert e.value.status_code == 422 and "prescription" in str(e.value.detail)
    with pytest.raises(RadiarchError) as e:
        ps.auto_navigate("no-such-template")
    assert e.value.status_code == 422
