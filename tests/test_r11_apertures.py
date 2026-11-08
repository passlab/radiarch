"""R11.11: a second Pareto set on a deliverable plan's apertures (option B1 of docs/reports/mco-deliverable-options.md).

On the stub patient through the SDK: static fields made deliverable from a navigated state, a second set over the
plan's segment metersets, a state navigated on it and made the plan. Every plan of the second set keeps the apertures,
so the plan made from a state is the state's dose exactly (static fields). Every plan of the second set is scaled to
its lower limits. The limits a deliverable plan cannot meet on its apertures are relaxed with a note; a proton plan and
a plan of a second set have no second set.
"""

from __future__ import annotations

import numpy as np
import pytest

from test_r11_navigation import rx  # noqa: F401  (the SDK on the stub patient)
from test_r6_rt_export_service import env  # noqa: F401

GOALS = {"goals": [{"structure": "PTV", "metric": "D95%[Gy]", "op": ">=", "value": 1.5, "priority": 1},
                   {"structure": "OAR", "metric": "Dmean[Gy]", "op": "<=", "value": 1.0, "priority": 2}]}
NORMALISE = {"structure": "PTV", "metric": "D95", "gy": 1.8}


def _first(rx):
    from radiarch.sdk import ops

    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    bm = geo.photon_beams([0, 90, 180, 270], machine="test-120", jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))
    ps = bm.mco([ops.uniform_rms("PTV", 2.0), ops.mean_dose("OAR")], engine="analytic", max_iterations=100, plan_budget=6,
                hard_constraints=[ops.hard("PTV", "Dmin", ">=", 1.0)])
    st = ps.navigate(move={"MeanDose(OAR)": 0.9 * ps.states()[0].values_gy[1]})
    plan = ps.deliverable(st, levels=5, max_iterations=60, goals=GOALS, prescription_gy=2.0, normalise=NORMALISE, tolerance_gy=0.05)
    return ps, plan


def _rows(plan):
    return [[(r.x_left_mm, r.x_right_mm) for r in s.mlc_rows] for b in plan.beams for s in b.segments]


def test_a_second_set_keeps_the_apertures_and_delivers_what_it_shows(rx, tmp_path):
    from radiarch.sdk import MCOPlan, ParetoSet, RadiarchError

    ps, plan = _first(rx)
    second = plan.pareto(plan_budget=5)
    res = second.result
    assert isinstance(second, ParetoSet) and res.source_deliverable_id == plan.id and res.elements == "segments"
    assert [f"{o.type}({o.structure_name})" for o in res.tradeoffs] == ["UniformRMS(PTV)", "MeanDose(OAR)"]
    assert res.beam_model_id == plan.result.beam_model_id and 3 <= len(res.plans) <= 5
    # the limits: the first set's, the coverage held at the deliverable plan's gEUD, the maximum at 1.2 x the prescription
    limits = {(c.structure_name, c.metric, c.op): c for c in res.hard_constraints}
    assert set(limits) == {("PTV", "Dmin", ">="), ("PTV", "gEUD", ">="), ("PTV", "Dmax", "<=")}
    assert limits[("PTV", "gEUD", ">=")].eud_a == -10.0 and any("coverage held" in n for n in res.notes)
    assert plan.pareto(plan_budget=5).id == second.id                                                      # cached

    # navigated on the second set and made the plan, without normalisation: the plan is the blend exactly
    oar = [p.values_gy[1] for p in res.plans]
    st = second.navigate(move={"MeanDose(OAR)": 0.5 * (min(oar) + max(oar))})
    made = second.deliverable(st, goals=GOALS, prescription_gy=2.0, tolerance_gy=0.05)
    assert isinstance(made, MCOPlan) and made.technique == "imrt" and made.mco_id == second.id
    assert made.sequence_id == plan.result.sequence_id and made.optimization_id == plan.result.optimization_id and made.rounds == []
    assert made.normalisation == 1.0 and made.deliverable
    for r in made.deviation_table():
        assert abs(r["worse_by"]) <= 1e-3, r                                                              # navigated = delivered
    from radiarch.services.beam_model import BeamModelService

    plans = BeamModelService().store
    first_plan, new_plan = plans.load_plan(plan.result.beam_model_id), plans.load_plan(made.result.beam_model_id)
    assert _rows(new_plan) == _rows(first_plan)                                                           # the apertures kept
    z = np.asarray(st.blend) @ np.asarray([[w for w in p] for p in np.load(res.weights_uri)])
    assert [s.mu for b in new_plan.beams for s in b.segments] == pytest.approx(z.tolist(), rel=1e-5, abs=1e-6)

    # with the first plan's normalisation: a check near 1
    normalised = second.deliverable(st, goals=GOALS, prescription_gy=2.0, normalise=NORMALISE, tolerance_gy=0.05)
    assert 0.85 <= normalised.normalisation <= 1.15 and normalised.id != made.id

    # lineage: the plan's beam model comes from the first plan's and from the second set
    graph = rx.get(f"/lineage/beam_model/{made.beam_model_id}")
    kinds = {(n["ref"]["kind"], n["ref"]["id"]) for n in graph["nodes"]}
    assert ("mco", second.id) in kinds and ("beam_model", plan.result.beam_model_id) in kinds
    assert made.export(label="MCO2", prescription={"dose_gy": 2.0, "fractions": 2}).download(tmp_path / "rt")

    # no third stage, and a projection is not asked of a second set
    with pytest.raises(RadiarchError) as e:
        made.pareto()
    assert e.value.status_code == 422 and "second set" in str(e.value)
    with pytest.raises(RadiarchError) as e:
        rx.post("/mco/deliverables/no-such-plan/pareto", {})
    assert e.value.status_code == 404
    assert any("not projected" in n for n in second.deliverable(st, project=True, tolerance_gy=0.05).notes)


