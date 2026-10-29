"""R11.6: robust MCO (docs/reports/mco-research-and-design.md, D8).

The pieces first: the worst case of a trade-off over a stacked dose, the smoothed scenario-wise weighted sum (its
gradient and its lower bound), a hard constraint in one scenario, the stacked dose operators. Then the sandwich on a
small robust problem: every attainable vector of worst cases must lie in the outer set its bounds prove, and within
the error bound of the plans' hull. Then the service on the stubbed patient: worst-case and nominal values, the stored
scenario doses, hard constraints in every scenario, navigation and automatic navigation on worst cases, and the
deliverable plan of a robust proton set.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import minimize
from scipy.sparse import csr_matrix

from radiarch.models.dose import ScenarioSpec
from radiarch.models.mco import AutoNavigateRequest, DeliverableRequest, NavigateRequest
from radiarch.models.optimization import HardConstraint, RobustnessSpec
from radiarch.services.objectives import MeanDose, UniformRMS
from radiarch.services.pareto import distance_to_inner, normalize, sandwich, Solved
from radiarch.services.robust_mco import ScenarioTerm, StackedOps, WorstCase, scenario_wise

from test_r11_pareto import _mreq, msvc, svc  # noqa: F401  (the stubbed services: a proton beam model, the analytic engine)

ROB = RobustnessSpec(enabled=True, scenarios=[ScenarioSpec(name="dens_up", density_scale=1.1),
                                              ScenarioSpec(name="dens_down", density_scale=0.9),
                                              ScenarioSpec(name="range_up", range_scale=1.2)])
COVER = [HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=5.0)]


# ---------------------------------------------------------------------------
# The pieces
# ---------------------------------------------------------------------------

def _small():
    """Two scenarios of a 5-voxel dose from 3 elements: voxels 0-2 a target, 3-4 an organ; the second scenario
    moves dose from the target's first voxel into the organ (a shift)."""
    A = np.array([[1.0, 0.2, 0.0], [0.6, 0.8, 0.3], [0.1, 0.5, 1.0], [0.3, 0.1, 0.0], [0.0, 0.2, 0.4]])
    B = A.copy()
    B[0] *= 0.7
    B[3] += 0.25
    target = np.array([1.0, 1.0, 1.0, 0.0, 0.0])
    organ = np.array([0.0, 0.0, 0.0, 1.0, 1.0])
    return StackedOps([csr_matrix(A), csr_matrix(B)]), [UniformRMS("T", 2.0), MeanDose("O", 0.0)], [target, organ]


class TestPieces:
    def test_stacked_operators_are_adjoint(self):
        ops, _, _ = _small()
        rng = np.random.default_rng(0)
        w, G = rng.uniform(size=3), rng.normal(size=(2, 5))
        assert ops.forward(w).shape == (2, 5)
        assert np.sum(ops.forward(w) * G) == pytest.approx(w @ ops.backward(G))

    def test_worst_case_and_its_gradient(self):
        ops, objs, masks = _small()
        D = ops.forward(np.array([1.0, 1.0, 1.0]))
        wc = WorstCase(objs[1])
        per = [objs[1].value(D[s], masks[1]) for s in range(2)]
        assert wc.value(D, masks[1]) == pytest.approx(max(per)) and wc.nominal(D, masks[1]) == pytest.approx(per[0])
        v, g = wc.value_and_grad(D, masks[1])
        assert g.shape == D.shape and np.all(g[int(np.argmin(per))] == 0.0) and v == pytest.approx(max(per))

    def test_scenario_wise_gradient_and_bound(self):
        ops, objs, masks = _small()
        raw = np.array([0.7, 0.3])
        terms, bound = scenario_wise(objs, masks, raw)
        rng = np.random.default_rng(1)
        for _ in range(5):
            D = ops.forward(rng.uniform(0.5, 3.0, 3))
            sums = [sum(r * o.value(D[s], m) for r, o, m in zip(raw, objs, masks)) for s in range(2)]
            val, g = terms(D)
            assert bound(D) <= max(sums) + 1e-12 <= val + 1e-12                      # bound <= worst scenario <= smoothed
            assert val - bound(D) == pytest.approx(0.01 * raw.sum() * np.log(2))
            for idx in [(0, 1), (1, 3), (1, 0)]:
                E = np.zeros_like(D)
                E[idx] = 1e-6
                fd = (terms(D + E)[0] - terms(D - E)[0]) / 2e-6
                assert g[idx] == pytest.approx(fd, rel=1e-4, abs=1e-7)

    def test_a_constraint_in_one_scenario(self):
        ops, _, masks = _small()
        D = ops.forward(np.array([1.0, 1.0, 1.0]))
        spec = HardConstraint(structure_name="O", metric="Dmax", op="<=", value_gy=0.5)
        t = ScenarioTerm(spec, masks[1], 1, "shift")
        assert t.violation(D) == pytest.approx(max(0.0, D[1, 3:].max() - 0.5))
        loss, g = t.term(D, 10.0)
        assert np.all(g[0] == 0.0) and np.any(g[1] != 0.0)
        assert t.outcome(D).label.endswith("[shift]") and not t.outcome(D).met


