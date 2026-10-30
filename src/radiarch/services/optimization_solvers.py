"""Solver plugins for the Optimization Service (Service 4).

A *solver* takes a differentiable cost function (returning value **and**
gradient together) plus an initial fluence-weight vector, and drives the
weights toward a minimum subject to physical non-negativity (fluence
weights cannot be negative). Every solver implements the same
:class:`SolverPlugin` protocol so :class:`OptimizationService` can swap
engines (L-BFGS-B, Adam, projected-gradient) without changing call sites.

Solvers are deliberately ignorant of the *meaning* of the cost: they only
see ``cost_and_grad`` and a starting point. The composite objective (dose
fidelity, DVH, EUD, regularizers) is assembled elsewhere and handed in as
a single callable. This keeps the optimizer decoupled from the objective
library and makes it trivially unit-testable on synthetic convex problems.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Protocol, Tuple, runtime_checkable

import numpy as np
from loguru import logger
from scipy.optimize import minimize

from ..models.optimization import ConvergenceInfo

GAIN_BOX = 2.0          # the box of the gain on offer: weights up to this multiple of the largest weight
MAX_RESTARTS = 100      # restarts of L-BFGS-B after a stall (a safety cap: the iteration budget is the limit)
STALL_WINDOW = 50       # the stall test's window, in iterations


def stalled(history: List[float], rel: float, window: int = STALL_WINDOW) -> bool:
    """The cost has stopped falling: over the last ``window`` iterations it fell by at most ``rel`` of itself. A window,
    unlike scipy's one-step test, is not ended by a single step that barely moves, and ``rel`` is free of the cost's scale."""
    return len(history) > window and history[-window - 1] - history[-1] <= rel * abs(history[-1])


def gain_on_offer(grad, x: np.ndarray, scale: float) -> float:
    """The most a solve could still gain, to first order, from ``x``: the Frank-Wolfe gap ``g.x - min g.y`` over
    ``0 <= y <= GAIN_BOX * scale``. Zero at an optimum on ``x >= 0``; if an optimum lies in that box, the cost at ``x``
    is above it by at most this much (convexity). Free of how the cost and the weights are scaled."""
    g = np.asarray(grad, dtype=float).ravel()
    x = np.clip(np.asarray(x, dtype=float).ravel(), 0.0, None)
    if not g.size:
        return 0.0
    if scale <= 0.0 and np.any(g < 0.0):
        return float("inf")             # all weights zero and a weight would lower the cost: no size to measure by
    return float(g @ x - GAIN_BOX * float(scale) * np.minimum(g, 0.0).sum())


# Signature of the value+gradient oracle. Returning both together (vs. two
# separate calls) lets us pass ``jac=True`` to scipy and avoids recomputing
# the forward dose pass twice per line-search step — the dose evaluation is
# by far the most expensive part of the objective.
CostAndGrad = Callable[[np.ndarray], Tuple[float, np.ndarray]]

# Per-iteration user hook: (iteration, cost, current_weights). Used by the
# service to mirror progress / write checkpoints. Never on the hot path of
# the solver math itself.
IterationCallback = Callable[[int, float, np.ndarray], None]


@runtime_checkable
class SolverPlugin(Protocol):
    """Contract every optimization engine implements.

    ``run`` minimizes ``cost_and_grad`` starting from ``w0``; ``stall_tol``, when given, is the stall test
    (:func:`stalled`) for a solver that supports it (L-BFGS-B), else ignored. Implementations
    must enforce non-negativity of the returned weights (fluence cannot be
    negative) and must populate a :class:`ConvergenceInfo` so the caller can
    report success / iteration count / cost trajectory without knowing which
    engine ran.
    """

    name: str

    def run(
        self,
        cost_and_grad: CostAndGrad,
        w0: np.ndarray,
        max_iter: int,
        convergence_tol: float,
        callback: Optional[IterationCallback] = None,
        stall_tol: Optional[float] = None,
    ) -> Tuple[np.ndarray, ConvergenceInfo]:
        ...


class LBFGSBSolver:
    """Bound-constrained quasi-Newton solver (the default engine).

    Wraps ``scipy.optimize.minimize`` with ``method="L-BFGS-B"``. L-BFGS-B is
    chosen as the default because:

    * It is a quasi-Newton method — it approximates curvature from gradient
      history, so it converges in far fewer expensive dose evaluations than a
      first-order method on the smooth, mildly ill-conditioned objectives that
      dominate IMPT/IMRT inverse planning.
    * It supports **box bounds natively**, which is exactly what we need:
      ``bounds=[(0, None)] * n`` enforces ``w >= 0`` without a penalty or a
      separate projection step, so the returned weights are always physical.

    We pass ``jac=True`` because ``cost_and_grad`` returns ``(cost, grad)`` in
    one call; this halves the number of forward dose passes scipy would
    otherwise need (one for the value, one for the gradient).

    ``convergence_tol`` is wired to scipy's ``ftol`` (relative reduction in
    cost between iterations), and ``max_iter`` to ``maxiter``.
    """

    name: str = "L-BFGS-B"

    def run(
        self,
        cost_and_grad: CostAndGrad,
        w0: np.ndarray,
        max_iter: int,
        convergence_tol: float,
        callback: Optional[IterationCallback] = None,
        stall_tol: Optional[float] = None,
    ) -> Tuple[np.ndarray, ConvergenceInfo]:
        """Minimize ``cost_and_grad`` from ``w0`` under ``w >= 0``.

        Returns the final (non-negative) weight vector and a
        :class:`ConvergenceInfo` carrying the per-iteration cost history. The
        optional ``callback`` is invoked once per accepted iteration with
        ``(iteration, cost, weights)`` for progress mirroring / checkpoints.
        """
        x0 = np.asarray(w0, dtype=float).ravel()
        n = x0.size

        # scipy's L-BFGS-B callback only receives the current vector, not the
        # cost. Rather than re-running the (expensive) objective inside the
        # callback, we cache the most recent (cost, grad) keyed by the vector
        # identity computed in ``_objective``. The optimizer always evaluates
        # the objective at the iterate immediately before invoking the
        # callback, so the cache is warm and exact.
        cost_history: List[float] = []
        last_eval: dict = {"x": None, "cost": None, "grad": None}
        iteration = 0
        scale = float(np.max(x0)) if n else 0.0         # the gain's box: the largest weight seen so far
        done = {"stalled": False}

        def _objective(x: np.ndarray) -> Tuple[float, np.ndarray]:
            cost, grad = cost_and_grad(x)
            cost = float(cost)
            grad = np.asarray(grad, dtype=float).ravel()
            last_eval["x"] = np.array(x, copy=True)
            last_eval["cost"] = cost
            last_eval["grad"] = grad
            return cost, grad

        def _gain(x: np.ndarray, grad: np.ndarray) -> float:
            nonlocal scale
            scale = max(scale, float(np.max(x)) if n else 0.0)
            return gain_on_offer(grad, x, scale)

        def _scipy_callback(xk: np.ndarray) -> None:
            nonlocal iteration
            iteration += 1
            # Use the cached cost from the matching objective evaluation; fall
            # back to a fresh evaluation only if the cache somehow missed.
            if last_eval["x"] is not None and np.array_equal(last_eval["x"], xk):
                cost = last_eval["cost"]
            else:  # pragma: no cover - defensive; scipy evaluates before cb
                cost, _ = cost_and_grad(xk)
                cost = float(cost)
            cost_history.append(cost)
            if callback is not None:
                callback(iteration, cost, np.array(xk, copy=True))
            if stall_tol is not None and stalled(cost_history, stall_tol):
                done["stalled"] = True
                raise StopIteration     # converged by the stall test; scipy ends the solve here

        logger.debug(
            "L-BFGS-B start: n={} max_iter={} ftol={}", n, max_iter, convergence_tol
        )

        # With ``stall_tol`` (multi-criteria solves, R11.8) the solve has converged when its cost has stopped falling
        # (:func:`stalled`), whatever stopped scipy. scipy's own tests are off: its projected-gradient test is absolute
        # (it stops a problem with small gradients before it moves), and so is its cost-change test for costs below 1
        # (one step that barely moves ends the solve, and scipy calls that converged). A failed line search restarts
        # L-BFGS-B from there with fresh curvature memory, within the same iteration budget; a restart that cannot take
        # a step means no step lowers the cost. The gain still on offer (:func:`gain_on_offer`) is reported, not tested:
        # its box makes it a valid but loose bound on a fluence problem, far above a cost that has stopped falling.
        x_start, used, restarts, gain, stuck = x0, 0, 0, None, False
        while True:
            res = minimize(
                fun=_objective,
                x0=x_start,
                method="L-BFGS-B",
                jac=True,  # _objective returns (cost, grad) together
                bounds=[(0, None)] * n,  # non-negativity of fluence weights
                options={"maxiter": max_iter - used,
                         **({"ftol": convergence_tol} if stall_tol is None else {"ftol": 0.0, "gtol": 0.0})},
                callback=_scipy_callback,
            )
            used += int(res.nit)
            if stall_tol is None or done["stalled"]:
                break
            failed = any(m in str(res.message) for m in ("REDUCTION OF F", "ABNORMAL"))
            if failed and res.nit == 0:
                stuck = True
                break
            if not failed or used >= max_iter or restarts >= MAX_RESTARTS:
                break
            x_start, restarts = np.asarray(res.x, dtype=float).ravel(), restarts + 1

        w_final = np.asarray(res.x, dtype=float).ravel()
        # Belt-and-braces: the bounds already guarantee w >= 0, but clip away
        # any tiny negative values from floating-point slack at the boundary.
        w_final = np.clip(w_final, 0.0, None)

        final_cost = float(res.fun)
        # Ensure the history ends on the final cost even if scipy stopped
        # without a final callback (e.g. maxiter reached, or 0 iterations).
        if not cost_history or cost_history[-1] != final_cost:
            cost_history.append(final_cost)

        if stall_tol is None:
            success = bool(res.success)
        else:
            gain = _gain(w_final, np.asarray(res.jac, dtype=float).ravel())
            # the stall test, a restart with no step to take, or a projected gradient of exactly zero
            success = (done["stalled"] or stuck or stalled(cost_history, stall_tol)
                       or "PROJECTED GRADIENT" in str(res.message))
        info = ConvergenceInfo(
            success=success,
            iterations=used,
            final_cost=final_cost,
            cost_history=cost_history,
            # The solver enforces the only hard constraint it knows about
            # (non-negativity) via box bounds, so there are no residual
            # constraint violations to report at this layer. Per-objective
            # penalty residuals are computed by the service, not the solver.
            constraint_violations={},
            remaining_gain=gain,
        )
        logger.debug(
            "L-BFGS-B done: success={} nit={} final_cost={:.6g} ({}){}",
            info.success,
            info.iterations,
            info.final_cost,
            res.message,
            "" if stall_tol is None else f", gain on offer {gain:.3g}, {restarts} restart(s)",
        )
        return w_final, info


class AdamSolver:
    """First-order adaptive-moment solver with non-negativity projection.

    Adam maintains per-coordinate running estimates of the gradient's first
    and second moments and rescales the step accordingly, which makes it
    robust to the wildly different per-spot sensitivities typical of a wide
    Dij. It is the right default when the weight vector is very large
    (>~100k spots) or the Hessian is too ill-conditioned for L-BFGS-B's
    limited-memory curvature model to help — each step is O(n) with no line
    search, so iterations are cheap even when there are hundreds of thousands
    of them.

    Non-negativity is enforced by projection (``w = max(w, 0)``) *after* each
    update rather than via bounds, so the returned weights are always physical.
    Convergence is declared when the relative cost improvement drops below
    ``convergence_tol`` for a couple of consecutive iterations.
    """

    name: str = "Adam"

    def __init__(self, learning_rate: float = 0.05, beta1: float = 0.9,
                 beta2: float = 0.999, eps: float = 1e-8):
        self.learning_rate = float(learning_rate)
        self.beta1 = float(beta1)
        self.beta2 = float(beta2)
        self.eps = float(eps)

    def run(
        self,
        cost_and_grad: CostAndGrad,
        w0: np.ndarray,
        max_iter: int,
        convergence_tol: float,
        callback: Optional[IterationCallback] = None,
        stall_tol: Optional[float] = None,
    ) -> Tuple[np.ndarray, ConvergenceInfo]:
        w = np.clip(np.asarray(w0, dtype=float).ravel(), 0.0, None)
        m = np.zeros_like(w)
        v = np.zeros_like(w)
        lr = self.learning_rate
        tol = convergence_tol if convergence_tol and convergence_tol > 0 else 1e-9

        cost_history: List[float] = []
        prev_cost: Optional[float] = None
        converged = False
        stable = 0
        it = 0

        for it in range(1, int(max_iter) + 1):
            cost, grad = cost_and_grad(w)
            cost = float(cost)
            grad = np.asarray(grad, dtype=float).ravel()
            cost_history.append(cost)
            if callback is not None:
                callback(it, cost, np.array(w, copy=True))

            if prev_cost is not None:
                denom = abs(prev_cost) if abs(prev_cost) > 1e-30 else 1.0
                if abs(prev_cost - cost) / denom < tol:
                    stable += 1
                    if stable >= 2:
                        converged = True
                        break
                else:
                    stable = 0
            prev_cost = cost

            m = self.beta1 * m + (1.0 - self.beta1) * grad
            v = self.beta2 * v + (1.0 - self.beta2) * (grad * grad)
            m_hat = m / (1.0 - self.beta1 ** it)
            v_hat = v / (1.0 - self.beta2 ** it)
            w = w - lr * m_hat / (np.sqrt(v_hat) + self.eps)
            np.clip(w, 0.0, None, out=w)  # project onto the feasible set

        final_cost = cost_history[-1] if cost_history else float(cost_and_grad(w)[0])
        info = ConvergenceInfo(
            success=converged,
            iterations=it,
            final_cost=final_cost,
            cost_history=cost_history,
            constraint_violations={},
        )
        logger.debug("Adam done: success={} nit={} final_cost={:.6g}",
                     info.success, info.iterations, info.final_cost)
        return w, info


class ProjectedGradientSolver:
    """Projected gradient descent with backtracking line search.

    The simplest of the three engines and the most predictable: at each step
    it takes a steepest-descent direction, backtracks the step size until the
    cost actually decreases (Armijo-style sufficient-decrease), and projects
    onto ``w >= 0``. It has no momentum and no curvature model, so it is slower
    to converge than L-BFGS-B or Adam — but for exactly that reason it is the
    debugging engine of choice: if a composite objective misbehaves under the
    fancier solvers, run it here to see the raw descent behaviour.
    """

    name: str = "ProjectedGradient"

    def __init__(self, initial_step: float = 1.0, shrink: float = 0.5,
                 max_backtracks: int = 30):
        self.initial_step = float(initial_step)
        self.shrink = float(shrink)
        self.max_backtracks = int(max_backtracks)

    def run(
        self,
        cost_and_grad: CostAndGrad,
        w0: np.ndarray,
        max_iter: int,
        convergence_tol: float,
        callback: Optional[IterationCallback] = None,
        stall_tol: Optional[float] = None,
    ) -> Tuple[np.ndarray, ConvergenceInfo]:
        w = np.clip(np.asarray(w0, dtype=float).ravel(), 0.0, None)
        tol = convergence_tol if convergence_tol and convergence_tol > 0 else 1e-9

        cost_history: List[float] = []
        converged = False
        it = 0
        cost, grad = cost_and_grad(w)
        cost = float(cost)

        for it in range(1, int(max_iter) + 1):
            grad = np.asarray(grad, dtype=float).ravel()
            step = self.initial_step
            new_w = w
            new_cost = cost
            # Backtracking line search with projection inside the loop, so the
            # accepted point is always feasible and strictly improves the cost.
            for _ in range(self.max_backtracks):
                cand = np.clip(w - step * grad, 0.0, None)
                cand_cost, cand_grad = cost_and_grad(cand)
                cand_cost = float(cand_cost)
                if cand_cost < cost:
                    new_w, new_cost = cand, cand_cost
                    grad = cand_grad
                    break
                step *= self.shrink
            else:
                # No decrease found — we're at a (projected) stationary point.
                converged = True
                cost_history.append(cost)
                if callback is not None:
                    callback(it, cost, np.array(w, copy=True))
                break

            cost_history.append(new_cost)
            if callback is not None:
                callback(it, new_cost, np.array(new_w, copy=True))

            denom = abs(cost) if abs(cost) > 1e-30 else 1.0
            improved = (cost - new_cost) / denom
            w, cost = new_w, new_cost
            if improved < tol:
                converged = True
                break

        info = ConvergenceInfo(
            success=converged,
            iterations=it,
            final_cost=float(cost),
            cost_history=cost_history or [float(cost)],
            constraint_violations={},
        )
        logger.debug("ProjectedGradient done: success={} nit={} final_cost={:.6g}",
                     info.success, info.iterations, info.final_cost)
        return w, info


# ---------------------------------------------------------------------------
# Registry — resolve a SolverConfig.method string to a solver instance
# ---------------------------------------------------------------------------

_SOLVERS = {
    "L-BFGS-B": LBFGSBSolver,
    "Adam": AdamSolver,
    "ProjectedGradient": ProjectedGradientSolver,
}


def get_solver(method: str) -> SolverPlugin:
    """Instantiate the solver plugin named by ``method``.

    The name set matches ``SolverConfig.method``'s allowed values, so a
    validated request always resolves. Raises :class:`ValueError` (surfaced as
    422 by the API) for an unknown method.
    """
    try:
        cls = _SOLVERS[method]
    except KeyError as exc:
        raise ValueError(
            f"unknown solver method {method!r}; "
            f"available: {sorted(_SOLVERS)}"
        ) from exc
    return cls()


__all__ = [
    "GAIN_BOX",
    "MAX_RESTARTS",
    "STALL_WINDOW",
    "gain_on_offer",
    "stalled",
    "CostAndGrad",
    "IterationCallback",
    "SolverPlugin",
    "LBFGSBSolver",
    "AdamSolver",
    "ProjectedGradientSolver",
    "get_solver",
]
