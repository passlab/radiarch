"""R11.2: the Pareto set (docs/reports/mco-research-and-design.md, D3, D4, and the tests of §5).

The sandwich algorithm is checked on problems whose Pareto fronts are known: its error bound must cover the true
error, never grow as plans are added, and reach the tolerance; every plan's weights must support the set it found; no
plan may dominate another. Then the service on the analytic engine (anchors, balance, sandwich plans, the stored
navigation doses, hard constraints, the cache) and the route, job, SDK and lineage on the stub patient.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import minimize

from radiarch.models.mco import MCORunRequest
from radiarch.models.dose import EngineSpec
from radiarch.models.optimization import HardConstraint, ObjectiveSpec, SolverConfig
from radiarch.services.pareto import Solved, distance_to_inner, normalize, sandwich

from test_optimization_service import _fake_beam_model_bundle, _fake_geometry_bundle  # noqa: F401


def _quadratics(anchors):
    """f_i(x) = |x - a_i|^2: convex, its Pareto set the convex hull of the a_i."""
    A = np.asarray(anchors, float)
    n, dim = A.shape

    def solve(w, warm):
        f = lambda x: sum(w[i] * np.sum((x - A[i]) ** 2) for i in range(n))         # noqa: E731
        g = lambda x: sum(2 * w[i] * (x - A[i]) for i in range(n))                   # noqa: E731
        r = minimize(f, np.full(dim, 0.3), jac=g, method="L-BFGS-B", options={"ftol": 1e-15, "gtol": 1e-12})
        return Solved(r.x, np.array([np.sum((r.x - A[i]) ** 2) for i in range(n)]))
    return solve, n


def _true_error(res, solve, n, samples=200, seed=0):
    """The largest distance from a Pareto point (weighted sums with random weights) to the plans' hull."""
    rng = np.random.default_rng(seed)
    P = res.normalized()
    worst = 0.0
    for _ in range(samples):
        z = normalize(solve(rng.dirichlet(np.ones(n)), None).values, res.ideal, res.nadir)
        worst = max(worst, distance_to_inner(P, z)[0])
    return worst


