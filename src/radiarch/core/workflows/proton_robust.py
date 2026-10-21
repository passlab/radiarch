"""Proton robust optimization workflow — IMPT over setup and range scenarios."""

from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from ._helpers import PlannerError, robust_scenarios
from .proton_optimized import optimize_and_compute
from ...models.dose import ScenarioSetSpec
from ...models.optimization import RobustnessSpec
from ...models.plan import PlanDetail, RobustnessConfig


def configure_robustness(rob_cfg: RobustnessConfig | None) -> RobustnessSpec:
    """Translate a :class:`RobustnessConfig` into the optimizer's :class:`RobustnessSpec`
    (worst-case aggregation over the scenarios of :func:`robust_scenarios`)."""
    scenarios = robust_scenarios(rob_cfg)
    if not scenarios:
        raise PlannerError("the robustness configuration yields no scenario (zero setup and range errors)")
    return RobustnessSpec(enabled=True, scenarios=scenarios, aggregation="WORST_CASE")


def run(plan: PlanDetail) -> Dict[str, Any]:
    logger.info("Starting robust proton optimization for plan %s", plan.id)
    rob_cfg = plan.robustness or RobustnessConfig()
    robustness = configure_robustness(rob_cfg)
    summary = optimize_and_compute(plan, robustness=robustness,
                                   scenarios=ScenarioSetSpec(scenarios=robustness.scenarios))
    summary["engine"] = "mcsquare_robust"
    summary["robustness"] = {
        "strategy": rob_cfg.selection_strategy,
        "scenarios": len(robustness.scenarios),
        "aggregation": robustness.aggregation,
        "setupSystematicErrorMm": list(rob_cfg.setup_systematic_error_mm),
        "rangeErrorPct": rob_cfg.range_systematic_error_pct,
        "notes": "random per-fraction setup error is not modelled as a scenario",
    }
    return summary
