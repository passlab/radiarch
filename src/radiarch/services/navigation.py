"""Navigation on a Pareto set (roadmap R11.3, D5).

A navigated plan is a blend of the Pareto plans, ``x = sum_j l_j x_j`` with ``l >= 0`` and ``sum l = 1``. Its dose is
exactly the same blend of their doses, so navigation needs no dose calculation, and every trade-off ``f_i`` is
convex, so its value is at most the blend of the plans' values, ``F_i(l) = sum_j l_j f_i(x_j)``. Navigation searches
with that linear bound (Monz et al., PMB 53:985, 2008) and then reports the exact values on the blended dose.

The search is Craft & Monz's piercing linear program (Med Phys 37:736, 2010) over the blend weights, in the
objectives normalized to ideal 0 and nadir 1::

    minimize   h + rho * sum_i F_i(l)
    subject to F_i(l) - h <= z_i      for the objectives that trade (z: the reference point)
               F_j(l)     <= c_j      for clamped and locked objectives (and a moved slider)
               sum_j l_j = 1,  l >= 0

The small ``rho`` keeps the answer off weakly dominated blends. A slider move asks for one objective at no more than a
value, with the others sharing the cost or the gain evenly from where they are; a reference point asks for every
objective toward a value; clamps hold whatever else moves; a lock clamps an objective where it is.

Automatic navigation (R11.4, D6) is lexicographic over the blend weights against a goal set's priorities: level 1's
summed relative shortfall is minimized, then level 2's with every level-1 goal held (a met goal stays met, a missed one
within a slip of what it reached), then level 3's, then the trade-offs' sum with every goal held. DVH goals are not linear in the blend, so each
level is a small constrained problem in the blend weights (SLSQP, then COBYLA when a shortfall remains), each
evaluation a weighted sum of the plans' doses on the goal's structure. RayStation describes automatic navigation the
same way in one sentence ("lexicographic optimization where the plan coefficients constitute optimization variables");
its algorithm is not published, so this one is radiarch's own.

On a robust set (R11.6, D8) every plan's dose is stored per scenario, and a blend's scenario doses are the same blend
of them. A trade-off's value is then its worst case over the scenarios (still convex, so the linear bound holds), its
nominal value is reported beside it, goals are graded on the nominal dose with their worst case over the scenarios,
and automatic navigation works on each goal's worst case.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import linprog, minimize

from ..models.mco import AutoLevel, AutoNavigateRequest, DVHCurve, MCOResult, NavigateRequest, NavigationState
from .clinical_goals import evaluate_metric, grade_goal_set, load_template, parse_metric, resolve_structure
from .dvh import dvh_on_bins
from .optimization import _objective_from_spec

RHO = 1e-3
BALANCE = "balance"


class NavigationError(ValueError):
    """A navigation request names an unknown objective or state, or no blend meets its clamps."""


class Navigator:
    """One Pareto set in memory: its plans' values and their doses on the navigation voxels."""

    def __init__(self, result: MCOResult, doses: np.ndarray, masks: Dict[str, np.ndarray],
                 scenario_doses: Optional[np.ndarray] = None) -> None:
        self.result = result
        self.doses = np.asarray(doses, dtype=np.float32)
        self.robust = scenario_doses is not None
        self.scenarios = list(result.scenarios) if self.robust else ["nominal"]
        self.scen = scenario_doses if self.robust else self.doses[None]                 # scenarios x plans x voxels
        self.masks = {k: np.asarray(v, dtype=bool) for k, v in masks.items()}
        self.F = np.array([p.values_gy for p in result.plans], dtype=np.float64)          # plans x objectives
        self.ideal, self.nadir = np.asarray(result.ideal_gy, float), np.asarray(result.nadir_gy, float)
        self.span = np.where(self.nadir - self.ideal > 1e-9, self.nadir - self.ideal, 1.0)
        self.Fn = (self.F - self.ideal) / self.span
        self.names = [f"{o.type}({o.structure_name})" for o in result.tradeoffs]
        self.objectives = [_objective_from_spec(o.model_copy(update={"weight": 1.0})) for o in result.tradeoffs]
        self.objective_masks = [self.masks[o.structure_name].astype(np.float64) for o in result.tradeoffs]

    # -- objectives by name or index ---------------------------------------------------------------------------------
    def index(self, key: str) -> int:
        if key in self.names:
            return self.names.index(key)
        try:
            i = int(key)
        except (TypeError, ValueError):
            raise NavigationError(f"unknown objective {key!r}; the trade-offs are {self.names}") from None
        if not 0 <= i < len(self.names):
            raise NavigationError(f"objective index {i} out of range 0..{len(self.names) - 1}")
        return i

    def to_norm(self, i: int, gy: float) -> float:
        return (float(gy) - self.ideal[i]) / self.span[i]

    # -- the blended plan -------------------------------------------------------------------------------------------
    def dose(self, blend: np.ndarray) -> np.ndarray:
        return np.asarray(blend, dtype=np.float64) @ self.doses

    def exact(self, dose: np.ndarray) -> np.ndarray:
        return np.array([o.value(dose, m) for o, m in zip(self.objectives, self.objective_masks)])

    def stack(self, blend: np.ndarray) -> np.ndarray:
        """The blend's dose in every scenario (nominal first), scenarios x voxels."""
        return np.einsum("k,skv->sv", np.asarray(blend, dtype=np.float64), self.scen, dtype=np.float64)

    def values(self, stack: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Each trade-off's value on a stacked dose: ``(worst case over the scenarios, nominal)`` (the same when nominal)."""
        per = np.array([self.exact(d) for d in stack])
        return per.max(axis=0), per[0]

    def grade(self, spec, stack: np.ndarray, prescription_gy: Optional[float], fractions: Optional[int]):
        """A goal set graded on the nominal dose of a stack; robust, each goal's worst case over the scenarios too."""
        scen = {nm: (lambda name, d=d: d[self.masks[name]]) for nm, d in zip(self.scenarios[1:], stack[1:])} if self.robust else None
        return grade_goal_set(spec, lambda name: stack[0][self.masks[name]], list(self.masks), self.result.voxel_cc or 0.0,
                              prescription_gy, fractions, scen)

    def balance_blend(self) -> np.ndarray:
        lam = np.zeros(len(self.F))
        lam[next(p.index for p in self.result.plans if p.kind == "balance")] = 1.0
        return lam

    # -- the linear programs ----------------------------------------------------------------------------------------
    def _lp(self, c: np.ndarray, rows: List[int], z: np.ndarray, upper: Dict[int, float], with_h: bool):
        k = self.Fn.shape[0]
        A, b = [], []
        for i in rows:
            A.append(np.r_[self.Fn[:, i], -1.0])
            b.append(z[i])
        for i, cap in upper.items():
            A.append(np.r_[self.Fn[:, i], 0.0])
            b.append(cap)
        bounds = [(0, None)] * k + [(None, None) if with_h else (0, 0)]
        res = linprog(c, A_ub=np.array(A) if A else None, b_ub=np.array(b) if b else None,
                      A_eq=np.r_[np.ones(k), 0.0][None, :], b_eq=[1.0], bounds=bounds, method="highs")
        return res.x[:k] if res.success else None

    def lowest(self, i: int, upper: Dict[int, float]) -> Optional[float]:
        """The least normalized value objective ``i`` reaches over blends that meet ``upper``."""
        lam = self._lp(np.r_[self.Fn[:, i], 0.0], [], np.zeros(len(self.names)), upper, with_h=False)
        return None if lam is None else float(lam @ self.Fn[:, i])

    def pierce(self, z: np.ndarray, rows: List[int], upper: Dict[int, float]) -> Optional[np.ndarray]:
        c = np.r_[RHO * self.Fn.sum(axis=1), 1.0 if rows else 0.0]
        return self._lp(c, rows, z, upper, with_h=bool(rows))

    def caps(self, clamps: Dict[str, float], locks: List[str], start: np.ndarray) -> Tuple[Dict[int, float], Dict[str, float]]:
        """Clamps (Gy) and locks (where ``start`` is) as normalized upper bounds; refused when no blend meets them."""
        current = start @ self.Fn
        upper: Dict[int, float] = {}
        clamps_gy: Dict[str, float] = {}
        for key, gy in clamps.items():
            i = self.index(key)
            upper[i] = min(upper.get(i, np.inf), self.to_norm(i, gy))
            clamps_gy[self.names[i]] = float(gy)
        for key in locks:
            i = self.index(key)
            upper[i] = min(upper.get(i, np.inf), float(current[i]) + 1e-9)
            clamps_gy[self.names[i]] = round(float(start @ self.F[:, i]), 6)
        if upper and self.pierce(current, [], upper) is None:
            raise NavigationError("no blend of the Pareto plans meets these clamps: " +
                                  ", ".join(f"{self.names[i]} <= {self.ideal[i] + c * self.span[i]:.3g} Gy" for i, c in upper.items()))
        return upper, clamps_gy

    # -- a request --------------------------------------------------------------------------------------------------
    def navigate(self, req: NavigateRequest, start: np.ndarray) -> Tuple[np.ndarray, Dict[str, float], List[str]]:
        """The blend a request asks for, the clamps it held (Gy, by name) and notes."""
        n = len(self.names)
        current = start @ self.Fn
        notes: List[str] = []
        upper, clamps_gy = self.caps(req.clamps, req.locks, start)
        if req.move:
            (key, gy), = req.move.items()
            k = self.index(key)
            target = self.to_norm(k, gy)
            low = self.lowest(k, upper)
            if low is not None and target < low - 1e-9:
                notes.append(f"{self.names[k]} reaches only {self.ideal[k] + low * self.span[k]:.3f} Gy with these clamps "
                             f"(asked {gy:g} Gy)")
                target = low
            upper[k] = min(upper.get(k, np.inf), target + 1e-9)
            rows = [i for i in range(n) if i != k]
            lam = self.pierce(current, rows, upper)
        elif req.reference:
            z = current.copy()
            for key, gy in req.reference.items():
                z[self.index(key)] = self.to_norm(self.index(key), gy)
            lam = self.pierce(z, list(range(n)), upper)
        else:
            lam = start.copy()
            for i, cap in upper.items():
                if float(lam @ self.Fn[:, i]) > cap + 1e-9:
                    lam = self.pierce(current, list(range(n)), upper)
                    notes.append("the starting state broke a clamp: moved to the nearest blend that holds them")
                    break
        if lam is None:
            raise NavigationError("no blend of the Pareto plans meets this request")
        lam = np.where(lam < 1e-9, 0.0, lam)
        return lam / lam.sum(), clamps_gy, notes

    # -- automatic navigation (R11.4) -------------------------------------------------------------------------------
    def _goals(self, req: AutoNavigateRequest) -> Tuple[list, List[str]]:
        """The goals the navigation voxels can grade: (goal, metric, voxel doses of every plan, scale, EQD2 α/β)."""
        from .radiobiology import default_alpha_beta

        spec = req.goals
        template = load_template(spec.template_id) if spec.template_id else None
        goals = (list(template.goals) if template else []) + list(spec.goals)
        aliases = dict(template.aliases) if template else {}
        basis = spec.dose_basis or (template.dose_basis if template else "physical")
        if basis == "EQD2" and req.fractions is None:
            raise NavigationError("EQD2 goals need the plan's fractions")
        prepared, missing = [], []
        for g in goals:
            name = resolve_structure(g.structure, list(self.masks), aliases, spec.structure_aliases)
            if name is None:
                missing.append(g.structure)
                continue
            metric = parse_metric(g.metric)
            if metric.needs_prescription and not req.prescription_gy:
                raise NavigationError(f"{g.metric} needs prescription_gy")
            ab = (spec.alpha_beta_gy.get(name, spec.alpha_beta_gy.get(g.structure, default_alpha_beta(name)))
                  if basis == "EQD2" else None)
            prepared.append((g, metric, np.asarray(self.scen[:, :, self.masks[name]], dtype=np.float64), abs(g.value) if abs(g.value) > 1e-9 else 1.0, ab))
        return prepared, sorted(set(missing))

    def _shortfall(self, item, lam: np.ndarray, rx: Optional[float], fractions: Optional[int]) -> float:
        from .radiobiology import eqd2

        g, metric, D, scale, ab = item              # D: scenarios x plans x the goal structure's voxels
        worst = 0.0
        for Ds in D:
            d = lam @ Ds
            if ab is not None:
                d = eqd2(d, fractions, ab)
            v = evaluate_metric(metric, d, self.result.voxel_cc or 0.0, rx)
            worst = max(worst, max(0.0, v - g.value) / scale if g.op in ("<=", "<") else max(0.0, g.value - v) / scale)
        return worst

    def auto_navigate(self, req: AutoNavigateRequest, start: np.ndarray) -> Tuple[np.ndarray, Dict[str, float], List[str], List[AutoLevel]]:
        upper, clamps_gy = self.caps(req.clamps, req.locks, start)
        goals, missing = self._goals(req)
        notes = [f"goals on {', '.join(missing)} are not used: not navigation structures (add them to the run's "
                 f"navigation_structures)"] if missing else []
        k = len(self.F)
        lam_of = lambda mu: mu / mu.sum() if mu.sum() > 1e-12 else np.full(k, 1.0 / k)          # noqa: E731
        short = lambda item, mu: self._shortfall(item, lam_of(mu), req.prescription_gy, req.fractions)  # noqa: E731
        clamp_cons = [{"type": "ineq", "fun": (lambda mu, i=i, c=c: c - lam_of(mu) @ self.Fn[:, i])} for i, c in upper.items()]
        lam0 = start
        if any(lam0 @ self.Fn[:, i] > c + 1e-9 for i, c in upper.items()):
            lam0 = self.pierce(start @ self.Fn, list(range(len(self.names))), upper)
            notes.append("the starting state broke a clamp: the search started from the nearest blend that holds them")
        mu = np.asarray(lam0, dtype=np.float64).copy()
        held: list = []
        levels: List[AutoLevel] = []

        def feasible(m: np.ndarray, cons) -> bool:
            return all(c["fun"](m) >= -1e-7 for c in cons)

        def search(fun, cons, m0: np.ndarray) -> np.ndarray:
            best, best_v = m0, fun(m0)
            bounds = [(0.0, 1.0)] * k
            for method, opts in (("SLSQP", {"maxiter": 200, "ftol": 1e-10, "eps": 1e-4}), ("COBYLA", {"maxiter": 600, "rhobeg": 0.05})):
                if best_v <= 1e-12:
                    break
                try:
                    r = minimize(fun, best, method=method, bounds=bounds, constraints=cons, options=opts)
                except Exception:                                    # a solver refusing the problem leaves the best so far
                    continue
                cand = np.clip(r.x, 0.0, 1.0)
                if cand.sum() > 1e-12 and feasible(cand, cons) and fun(cand) < best_v - 1e-12:
                    best, best_v = cand, fun(cand)
            return best

        for p in sorted({int(item[0].priority) for item in goals}):
            level = [item for item in goals if int(item[0].priority) == p]
            fun = lambda m, level=level: sum(short(item, m) for item in level)          # noqa: E731
            before = fun(mu)
            cons = clamp_cons + [{"type": "ineq", "fun": (lambda m, item=item, cap=cap: cap - short(item, m))} for item, cap in held]
            mu = search(fun, cons, mu)
            after = fun(mu)
            levels.append(AutoLevel(priority=p, goals=len(level), passed=sum(short(item, mu) <= 1e-9 for item in level),
                                    shortfall_before=round(before, 6), shortfall=round(after, 6)))
            # a goal the level met stays met; one it could not meet may slip by a fraction of its value for the levels below
            held += [(item, 0.0 if short(item, mu) <= 1e-9 else short(item, mu) + req.slip) for item in level]
        # last: the trade-offs as low as the goals allow
        cons = clamp_cons + [{"type": "ineq", "fun": (lambda m, item=item, cap=cap: cap - short(item, m))} for item, cap in held]
        total = lambda m: float(lam_of(m) @ self.Fn.sum(axis=1))                            # noqa: E731
        mu = search(total, cons, mu)
        lam = lam_of(mu)
        lam = np.where(lam < 1e-9, 0.0, lam)
        return lam / lam.sum(), clamps_gy, notes, levels

    # -- what a state reports ---------------------------------------------------------------------------------------
    def state(self, lam: np.ndarray, req, state_id: str, clamps: Dict[str, float], notes: List[str],
              from_state: Optional[str], levels: Optional[List[AutoLevel]] = None) -> NavigationState:
        """The state of a blend: exact values, DVHs, and the request's goals (a navigation or an automatic one)."""
        stack = self.stack(lam)
        d = stack[0]
        exact, nominal = self.values(stack)
        bound = lam @ self.F
        goals = None
        bins = req.dvh_bins if req is not None else 60
        if req is not None and req.goals is not None:
            goals = self.grade(req.goals, stack, req.prescription_gy, req.fractions)
            missing = sorted({g.structure for g in goals.results if g.missing})
            if missing:
                notes = notes + [f"goals on {', '.join(missing)} are not graded: not navigation structures (add them to the "
                                 f"run's navigation_structures)"]
        dvh: List[DVHCurve] = []
        if bins:
            top = max((float(d[m].max()) for m in self.masks.values() if m.any()), default=0.0)
            axis = np.linspace(0.0, top if top > 0 else 1.0, bins)
            dvh = [DVHCurve(structure=name, dose_gy=[round(float(v), 4) for v in axis],
                            volume_pct=[round(float(v), 3) for v in dvh_on_bins(d, m, axis)]) for name, m in self.masks.items() if m.any()]
        return NavigationState(
            state_id=state_id, mco_id=self.result.mco_id, name=req.name if req is not None else "balance plan", from_state=from_state,
            blend=[round(float(v), 9) for v in lam], values_gy=[round(float(v), 6) for v in exact],
            nominal_gy=[round(float(v), 6) for v in nominal] if self.robust else None, bound_gy=[round(float(v), 6) for v in bound],
            normalized=[round(float(v), 6) for v in (exact - self.ideal) / self.span], clamps=clamps, notes=notes, goals=goals,
            levels=levels or [], dvh=dvh,
            created_at=datetime.now(timezone.utc))


class NavigationService:
    """Navigation states of the stored Pareto sets: ``mco/{mco_id}/states/{state_id}.json``."""

    def __init__(self, mco_store) -> None:
        self.store = mco_store
        self._cache: Dict[str, Navigator] = {}

    def navigator(self, mco_id: str) -> Navigator:
        nav = self._cache.get(mco_id)
        if nav is None:
            result = self.store.get_by_id(mco_id)
            if result is None:
                raise KeyError(mco_id)
            _, doses, masks = self.store.load_navigation(mco_id)
            nav = Navigator(result, doses, masks, self.store.load_scenario_doses(mco_id))
            if len(self._cache) >= 4:
                self._cache.pop(next(iter(self._cache)))
            self._cache[mco_id] = nav
        return nav

    def _dir(self, mco_id: str):
        return self.store.dir(mco_id) / "states"

    def _save(self, state: NavigationState) -> None:
        d = self._dir(state.mco_id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f".{state.state_id}.json.tmp"
        tmp.write_text(state.model_dump_json(indent=1), encoding="utf-8")
        os.replace(tmp, d / f"{state.state_id}.json")

    def get_state(self, mco_id: str, state_id: str) -> Optional[NavigationState]:
        path = self._dir(mco_id) / f"{state_id}.json"
        if path.is_file():
            return NavigationState.model_validate_json(path.read_text(encoding="utf-8"))
        if state_id == BALANCE:
            nav = self.navigator(mco_id)
            state = nav.state(nav.balance_blend(), None, BALANCE, {}, [], None)
            self._save(state)
            return state
        return None

    def list_states(self, mco_id: str) -> List[NavigationState]:
        self.get_state(mco_id, BALANCE)
        states = [NavigationState.model_validate_json(p.read_text(encoding="utf-8")) for p in self._dir(mco_id).glob("*.json")]
        return sorted(states, key=lambda s: (s.state_id != BALANCE, s.created_at or datetime.min.replace(tzinfo=timezone.utc)))

    def navigate(self, mco_id: str, req: NavigateRequest) -> NavigationState:
        nav = self.navigator(mco_id)
        start = self.get_state(mco_id, req.from_state)
        if start is None:
            raise NavigationError(f"no state {req.from_state!r} in Pareto set {mco_id}")
        lam, clamps, notes = nav.navigate(req, np.asarray(start.blend, dtype=np.float64))
        state = nav.state(lam, req, str(uuid.uuid4()), clamps, notes, start.state_id)
        if req.save:
            self._save(state)
        return state


    def auto_navigate(self, mco_id: str, req: AutoNavigateRequest) -> NavigationState:
        nav = self.navigator(mco_id)
        start = self.get_state(mco_id, req.from_state)
        if start is None:
            raise NavigationError(f"no state {req.from_state!r} in Pareto set {mco_id}")
        lam, clamps, notes, levels = nav.auto_navigate(req, np.asarray(start.blend, dtype=np.float64))
        state = nav.state(lam, req, str(uuid.uuid4()), clamps, notes, start.state_id, levels)
        if req.save:
            self._save(state)
        return state


__all__ = ["Navigator", "NavigationService", "NavigationError", "BALANCE", "RHO"]
