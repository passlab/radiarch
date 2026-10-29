"""Approximating a convex Pareto set by sandwiching (roadmap R11, D3).

The algorithm knows nothing about doses: it asks a ``solve`` callable for the plan that minimizes a weighted sum of
the objectives, ``sum_i w_i f_i``, and keeps what each answer proves about the set of attainable objective vectors
``Z``. In objectives normalized to ideal 0 and nadir 1:

* every solved plan's objective vector ``P_k`` lies in ``Z``, so the *inner* set ``conv(P) + R^n_+`` is inside
  ``Z + R^n_+``;
* every solve with normalized weights ``a_k`` proves ``a_k . z >= a_k . P_k`` for every attainable ``z``, so the
  *outer* set ``{z : a_k . z >= b_k}`` contains ``Z``.

The Pareto set lies between the two. The largest distance from a point of the outer set to the inner set,
``h = max_{v in outer} min_{z in inner} max_i (z_i - v_i)``, bounds how far any Pareto point can be from the
plans' convex hull (Bokrantz & Forsgren, INFORMS J Comput 25:377, 2013). It is attained at a vertex of the outer set,
so the vertices are enumerated (Qhull, through ``scipy.spatial.HalfspaceIntersection``) and one linear program per
vertex measures its distance (HiGHS, through ``scipy.optimize.linprog``). The dual multipliers of the worst vertex's
program are the normal of a supporting hyperplane there: the weights of the next plan.

Order (as in RayStation's MCO): one anchor plan per objective (weight 1 on it and ``eps`` on the others, so that it is
Pareto optimal rather than only weakly so), which fix the ideal and nadir; a balance plan with equal normalized
weights; then sandwich plans until the bound is within ``tol`` or the plan budget is spent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np
from loguru import logger
from scipy.optimize import linprog
from scipy.spatial import HalfspaceIntersection

MIN_RANGE = 1e-6        # an objective whose anchors span less than this (in its own units) is not traded


@dataclass
class Solved:
    """One weighted-sum solve: its decision vector and its objective values (raw units).

    ``bound``, when given, is a lower bound on the weighted sum over every attainable vector, used for the outer set
    in place of the plan's own weighted sum (a robust solve minimizes something below it; ``robust_mco``)."""

    x: np.ndarray
    values: np.ndarray
    ok: bool = True
    bound: Optional[float] = None


@dataclass
class SandwichPlan:
    kind: str                          # anchor | balance | sandwich
    raw_weights: np.ndarray
    solved: Solved


@dataclass
class SandwichResult:
    plans: List[SandwichPlan]
    ideal: np.ndarray
    nadir: np.ndarray
    history: List[Tuple[int, float]] = field(default_factory=list)     # (plans so far, error bound)
    stop_reason: str = ""
    flat: List[int] = field(default_factory=list)                     # objectives the anchors did not spread

    @property
    def error(self) -> float:
        return self.history[-1][1] if self.history else float("inf")

    def normalized(self) -> np.ndarray:
        return normalize(np.array([p.solved.values for p in self.plans]), self.ideal, self.nadir)


def normalize(values: np.ndarray, ideal: np.ndarray, nadir: np.ndarray) -> np.ndarray:
    span = np.where(nadir - ideal > MIN_RANGE, nadir - ideal, 1.0)
    return (np.asarray(values, float) - ideal) / span


def _interior(halfspaces: np.ndarray) -> Optional[np.ndarray]:
    """The Chebyshev centre of ``{x : A x + c <= 0}``, or None when the set has no interior."""
    A, c = halfspaces[:, :-1], halfspaces[:, -1]
    norm = np.linalg.norm(A, axis=1)
    n = A.shape[1]
    res = linprog(np.r_[np.zeros(n), -1.0], A_ub=np.c_[A, norm], b_ub=-c, bounds=[(None, None)] * n + [(0, None)], method="highs")
    if not res.success or res.x[-1] < 1e-9:
        return None
    return res.x[:-1]


