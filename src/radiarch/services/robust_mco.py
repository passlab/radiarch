"""Robust multi-criteria optimization (roadmap R11.6, D8).

With robustness on, a Pareto set is computed over scenarios (setup shifts, range errors) instead of the nominal dose
alone. Every dose here is a stack, one row per scenario (nominal first), on the navigation voxels only: a scenario's
dose matrix restricted to those voxels makes a stacked dose cheap to compute and to store.

* **Generation: the scenario-wise worst case.** Each Pareto plan minimizes the worst scenario of its weighted sum,
  ``max_s sum_i w_i f_i(x; s)`` (Bokrantz & Fredriksson, EJOR 262:682, 2017). That protects the scenarios that can
  occur; the objective-wise worst case ``sum_i w_i max_s f_i(x; s)`` also guards against an underdosed target and an
  overdosed organ from opposite range errors at once, which no single scenario produces. The maximum is smoothed by
  a log-sum-exp of width ``tau`` per unit weight (a kink stalls the quasi-Newton solvers), which overestimates it by at
  most ``tau * ln S``. ``tau`` is ``SMOOTHING_FRACTION`` of the highest dose level the trade-offs and hard constraints
  name, the prescription in practice (:func:`smoothing_width`): 0.01 Gy at 2 Gy, 0.3 Gy at 60 Gy, so a set smooths
  alike at any dose scale.
* **What a plan reports: each trade-off's worst case** ``F_i(x) = max_s f_i(x; s)``, and its nominal value. ``F_i`` is
  convex (a maximum of convex functions), so a blend of plans is at most the blend of their values, as navigation
  needs. The sandwich algorithm works on ``F``: every plan's ``F`` is attainable (the inner set), and a solve with
  weights ``w`` proves ``w . F(x) >= max_s sum_i w_i f_i(x; s) >= v*`` for every plan ``x``, so ``v*`` (the smoothed
  optimum less ``tau * ln S``) is a valid offset for the outer set. That offset lies below the plan's own
  ``w . F``; the gap is what the objective-wise worst case adds to the scenario-wise one, and the error bound
  includes it.
* **Hard constraints hold in every scenario:** one constraint term per scenario.
"""

from __future__ import annotations

from typing import Callable, List, Sequence, Tuple

import numpy as np

from ..models.optimization import HardConstraint
from .hard_constraints import HardConstraintTerm

SMOOTHING_GY = 0.01      # width of the log-sum-exp over scenarios, in Gy of the weighted sum (per unit weight), when
                         # nothing names a dose level
SMOOTHING_FRACTION = 0.005   # the width as a fraction of the highest dose level named (R11.8)


def smoothing_width(tradeoffs: Sequence, hard_constraints: Sequence[HardConstraint]) -> float:
    """The log-sum-exp width per unit weight for a robust set: ``SMOOTHING_FRACTION`` of the highest dose level its
    trade-offs (``dose_gy``) and hard constraints (``value_gy``) name, else ``SMOOTHING_GY``."""
    levels = [float(o.dose_gy or 0.0) for o in tradeoffs] + [float(c.value_gy) for c in hard_constraints]
    top = max(levels, default=0.0)
    return SMOOTHING_FRACTION * top if top > 0.0 else SMOOTHING_GY


