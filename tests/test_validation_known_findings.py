"""The harness's CI exit mode: recorded findings pass, anything else (a new graded failure, an error) does not."""

from __future__ import annotations

from radiarch.validation.common import CaseResult
from radiarch.validation.run import _exit_with_known_findings


def _case(name, checks, status="fail"):
    r = CaseResult(name, "kind")
    for check, passed in checks:
        r.add(check, 1.0, "target", passed)
    r.status = status
    return r


def test_recorded_findings_pass_and_new_failures_do_not():
    known = _case("photon_vs_mc", [("[shipped] water_10x10: gamma 3 %/3 mm pass rate (%)", False), ("[full] lung_slab: x", False), ("ok", True)])
    assert _exit_with_known_findings([known, _case("pb_vs_mc", [("a", True)], "pass")]) == 0
    new = _case("pb_vs_mc", [("water_10x10: PDD10 pb vs MC (%)", False)])
    assert _exit_with_known_findings([known, new]) == 1
    unlisted_in_listed_case = _case("photon_vs_mc", [("water_10x10: something new", False)])
    assert _exit_with_known_findings([unlisted_in_listed_case]) == 1
    assert _exit_with_known_findings([_case("photon_vs_mc", [], "error")]) == 1
