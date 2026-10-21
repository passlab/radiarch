"""Dose impact comparisons (roadmap R5): ``dvh_impact`` as a first-class result.

Two evaluations side by side — the same dose on two structure sets (an AI
contour set against the physician's), or two doses on one geometry (a plan
and its re-optimization) — with the DVH metrics of every structure in both,
their differences, and the goals that changed state.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from ..models.evaluation import DVHMetrics, EvaluationRequest, EvaluationResult


def _metric_fields() -> List[str]:
    return list(DVHMetrics.model_fields)


def compare_evaluations(a: EvaluationResult, b: EvaluationResult, structures: Optional[List[str]] = None) -> dict:
    """Structure-by-structure differences ``b − a`` of the DVH metrics, indices and goal states."""
    ma = {c.structure_name: c.metrics for c in a.dvh_curves}
    mb = {c.structure_name: c.metrics for c in b.dvh_curves}
    names = structures or sorted(set(ma) | set(mb))
    per_structure = []
    for name in names:
        row: dict = {"structure": name, "in_a": name in ma, "in_b": name in mb, "delta": {}, "delta_pct": {}, "a": None, "b": None}
        if name in ma:
            row["a"] = ma[name].model_dump()
        if name in mb:
            row["b"] = mb[name].model_dump()
        if name in ma and name in mb:
            for f in _metric_fields():
                va, vb = float(getattr(ma[name], f)), float(getattr(mb[name], f))
                row["delta"][f] = vb - va
                row["delta_pct"][f] = (vb - va) / va * 100.0 if abs(va) > 1e-12 else None
        per_structure.append(row)
    indices = None
    if a.indices is not None and b.indices is not None:
        indices = {f: float(getattr(b.indices, f)) - float(getattr(a.indices, f))
                   for f in ("homogeneity_index", "conformity_index", "coverage_pct", "hotspot_gy")}
    goal_changes = []
    if a.goals is not None and b.goals is not None:
        key = lambda r: (r.structure, r.metric, r.op, round(r.value, 9))
        ga = {key(r): r for r in a.goals.results}
        for r in b.goals.results:
            k = key(r)
            if k in ga and ga[k].passed != r.passed:
                goal_changes.append({"structure": r.structure, "metric": r.metric, "op": r.op, "value": r.value, "priority": r.priority,
                                     "a_passed": ga[k].passed, "b_passed": r.passed, "a_achieved": ga[k].achieved, "b_achieved": r.achieved})
    largest = max((abs(v) for row in per_structure for v in row["delta"].values()), default=0.0)
    return {
        "evaluation_a": a.evaluation_id, "evaluation_b": b.evaluation_id,
        "structures": per_structure, "indices_delta": indices, "goal_changes": goal_changes,
        "largest_metric_delta": float(largest), "dose_units": b.dose_units,
    }


__all__ = ["compare_evaluations"]