def outer_vertices(normals: np.ndarray, offsets: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Vertices of ``{z : normals z >= offsets, lo <= z <= hi}`` (the box only bounds it; the hyperplanes cut it)."""
    n = normals.shape[1]
    eye = np.eye(n)
    hs = np.vstack([np.c_[-normals, offsets], np.c_[-eye, lo], np.c_[eye, -hi]])
    centre = _interior(hs)
    if centre is None:
        return np.empty((0, n))
    try:
        verts = HalfspaceIntersection(hs, centre).intersections
    except Exception as exc:                                   # Qhull on a degenerate set
        logger.warning("outer-set vertex enumeration failed ({}); joggling", exc)
        verts = HalfspaceIntersection(hs, centre, qhull_options="QJ").intersections
    return np.unique(np.round(verts, 12), axis=0)


def distance_to_inner(points: np.ndarray, v: np.ndarray) -> Tuple[float, np.ndarray, np.ndarray]:
    """``min eta`` s.t. ``sum_k l_k P_k - eta <= v``, ``sum l = 1``, ``l >= 0``: how far ``v`` lies below the inner set.

    Returns the distance (``max(eta, 0)``), the blend ``l`` that attains it and the dual multipliers of the ``n`` rows,
    a nonnegative vector summing to 1: the normal of a hyperplane supporting the inner set where ``v`` is farthest."""
    k, n = points.shape
    c = np.r_[np.zeros(k), 1.0]
    A_ub = np.c_[points.T, -np.ones(n)]
    A_eq = np.r_[np.ones(k), 0.0][None, :]
    res = linprog(c, A_ub=A_ub, b_ub=v, A_eq=A_eq, b_eq=[1.0], bounds=[(0, None)] * k + [(None, None)], method="highs")
    if not res.success:
        raise RuntimeError(f"distance linear program failed: {res.message}")
    duals = -np.asarray(res.ineqlin.marginals, float)
    return max(float(res.x[-1]), 0.0), res.x[:k], duals


def sandwich_error(points: np.ndarray, normals: np.ndarray, offsets: np.ndarray, lo: np.ndarray,
                   hi: np.ndarray) -> Tuple[float, Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """The error bound and, at the worst vertex, the vertex, the blend nearest it and the next weights."""
    verts = outer_vertices(normals, offsets, lo, hi)
    best = (0.0, None, None, None)
    for v in verts:
        d, lam, duals = distance_to_inner(points, v)
        if d > best[0]:
            best = (d, v, lam, duals)
    return best


def sandwich(solve: Callable[[np.ndarray, Optional[int]], Solved], n: int, budget: int, tol: float = 0.05,
             eps: float = 1e-3, on_plan: Optional[Callable[[SandwichPlan, int, float], None]] = None) -> SandwichResult:
    """Anchors, a balance plan, then sandwich plans (module docstring).

    ``solve(raw_weights, warm)`` returns the plan minimizing ``sum_i raw_weights[i] * f_i``, warm-started from plan
    ``warm`` (an index into the plans so far) when given. ``budget`` counts every plan, anchors included."""
    if n < 2:
        raise ValueError("a Pareto set needs at least two objectives")
    budget = max(int(budget), n + 1)
    plans: List[SandwichPlan] = []

    def add(kind: str, raw: np.ndarray, warm: Optional[int]) -> SandwichPlan:
        p = SandwichPlan(kind=kind, raw_weights=np.asarray(raw, float), solved=solve(np.asarray(raw, float), warm))
        plans.append(p)
        return p

    for i in range(n):
        raw = np.full(n, eps)
        raw[i] = 1.0
        p = add("anchor", raw, None if i == 0 else 0)
        if on_plan:
            on_plan(p, len(plans), float("nan"))
    vals = np.array([p.solved.values for p in plans])
    ideal, nadir = vals.min(axis=0), vals.max(axis=0)
    flat = [i for i in range(n) if nadir[i] - ideal[i] <= MIN_RANGE]
    span = np.where(nadir - ideal > MIN_RANGE, nadir - ideal, 1.0)
    out = SandwichResult(plans=plans, ideal=ideal, nadir=nadir, flat=flat)

    def supporting(p: SandwichPlan) -> Tuple[np.ndarray, float]:
        a = p.raw_weights * span
        if p.solved.bound is not None:          # raw . z >= bound, normalized
            return a / a.sum(), float((p.solved.bound - p.raw_weights @ ideal) / a.sum())
        a = a / a.sum()
        return a, float(a @ normalize(p.solved.values, ideal, nadir))

    p = add("balance", np.full(n, 1.0 / n) / span, int(np.argmin(vals.sum(axis=1))))
    while True:
        P = out.normalized()
        hyper = [supporting(q) for q in plans]
        A, b = np.array([h[0] for h in hyper]), np.array([h[1] for h in hyper])
        lo = np.minimum(P.min(axis=0), 0.0) - 0.5
        hi = np.maximum(P.max(axis=0), 1.0) + 0.5
        err, vertex, lam, duals = sandwich_error(P, A, b, lo, hi)
        out.history.append((len(plans), err))
        if on_plan:
            on_plan(plans[-1], len(plans), err)
        logger.info("Pareto set: {} plans, error bound {:.4f}", len(plans), err)
        if err <= tol:
            out.stop_reason = f"error bound {err:.4f} within {tol}"
            break
        if len(plans) >= budget:
            out.stop_reason = f"plan budget {budget} reached, error bound {err:.4f}"
            break
        a = np.maximum(duals, 1e-3)
        a = a / a.sum()
        if any(np.abs(a - h[0]).max() < 1e-4 for h in hyper):
            out.stop_reason = f"the next weights repeat a plan's; error bound {err:.4f}"
            break
        add("sandwich", a / span, int(np.argmax(lam)))
    return out


__all__ = ["Solved", "SandwichPlan", "SandwichResult", "normalize", "outer_vertices", "distance_to_inner",
           "sandwich_error", "sandwich", "MIN_RANGE"]
