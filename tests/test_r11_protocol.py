"""R11.7: a planning protocol with an ``mco`` section (docs/reports/mco-research-and-design.md, D9).

The protocol plans by multi-criteria optimization instead of the reweighting rounds: the Pareto set of its trade-offs
on its beams, automatic navigation by its goals (the main target's at priority 1), and the navigated plan made
deliverable and normalised to the coverage goal. The run keeps the Pareto set, its state and the deviation table, and
the command prints them. A protocol without the section keeps its digest, so earlier runs stay cached.
"""

from __future__ import annotations

import json

import pydicom
import pytest

from radiarch.models.protocol import MCOSection, PlanningProtocol, navigation_goals

from test_r6_rt_export_service import env  # noqa: F401  (stub CT: a cube PTV and an OAR; the test machine; test engines)
from test_r10_protocols import PROTOCOL, rx  # noqa: F401  (the stub patient through the SDK)

MCO = {**PROTOCOL, "protocol_id": "test-static-mco", "name": "test: three static fields, MCO",
       "mco": {"tradeoffs": [{"type": "UniformRMS", "structure_name": "PTV", "dose_gy": 2.0, "weight": 1.0},
                             {"type": "MeanDose", "structure_name": "Cord", "dose_gy": 0.0, "weight": 1.0}],
               "hard_constraints": [{"structure_name": "PTV", "metric": "Dmin", "op": ">=", "value_gy": 1.0}],
               "plan_budget": 5}}


class TestSection:
    def test_the_digest_of_a_protocol_without_one_is_unchanged(self):
        import hashlib

        p = PlanningProtocol(**PROTOCOL)
        old = p.model_dump(mode="json")
        old.pop("mco")
        assert p.digest() == hashlib.sha256(json.dumps(old, sort_keys=True).encode("utf-8")).hexdigest()
        assert PlanningProtocol(**MCO).digest() != PlanningProtocol(**{**MCO, "mco": None}).digest()

    def test_navigation_goals_from_the_planning_goals(self):
        gs = navigation_goals(PlanningProtocol(**MCO))
        assert [(g.structure, g.metric, g.op, g.value, g.priority) for g in gs.goals] == [
            ("PTV", "D95%[Gy]", ">=", 2.0, 1), ("Cord", "Dmax[Gy]", "<=", 1.8, 2), ("Liver", "Dmean[Gy]", "<=", 1.0, 2)]
        own = {**MCO["mco"], "navigation_goals": {"goals": [{"structure": "Cord", "metric": "Dmean[Gy]", "op": "<=", "value": 0.5}]}}
        assert navigation_goals(PlanningProtocol(**{**MCO, "mco": own})).goals[0].metric == "Dmean[Gy]"

    def test_refusals(self):
        with pytest.raises(ValueError, match="not trade-off objectives"):
            MCOSection(tradeoffs=[{"type": "DMax", "structure_name": "Cord", "dose_gy": 1.0, "weight": 1.0},
                                  {"type": "MeanDose", "structure_name": "Cord", "dose_gy": 0.0, "weight": 1.0}])
        with pytest.raises(ValueError, match="4 N"):
            MCOSection(**{**MCO["mco"], "plan_budget": 10})


def test_an_mco_protocol_plans_a_patient(rx, tmp_path):
    geo = rx.build_geometry("1.2.3", hu_model="LINEAR")
    run = geo.run_protocol(MCO)
    r = run.result
    assert r.mco_id and r.state_id and r.deliverable_id and r.sequence_id and r.vmat_id is None and r.normalisation > 0
    ps = rx.get(f"/mco/{r.mco_id}")
    assert ps["navigation_structures"][:2] == ["PTV", "Cord"] and len(ps["plans"]) <= 5
    state = rx.get(f"/mco/{r.mco_id}/states/{r.state_id}")
    assert state["name"] == "protocol test-static-mco" and [lv["priority"] for lv in state["levels"]] == [1, 2]
    plan = rx.get(f"/mco/deliverables/{r.deliverable_id}")
    assert plan["beam_model_id"] == r.beam_model_id and plan["dose_id"] == r.dose_id and plan["technique"] == "imrt"
    goals = {g["structure"]: g for g in run.goals_table()}
    assert goals["PTV"]["achieved"] == pytest.approx(2.0 * 1.002, rel=1e-3) and goals["PTV"]["passed"]     # normalised
    assert goals["Liver"]["passed"] is None
    assert [list(h)[0] for h in r.history] == ["mco_id", "state_id", "deliverable_id"]
    assert geo.run_protocol(MCO).id == run.id                                                               # cached
    # a planner navigates from the protocol's state
    st = rx.post(f"/mco/{r.mco_id}/navigate", {"from_state": r.state_id, "locks": ["UniformRMS(PTV)"]})
    assert st["from_state"] == r.state_id
    assert run.pareto_set().id == r.mco_id and r.state_id in {s.state_id for s in run.pareto_set().states()}
    exp = run.export(label="MCO")
    assert pydicom.dcmread(next(p for p in exp.download(tmp_path) if p.name == "RP.dcm")).RTPlanLabel == "MCO"


def test_the_command_prints_the_pareto_set(rx, tmp_path, capsys, monkeypatch):  # noqa: F811
    from radiarch.cli import main

    path = tmp_path / "mco.json"
    path.write_text(json.dumps(MCO), encoding="utf-8")
    monkeypatch.delenv("RADIARCH_SERVER", raising=False)
    code = main(["plan", "--protocol", str(path), "--study", "1.2.3", "--poll", "0.01"])
    out = capsys.readouterr().out
    assert code == 0 and "Pareto set" in out and "navigate from state" in out and "deviation" in out