class TestSandwich:
    def test_two_objectives_known_front(self):
        # f1 = t^2, f2 = (1 - t)^2 along the segment: the front f2 = (1 - sqrt(f1))^2
        solve, n = _quadratics([[0.0, 0.0], [1.0, 0.0]])
        res = sandwich(solve, n, budget=30, tol=0.01)
        assert res.error <= 0.01 and "within" in res.stop_reason
        assert [p.kind for p in res.plans[:3]] == ["anchor", "anchor", "balance"]
        for p in res.plans:
            f1, f2 = p.solved.values
            assert f2 == pytest.approx((1 - np.sqrt(f1)) ** 2, abs=1e-6)          # every plan is on the true front
        t = np.linspace(0, 1, 400)
        P = res.normalized()
        true = max(distance_to_inner(P, np.array([ti ** 2, (1 - ti) ** 2]))[0] for ti in t)
        assert true <= res.error + 1e-9

    @pytest.mark.parametrize("anchors", [[[0, 0], [1, 0], [0.5, 0.9]], [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]])
    def test_bound_covers_the_true_error_and_never_grows(self, anchors):
        solve, n = _quadratics(anchors)
        res = sandwich(solve, n, budget=4 * n + 1, tol=0.02)
        errs = [e for _, e in res.history]
        assert all(b <= a + 1e-6 for a, b in zip(errs, errs[1:]))
        assert errs[-1] < errs[0]
        assert _true_error(res, solve, n) <= res.error + 1e-6
        assert len(res.plans) <= 4 * n + 1

    @pytest.mark.parametrize("n", [3, 4])
    def test_a_spherical_front_in_n_objectives(self, n):
        # the scalable test problem: minimize f(x) = x over the ball |x - 1| <= 1; the front is the part of the sphere
        # facing the origin, and a weighted sum has its minimum at 1 - w / |w|
        def solve(w, warm):
            x = 1.0 - w / np.linalg.norm(w)
            return Solved(x, x.copy())
        res = sandwich(solve, n, budget=4 * n + 1, tol=0.0)
        errs = [e for _, e in res.history]
        assert all(b <= a + 1e-9 for a, b in zip(errs, errs[1:])) and errs[-1] < errs[0]
        for p in res.plans:
            assert np.linalg.norm(p.solved.values - 1.0) == pytest.approx(1.0)          # every plan on the front
        rng = np.random.default_rng(1)
        P = res.normalized()
        true = max(distance_to_inner(P, normalize(solve(rng.dirichlet(np.ones(n)), None).values, res.ideal, res.nadir))[0]
                   for _ in range(300))
        assert true <= res.error + 1e-9

    def test_an_unconverged_plan_proves_nothing(self):
        # a solve stopped short of the optimum (R11.8's proton case at 200 iterations): its point is worse than the
        # front, and a hyperplane through it would cut off Pareto points and understate the error
        good, n = _quadratics([[0, 0], [1, 0], [0.5, 0.9]])

        def stopped(ok):
            def solve(w, warm):
                s = good(w, warm)
                if len(calls) == n:                      # the balance plan stops early, well off the front
                    x = s.x + np.array([0.0, 0.6])
                    s = Solved(x, np.array([np.sum((x - a) ** 2) for a in np.array([[0, 0], [1, 0], [0.5, 0.9]])]), ok=ok)
                calls.append(1)
                return s
            return solve
        for ok, covered in ((False, True), (True, False)):
            calls = []
            res = sandwich(stopped(ok), n, budget=n + 1, tol=0.0)
            assert (_true_error(res, good, n) <= res.error + 1e-6) is covered

    def test_weights_support_the_set_and_no_plan_dominates(self):
        solve, n = _quadratics([[0, 0], [1, 0], [0.5, 0.9]])
        res = sandwich(solve, n, budget=13, tol=0.0)
        P = res.normalized()
        span = res.nadir - res.ideal
        for k, p in enumerate(res.plans):
            a = p.raw_weights * span
            assert np.all(a @ P[k] <= P @ a + 1e-6)             # plan k minimizes its own weighted sum among the plans
            for j in range(len(P)):
                if j != k:
                    assert not (np.all(P[j] <= P[k] - 1e-6))    # no plan strictly better in every objective

    def test_anchors_fix_the_ideal_and_nadir(self):
        solve, n = _quadratics([[0, 0], [2, 0], [0, 1]])
        res = sandwich(solve, n, budget=4, tol=0.0)
        anchors = np.array([p.solved.values for p in res.plans if p.kind == "anchor"])
        assert np.allclose(res.ideal, anchors.min(axis=0)) and np.allclose(res.nadir, anchors.max(axis=0))
        assert np.allclose(np.diag(normalize(anchors, res.ideal, res.nadir)), 0.0, atol=1e-3)
        assert len(res.plans) == 4 and "budget" in res.stop_reason

    def test_needs_two_objectives(self):
        solve, _ = _quadratics([[0, 0], [1, 0]])
        with pytest.raises(ValueError, match="two objectives"):
            sandwich(solve, 1, 4)


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------

def _mreq(**over) -> MCORunRequest:
    kw = dict(geometry_id="g-1", beam_model_id="bm-1", dose_engine=EngineSpec(name="analytic"),
              tradeoffs=[ObjectiveSpec(type="UniformRMS", structure_name="PTV", dose_gy=10.0, weight=1.0),
                         ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=0.0, weight=1.0)],
              solver=SolverConfig(method="L-BFGS-B", max_iterations=200))
    kw.update(over)
    return MCORunRequest(**kw)


class TestRequest:
    def test_refuses_nonconvex_tradeoffs_and_duplicates(self):
        with pytest.raises(ValueError, match="not trade-off objectives"):
            _mreq(tradeoffs=[ObjectiveSpec(type="DVHMax", structure_name="OAR", dose_gy=5, weight=1, volume_fraction=0.2),
                             ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=0, weight=1)])
        with pytest.raises(ValueError, match="same type on the same structure"):
            _mreq(tradeoffs=[ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=0, weight=1),
                             ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=5, weight=1)])
        with pytest.raises(ValueError, match="at least 2"):
            _mreq(tradeoffs=[ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=0, weight=1)])

    def test_budget(self):
        assert _mreq().budget == 7
        assert _mreq(plan_budget=9).budget == 9
        with pytest.raises(ValueError, match="at most 4 N"):
            _mreq(plan_budget=10)

    def test_cache_key_ignores_the_tradeoff_weights(self):
        a = _mreq()
        b = _mreq(tradeoffs=[o.model_copy(update={"weight": 7.0}) for o in a.tradeoffs])
        assert a.compute_cache_key() == b.compute_cache_key()
        assert _mreq(error_tolerance=0.01).compute_cache_key() != a.compute_cache_key()


