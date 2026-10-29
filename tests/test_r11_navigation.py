"""R11.3: navigation on a Pareto set (docs/reports/mco-research-and-design.md, D5, and §5's navigation tests).

A small synthetic problem (three structures, eight beamlets) gives a real Pareto set through the sandwich algorithm
and radiarch's trade-off objectives; the navigator is checked on it: blends are exact doses, exact values never exceed
the linear bound, a slider move reaches its value and moves no clamped or locked objective, a move beyond reach is
limited and said so, contradictory clamps are refused, goals and DVHs come from the blended dose. Then the routes, the
stored states and the SDK on the stub patient.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import minimize

from radiarch.models.dose import EngineSpec
from radiarch.models.evaluation import ClinicalGoal, GoalSetSpec
from radiarch.models.mco import MCOResult, NavigateRequest, ParetoPlan
from radiarch.models.optimization import ObjectiveSpec
from radiarch.services.navigation import NavigationError, Navigator
from radiarch.services.optimization import _objective_from_spec
from radiarch.services.pareto import Solved, sandwich

TRADEOFFS = [ObjectiveSpec(type="UniformRMS", structure_name="PTV", dose_gy=10.0, weight=1.0),
             ObjectiveSpec(type="MeanDose", structure_name="A", dose_gy=0.0, weight=1.0),
             ObjectiveSpec(type="MeanDose", structure_name="B", dose_gy=0.0, weight=1.0)]
NAMES = ["UniformRMS(PTV)", "MeanDose(A)", "MeanDose(B)"]


@pytest.fixture(scope="module")
def nav() -> Navigator:
    rng = np.random.default_rng(11)
    dij = rng.uniform(0.0, 1.0, (30, 8))
    dij[10:20, :4] += 1.5          # organ A sits in beamlets 0-3, organ B in 4-7
    dij[20:30, 4:] += 1.5
    masks = {"PTV": np.arange(30) < 10, "A": (np.arange(30) >= 10) & (np.arange(30) < 20), "B": np.arange(30) >= 20}
    objs = [_objective_from_spec(o) for o in TRADEOFFS]
    fm = [masks[o.structure_name].astype(float) for o in TRADEOFFS]

    def solve(w, warm):
        def fg(x):
            d = dij @ x
            v, g = 0.0, np.zeros(30)
            for wi, o, m in zip(w, objs, fm):
                a, b = o.value_and_grad(d, m)
                v, g = v + wi * a, g + wi * b
            return v, dij.T @ g
        r = minimize(fg, np.ones(8), jac=True, method="L-BFGS-B", bounds=[(0, None)] * 8, options={"ftol": 1e-14, "gtol": 1e-10, "maxiter": 2000})
        d = dij @ r.x
        return Solved(r.x, np.array([o.value(d, m) for o, m in zip(objs, fm)]))

    res = sandwich(solve, 3, budget=13, tol=0.01)
    doses = np.stack([dij @ p.solved.x for p in res.plans])
    norm = res.normalized()
    result = MCOResult(
        mco_id="m-1", cache_key="k", geometry_id="g", beam_model_id="b", engine_name="synthetic", engine_version="1",
        tradeoffs=TRADEOFFS, ideal_gy=list(res.ideal), nadir_gy=list(res.nadir),
        plans=[ParetoPlan(index=k, kind=p.kind, weights=list(p.raw_weights), values_gy=list(p.solved.values), normalized=list(norm[k]))
               for k, p in enumerate(res.plans)],
        error_bound=res.error, converged=True, navigation_structures=list(masks), navigation_voxels=30, voxel_cc=1.0,
        weights_uri="-", navigation_dose_uri="-")
    return Navigator(result, doses, masks)


def _mid(nav) -> np.ndarray:
    """An interior start: every plan equally (this problem's balance plan sits at zero dose)."""
    return np.full(len(nav.F), 1.0 / len(nav.F))


def _go(nav, start=None, **kw):
    start = _mid(nav) if start is None else start
    lam, clamps, notes = nav.navigate(NavigateRequest(**kw), start)
    return lam, clamps, notes


class TestBlend:
    def test_balance_is_the_balance_plan(self, nav):
        lam = nav.balance_blend()
        k = int(np.argmax(lam))
        assert nav.result.plans[k].kind == "balance"
        assert np.allclose(nav.exact(nav.dose(lam)), nav.F[k], rtol=1e-5, atol=1e-6)

    def test_a_blend_is_the_blend_of_doses_and_bounded_by_its_parents(self, nav):
        rng = np.random.default_rng(0)
        for _ in range(50):
            lam = rng.dirichlet(np.ones(len(nav.F)))
            d = nav.dose(lam)
            assert np.allclose(d, sum(l * nav.doses[j] for j, l in enumerate(lam)), rtol=1e-6)
            assert np.all(nav.exact(d) <= lam @ nav.F + 1e-6)


class TestMoves:
    # every move starts from the interior blend _mid
    def test_a_slider_reaches_its_value_and_the_others_share(self, nav):
        start = _mid(nav)
        a0 = float(start @ nav.F[:, 1])
        target = a0 - 0.4 * (a0 - nav.ideal[1])
        lam, _, notes = _go(nav, move={"MeanDose(A)": target})
        assert not notes and abs(lam.sum() - 1) < 1e-9 and np.all(lam >= 0)
        assert lam @ nav.F[:, 1] <= target + 1e-6
        assert nav.exact(nav.dose(lam))[1] <= target + 1e-6
        others = lam @ nav.F - start @ nav.F
        assert others[0] > 0 or others[2] > 0                    # the gain is paid for elsewhere

    def test_clamps_and_locks_hold(self, nav):
        start = _mid(nav)
        b0 = float(start @ nav.F[:, 2])
        a0 = float(start @ nav.F[:, 1])
        target = a0 - 0.3 * (a0 - nav.ideal[1])
        lam, clamps, _ = _go(nav, move={"1": target}, locks=["MeanDose(B)"])
        assert lam @ nav.F[:, 2] <= b0 + 1e-6 and clamps == {"MeanDose(B)": pytest.approx(b0, abs=1e-5)}
        cap = float(start @ nav.F[:, 0]) + 0.1
        lam, clamps, _ = _go(nav, move={"MeanDose(A)": target}, clamps={"UniformRMS(PTV)": cap})
        assert lam @ nav.F[:, 0] <= cap + 1e-6 and clamps == {"UniformRMS(PTV)": cap}

    def test_a_move_beyond_reach_is_limited_and_said_so(self, nav):
        start = _mid(nav)
        lock_ptv = float(start @ nav.F[:, 0])
        lam, _, notes = _go(nav, move={"MeanDose(A)": nav.ideal[1] - 5.0}, clamps={"UniformRMS(PTV)": lock_ptv})
        assert notes and "reaches only" in notes[0] and "MeanDose(A)" in notes[0]
        assert lam @ nav.F[:, 0] <= lock_ptv + 1e-6

    def test_better_slider_values_give_better_values(self, nav):
        start = _mid(nav)
        a0 = float(start @ nav.F[:, 1])
        got = [float(_go(nav, move={"MeanDose(A)": a0 - f * (a0 - nav.ideal[1])})[0] @ nav.F[:, 1]) for f in (0.1, 0.4, 0.8)]
        assert got[0] >= got[1] >= got[2]

    def test_a_reference_point(self, nav):
        start = _mid(nav)
        here = start @ nav.F
        ref = {"UniformRMS(PTV)": float(here[0]), "MeanDose(B)": float(here[2] - 0.2 * (here[2] - nav.ideal[2]))}
        lam, _, _ = _go(nav, reference=ref)
        assert lam @ nav.F[:, 2] < here[2]

    def test_refusals(self, nav):
        with pytest.raises(NavigationError, match="unknown objective"):
            _go(nav, move={"MeanDose(Liver)": 1.0})
        with pytest.raises(NavigationError, match="out of range"):
            _go(nav, move={"7": 1.0})
        with pytest.raises(NavigationError, match="meets these clamps"):
            _go(nav, clamps={"UniformRMS(PTV)": nav.ideal[0], "MeanDose(A)": nav.ideal[1], "MeanDose(B)": nav.ideal[2]})
        with pytest.raises(ValueError, match="not both"):
            NavigateRequest(move={"0": 1.0}, reference={"1": 1.0})


class TestReport:
    def test_goals_and_dvh_from_the_blended_dose(self, nav):
        lam = nav.balance_blend()
        d = nav.dose(lam)
        goals = GoalSetSpec(goals=[ClinicalGoal(structure="PTV", metric="Dmean[Gy]", op=">=", value=0.0, priority=1),
                                   ClinicalGoal(structure="A", metric="Dmax[Gy]", op="<=", value=float(d[10:20].max()) - 0.01, priority=2),
                                   ClinicalGoal(structure="Liver", metric="Dmean[Gy]", op="<=", value=5.0, priority=2)])
        st = nav.state(lam, NavigateRequest(goals=goals, dvh_bins=20), "s", {}, [], "balance")
        res = {g.structure: g for g in st.goals.results}
        assert res["PTV"].passed and res["A"].passed is False and res["Liver"].missing
        assert res["A"].achieved == pytest.approx(float(d[10:20].max()), rel=1e-6)
        assert any("Liver" in n and "navigation_structures" in n for n in st.notes)
        assert {c.structure for c in st.dvh} == {"PTV", "A", "B"} and all(len(c.dose_gy) == 20 for c in st.dvh)
        assert st.dvh[0].volume_pct[0] == 100.0
        assert all(v <= b + 1e-6 for v, b in zip(st.values_gy, st.bound_gy))


# ---------------------------------------------------------------------------
# Routes, states and SDK on the stub patient
# ---------------------------------------------------------------------------

from test_r6_rt_export_service import env  # noqa: E402,F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)


@pytest.fixture()
def rx(env, monkeypatch):  # noqa: F811
    import radiarch.app as radiarch_app
    from radiarch.api.routes import mco as routes
    from radiarch.sdk import Radiarch

    routes._service.cache_clear()
    routes._navigation.cache_clear()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with Radiarch.local(poll_interval=0.01) as client:
        yield client
    routes._service.cache_clear()
    routes._navigation.cache_clear()


def test_navigation_through_the_sdk(rx):
    from radiarch.models.mco import NavigationState
    from radiarch.sdk import RadiarchError, ops

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=6)

    states = ps.states()
    assert [s.state_id for s in states] == ["balance"] and states[0].name == "balance plan"
    bal = states[0]
    oar0 = bal.values_gy[1]
    st = ps.navigate(move={"MeanDose(OAR)": 0.8 * oar0}, name="spare the OAR",
                     goals={"goals": [{"structure": "PTV", "metric": "D95%[Gy]", "op": ">=", "value": 1.0, "priority": 1}]},
                     prescription_gy=2.0)
    assert isinstance(st, NavigationState) and st.from_state == "balance" and st.name == "spare the OAR"
    assert st.values_gy[1] <= 0.8 * oar0 + 1e-4 and st.values_gy[0] >= bal.values_gy[0] - 1e-6
    assert st.goals.n_goals == 1 and st.dvh
    assert [s.state_id for s in ps.states()] == ["balance", st.state_id]
    assert rx.get(f"/mco/{ps.id}/states/{st.state_id}")["state_id"] == st.state_id

    # onward from that state, with the OAR locked
    nxt = ps.navigate(from_state=st, move={"UniformRMS(PTV)": bal.values_gy[0]}, locks=["MeanDose(OAR)"], save=False)
    assert nxt.from_state == st.state_id and nxt.bound_gy[1] <= st.bound_gy[1] + 1e-6
    assert len(ps.states()) == 2                                          # not saved

    with pytest.raises(RadiarchError) as e:
        ps.navigate(move={"MeanDose(Liver)": 1.0})
    assert e.value.status_code == 422 and "unknown objective" in str(e.value.detail)
    with pytest.raises(RadiarchError) as e:
        ps.navigate(from_state="no-such-state")
    assert e.value.status_code == 404
    with pytest.raises(RadiarchError) as e:
        rx.post("/mco/no-such-set/navigate", {})
    assert e.value.status_code == 404
