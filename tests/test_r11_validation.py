"""R11.8: the pieces of the MCO validation cases that run without engines or data: the cases are registered, the robust
case's phantom is what it says and the geometry service reads it, and the checks every Pareto set gets pass on the
stubbed sets (nominal and robust) and catch a set that breaks them."""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.validation.cases_r11 import _set_checks, robust_phantom
from radiarch.validation.common import CaseResult
from radiarch.validation.run import KINDS, load_cases

from test_r11_pareto import _mreq, msvc, svc  # noqa: F401
from test_r11_robust import COVER, ROB


def test_the_cases_are_registered():
    cases = load_cases()
    for name, kind in (("mco_front_tg119", "mco_front"), ("mco_protocol_lung", "mco_protocol"), ("mco_robust_proton", "mco_robust")):
        assert cases[name]["kind"] == kind and kind in KINDS


def test_the_robust_phantom(tmp_path):
    from radiarch.models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from radiarch.services.geometry import GeometryService
    from radiarch.services.geometry_bundle import load_geometry_arrays
    from radiarch.validation.phantoms import write_case

    hu, origin, masks = robust_phantom(4.0)
    t, o = masks["CTV"], masks["OAR"]
    assert not (t & o).any()
    y = origin[1] + np.arange(hu.shape[1]) * 4.0
    ty, oy = y[np.where(t.any(axis=(0, 2)))[0]], y[np.where(o.any(axis=(0, 2)))[0]]
    assert oy.min() > ty.max()                                         # the organ lies behind the target (beyond it from -y)
    assert (hu == 800).any() and y[np.where((hu == 800).any(axis=(0, 2)))[0]].max() < ty.min()   # the slab is in front

    d = write_case(tmp_path / "ph", hu, 4.0, origin, masks, "test-robust")
    assert write_case(tmp_path / "ph2", hu, 4.0, origin, masks, "test-robust").name == "ph2"     # same UIDs, same files
    import pydicom
    a, b = pydicom.dcmread(d / "CT000.dcm"), pydicom.dcmread(tmp_path / "ph2" / "CT000.dcm")
    assert a.SOPInstanceUID == b.SOPInstanceUID and a.FrameOfReferenceUID == b.FrameOfReferenceUID
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="test-robust"), data_root_override=str(d),
                                                       grid_spec=GridSpec(spacing_mm=(4.0, 4.0, 4.0))))
    arr = load_geometry_arrays(geo)
    assert {"CTV", "OAR"} <= set(arr.structure_index)
    cc = arr.mask_zyx(arr.structure_index["CTV"]).sum() * 4.0 ** 3 / 1000.0
    assert cc == pytest.approx(t.sum() * 4.0 ** 3 / 1000.0, rel=0.2)     # the contours give back the mask (boundary voxels at 4 mm)


def _graded(res: CaseResult):
    return {c.name: c.passed for c in res.checks if c.passed is not None}


def test_the_set_checks_pass_on_a_nominal_and_a_robust_set(msvc):  # noqa: F811
    for label, req in (("nominal", _mreq(hard_constraints=COVER, plan_budget=6)), ("robust", _mreq(robustness=ROB, hard_constraints=COVER))):
        mco = msvc.run(req)
        res = CaseResult("t", "mco_front")
        front = _set_checks(res, label, mco, msvc.store)
        graded = _graded(res)
        assert graded and all(graded.values()), graded
        assert any("hard constraint PTV Dmin" in n for n in graded)
        assert any(f"each converged plan is the best of the set in its own {w}" in n for n in graded
                   for w in (("weighted sum",) if label == "nominal" else ("worst-scenario sum",)))
        assert len(front["plans"]) == len(mco.plans) and front["error_history"][-1]["seconds"] is not None
        assert any("error bound with" in c.name and "tolerance 0.05" in c.target for c in res.checks)


def test_the_set_checks_catch_a_broken_set(msvc):  # noqa: F811
    mco = msvc.run(_mreq(hard_constraints=COVER, plan_budget=6))
    plans = list(mco.plans)
    src = next(p for p in reversed(plans) if p.converged)                  # the checks judge converged plans only
    worse = src.model_copy(update={"normalized": [v + 0.2 for v in src.normalized]})                # dominated by the plan it copies
    hist = list(mco.error_history) + [mco.error_history[-1].model_copy(update={"plans": len(plans) + 1, "error": mco.error_history[-1].error + 0.1})]
    broken = mco.model_copy(update={"plans": plans + [worse.model_copy(update={"index": len(plans)})], "error_history": hist,
                                    "hard_constraints": [COVER[0].model_copy(update={"value_gy": 1e3})]})
    res = CaseResult("t", "mco_front")
    _set_checks(res, "broken", broken, msvc.store)
    failed = {n for n, p in _graded(res).items() if p is False}
    assert any("never grows" in n for n in failed) and any("own weighted sum" in n for n in failed) and any("hard constraint" in n for n in failed)
    assert next(c for c in res.checks if "dominated by another plan" in c.name).value >= 1


def test_robust_plans_are_compared_only_with_nominal_plans_that_hold_in_every_scenario(msvc):  # noqa: F811
    # a nominal plan that misses the target in a scenario can have a lower scenario-wise sum than any robust plan: it is
    # no rival, since a robust plan minimizes over plans that meet the hard constraints in every scenario (R11.8's record)
    from radiarch.validation.cases_r11 import _robust_against_nominal

    rreq = _mreq(robustness=ROB, hard_constraints=COVER)
    robust, nominal = msvc.run(rreq), msvc.run(_mreq(hard_constraints=COVER))
    ops = msvc.ops(msvc.optimization._assemble_problem(msvc._base(rreq)), rreq)
    w_rob, w_nom = np.load(robust.weights_uri), np.load(nominal.weights_uri)
    feasible, gap = _robust_against_nominal(ops, robust.plans, w_rob, w_nom, len(robust.scenarios))
    expected = [k for k, w in enumerate(w_nom) if all(t.violation(ops.forward(w)) <= t.spec.tolerance_gy for t in ops.terms)]
    assert feasible == expected
    off = np.vstack([w_nom, np.zeros_like(w_nom[:1])])                   # no dose: the organs' best, the target missed
    feasible2, gap2 = _robust_against_nominal(ops, robust.plans, w_rob, off, len(robust.scenarios))
    assert feasible2 == expected and gap2 == gap
    _, none = _robust_against_nominal(ops, robust.plans, w_rob, off[-1:], len(robust.scenarios))
    assert none == -np.inf                                                # nothing to compare
