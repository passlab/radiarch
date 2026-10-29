"""Clinical goals (roadmap R5): DVH statements with pass or fail.

A goal is a TG-263 style DVH metric on a structure compared with a value:
``D95%[Gy] >= 57``, ``V20Gy[%] <= 37``, ``D0.03cc[Gy] <= 50.5``,
``Dmean[Gy] < 20``, ``V12.5Gy[cc] <= 1000``, ``D1500cc[Gy] <= 11.6``,
``D95%[%] >= 95`` (relative to the prescription), ``V95%[%] >= 95``. Goals
come in priority levels (1 must, 2 should, 3 would like) and carry their
source. Templates ship in ``radiarch/goals/`` (RTOG 0617, QUANTEC, TG-101
3 and 5 fractions, PENTEC provisional, NCCN head-and-neck) and are
transcriptions of published tables; every template says where it comes
from, and the PENTEC one is marked provisional.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..models.evaluation import ClinicalGoal, GoalResult, GoalTemplate
from .dvh import dose_at_volume, volume_at_dose

GOALS_DIR = Path(__file__).resolve().parent.parent / "goals"

_METRIC = re.compile(
    r"^(?P<kind>D|V)(?P<arg>mean|max|min|median|[0-9]*\.?[0-9]+)(?P<arg_unit>%|cc|Gy)?\[(?P<unit>Gy|%|cc)\]$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Metric:
    """A parsed DVH metric."""

    kind: str          # "D" or "V"
    arg: Optional[float]
    arg_unit: str      # "%", "cc", "Gy", or "" for Dmean/Dmax/Dmin/Dmedian
    stat: str          # "mean", "max", "min", "median" or ""
    unit: str          # "Gy", "%" or "cc"

    @property
    def needs_prescription(self) -> bool:
        return self.unit == "%" and self.kind == "D" or (self.kind == "V" and self.arg_unit == "%")

    def text(self) -> str:
        if self.stat:
            return f"D{self.stat}[{self.unit}]"
        arg = f"{self.arg:g}"
        return f"{self.kind}{arg}{self.arg_unit}[{self.unit}]"


def parse_metric(text: str) -> Metric:
    m = _METRIC.match(text.strip())
    if not m:
        raise ValueError(f"not a DVH metric: {text!r} (examples: D95%[Gy], V20Gy[%], D0.03cc[Gy], Dmean[Gy])")
    kind = m.group("kind").upper()
    arg = m.group("arg").lower()
    _units = {"gy": "Gy", "%": "%", "cc": "cc"}
    arg_unit = _units.get((m.group("arg_unit") or "").lower(), "")
    unit = _units[m.group("unit").lower()]
    if arg in ("mean", "max", "min", "median"):
        if kind != "D" or arg_unit:
            raise ValueError(f"{text!r}: Dmean/Dmax/Dmin/Dmedian take no argument")
        if unit == "cc":
            raise ValueError(f"{text!r}: a dose statistic is in Gy or %")
        return Metric("D", None, "", arg, "Gy" if unit == "Gy" else "%")
    value = float(arg)
    if kind == "D":
        if arg_unit not in ("%", "cc"):
            raise ValueError(f"{text!r}: D<x> needs % (volume fraction) or cc")
        if unit == "cc":
            raise ValueError(f"{text!r}: D<x> is a dose, in Gy or %")
        return Metric("D", value, arg_unit, "", unit)
    if arg_unit not in ("Gy", "%"):
        raise ValueError(f"{text!r}: V<d> needs Gy or % (of the prescription)")
    if unit not in ("%", "cc"):
        raise ValueError(f"{text!r}: V<d> is a volume, in % or cc")
    return Metric("V", value, arg_unit, "", unit)


def evaluate_metric(metric: Metric, doses: np.ndarray, voxel_cc: float, prescription_gy: Optional[float]) -> float:
    """The metric's value on a structure's voxel doses."""
    d = np.asarray(doses, dtype=np.float64).ravel()
    if metric.needs_prescription and not prescription_gy:
        raise ValueError(f"{metric.text()} needs a prescription dose")
    if d.size == 0:
        return 0.0
    if metric.kind == "D":
        if metric.stat == "mean":
            val = float(d.mean())
        elif metric.stat == "max":
            val = float(d.max())
        elif metric.stat == "min":
            val = float(d.min())
        elif metric.stat == "median":
            val = float(np.median(d))
        elif metric.arg_unit == "%":
            val = dose_at_volume(d, float(metric.arg))
        else:   # D<cc>: the dose received by at least <cc> of the structure
            vol_cc = d.size * voxel_cc
            pct = min(100.0, 100.0 * float(metric.arg) / vol_cc) if vol_cc > 0 else 100.0
            val = dose_at_volume(d, pct) if float(metric.arg) <= vol_cc else float(d.min())
        if metric.unit == "%":
            val = 100.0 * val / float(prescription_gy)
        return float(val)
    # V<d>
    dose_level = float(metric.arg) if metric.arg_unit == "Gy" else float(metric.arg) / 100.0 * float(prescription_gy)
    pct = volume_at_dose(d, dose_level)
    return float(pct if metric.unit == "%" else pct / 100.0 * d.size * voxel_cc)


_OPS: Dict[str, Callable[[float, float], bool]] = {
    "<=": lambda a, b: a <= b + 1e-9, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b - 1e-9, ">": lambda a, b: a > b,
}


def evaluate_goal(goal: ClinicalGoal, doses: np.ndarray, voxel_cc: float, prescription_gy: Optional[float],
                  scenario_doses: Optional[Dict[str, np.ndarray]] = None, resolved_structure: Optional[str] = None) -> GoalResult:
    metric = parse_metric(goal.metric)
    achieved = evaluate_metric(metric, doses, voxel_cc, prescription_gy)
    op = _OPS[goal.op]
    passed = op(achieved, goal.value)
    per_scenario: Dict[str, float] = {}
    worst = achieved
    if scenario_doses:
        for name, sd in scenario_doses.items():
            v = evaluate_metric(metric, sd, voxel_cc, prescription_gy)
            per_scenario[name] = v
        vals = [achieved] + list(per_scenario.values())
        worst = min(vals) if goal.op in (">=", ">") else max(vals)
    return GoalResult(
        structure=goal.structure, resolved_structure=resolved_structure or goal.structure, metric=metric.text(), op=goal.op,
        value=goal.value, priority=goal.priority, achieved=achieved, passed=bool(passed),
        margin=float(achieved - goal.value) if goal.op in (">=", ">") else float(goal.value - achieved),
        worst_case=float(worst), passed_all_scenarios=bool(op(worst, goal.value)) if scenario_doses else None,
        per_scenario=per_scenario, note=goal.note, source=goal.source,
    )


# ---------------------------------------------------------------------------
# Templates and name resolution
# ---------------------------------------------------------------------------

def builtin_templates() -> Dict[str, Path]:
    return {p.stem: p for p in sorted(GOALS_DIR.glob("*.json"))}


def load_template(template_id: str) -> GoalTemplate:
    path = builtin_templates().get(template_id)
    if path is None:
        raise ValueError(f"unknown goal template {template_id!r}; available: {sorted(builtin_templates())}")
    data = json.loads(path.read_text())
    return GoalTemplate.model_validate(data)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve_structure(goal_structure: str, available: Sequence[str], aliases: Dict[str, List[str]],
                      user_aliases: Optional[Dict[str, str]] = None) -> Optional[str]:
    """The geometry structure a goal applies to: the user's mapping, the exact name, an alias
    (``Lung_L+Lung_R`` style unions are not resolved here), or a case- and punctuation-insensitive match."""
    if user_aliases and goal_structure in user_aliases:
        wanted = user_aliases[goal_structure]
        return next((a for a in available if a == wanted), None)
    by_norm = {_norm(a): a for a in available}
    if goal_structure in available:
        return goal_structure
    if _norm(goal_structure) in by_norm:
        return by_norm[_norm(goal_structure)]
    for alias in aliases.get(goal_structure, []):
        if alias in available:
            return alias
        if _norm(alias) in by_norm:
            return by_norm[_norm(alias)]
    return None


def grade_goal_set(spec, doses_of: Callable[[str], np.ndarray], available: Sequence[str], voxel_cc: float,
                   prescription_gy: Optional[float], fractions: Optional[int] = None,
                   scenario_doses_of: Optional[Dict[str, Callable[[str], np.ndarray]]] = None):
    """A :class:`~radiarch.models.evaluation.GoalSetSpec` graded on one dose, given the voxel doses of each available
    structure (``doses_of``): the goals of the template and the spec, resolved by name and alias, physical or EQD2.
    With ``scenario_doses_of`` (scenario name → the same for that scenario) each goal also gets its worst case and
    the report ``robust_all_passed``. The evaluation service grades a dose's scenarios; navigation (R11) grades a
    blended dose with this."""
    from ..models.evaluation import GoalsReport
    from .radiobiology import default_alpha_beta, eqd2

    template = load_template(spec.template_id) if spec.template_id else None
    goals = (list(template.goals) if template else []) + list(spec.goals)
    aliases = dict(template.aliases) if template else {}
    basis = spec.dose_basis or (template.dose_basis if template else "physical")
    if basis == "EQD2" and fractions is None:
        raise ValueError("EQD2 goals need the plan's fractions")
    results: List[GoalResult] = []
    for goal in goals:
        resolved = resolve_structure(goal.structure, available, aliases, spec.structure_aliases)
        source = goal.source or (template.source if template else "")
        if resolved is None:
            results.append(GoalResult(structure=goal.structure, metric=goal.metric, op=goal.op, value=goal.value, priority=goal.priority,
                                      note=goal.note, source=source, missing=True, passed=None if spec.skip_missing else False))
            continue
        doses = doses_of(resolved)
        scen = {nm: f(resolved) for nm, f in scenario_doses_of.items()} if scenario_doses_of else None
        if basis == "EQD2":
            ab = spec.alpha_beta_gy.get(resolved, spec.alpha_beta_gy.get(goal.structure, default_alpha_beta(resolved)))
            doses = eqd2(doses, fractions, ab)
            scen = {nm: eqd2(d, fractions, ab) for nm, d in scen.items()} if scen else scen
        r = evaluate_goal(goal, doses, voxel_cc, prescription_gy, scen, resolved)
        r.source = r.source or source
        results.append(r)
    evaluable = [r for r in results if not r.missing]
    return GoalsReport(
        template_id=spec.template_id, dose_basis=basis, fractions=fractions, n_goals=len(results),
        n_passed=sum(1 for r in evaluable if r.passed), n_failed=sum(1 for r in evaluable if not r.passed),
        n_missing=sum(1 for r in results if r.missing),
        passed_by_priority={p: sum(1 for r in evaluable if r.priority == p and r.passed) for p in (1, 2, 3)},
        failed_by_priority={p: sum(1 for r in evaluable if r.priority == p and not r.passed) for p in (1, 2, 3)},
        all_priority1_passed=all(r.passed for r in evaluable if r.priority == 1),
        robust_all_passed=all(r.passed_all_scenarios for r in evaluable) if scenario_doses_of else None, results=results)


__all__ = ["GOALS_DIR", "Metric", "parse_metric", "evaluate_metric", "evaluate_goal", "builtin_templates", "load_template",
           "resolve_structure", "grade_goal_set"]
