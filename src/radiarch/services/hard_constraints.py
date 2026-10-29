"""Hard constraints by an augmented Lagrangian (roadmap R11, D2).

A :class:`~radiarch.models.optimization.ConstraintSpec` is a weighted penalty: the optimizer trades it against the
objectives like any other term. A multi-criteria run needs limits that hold in every Pareto plan, so that a blend of
plans holds them too. This module enforces :class:`~radiarch.models.optimization.HardConstraint` limits with the
method of multipliers (Nocedal & Wright, *Numerical Optimization*, 2nd ed., §17.4) around the same bound-constrained
solvers: each round minimizes the objectives plus, for every constraint residual ``c <= 0``,

    ``(max(0, mu + rho c)^2 - mu^2) / (2 rho)``

then updates ``mu <- max(0, mu + rho c)`` and raises ``rho`` tenfold when the worst violation has not fallen to a
quarter. ``Dmax`` and ``Dmin`` have one residual per voxel of the structure, ``Dmean`` and ``gEUD`` one each.

Before that, a feasibility run minimizes the constraint terms alone. If even that leaves a violation beyond a
constraint's tolerance, no plan on these beams meets the set, and :class:`InfeasibleConstraintsError` names the
constraints that fail, as a commercial MCO does before it generates any plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np
from loguru import logger

from ..models.optimization import HardConstraint, HardConstraintOutcome
from .objectives import _geud

AL_ROUNDS = 12          # outer rounds before giving up on a tolerance
RHO_START = 10.0
RHO_MAX = 1e8


class InfeasibleConstraintsError(ValueError):
    """No plan on these beams meets the hard constraints; the message lists the ones that fail."""


class HardConstraintTerm:
    """One hard constraint on its structure: residuals ``c`` (``c <= 0`` is met) and their augmented-Lagrangian term."""

    def __init__(self, spec: HardConstraint, mask: np.ndarray):
        self.spec = spec
        self.mask = np.asarray(mask, dtype=np.float64)
        self.idx = np.flatnonzero(self.mask.ravel() > 0)
        self.n = float(self.idx.size)
        self.voxelwise = spec.metric in ("Dmax", "Dmin")
        self.mu = np.zeros(self.idx.size if self.voxelwise else 1)

    def residuals(self, dose: np.ndarray) -> Tuple[np.ndarray, Callable[[np.ndarray], np.ndarray]]:
        """``c`` and a map from ``dPhi/dc`` to the gradient in dose."""
        s, flat = self.spec, np.asarray(dose, dtype=np.float64).ravel()
        if self.n == 0:
            return np.zeros(self.mu.size), lambda y: np.zeros(dose.shape)
        if self.voxelwise:
            sign = 1.0 if s.metric == "Dmax" else -1.0
            c = sign * (flat[self.idx] - s.value_gy)

            def back(y: np.ndarray) -> np.ndarray:
                g = np.zeros(flat.size)
                g[self.idx] = sign * y
                return g.reshape(dose.shape)
            return c, back
        if s.metric == "Dmean":
            value, dvdd = float(flat[self.idx].mean()), self.mask / self.n
        else:
            value, dvdd = _geud(np.asarray(dose, dtype=np.float64), self.mask, self.n, float(s.eud_a))
        sign = 1.0 if s.op == "<=" else -1.0
        return np.array([sign * (value - s.value_gy)]), lambda y: sign * float(y[0]) * dvdd

    def term(self, dose: np.ndarray, rho: float) -> Tuple[float, np.ndarray]:
        c, back = self.residuals(dose)
        y = np.maximum(0.0, self.mu + rho * c)
        return float((np.sum(y * y) - np.sum(self.mu * self.mu)) / (2.0 * rho)), back(y)

    def update(self, dose: np.ndarray, rho: float) -> None:
        c, _ = self.residuals(dose)
        self.mu = np.maximum(0.0, self.mu + rho * c)

    def violation(self, dose: np.ndarray) -> float:
        c, _ = self.residuals(dose)
        return float(max(0.0, c.max())) if c.size else 0.0

    def outcome(self, dose: np.ndarray) -> HardConstraintOutcome:
        s, flat = self.spec, np.asarray(dose, dtype=np.float64).ravel()
        if self.n == 0:
            achieved = 0.0
        elif s.metric == "Dmax":
            achieved = float(flat[self.idx].max())
        elif s.metric == "Dmin":
            achieved = float(flat[self.idx].min())
        elif s.metric == "Dmean":
            achieved = float(flat[self.idx].mean())
        else:
            achieved = _geud(np.asarray(dose, dtype=np.float64), self.mask, self.n, float(s.eud_a))[0]
        v = self.violation(dose)
        return HardConstraintOutcome(label=s.label, achieved_gy=round(achieved, 6), violation_gy=round(v, 6),
                                     met=v <= s.tolerance_gy)


@dataclass
class ConstrainedSolve:
    weights: np.ndarray
    dose: np.ndarray
    outcomes: List[HardConstraintOutcome]
    rounds: int
    iterations: int
    cost_history: List[float] = field(default_factory=list)
    success: bool = True

    @property
    def met(self) -> bool:
        return all(o.met for o in self.outcomes)


def solve_with_hard_constraints(
    terms: Sequence[HardConstraintTerm],
    forward: Callable[[np.ndarray], np.ndarray],
    backward: Callable[[np.ndarray], np.ndarray],
    w0: np.ndarray,
    solver,
    max_iter: int,
    tol: float,
    dose_terms: Optional[Callable[[np.ndarray], Tuple[float, np.ndarray]]] = None,
    weight_terms: Optional[Callable[[np.ndarray], Tuple[float, np.ndarray]]] = None,
    rounds: int = AL_ROUNDS,
    callback=None,
) -> ConstrainedSolve:
    """Minimize ``dose_terms`` (and ``weight_terms``) subject to ``terms`` by the method of multipliers.

    ``forward`` maps weights to the dose grid, ``backward`` a dose-grid gradient to weights. Without ``dose_terms``
    this is the feasibility run: the constraint terms alone. Stops when every violation is within its tolerance or
    after ``rounds``; the multipliers start at zero for each call.
    """
    for t in terms:
        t.mu = np.zeros_like(t.mu)
    rho = RHO_START
    w = np.asarray(w0, dtype=np.float64).ravel()
    history: List[float] = []
    iterations = 0
    success = True
    worst_prev = np.inf
    dose = forward(w)
    r = 0
    for r in range(1, rounds + 1):
        def cost_and_grad(x: np.ndarray, rho=rho) -> Tuple[float, np.ndarray]:
            x = np.asarray(x, dtype=np.float64).ravel()
            d = forward(x)
            loss, gd = dose_terms(d) if dose_terms is not None else (0.0, np.zeros(d.shape))
            for t in terms:
                tl, tg = t.term(d, rho)
                loss += tl
                gd = gd + tg
            gw = backward(gd)
            if weight_terms is not None:
                rl, rg = weight_terms(x)
                loss, gw = loss + rl, gw + rg
            return float(loss), np.asarray(gw, dtype=np.float64)

        w, conv = solver.run(cost_and_grad, w, max_iter, tol, callback=callback)
        w = np.clip(np.asarray(w, dtype=np.float64).ravel(), 0.0, None)
        iterations += conv.iterations
        history.extend(conv.cost_history)
        success = success and conv.success
        dose = forward(w)
        excess = [t.violation(dose) - t.spec.tolerance_gy for t in terms]
        worst = max(t.violation(dose) for t in terms) if terms else 0.0
        logger.debug("augmented Lagrangian round {}: rho={:.3g}, worst violation {:.4g} Gy", r, rho, worst)
        if all(e <= 0.0 for e in excess):
            break
        for t in terms:
            t.update(dose, rho)
        if worst > 0.25 * worst_prev:
            rho = min(rho * 10.0, RHO_MAX)
        worst_prev = worst
    return ConstrainedSolve(weights=w, dose=dose, outcomes=[t.outcome(dose) for t in terms], rounds=r,
                            iterations=iterations, cost_history=history, success=success)


def infeasible_message(outcomes: Sequence[HardConstraintOutcome]) -> str:
    failing = [f"{o.label} (best {o.achieved_gy:.3g} Gy, {o.violation_gy:.3g} Gy over)" for o in outcomes if not o.met]
    return "no plan on these beams meets the hard constraints: " + "; ".join(failing)


__all__ = ["AL_ROUNDS", "InfeasibleConstraintsError", "HardConstraintTerm", "ConstrainedSolve",
           "solve_with_hard_constraints", "infeasible_message"]