def test_the_second_set_starts_from_the_deliverable_plan(rx):
    """Its plans are metersets at or above the machine's minimum, and at the deliverable plan's own metersets the set's
    dose is the deliverable plan's dose."""
    from radiarch.services.autoplan import read_volume
    from radiarch.services.dose import DoseService
    from radiarch.services.mco import MCOService
    from radiarch.services.mco_apertures import deliverable_elements, element_dose
    from radiarch.services.mco_deliverable import DeliverableService

    ps, plan = _first(rx)
    second = plan.pareto(plan_budget=4)
    W = np.load(second.result.weights_uri)
    d = DeliverableService().store.get_by_id(plan.id)
    el = deliverable_elements(d)
    assert W.shape == (len(second.result.plans), el.z0.size) and np.all(W >= el.lower - 1e-6)
    _, mreq, prob = MCOService().problem(d.mco_id)
    delivered = read_volume(DoseService().dose_store.get_by_id(plan.result.dose_id).dose_grid_uri)
    np.testing.assert_allclose(element_dose(el, el.z0, prob, mreq), delivered, rtol=1e-4, atol=1e-5)


def test_a_blend_of_plans_at_the_minimum_is_deliverable(rx):
    """Three plans hold a segment at a 2 MU minimum; weights 0.7, 0.2 and 0.1 blend it to 1.9999999999999998 MU, which
    the static check flags. The blend's metersets are put back at the minimum; a meterset below it by more than
    rounding stays below."""
    import dataclasses

    from radiarch.services.mco_apertures import blend_metersets, deliverable_elements
    from radiarch.services.mco_deliverable import DeliverableService

    ps, plan = _first(rx)
    el = deliverable_elements(DeliverableService().store.get_by_id(plan.id))
    floor = dataclasses.replace(el, machine=el.machine.model_copy(update={"min_mu_per_segment": 2.0}), lower=np.full(el.z0.size, 2.0))
    W = np.stack([np.maximum(el.z0, 2.0) * f for f in (1.0, 1.1, 1.2)]).astype(np.float32)
    W[:, 0] = 2.0
    lam = [0.7, 0.2, 0.1]
    raw = np.asarray(lam) @ W.astype(np.float64)
    assert raw[0] < 2.0 and any("MU" in i for i in floor.issues(floor.with_metersets(raw)))
    z = blend_metersets(lam, W, floor.lower)
    assert z[0] == 2.0 and np.array_equal(z[1:], raw[1:]) and floor.issues(floor.with_metersets(z)) == []
    assert blend_metersets([0.5, 0.5], np.asarray([[2.0], [1.9]]), np.asarray([2.0]))[0] == pytest.approx(1.95)