class WorstCase:
    """A trade-off's worst case over the scenarios of a stacked dose: ``max_s f(dose[s])``, with the gradient of the
    worst scenario (a subgradient where two tie)."""

    def __init__(self, objective) -> None:
        self.objective = objective
        self.name = getattr(objective, "name", "")

    def per_scenario(self, dose: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return np.array([self.objective.value(d, mask) for d in dose])

    def value(self, dose: np.ndarray, mask: np.ndarray) -> float:
        return float(self.per_scenario(dose, mask).max())

    def value_and_grad(self, dose: np.ndarray, mask: np.ndarray) -> Tuple[float, np.ndarray]:
        s = int(np.argmax(self.per_scenario(dose, mask)))
        v, g = self.objective.value_and_grad(dose[s], mask)
        grad = np.zeros(dose.shape)
        grad[s] = g
        return float(v), grad

    def nominal(self, dose: np.ndarray, mask: np.ndarray) -> float:
        return float(self.objective.value(dose[0], mask))


class ScenarioTerm:
    """A hard constraint on one scenario's row of a stacked dose (the interface of :class:`HardConstraintTerm`)."""

    def __init__(self, spec: HardConstraint, mask: np.ndarray, scenario: int, scenario_name: str) -> None:
        self.inner = HardConstraintTerm(spec, mask)
        self.spec, self.scenario, self.scenario_name = spec, scenario, scenario_name

    @property
    def mu(self) -> np.ndarray:
        return self.inner.mu

    @mu.setter
    def mu(self, value: np.ndarray) -> None:
        self.inner.mu = value

    def term(self, dose: np.ndarray, rho: float) -> Tuple[float, np.ndarray]:
        loss, g = self.inner.term(dose[self.scenario], rho)
        grad = np.zeros(dose.shape)
        grad[self.scenario] = g
        return loss, grad

    def update(self, dose: np.ndarray, rho: float) -> None:
        self.inner.update(dose[self.scenario], rho)

    def violation(self, dose: np.ndarray) -> float:
        return self.inner.violation(dose[self.scenario])

    def outcome(self, dose: np.ndarray):
        out = self.inner.outcome(dose[self.scenario])
        if self.scenario:
            out.label = f"{out.label} [{self.scenario_name}]"
        return out


def scenario_terms(constraints: Sequence[HardConstraint], masks: Sequence[np.ndarray], names: Sequence[str]) -> List[ScenarioTerm]:
    return [ScenarioTerm(c, m, s, nm) for c, m in zip(constraints, masks) for s, nm in enumerate(names)]


def scenario_wise(objectives: Sequence, masks: Sequence[np.ndarray], raw: np.ndarray,
                  smoothing_gy: float = SMOOTHING_GY) -> Tuple[Callable[[np.ndarray], Tuple[float, np.ndarray]], Callable[[np.ndarray], float]]:
    """``(dose_terms, bound)`` for the weights ``raw``: ``dose_terms`` the smoothed worst scenario of the weighted sum
    of the (unwrapped) objectives over a stacked dose and its gradient; ``bound(dose)`` that value less the most the
    smoothing adds, a lower bound on the worst scenario's weighted sum."""
    raw = np.asarray(raw, dtype=np.float64)
    tau = smoothing_gy * float(raw.sum())

    def dose_terms(dose: np.ndarray) -> Tuple[float, np.ndarray]:
        S = dose.shape[0]
        sums, grads = np.zeros(S), np.zeros(dose.shape)
        for s in range(S):
            for wi, o, m in zip(raw, objectives, masks):
                v, g = o.value_and_grad(dose[s], m)
                sums[s] += wi * v
                grads[s] += wi * g
        top = sums.max()
        p = np.exp((sums - top) / tau)
        lse = top + tau * np.log(p.sum())
        p /= p.sum()
        return float(lse), grads * p.reshape((S,) + (1,) * (dose.ndim - 1))

    def bound(dose: np.ndarray) -> float:
        return dose_terms(dose)[0] - tau * np.log(dose.shape[0])

    return dose_terms, bound


class StackedOps:
    """Weights to the stacked dose on the navigation voxels and back: one dose-matrix row block per scenario."""

    def __init__(self, matrices: Sequence) -> None:
        self.matrices = list(matrices)

    def forward(self, w: np.ndarray) -> np.ndarray:
        w = np.asarray(w, dtype=np.float64).ravel()
        return np.stack([np.asarray(M @ w, dtype=np.float64).ravel() for M in self.matrices])

    def backward(self, grad: np.ndarray) -> np.ndarray:
        out = np.zeros(self.matrices[0].shape[1])
        for M, g in zip(self.matrices, grad):
            out += np.asarray(M.T @ np.asarray(g, dtype=np.float64).ravel(), dtype=np.float64)
        return out


__all__ = ["SMOOTHING_GY", "SMOOTHING_FRACTION", "smoothing_width", "WorstCase", "ScenarioTerm", "scenario_terms", "scenario_wise", "StackedOps"]