# ---------------------------------------------------------------------------
# The sandwich on a robust problem
# ---------------------------------------------------------------------------

def _robust_solve(ops, objs, masks):
    def solve(raw, warm):
        terms, bound = scenario_wise(objs, masks, raw)

        def f(w):
            v, gd = terms(ops.forward(w))
            return v, ops.backward(gd)
        r = minimize(f, np.full(3, 1.0), jac=True, method="L-BFGS-B", bounds=[(0, None)] * 3, options={"ftol": 1e-15, "gtol": 1e-12})
        D = ops.forward(r.x)
        return Solved(r.x, np.array([WorstCase(o).value(D, m) for o, m in zip(objs, masks)]), bound=bound(D))
    return solve


def test_the_bounds_hold_for_every_attainable_worst_case():
    ops, objs, masks = _small()
    res = sandwich(_robust_solve(ops, objs, masks), 2, budget=9, tol=0.001)
    P = res.normalized()
    span = res.nadir - res.ideal
    hyper = [(p.raw_weights * span / (p.raw_weights @ span), (p.solved.bound - p.raw_weights @ res.ideal) / (p.raw_weights @ span))
             for p in res.plans]
    for p in res.plans:                                                 # each bound lies below the plan's own weighted sum
        assert p.solved.bound <= p.raw_weights @ p.solved.values + 1e-9
    rng = np.random.default_rng(3)
    for _ in range(300):
        D = ops.forward(rng.uniform(0.0, 4.0, 3))
        z = normalize(np.array([WorstCase(o).value(D, m) for o, m in zip(objs, masks)]), res.ideal, res.nadir)
        assert all(a @ z >= b - 1e-6 for a, b in hyper)                 # inside the outer set
        assert distance_to_inner(P, z)[0] <= res.error + 1e-6          # within the bound of the plans' hull


def test_the_scenario_wise_plan_protects_the_worst_scenario():
    ops, objs, masks = _small()
    raw = np.array([0.5, 0.5])
    robust = _robust_solve(ops, objs, masks)(raw, None)

    def nominal_plan():
        def f(w):
            d = ops.forward(w)[0]
            v = sum(r * o.value_and_grad(d, m)[0] for r, o, m in zip(raw, objs, masks))
            g = sum(r * o.value_and_grad(d, m)[1] for r, o, m in zip(raw, objs, masks))
            return v, ops.matrices[0].T @ g
        return minimize(f, np.full(3, 1.0), jac=True, method="L-BFGS-B", bounds=[(0, None)] * 3).x

    def worst_sum(w):
        D = ops.forward(w)
        return max(sum(r * o.value(D[s], m) for r, o, m in zip(raw, objs, masks)) for s in range(2))
    assert worst_sum(robust.x) <= worst_sum(nominal_plan()) + 1e-9


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------

class TestRequest:
    def test_worst_case_is_the_default_and_the_only_aggregation(self):
        r = _mreq(robustness=RobustnessSpec(enabled=True, scenarios=ROB.scenarios))
        assert r.robustness.aggregation == "WORST_CASE"
        with pytest.raises(ValueError, match="WORST_CASE"):
            _mreq(robustness=RobustnessSpec(enabled=True, scenarios=ROB.scenarios, aggregation="EXPECTED"))

    def test_hard_constraints_are_allowed_and_the_nominal_key_is_unchanged(self):
        r = _mreq(robustness=ROB, hard_constraints=COVER)
        assert r.compute_cache_key() != _mreq(hard_constraints=COVER).compute_cache_key()
        assert _mreq(robustness=RobustnessSpec()).compute_cache_key() == _mreq().compute_cache_key()


# ---------------------------------------------------------------------------
# The service, navigation and the deliverable plan on the stubbed patient
# ---------------------------------------------------------------------------

@pytest.fixture
def robust_set(msvc):
    return msvc.run(_mreq(robustness=ROB, hard_constraints=COVER))


