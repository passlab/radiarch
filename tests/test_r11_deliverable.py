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
        out = svc_d.run(res.mco_id, DeliverableRequest())
        assert out.technique == "proton" and out.projected and out.dose_id is None and out.beam_model_id == res.beam_model_id
        assert any("minimum spot meterset" in n for n in out.notes)
        rows = {r.name: r for r in out.deviation}
        assert set(rows) == {"UniformRMS(PTV)", "MeanDose(OAR)"}
        assert all(r.worse_by <= 0.011 and not r.flagged for r in rows.values())       # projected: no trade-off worse
        opt = msvc.optimization.store.get_by_id(out.optimization_id)
        assert opt.cache_key.startswith(f"mco:{res.mco_id}:") and opt.geometry_id == res.geometry_id
        assert svc_d.run(res.mco_id, DeliverableRequest()).deliverable_id == out.deliverable_id            # cached
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
                          tolerance_gy=0.05)
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
                          tolerance_gy=0.05).id == plan.id                                                     # cached
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
