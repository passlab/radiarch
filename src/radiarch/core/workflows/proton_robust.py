"""Proton robust optimization workflow — IMPT over setup and range scenarios."""

from __future__ import annotations

from typing import Any, Dict

from loguru import logger

from ._helpers import PlannerError, robust_scenarios
from .proton_optimized import optimize_and_compute
from ...models.dose import EngineScenarioSet, ScenarioSetSpec
from ...models.optimization import RobustnessSpec
from ...models.plan import PlanDetail, RobustnessConfig


def configure_robustness(rob_cfg: RobustnessConfig | None) -> RobustnessSpec:
    """Translate a :class:`RobustnessConfig` into the optimizer's :class:`RobustnessSpec`:
    MCsquare's own scenario sets (ALL 81, REDUCED_SET 21, RANDOM n) with the
    systematic and random setup errors and the range error, worst-case aggregation."""
    cfg = rob_cfg or RobustnessConfig()
    strategy = str(cfg.selection_strategy).strip().upper()
    if strategy not in ("REDUCED_SET", "ALL", "RANDOM"):
        raise PlannerError(f"Unknown robustness selection_strategy {cfg.selection_strategy!r}; expected REDUCED_SET, ALL or RANDOM")
    err = [float(v) for v in cfg.setup_systematic_error_mm][:3] + [0.0] * (3 - len(cfg.setup_systematic_error_mm))
    rnd = [float(v) for v in cfg.setup_random_error_mm][:3] + [0.0] * (3 - len(cfg.setup_random_error_mm))
    native = EngineScenarioSet(
        selection=strategy, setup_systematic_mm=(err[0], err[1], err[2]), setup_random_mm=(rnd[0], rnd[1], rnd[2]),
        range_error_pct=float(cfg.range_systematic_error_pct), count=int(cfg.num_scenarios),
    )
    return RobustnessSpec(enabled=True, engine_native=native, aggregation="WORST_CASE")


def run(plan: PlanDetail) -> Dict[str, Any]:
    logger.info("Starting robust proton optimization for plan {}", plan.id)
    rob_cfg = plan.robustness or RobustnessConfig()
    robustness = configure_robustness(rob_cfg)
    native = robustness.engine_native
    summary = optimize_and_compute(plan, robustness=robustness, scenarios=ScenarioSetSpec(engine_native=native))
    summary["engine"] = "mcsquare_robust"
    summary["robustness"] = {
        "strategy": native.selection,
        "scenarios": len(summary.get("scenarioDoses", [])) or native.n_scenarios,
        "aggregation": robustness.aggregation,
        "setupSystematicErrorMm": list(native.setup_systematic_mm),
        "setupRandomErrorMm": list(native.setup_random_mm),
        "rangeErrorPct": native.range_error_pct,
    }
    return summary