class TestService:
    def test_worst_case_and_nominal_values_and_the_stored_scenarios(self, msvc, robust_set):
        res = robust_set
        assert res.scenarios == ["nominal", "dens_up", "dens_down", "range_up"] and res.modality == "PROTON_PBS"
        assert any("robust over 4 scenarios" in n for n in res.notes)
        assert 0.0 <= res.robust_gap <= res.error_bound + 1e-6
        scen = msvc.store.load_scenario_doses(res.mco_id)
        index, doses, masks = msvc.store.load_navigation(res.mco_id)
        assert scen.shape == (4, len(res.plans), index.size) and np.allclose(scen[0], doses)
        ptv, oar = masks["PTV"].astype(float), masks["OAR"].astype(float)
        for k, p in enumerate(res.plans):
            per = np.array([[UniformRMS("PTV", 10.0).value(scen[s, k], ptv), MeanDose("OAR", 0.0).value(scen[s, k], oar)] for s in range(4)])
            assert np.allclose(p.values_gy, per.max(axis=0), atol=1e-4) and np.allclose(p.nominal_gy, per[0], atol=1e-4)
            assert all(w >= n - 1e-6 for w, n in zip(p.values_gy, p.nominal_gy))
            assert scen[:, k][:, masks["PTV"]].min() >= 5.0 - 0.1                # coverage holds in every scenario

    def test_infeasible_in_a_scenario_is_refused(self, msvc):
        from radiarch.services.hard_constraints import InfeasibleConstraintsError

        # a narrow band on the PTV that the nominal dose can meet but not the +-10 % density scenarios as well
        with pytest.raises(InfeasibleConstraintsError, match=r"\[dens_"):
            msvc.run(_mreq(robustness=ROB, hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=9.8),
                                                             HardConstraint(structure_name="PTV", metric="Dmax", op="<=", value_gy=10.2)]))

    def test_navigation_reports_worst_case_and_nominal(self, msvc, robust_set):
        from radiarch.services.navigation import NavigationService

        res = robust_set
        nav = NavigationService(msvc.store)
        bal = nav.get_state(res.mco_id, "balance")
        plan = next(p for p in res.plans if p.kind == "balance")
        assert np.allclose(bal.values_gy, plan.values_gy, atol=1e-4) and np.allclose(bal.nominal_gy, plan.nominal_gy, atol=1e-4)
        goals = {"goals": [{"structure": "PTV", "metric": "D95%[Gy]", "op": ">=", "value": 9.0, "priority": 1},
                           {"structure": "OAR", "metric": "Dmean[Gy]", "op": "<=", "value": 9.5, "priority": 2}]}
        st = nav.navigate(res.mco_id, NavigateRequest(from_state="balance", move={"MeanDose(OAR)": 0.5 * (res.ideal_gy[1] + res.nadir_gy[1])},
                                                     goals=goals))
        assert all(v <= b + 1e-6 for v, b in zip(st.values_gy, st.bound_gy))                 # the linear bound holds on worst cases
        assert st.goals.robust_all_passed is not None
        for g in st.goals.results:
            assert set(g.per_scenario) == {"dens_up", "dens_down", "range_up"}
            vals = [g.achieved] + list(g.per_scenario.values())
            assert g.worst_case == pytest.approx(min(vals) if g.op == ">=" else max(vals))

        req = AutoNavigateRequest(goals=goals)
        auto = nav.auto_navigate(res.mco_id, req)
        n, lam = nav.navigator(res.mco_id), np.asarray(auto.blend)
        report = n.grade(req.goals, n.stack(lam), None, None)
        for item, r in zip(n._goals(req)[0], report.results):                              # the search works on worst cases
            miss = max(0.0, r.value - r.worst_case) if r.op == ">=" else max(0.0, r.worst_case - r.value)
            assert n._shortfall(item, lam, None, None) == pytest.approx(miss / abs(r.value), abs=1e-9)
        assert auto.nominal_gy is not None and len(auto.levels) == 2

    def test_the_deliverable_plan_of_a_robust_proton_set(self, msvc, robust_set, tmp_path):
        from radiarch.services.mco_deliverable import DeliverableRefused, DeliverableService

        res = robust_set
        svc_d = DeliverableService(base_dir=tmp_path / "d", mco_service=msvc)
        out = svc_d.run(res.mco_id, DeliverableRequest())
        assert out.technique == "proton" and out.projected
        rows = {r.name: r for r in out.deviation}
        assert set(rows) == {"UniformRMS(PTV)", "MeanDose(OAR)"}
        bal = next(p for p in res.plans if p.kind == "balance")
        assert np.allclose([rows[n].navigated for n in ("UniformRMS(PTV)", "MeanDose(OAR)")], bal.values_gy, atol=1e-3)   # worst cases
        assert all(r.worse_by <= 0.011 and not r.flagged for r in rows.values())             # projection: no worst case worse

        photon = res.model_copy(update={"modality": "PHOTON_IMRT"})
        msvc.store.save(photon)
        with pytest.raises(DeliverableRefused, match="robust photon"):
            svc_d.cache_key(res.mco_id, DeliverableRequest(state_id="balance"))