def test_a_plan_inside_a_lower_limit_is_scaled_to_it():
    """A plan whose gEUD is 0.5 % below its limit, within the limit's 1 % tolerance, is scaled up to the limit exactly;
    a plan that meets it is kept; an upper limit caps the scale at its own tolerance."""
    from radiarch.models.optimization import HardConstraint
    from radiarch.services.hard_constraints import HardConstraintTerm
    from radiarch.services.mco_apertures import at_lower_limits
    from radiarch.services.objectives import _geud

    S = np.random.default_rng(7).uniform(0.5, 1.5, size=(12, 4))
    lower, mask = np.full(4, 0.5), np.r_[np.ones(8), np.zeros(4)]

    def forward(y):
        return S @ (lower + np.asarray(y, dtype=np.float64))

    def geud(d):
        return float(_geud(d, mask, 8.0, -10.0)[0])

    def limits(g, top, top_tol):
        return [HardConstraintTerm(HardConstraint(structure_name="PTV", metric="gEUD", op=">=", value_gy=g, eud_a=-10.0,
                                                  tolerance_gy=0.01 * g), mask),
                HardConstraintTerm(HardConstraint(structure_name="PTV", metric="Dmax", op="<=", value_gy=top, tolerance_gy=top_tol), mask)]

    y = np.array([1.0, 2.0, 0.0, 1.5])
    d = forward(y)
    g, dmax = geud(d) / 0.995, float(d[:8].max())
    terms = limits(g, 2.0 * dmax, 0.1)
    assert 0.0 < terms[0].violation(d) < terms[0].spec.tolerance_gy                                    # met, within tolerance
    out = at_lower_limits(terms, forward, lower)(y)
    np.testing.assert_allclose(lower + out, (lower + y) / 0.995, rtol=1e-12)
    assert geud(forward(out)) == pytest.approx(g, rel=1e-12) and np.all(out >= y)

    kept = at_lower_limits(limits(0.99 * geud(d), 2.0 * dmax, 0.1), forward, lower)(y)
    assert np.array_equal(kept, y)

    capped = limits(g, 1.002 * dmax, 0.001 * dmax)                                                     # room for 1.003 only
    out = at_lower_limits(capped, forward, lower)(y)
    np.testing.assert_allclose(lower + out, 1.003 * (lower + y), rtol=1e-12)
    assert capped[1].violation(forward(out)) == pytest.approx(0.001 * dmax, rel=1e-9)
    assert 0.0 < capped[0].violation(forward(out)) < capped[0].violation(d)


def test_every_plan_of_the_second_set_meets_its_lower_limits(rx, monkeypatch):
    """Each solved plan of the second set leaves at_lower_limits meeting every lower limit exactly, or with an upper
    limit at its tolerance, and those are the metersets stored. With every plan at the same coverage, each converged
    plan is the best of the set in its own weighted sum."""
    import radiarch.services.mco_apertures as mod

    real, seen = mod.at_lower_limits, []

    def spy(terms, forward, lower):
        finish = real(terms, forward, lower)

        def wrapped(y):
            out = finish(y)
            seen.append((terms, forward(out), lower + out))
            return out
        return wrapped

    monkeypatch.setattr(mod, "at_lower_limits", spy)
    ps, plan = _first(rx)
    res = plan.pareto(plan_budget=5).result
    assert len(seen) == len(res.plans) and any("meets the lower limits exactly" in n for n in res.notes)
    for terms, dose, _ in seen:
        low = max(t.violation(dose) / t.spec.value_gy for t in terms if t.spec.op == ">=")
        assert low <= 1e-9 or any(t.violation(dose) >= 0.999 * t.spec.tolerance_gy for t in terms if t.spec.op == "<=")
    np.testing.assert_allclose(np.load(res.weights_uri), np.stack([z for *_, z in seen]), rtol=1e-6)

    W, V = np.array([p.weights for p in res.plans]), np.array([p.values_gy for p in res.plans])
    span = np.array(res.nadir_gy) - np.array(res.ideal_gy)
    span = np.where(span > 1e-9, span, 1.0)
    s = W @ V.T
    assert max((s[k, k] - s[k].min()) / (W[k] @ span) for k, p in enumerate(res.plans) if p.converged) <= 0.01


