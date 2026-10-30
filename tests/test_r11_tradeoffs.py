"""R11.1: convex trade-off objectives and hard constraints (docs/reports/mco-research-and-design.md, D1 and D2).

The trade-off objectives are checked for their values in Gy, their gradients against finite differences, and the
convexity a blend of plans relies on (f(l x + (1 - l) y) <= l f(x) + (1 - l) f(y)). The hard constraints are checked
against SciPy's SLSQP on small problems with the constraints written out, through the service on the analytic engine,
and for an infeasible set, which must be refused with its constraints named.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import minimize

from radiarch.models.dose import EngineSpec
from radiarch.models.dose import ScenarioSpec
from radiarch.models.optimization import (
    TRADEOFF_TYPES,
    ConstraintSpec,
    HardConstraint,
    ObjectiveSpec,
    OptimizationRunRequest,
    RobustnessSpec,
    SolverConfig,
    check_tradeoffs,
)
from radiarch.services.hard_constraints import HardConstraintTerm, InfeasibleConstraintsError, solve_with_hard_constraints
from radiarch.services.objectives import EUDMax, EUDMin, MeanDose, RMSOver, RMSUnder, UniformRMS
from radiarch.services.optimization import _objective_from_spec
from radiarch.services.optimization_solvers import get_solver

from test_optimization_service import _req, svc  # noqa: F401  (the stubbed service fixture)


def _tradeoffs(level: float = 10.0):
    return [MeanDose("S", level), EUDMax("S", level, 4.0), EUDMax("S", 0.0, 1.0), EUDMin("S", level, -8.0),
            EUDMin("S", level + 5.0, 0.5), RMSOver("S", level), RMSUnder("S", level), UniformRMS("S", level)]


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------

class TestTradeoffValues:
    def test_values_read_in_gy(self):
        d = np.array([8.0, 12.0, 10.0, 30.0])
        m = np.array([1.0, 1.0, 1.0, 0.0])          # the fourth voxel is outside the structure
        assert MeanDose("S", 0.0).value(d, m) == pytest.approx(10.0)
        assert MeanDose("S", 9.0).value(d, m) == pytest.approx(1.0)
        assert MeanDose("S", 11.0).value(d, m) == 0.0
        assert EUDMax("S", 0.0, 1.0).value(d, m) == pytest.approx(10.0)              # a = 1 is the mean
        assert EUDMax("S", 0.0, 60.0).value(d, m) == pytest.approx(12.0, abs=0.3)    # large a tends to the maximum
        assert EUDMin("S", 10.0, -60.0).value(d, m) == pytest.approx(2.0, abs=0.3)   # very negative a: the minimum
        s = RMSOver.SMOOTHING_GY                    # the RMS, smoothed at zero: below it by at most s
        assert RMSOver("S", 10.0).value(d, m) == pytest.approx(np.sqrt(4.0 / 3.0 + s * s) - s)
        assert RMSUnder("S", 10.0).value(d, m) == pytest.approx(np.sqrt(4.0 / 3.0 + s * s) - s)
        assert UniformRMS("S", 10.0).value(d, m) == pytest.approx(np.sqrt(8.0 / 3.0), abs=s)

    def test_the_rms_is_smooth_where_it_reaches_zero(self):
        # the plain RMS has a corner at zero (L-BFGS-B stalled there, R11.8): smoothed, its value and gradient go to 0
        m = np.ones(4)
        for t in (0.0, 1e-4, 1e-2):
            d = np.array([10.0 - t, 10.0, 11.0, 12.0])
            v, g = RMSUnder("S", 10.0).value_and_grad(d, m)
            assert v >= 0.0 and v <= t / 2.0 + 1e-12 and np.all(np.abs(g) <= t / (4 * RMSUnder.SMOOTHING_GY) + 1e-12)

    def test_an_organ_at_its_level_still_has_a_gradient(self):
        # at 0 Gy with a 0 Gy level the value is 0, but adding dose must cost: the one-sided subgradient, not zero
        d, m = np.zeros(5), np.array([1.0, 1.0, 1.0, 0.0, 0.0])
        for obj in (MeanDose("S", 0.0), EUDMax("S", 0.0, 1.0), EUDMax("S", 0.0, 6.0)):
            v, g = obj.value_and_grad(d, m)
            assert v == 0.0 and np.allclose(g, m / 3.0)

    def test_loss_is_weight_times_value(self):
        rng = np.random.default_rng(1)
        d, m = rng.uniform(0, 20, 50), (rng.uniform(size=50) > 0.3).astype(float)
        for cls in (MeanDose, RMSOver, RMSUnder, UniformRMS):
            one, five = cls("S", 10.0, 1.0), cls("S", 10.0, 5.0)
            assert five(d, m)[0] == pytest.approx(5.0 * one.value(d, m))
            assert np.allclose(five(d, m)[1], 5.0 * one(d, m)[1])

    @pytest.mark.parametrize("obj", _tradeoffs(), ids=lambda o: o.name)
    def test_gradient_matches_finite_differences(self, obj):
        rng = np.random.default_rng(7)
        d = rng.uniform(2.0, 20.0, 40)
        m = (rng.uniform(size=40) > 0.25).astype(float)
        v, g = obj.value_and_grad(d, m)
        if v == 0.0:
            pytest.skip("objective met at this dose")
        h = 1e-6
        for i in rng.choice(np.flatnonzero(m), 8, replace=False):
            e = np.zeros_like(d)
            e[i] = h
            fd = (obj.value(d + e, m) - obj.value(d - e, m)) / (2 * h)
            assert g[i] == pytest.approx(fd, rel=1e-4, abs=1e-7)
        assert np.all(g[m == 0] == 0.0)

    @pytest.mark.parametrize("obj", _tradeoffs(), ids=lambda o: o.name)
    def test_convex_so_a_blend_is_bounded_by_its_parents(self, obj):
        rng = np.random.default_rng(3)
        m = (rng.uniform(size=60) > 0.2).astype(float)
        for _ in range(40):
            x, y = rng.uniform(0.0, 25.0, 60), rng.uniform(0.0, 25.0, 60)
            for lam in (0.1, 0.35, 0.5, 0.8):
                blend = obj.value(lam * x + (1 - lam) * y, m)
                assert blend <= lam * obj.value(x, m) + (1 - lam) * obj.value(y, m) + 1e-9

    def test_the_dvh_surrogate_is_not_convex_which_is_why_it_is_refused(self):
        from radiarch.services.objectives import DVHMax

        obj, m = DVHMax("S", 8.0, 0.5), np.ones(4)        # at most half the structure above 8 Gy
        x, y = np.array([0.0, 0.0, 20.0, 20.0]), np.array([20.0, 20.0, 0.0, 0.0])
        blend = obj(0.5 * x + 0.5 * y, m)[0]
        assert blend > 0.5 * obj(x, m)[0] + 0.5 * obj(y, m)[0]


class TestTradeoffSpecs:
    def test_spec_builds_each_type(self):
        for t in TRADEOFF_TYPES:
            a = {"EUDMax": 2.0, "EUDMin": -10.0}.get(t)
            spec = ObjectiveSpec(type=t, structure_name="S", dose_gy=0.0, weight=1.0, eud_a=a)
            assert spec.is_tradeoff
            assert _objective_from_spec(spec).value(np.full(3, 5.0), np.ones(3)) >= 0.0

    def test_eud_exponent_ranges(self):
        with pytest.raises(ValueError, match="EUDMax needs eud_a >= 1"):
            ObjectiveSpec(type="EUDMax", structure_name="S", dose_gy=0.0, weight=1.0, eud_a=0.5)
        with pytest.raises(ValueError, match="EUDMax needs eud_a >= 1"):
            ObjectiveSpec(type="EUDMax", structure_name="S", dose_gy=0.0, weight=1.0)
        with pytest.raises(ValueError, match="EUDMin needs eud_a <= 1"):
            ObjectiveSpec(type="EUDMin", structure_name="S", dose_gy=60.0, weight=1.0, eud_a=2.0)

    def test_check_tradeoffs_refuses_nonconvex_and_squared_types(self):
        ok = [ObjectiveSpec(type="MeanDose", structure_name="Heart", dose_gy=0.0, weight=1.0)]
        check_tradeoffs(ok)
        bad = ok + [ObjectiveSpec(type="DVHMax", structure_name="Lung", dose_gy=20.0, weight=1.0, volume_fraction=0.3),
                    ObjectiveSpec(type="EUD", structure_name="Cord", dose_gy=20.0, weight=1.0)]
        with pytest.raises(ValueError, match=r"DVHMax\(Lung\), EUD\(Cord\)"):
            check_tradeoffs(bad)

    def test_earlier_objectives_and_requests_keep_their_hashes(self):
        # computed with the models before R11.1: an unset eud_a and no hard constraints change nothing
        o = ObjectiveSpec(type="EUD", structure_name="Heart", dose_gy=20.0, weight=5.0)
        assert o.hash() == "ad835e2d5b83e014"
        r = OptimizationRunRequest(
            geometry_id="g-1", beam_model_id="bm-1", dose_engine=EngineSpec(name="analytic"),
            objectives=[o, ObjectiveSpec(type="DVHMax", structure_name="Lung", dose_gy=20.0, weight=1.0, volume_fraction=0.3)],
            constraints=[ConstraintSpec(structure_name="Cord", type="max_dose", op="<=", value_gy=45.0, weight=10.0)],
            solver=SolverConfig(method="L-BFGS-B", max_iterations=50))
        assert r.compute_cache_key() == "547216dbc002d163ad15cd3ec31b3122ec56bf9eabd0627329fed0545a424a24"
        with_a = o.model_copy(update={"eud_a": 10.0})
        assert with_a.hash() != o.hash()
        hard = r.model_copy(update={"hard_constraints": [HardConstraint(structure_name="Cord", metric="Dmax", op="<=", value_gy=45.0)]})
        assert hard.compute_cache_key() != r.compute_cache_key()


class TestHardConstraintSpecs:
    @pytest.mark.parametrize("kw, msg", [
        (dict(metric="Dmax", op=">="), "Dmax takes <="),
        (dict(metric="Dmean", op=">="), "Dmean takes <="),
        (dict(metric="Dmin", op="<="), "Dmin takes >="),
        (dict(metric="gEUD", op="<="), "non-zero eud_a"),
        (dict(metric="gEUD", op="<=", eud_a=0.5), "gEUD <= needs eud_a >= 1"),
        (dict(metric="gEUD", op=">=", eud_a=4.0), "gEUD >= needs eud_a <= 1"),
    ])
    def test_only_convex_limits(self, kw, msg):
        with pytest.raises(ValueError, match=msg):
            HardConstraint(structure_name="S", value_gy=10.0, **kw)

    def test_not_in_a_robust_single_optimization(self):
        # robust hard constraints hold in every scenario of an MCO run (R11.6, test_r11_robust.py)
        with pytest.raises(ValueError, match="an MCO run"):
            _req(hard_constraints=[HardConstraint(structure_name="OAR", metric="Dmax", op="<=", value_gy=5.0)],
                 robustness=RobustnessSpec(enabled=True, aggregation="WORST_CASE",
                                           scenarios=[ScenarioSpec(name="x+", setup_shift_mm=(2.0, 0.0, 0.0))]))


# ---------------------------------------------------------------------------
# The augmented Lagrangian against SLSQP on small problems
# ---------------------------------------------------------------------------

def _small_problem(seed: int = 0):
    """20 voxels (target 0-9, organ 10-19) and 8 beamlets; organ voxels see the beamlets the target needs."""
    rng = np.random.default_rng(seed)
    dij = rng.uniform(0.0, 1.0, (20, 8))
    dij[10:] = 0.8 * dij[:10] + 0.2 * dij[10:]
    target = np.zeros(20)
    target[:10] = 1.0
    organ = 1.0 - target
    return dij, target, organ


def _solve(dij, terms, dose_terms, w0=None, stall_tol=None):
    w0 = np.ones(dij.shape[1]) if w0 is None else w0
    return solve_with_hard_constraints(terms, lambda w: dij @ w, lambda g: dij.T @ g, w0, get_solver("L-BFGS-B"),
                                       500, 1e-12, dose_terms=dose_terms, stall_tol=stall_tol)


def _slsqp(dij, f, cons):
    best = None
    for start in (np.ones(dij.shape[1]), np.full(dij.shape[1], 3.0)):
        r = minimize(lambda w: f(dij @ w), start, method="SLSQP", bounds=[(0, None)] * dij.shape[1],
                     constraints=cons, options={"maxiter": 1000, "ftol": 1e-12})
        if best is None or (r.success and r.fun < best.fun):
            best = r
    return best


class TestAugmentedLagrangian:
    def test_organ_maximum_against_slsqp(self):
        dij, target, organ = _small_problem()
        cover = UniformRMS("PTV", 10.0)
        free = _solve(dij, [], lambda d: cover(d, target))
        limit = 0.6 * float((dij @ free.weights)[organ > 0].max())
        con = HardConstraint(structure_name="OAR", metric="Dmax", op="<=", value_gy=limit, tolerance_gy=0.01)
        out = _solve(dij, [HardConstraintTerm(con, organ)], lambda d: cover(d, target))
        assert out.met and out.rounds >= 2
        assert (dij @ out.weights)[organ > 0].max() <= limit + 0.01
        ref = _slsqp(dij, lambda d: cover.value(d, target), [{"type": "ineq", "fun": lambda w: limit - (dij @ w)[10:]}])
        assert ref.success
        assert cover.value(dij @ out.weights, target) == pytest.approx(ref.fun, rel=2e-3, abs=1e-3)
        assert cover.value(dij @ out.weights, target) > cover.value(dij @ free.weights, target)

    def test_organ_mean_and_geud_against_slsqp(self):
        dij, target, organ = _small_problem(1)
        cover = UniformRMS("PTV", 10.0)
        mean_lim, eud_lim = 4.0, 6.0
        cons = [HardConstraint(structure_name="OAR", metric="Dmean", op="<=", value_gy=mean_lim, tolerance_gy=0.005),
                HardConstraint(structure_name="OAR", metric="gEUD", op="<=", value_gy=eud_lim, eud_a=8.0, tolerance_gy=0.005)]
        out = _solve(dij, [HardConstraintTerm(c, organ) for c in cons], lambda d: cover(d, target))
        assert out.met
        eud = EUDMax("OAR", 0.0, 8.0)
        ref = _slsqp(dij, lambda d: cover.value(d, target),
                     [{"type": "ineq", "fun": lambda w: mean_lim - (dij @ w)[10:].mean()},
                      {"type": "ineq", "fun": lambda w: eud_lim - eud.value(dij @ w, organ)}])
        assert ref.success
        assert cover.value(dij @ out.weights, target) == pytest.approx(ref.fun, rel=2e-3, abs=1e-3)

    def test_target_minimum_against_slsqp(self):
        dij, target, organ = _small_problem(2)
        spare = MeanDose("OAR", 0.0)
        con = HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=8.0, tolerance_gy=0.01)
        out = _solve(dij, [HardConstraintTerm(con, target)], lambda d: spare(d, organ))
        assert out.met
        assert (dij @ out.weights)[:10].min() >= 8.0 - 0.01
        ref = _slsqp(dij, lambda d: spare.value(d, organ), [{"type": "ineq", "fun": lambda w: (dij @ w)[:10] - 8.0}])
        assert spare.value(dij @ out.weights, organ) == pytest.approx(ref.fun, rel=2e-3, abs=1e-3)

    def test_the_penalty_starts_matched_to_the_objectives(self):
        # a fixed start of 10 was thousands of times the objectives' cost on TG-119 (R11.8): with every residual at its
        # tolerance, the penalty starts at RHO_SHARE of the cost, and the constraints still hold as the MCO solves them
        from radiarch.services.hard_constraints import RHO_SHARE, RHO_START, rho_start

        dij, target, organ = _small_problem()
        cover = UniformRMS("PTV", 10.0)
        free = _solve(dij, [], lambda d: cover(d, target))
        limit = 0.6 * float((dij @ free.weights)[organ > 0].max())
        con = HardConstraint(structure_name="OAR", metric="Dmax", op="<=", value_gy=limit, tolerance_gy=0.01)
        term = HardConstraintTerm(con, organ)
        rho = rho_start(2e-3, [term])
        assert rho < RHO_START and rho / 2 * 10 * 0.01 ** 2 == pytest.approx(RHO_SHARE * 2e-3)    # 10 organ voxels at 0.01 Gy
        assert rho_start(2.0, [term]) == rho_start(0.0, [term]) == RHO_START             # the ceiling; the feasibility run's

        def small(d):                                                                    # a cost the old start swamped
            v, g = cover(d, target)
            return 1e-3 * v, 1e-3 * g
        out = _solve(dij, [term], small, stall_tol=1e-5)
        assert out.rho_start < RHO_START and out.rho_start == pytest.approx(rho_start(small(dij @ np.ones(8))[0], [term]))
        assert out.met and out.success and (dij @ out.weights)[organ > 0].max() <= limit + 0.01
        ref = _slsqp(dij, lambda d: cover.value(d, target), [{"type": "ineq", "fun": lambda w: limit - (dij @ w)[10:]}])
        assert cover.value(dij @ out.weights, target) == pytest.approx(ref.fun, rel=2e-3, abs=1e-3)

    def test_success_is_the_final_rounds(self):
        # the early rounds solve for multipliers still moving, inexactly by design: an early round's stop does not
        # make the result unconverged (R11.8)
        dij, target, organ = _small_problem()
        cover = UniformRMS("PTV", 10.0)
        free = _solve(dij, [], lambda d: cover(d, target))
        limit = 0.6 * float((dij @ free.weights)[organ > 0].max())
        con = HardConstraint(structure_name="OAR", metric="Dmax", op="<=", value_gy=limit, tolerance_gy=0.01)

        class FirstRoundShort:
            calls = 0

            def run(self, cost_and_grad, w0, max_iter, tol, callback=None, **kw):
                FirstRoundShort.calls += 1
                w, info = get_solver("L-BFGS-B").run(cost_and_grad, w0, max_iter, tol, callback=callback, **kw)
                return w, info.model_copy(update={"success": info.success and FirstRoundShort.calls > 1})
        out = solve_with_hard_constraints([HardConstraintTerm(con, organ)], lambda w: dij @ w, lambda g: dij.T @ g,
                                          np.ones(dij.shape[1]), FirstRoundShort(), 500, 1e-12,
                                          dose_terms=lambda d: cover(d, target))
        assert out.met and out.rounds >= 2 and out.success

    def test_feasibility_run_reports_an_impossible_set(self):
        dij, target, organ = _small_problem()
        cons = [HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=10.0),
                HardConstraint(structure_name="PTV", metric="Dmax", op="<=", value_gy=5.0)]
        out = _solve(dij, [HardConstraintTerm(c, target) for c in cons], None)
        assert not out.met
        assert any(not o.met for o in out.outcomes)


# ---------------------------------------------------------------------------
# Through the service (analytic engine)
# ---------------------------------------------------------------------------

class TestServiceHardConstraints:
    def test_organ_limit_holds_and_is_reported(self, svc):
        free = svc.run(_req())
        import SimpleITK as sitk  # noqa: F401  (dose files are NIfTI)
        from radiarch.services.autoplan import read_volume

        oar_free = float(read_volume(free.dose_ref_uri)[1:3, 6:8, 2:6].max())
        limit = round(0.5 * oar_free, 3)
        res = svc.run(_req(hard_constraints=[HardConstraint(structure_name="OAR", metric="Dmax", op="<=", value_gy=limit,
                                                            tolerance_gy=0.02)]))
        c = res.convergence
        assert c.constraint_rounds >= 1 and len(c.hard_constraints) == 1
        assert c.hard_constraints[0].met and c.hard_constraints[0].achieved_gy <= limit + 0.02
        assert float(read_volume(res.dose_ref_uri)[1:3, 6:8, 2:6].max()) <= limit + 0.02
        assert res.cache_key != free.cache_key
        assert len(c.objective_values) == 1 and c.objective_values[0] > free.convergence.objective_values[0]

    def test_tradeoff_values_and_a_redundant_objective(self, svc):
        res = svc.run(_req(
            objectives=[ObjectiveSpec(type="UniformRMS", structure_name="PTV", dose_gy=10.0, weight=1.0),
                        ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=500.0, weight=1.0)],
            hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=1.0)]))
        vals = res.convergence.objective_values
        assert len(vals) == 2 and vals[1] == 0.0
        assert any("MeanDose(OAR" in n and "trades nothing" in n for n in res.convergence.notes)

    def test_infeasible_set_is_refused_with_its_constraints(self, svc):
        with pytest.raises(InfeasibleConstraintsError, match="no plan on these beams meets the hard constraints: .*PTV"):
            svc.run(_req(hard_constraints=[
                HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=10.0),
                HardConstraint(structure_name="PTV", metric="Dmax", op="<=", value_gy=5.0)]))
