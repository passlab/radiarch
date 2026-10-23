"""What the validation cases share (roadmap R7): result types, the run context, the
reference tables, the phantoms as the engines see them. ``run.py`` (the runner) and
``cases_r7.py`` (the R7 cases) both import from here, so running the runner as
``python -m radiarch.validation.run`` never imports a second copy of these classes.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from . import phantoms as ph

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "cases"
REF_DIR = HERE / "references"
RADIARCH_ROOT = HERE.parents[2]
PARENT_ROOT = RADIARCH_ROOT.parent


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    value: Any
    target: str
    passed: Optional[bool]          # None = informative
    note: str = ""


@dataclass
class CaseResult:
    name: str
    kind: str
    status: str = "pending"
    seconds: float = 0.0
    checks: List[Check] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def add(self, name: str, value: Any, target: str, passed: Optional[bool], note: str = "") -> None:
        # numpy comparisons give numpy bools, which JSON cannot write
        self.checks.append(Check(name, _jsonable(value), target, None if passed is None else bool(passed), note))

    def finish(self) -> None:
        if self.status in ("skip", "error"):
            return
        graded = [c.passed for c in self.checks if c.passed is not None]
        if any(p is False for p in graded):
            self.status = "fail"
        elif graded:
            self.status = "pass"
        else:
            self.status = "info"


class Skip(Exception):
    """Raised by a case when a prerequisite is missing."""


def _jsonable(v):
    if isinstance(v, (np.floating, np.integer)):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def load_reference(name: str) -> dict:
    return json.loads((REF_DIR / f"{name}.json").read_text(encoding="utf-8"))


def data_root() -> Path:
    env = os.environ.get("RADIARCH_VALIDATION_DATA")
    return Path(env) if env else PARENT_ROOT / "data" / "public"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@dataclass
class Context:
    fast: bool = False
    spacing_scale: float = 1.0
    workdir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="radiarch-validation-")))

    def spacing(self, mm: float) -> float:
        return float(mm) * (2.0 if self.fast else 1.0) * self.spacing_scale


def _phantom(spec: dict, ctx: Context) -> ph.Phantom:
    kind = spec.get("type", "water_box")
    s = ctx.spacing(spec.get("spacing_mm", 2.5))
    if kind == "water_box":
        return ph.water_box(spec.get("half_width_mm", 150.0), spec.get("depth_mm", 300.0), s)
    if kind == "lung_slab":
        return ph.lung_slab(s)
    if kind == "bone_slab":
        return ph.bone_slab(s)
    if kind == "thorax_like":
        return ph.thorax_like(s)
    raise ValueError(f"unknown phantom type {kind!r}")


def _open_field_plan(field_mm: float, leaf_mm: float, beamlet_mm: float, gantry_deg: float = 0.0, mu: float = 1.0):
    from ..services.photon_beamlets import build_photon_plan
    h = field_mm / 2.0
    return build_photon_plan([(gantry_deg, 0.0)], (-h, h), (-h, h), leaf_mm, mu, (beamlet_mm, beamlet_mm),
                             name=f"validation-{field_mm:g}mm")


def _ccc_engine():
    from ..services.dose_engines.ccc import CCCEngine
    eng = CCCEngine()
    ok, reason = eng.driver().availability()
    if not ok:
        raise Skip(reason)
    return eng


def _ccc_dose(eng, phantom: ph.Phantom, plan, ctx: Context) -> np.ndarray:
    params = {"calibration_spacing_mm": 5.0} if ctx.fast else None
    return eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params=params)



def _photon_engine(spec: dict):
    """The photon engine a case names (``engine: ccc`` or ``pb``; CCC by default)."""
    name = str(spec.get("engine", "ccc")).lower()
    if name == "ccc":
        return _ccc_engine()
    if name == "pb":
        from ..services.dose_engines.pb import PencilBeamEngine
        eng = PencilBeamEngine()
        ok, reason = eng.availability()
        if not ok:
            raise Skip(reason)
        return eng
    raise ValueError(f"unknown photon engine {name!r}")


def _photon_dose(eng, phantom: ph.Phantom, plan, ctx: Context) -> np.ndarray:
    """A phantom dose from either photon engine (CCC through its Dij, pb by convolving the apertures)."""
    if getattr(eng, "name", "") == "pb":
        return eng.compute_plan_dose(phantom.density, phantom.spacing_mm, phantom.origin_mm, plan, params={"fluence": "apertures"})
    return _ccc_dose(eng, phantom, plan, ctx)

def _cax(dose: np.ndarray, phantom: ph.Phantom) -> np.ndarray:
    return dose[phantom.centre_index("z"), :, phantom.centre_index("x")]


def _within(value: float, target: float, tol: float) -> bool:
    return abs(value - target) <= tol



__all__ = ["HERE", "CASES_DIR", "REF_DIR", "RADIARCH_ROOT", "PARENT_ROOT", "Check", "CaseResult", "Skip", "_jsonable", "load_reference",
           "data_root", "Context", "_phantom", "_open_field_plan", "_ccc_engine", "_ccc_dose", "_photon_engine", "_photon_dose", "_cax", "_within"]