# ---------------------------------------------------------------------------
# The service on the analytic engine
# ---------------------------------------------------------------------------

@pytest.fixture
def msvc(svc):  # noqa: F811  (the stubbed OptimizationService)
    import tempfile

    from radiarch.services.mco import MCOService

    d = tempfile.TemporaryDirectory()
    yield MCOService(base_dir=d.name, optimization_service=svc)
    d.cleanup()


from test_optimization_service import svc  # noqa: E402,F401


class TestService:
    def test_every_solve_uses_the_stall_test(self, msvc, monkeypatch):
        # converged when the cost has stopped falling (R11.8: tests on the projected gradient, absolute or relative to
        # the run's start, and on the gain still on offer, failed on TG-119)
        import radiarch.services.mco as mco_mod
        from radiarch.services.mco import STALL_RELATIVE
        from radiarch.services.optimization_solvers import get_solver

        seen = []

        class Recording:
            def run(self, cost_and_grad, w0, max_iter, tol, callback=None, stall_tol=None):
                seen.append(stall_tol)
                return get_solver("L-BFGS-B").run(cost_and_grad, w0, max_iter, tol, callback=callback, stall_tol=stall_tol)
        monkeypatch.setattr(mco_mod, "get_solver", lambda method: Recording())
        res = msvc.run(_mreq(plan_budget=5))
        assert len(seen) == len(res.plans) >= 3 and all(t == STALL_RELATIVE for t in seen)

    def test_a_tiny_dose_matrix_still_moves(self):
        from radiarch.services.mco import STALL_RELATIVE
        from radiarch.services.optimization_solvers import get_solver

        A = np.array([[1e-7, 2e-7], [3e-7, 0.0]])                        # gradients far below scipy's absolute tests
        best = np.array([3.0, 2.0])
        target = A @ best
        terms = lambda d: (float(np.sum((d - target) ** 2)), 2 * (d - target))   # noqa: E731
        fwd, bwd = (lambda w: A @ w), (lambda g: A.T @ g)                 # noqa: E731
        cg = lambda w: (terms(fwd(w))[0], bwd(terms(fwd(w))[1]))          # noqa: E731
        w0 = np.array([1.0, 1.0])
        stuck, _ = get_solver("L-BFGS-B").run(cg, w0, 500, 1e-15)
        assert np.allclose(stuck, w0)                                    # scipy's tests: it never moves
        moved, info = get_solver("L-BFGS-B").run(cg, w0, 500, 1e-15, stall_tol=STALL_RELATIVE)
        assert info.success and np.allclose(moved, best, rtol=1e-3)

    def test_a_solve_runs_until_its_cost_stops_falling(self):
        # scipy's cost-change test is absolute for costs below 1: one step that barely moves stops it, and scipy calls
        # that converged (R11.8: a TG-119 plan and a lung anchor). With the stall test it is off.
        from radiarch.services.optimization_solvers import get_solver

        a, c = np.linspace(1.0, 50.0, 30), np.linspace(0.5, 2.0, 30)
        cg = lambda w: (float(0.5 * np.sum(a * (w - c) ** 2)), a * (w - c))   # noqa: E731
        w0 = np.full(30, 10.0)
        lbfgsb = get_solver("L-BFGS-B")
        x, info = lbfgsb.run(cg, w0, 2000, 1e-2)
        assert info.success and np.abs(x - c).max() > 1e-2                    # scipy's word: converged, short of it
        x, info = lbfgsb.run(cg, w0, 2000, 1e-2, stall_tol=1e-5)
        assert info.success and np.abs(x - c).max() < 1e-5 and info.remaining_gain is not None

    def test_a_solve_at_the_iteration_cap_is_judged_by_the_stall_test(self):
        from radiarch.services.optimization_solvers import get_solver

        a, c = np.linspace(1.0, 50.0, 30), np.linspace(0.5, 2.0, 30)
        cg = lambda w: (float(0.5 * np.sum(a * (w - c) ** 2)), a * (w - c))   # noqa: E731
        _, info = get_solver("L-BFGS-B").run(cg, np.full(30, 10.0), 3, 1e-15, stall_tol=1e-5)
        assert not info.success and info.iterations == 3                       # still falling at the cap

    def test_the_stall_test(self):
        from radiarch.services.optimization_solvers import STALL_WINDOW, stalled

        flat = [1.0 + 1e-7 * (STALL_WINDOW - k) for k in range(STALL_WINDOW + 1)]   # fell by 5e-6 of itself in the window
        assert stalled(flat, 1e-5) and not stalled(flat, 1e-6)
        assert not stalled(flat[1:], 1e-5)                                        # too short to judge
        one_step = [2.0] * STALL_WINDOW + [1.0]                                   # a big step at the end: still falling
        assert not stalled(one_step, 1e-5)
        assert stalled([3e-9] * (STALL_WINDOW + 1), 1e-5)                         # free of the cost's scale

    def test_the_gain_on_offer(self):
        from radiarch.services.optimization_solvers import gain_on_offer

        # a weight at 3 the gradient pushes up (box up to 6: gain 2 x 3) and one at 1e-6 it pushes down (gain 5e-6)
        assert gain_on_offer(np.array([5.0, -2.0, 0.0]), np.array([1e-6, 3.0, 0.0]), 3.0) == pytest.approx(6.000005)
        assert gain_on_offer(np.array([5.0, 0.0]), np.array([0.0, 2.0]), 2.0) == 0.0     # an optimum on x >= 0
        assert gain_on_offer(np.array([-1.0]), np.array([0.0]), 0.0) == float("inf")     # no size to measure by

    def test_the_nominal_dose_is_computed_in_float64(self, msvc):
        # the engines' apply_influence works in float32: the cost became a staircase at 1e-7 of the weights, and line
        # searches near an optimum failed (R11.8, TG-119)
        req = _mreq()
        prob = msvc.optimization._assemble_problem(msvc._base(req))
        forward, backward, _ = msvc.optimization.nominal_ops(prob)
        w = np.ones(backward(np.zeros(prob.grid_shape)).size)
        d = forward(w)
        assert d.dtype == np.float64 and np.any(forward(w * (1.0 + 1e-9)) != d)
        g = np.random.default_rng(0).random(d.shape)
        assert float(np.sum(d * g)) == pytest.approx(float(w @ backward(g)), rel=1e-12)   # the adjoint of the backward

    def test_every_plan_records_the_gain_left(self, msvc):
        # reported, not tested: the stall test decides convergence
        for req in (_mreq(plan_budget=5), _mreq(plan_budget=5, hard_constraints=[
                HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=1.0, tolerance_gy=0.05)])):
            res = msvc.run(req)
            assert all(p.gain is not None and p.gain >= 0.0 for p in res.plans)
            assert all(p.converged for p in res.plans)                          # a small problem converges within its budget

    def test_a_pareto_set_and_its_navigation_doses(self, msvc):
        stages = []
        res = msvc.run(_mreq(navigation_structures=["PTV"]), progress_callback=lambda s, f, m: stages.append(s.value))
        assert [p.kind for p in res.plans[:3]] == ["anchor", "anchor", "balance"] and len(res.plans) <= 7
        assert res.error_history and res.error_bound == res.error_history[-1].error
        assert res.converged == (res.error_bound <= 0.05)
        # anchors: each the best in its own objective
        assert res.plans[0].values_gy[0] == pytest.approx(res.ideal_gy[0]) and res.plans[1].values_gy[1] == pytest.approx(res.ideal_gy[1])
        assert res.ideal_gy[1] < res.nadir_gy[1]
        assert {"loading", "anchors", "persisting", "done"} <= set(stages)

        index, doses, masks = msvc.store.load_navigation(res.mco_id)
        weights = msvc.store.load_weights(res.mco_id)
        assert doses.shape == (len(res.plans), index.size) == (len(res.plans), res.navigation_voxels)
        assert weights.shape[0] == len(res.plans) and set(masks) == {"PTV", "OAR"}
        assert res.navigation_voxels == int(sum(m.sum() for m in masks.values()))   # PTV and OAR do not overlap here
        # a plan's stored dose reproduces its stored values
        from radiarch.services.objectives import MeanDose, UniformRMS

        for k, p in enumerate(res.plans):
            d = doses[k]
            assert UniformRMS("PTV", 10.0).value(d, masks["PTV"].astype(float)) == pytest.approx(p.values_gy[0], rel=1e-4, abs=1e-5)
            assert MeanDose("OAR", 0.0).value(d, masks["OAR"].astype(float)) == pytest.approx(p.values_gy[1], rel=1e-4, abs=1e-5)
        assert msvc.run(_mreq(navigation_structures=["PTV"])).mco_id == res.mco_id                  # cached

    def test_hard_constraints_hold_in_every_plan(self, msvc):
        free = msvc.run(_mreq())
        oar_cap = round(0.5 * max(p.values_gy[1] for p in free.plans), 4)
        res = msvc.run(_mreq(hard_constraints=[HardConstraint(structure_name="OAR", metric="Dmean", op="<=", value_gy=oar_cap,
                                                              tolerance_gy=0.01)]))
        assert all(p.values_gy[1] <= oar_cap + 0.01 for p in res.plans)
        assert res.nadir_gy[1] <= oar_cap + 0.01

    def test_infeasible_constraints_are_refused(self, msvc):
        from radiarch.services.hard_constraints import InfeasibleConstraintsError

        with pytest.raises(InfeasibleConstraintsError, match="PTV"):
            msvc.run(_mreq(hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=10.0),
                                             HardConstraint(structure_name="PTV", metric="Dmax", op="<=", value_gy=5.0)]))

    def test_a_plan_without_dose_is_noted_and_a_coverage_constraint_prevents_it(self, msvc):
        res = msvc.run(_mreq())                     # the OAR's anchor switches every beamlet off
        assert any("deliver no dose" in n and "PTV Dmin" in n for n in res.notes)
        cov = msvc.run(_mreq(hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=5.0)]))
        assert not any("deliver no dose" in n for n in cov.notes)

    def test_an_objective_that_trades_nothing_is_noted(self, msvc):
        res = msvc.run(_mreq(tradeoffs=[ObjectiveSpec(type="UniformRMS", structure_name="PTV", dose_gy=10.0, weight=1.0),
                                        ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=1000.0, weight=1.0)]))
        assert any("MeanDose(OAR)" in n and "trades nothing" in n for n in res.notes)