def test_a_limit_the_apertures_cannot_meet_is_relaxed_with_a_note(rx, monkeypatch):
    import radiarch.services.mco_apertures as mod

    real = mod.solve_with_hard_constraints

    def first_unmet(*args, **kwargs):                       # the feasibility run, with its first limit reported unmet
        out = real(*args, **kwargs)
        out.outcomes[0] = out.outcomes[0].model_copy(update={"met": False, "achieved_gy": round(out.outcomes[0].achieved_gy - 0.2, 6)})
        return out

    monkeypatch.setattr(mod, "solve_with_hard_constraints", first_unmet)
    ps, plan = _first(rx)
    res = plan.pareto(plan_budget=4).result
    dmin = next(c for c in res.hard_constraints if c.metric == "Dmin")
    assert dmin.value_gy != 1.0 and any("is relaxed to" in n and "PTV" in n for n in res.notes)


def test_a_proton_plan_has_no_second_set(msvc, tmp_path):  # noqa: F811
    from radiarch.models.mco import ApertureSetRequest, DeliverableRequest
    from radiarch.models.optimization import HardConstraint
    from radiarch.services.mco_apertures import ApertureSetRefused, ApertureSetService
    from radiarch.services.mco_deliverable import DeliverableService

    from test_r11_pareto import _mreq

    res = msvc.run(_mreq(hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=5.0)]))
    dsvc = DeliverableService(base_dir=tmp_path / "d", mco_service=msvc)
    out = dsvc.run(res.mco_id, DeliverableRequest())
    with pytest.raises(ApertureSetRefused, match="proton"):
        ApertureSetService(mco_service=msvc, deliverable_service=dsvc).run(out.deliverable_id, ApertureSetRequest())


from test_r11_pareto import msvc, svc  # noqa: E402,F401  (the stubbed proton services)


def test_the_record_follows_a_run_from_the_first_navigation_to_the_plan(rx):
    """The R11 cases (cases_r11): from a run's plan back to the first set and its deliverable plan, the second set
    checked like any set, and a row per trade-off and goal from the first navigation to the plan."""
    from radiarch.services.mco import MCOService
    from radiarch.services.mco_deliverable import DeliverableService
    from radiarch.validation.cases_r11 import _second_set_checks, _stages
    from radiarch.validation.common import CaseResult

    ps, plan = _first(rx)
    second = plan.pareto(plan_budget=4)
    made = second.deliverable(second.auto_navigate(GOALS, prescription_gy=2.0), goals=GOALS, prescription_gy=2.0, normalise=NORMALISE,
                              tolerance_gy=0.05)
    msvc = MCOService()
    dsvc = DeliverableService(mco_service=msvc)
    first, first_plan, s2, last = _stages(dsvc, msvc, made.id)
    assert (first.mco_id, first_plan.deliverable_id, s2.mco_id, last.deliverable_id) == (ps.id, plan.id, second.id, made.id)
    assert _stages(dsvc, msvc, plan.id)[2] is None
    res = CaseResult("c", "mco_front")
    out = _second_set_checks(res, "static fields", first_plan, s2, last, msvc.store)
    names = [c.name for c in res.checks]
    assert "static fields: second set: hard constraints hold in every plan" in names or any(n.startswith("static fields: second set:") for n in names)
    trail = [c for c in res.checks if "navigated → deliverable → second navigation → plan" in c.name]
    assert {c.name.split(": ")[1].split(" navigated")[0] for c in trail} >= {"UniformRMS(PTV)", "MeanDose(OAR)"}
    assert all(len(c.value.split(" → ")) == 4 for c in trail) and out["deliverable_id"] == made.id
    assert not any(c.passed is False for c in res.checks if "second set" in c.name), [(c.name, c.value) for c in res.checks if c.passed is False]