# ---------------------------------------------------------------------------
# Route, job, SDK and lineage on the stub patient
# ---------------------------------------------------------------------------

from test_r6_rt_export_service import env  # noqa: E402,F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)


@pytest.fixture()
def rx(env, monkeypatch):  # noqa: F811
    import radiarch.app as radiarch_app
    from radiarch.api.routes import mco as routes
    from radiarch.sdk import Radiarch

    routes._service.cache_clear()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with Radiarch.local(poll_interval=0.01) as client:
        yield client
    routes._service.cache_clear()


def test_a_pareto_set_through_the_sdk(rx):
    from radiarch.sdk import ParetoSet, RadiarchError, ops

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=1000, plan_budget=6)
    assert isinstance(ps, ParetoSet) and ps.beam_model_id == bm.id and 3 <= len(ps.plans) <= 6
    rows = ps.table()
    assert rows[0]["kind"] == "anchor" and set(rows[0]) == {"plan", "kind", "UniformRMS(PTV)", "MeanDose(OAR)"}
    assert rx.get(f"/mco/{ps.id}")["mco_id"] == ps.id
    assert bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=1000, plan_budget=6).id == ps.id

    graph = ps.lineage()
    assert {n["ref"]["kind"] for n in graph["nodes"]} >= {"mco", "beam_model", "geometry"}

    with pytest.raises(ValueError, match="not trade-off objectives"):          # the SDK validates before it sends
        bm.mco([ops.uniform_rms("PTV", 2.0), ops.dvh_max("OAR", 1.0, 0.2)], engine="analytic")
    body = {"geometry_id": geo.id, "beam_model_id": bm.id, "dose_engine": {"name": "analytic"},
            "tradeoffs": [ops.uniform_rms("PTV", 2.0).model_dump(), ops.dvh_max("OAR", 1.0, 0.2).model_dump()]}
    with pytest.raises(RadiarchError) as e:                                    # and so does the server
        rx.request("POST", "/mco/run", json=body)
    assert e.value.status_code == 422 and "not trade-off objectives" in str(e.value.detail)
    assert all(p.converged for p in ps.plans) and all("deliver no dose" in n for n in ps.notes)
    with pytest.raises(RadiarchError) as e:
        rx.get("/mco/no-such-set")
    assert e.value.status_code == 404
    with pytest.raises(RadiarchError) as e:
        bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic",
               hard_constraints=[ops.hard("PTV", "Dmin", ">=", 50.0), ops.hard("PTV", "Dmax", "<=", 1.0)])
    assert "InfeasibleConstraintsError" in str(e.value) and "PTV Dmin" in str(e.value)
