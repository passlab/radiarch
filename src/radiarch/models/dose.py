"""Pydantic I/O models for the Dose Service (Service 3).

The Dose Service is the third stage of the TPS pipeline. Given a built
geometry (Service 1), a built beam model (Service 2), and a set of
*fluence weights* — one scalar per element in the beam model's
``FluenceElementSet`` — it computes:

* **Dose** — the resulting 3D dose grid (Gy), evaluated on the geometry
  grid. This is the primary deliverable.
* **Influence** (optional, expensive) — the per-element dose-deposition
  matrix Dij such that ``dose ≈ Dij @ weights``. Required by inverse
  optimization (Service 4) and by the differentiable robust dose path.
* **Scenario dose** — dose recomputed under a perturbed setup/range
  scenario, for robustness evaluation.

Engines are plugins (see ``services/dose_engines/``). The request carries
an :class:`EngineSpec` so callers can pin a specific engine + version;
the service rejects engines whose ``modalities`` don't include the beam
model's modality.

See ``docs/architecture.md`` (§4.3) for the
full specification. The cache key folds in plan/geometry/beam model ids,
engine name+version, a hash of the weight vector, and the scenario hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

from .beam_model import Modality
from .job import JobState
from .common import ResearchArtifact


# ---------------------------------------------------------------------------
# RBE
# ---------------------------------------------------------------------------

PROTON_RBE = 1.1


def default_rbe(modality: Modality) -> float:
    """The relative biological effectiveness applied by default: 1.1 for
    protons (the clinical constant), 1.0 for photons."""
    return PROTON_RBE if modality is Modality.proton_pbs else 1.0


def dose_units_for(rbe: float) -> str:
    return "Gy(RBE)" if abs(float(rbe) - 1.0) > 1e-9 else "Gy"


# ---------------------------------------------------------------------------
# Engine spec
# ---------------------------------------------------------------------------

class EngineSpec(BaseModel):
    """Names a dose engine + version + engine-specific kwargs.

    ``params`` is an opaque dict — the engine validates its own params via
    its ``validate()`` method on a build request. We hash it into the
    cache key, but otherwise treat it as engine-private.
    """

    name: str = Field(..., min_length=1, max_length=64,
                      description='Registered engine name, e.g. "mcsquare", "ccc" or "pb".')
    version: str = Field(default="default", max_length=32,
                         description="Engine version pin. Default = whatever the registry exposes.")
    params: Dict[str, Any] = Field(default_factory=dict,
                                   description="Engine-specific tuning knobs (folded into cache key).")

    def key_version(self) -> str:
        """The version that goes into cache keys: the pinned one, or for "default" the registered
        engine's own version, so a fix in an engine invalidates the doses and influence matrices it
        computed before (R8: they were keyed by the literal "default")."""
        if self.version != "default":
            return self.version
        try:
            from ..services.dose_engines.registry import get_engine
            return f"default={getattr(get_engine(self.name), 'version', 'unknown')}"
        except Exception:
            return "default"


# ---------------------------------------------------------------------------
# Scenarios — robustness perturbations
# ---------------------------------------------------------------------------

class ScenarioSpec(BaseModel):
    """A single setup-error / range-error perturbation.

    All perturbations are mechanically additive on top of the nominal
    beam model. v1 supports:

    * ``setup_shift_mm`` — rigid shift of the patient in (x, y, z) mm.
    * ``range_scale`` — multiplicative scaling of proton range (e.g.
      1.035 = +3.5% range). Ignored for photon engines.
    * ``density_scale`` — multiplicative scaling of the density grid (a
      stand-in for HU calibration uncertainty).

    Each field is optional; nominal scenarios pass them all as ``None``
    or use ``ScenarioSpec()`` directly. The empty scenario is the
    *nominal* scenario.
    """

    name: str = Field(default="nominal", min_length=1, max_length=48)
    setup_shift_mm: Optional[Tuple[float, float, float]] = Field(
        default=None,
        description="Rigid patient shift in patient LPS mm — (dx, dy, dz).",
    )
    range_scale: Optional[float] = Field(
        default=None, gt=0.0, lt=2.0,
        description="Proton range scaling factor (e.g. 1.035 = +3.5%).",
    )
    density_scale: Optional[float] = Field(
        default=None, gt=0.0, lt=2.0,
        description="Density grid scaling (HU calibration uncertainty stand-in).",
    )
    setup_random_sigma_mm: Optional[Tuple[float, float, float]] = Field(
        default=None,
        description="Standard deviation of the per-fraction random setup error (x, y, z, mm); "
                    "modelled only by engines that blur each fraction's dose (MCsquare's robustness mode).",
    )

    def is_nominal(self) -> bool:
        return (
            self.setup_shift_mm is None
            and self.range_scale is None
            and self.density_scale is None
            and self.setup_random_sigma_mm is None
        )

    def hash(self) -> str:
        """Deterministic short hash, fed into the dose cache key."""
        payload = {
            "name": self.name,
            "shift": list(self.setup_shift_mm) if self.setup_shift_mm else None,
            "range": self.range_scale,
            "density": self.density_scale,
        }
        if self.setup_random_sigma_mm is not None:
            payload["random"] = list(self.setup_random_sigma_mm)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class EngineScenarioSet(BaseModel):
    """A scenario set the engine samples itself in one run (MCsquare's robustness mode).

    ``ALL`` is every combination of a systematic setup error of ±σ or 0 on
    each axis with a range error of ±r or 0 (81 scenarios), ``REDUCED_SET``
    the single-axis shifts and the range states (21), ``RANDOM`` ``count``
    draws from the error distributions. Every scenario also carries the
    per-fraction random setup error as a blur of its dose. The engine
    reports the errors it applied, so each scenario comes back as a
    :class:`ScenarioSpec`. ``n_scenarios`` is the nominal size of the set;
    MCsquare leaves out the scenario that coincides with the nominal plan
    when the random setup error is zero (20 for REDUCED_SET, 80 for ALL).
    """

    selection: str = Field(default="REDUCED_SET", description='"ALL" (81), "REDUCED_SET" (21) or "RANDOM" (count).')
    setup_systematic_mm: Tuple[float, float, float] = Field(default=(2.5, 2.5, 2.5))
    setup_random_mm: Tuple[float, float, float] = Field(default=(1.0, 1.0, 1.0))
    range_error_pct: float = Field(default=3.0, ge=0.0, le=20.0)
    count: int = Field(default=20, ge=1, le=200, description="Scenarios drawn in RANDOM mode.")

    _ALLOWED = ("ALL", "REDUCED_SET", "RANDOM")

    @model_validator(mode="after")
    def _check(self) -> "EngineScenarioSet":
        self.selection = str(self.selection).upper()
        if self.selection not in self._ALLOWED:
            raise ValueError(f"selection must be one of {self._ALLOWED}, got {self.selection!r}")
        if any(v < 0 for v in self.setup_systematic_mm) or any(v < 0 for v in self.setup_random_mm):
            raise ValueError("setup errors must be non-negative")
        return self

    @property
    def n_scenarios(self) -> int:
        return {"ALL": 81, "REDUCED_SET": 21, "RANDOM": int(self.count)}[self.selection]

    def hash(self) -> str:
        blob = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class ScenarioSetSpec(BaseModel):
    """A bundle of scenarios for robust evaluation / robust optimization.

    Three construction modes:

    1. **Explicit list** — pass ``scenarios=[...]`` directly. The service
       will evaluate dose for each scenario in turn.
    2. **Generated** — set ``setup_sigma_mm`` and/or ``range_sigma`` and
       a ``count``; the generator produces a deterministic stratified
       sample (axis-aligned worst-case corners + nominal). This matches
       the SDD's "generator" path.
    3. **Engine-native** — ``engine_native`` describes the set and the
       engine samples and simulates it in a single run (R3); only engines
       with a native robustness mode accept it.

    If several are set, the explicit list wins, then the native set.
    """

    scenarios: Optional[List[ScenarioSpec]] = Field(default=None, max_length=256)
    setup_sigma_mm: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    range_sigma: Optional[float] = Field(default=None, ge=0.0, le=0.1)
    count: Optional[int] = Field(default=None, ge=1, le=256)
    engine_native: Optional[EngineScenarioSet] = Field(default=None)

    @model_validator(mode="after")
    def _at_least_one_mode(self) -> "ScenarioSetSpec":
        explicit = bool(self.scenarios)
        generator = (
            self.setup_sigma_mm is not None
            or self.range_sigma is not None
        )
        if not explicit and not generator and self.engine_native is None:
            raise ValueError(
                "ScenarioSetSpec requires an explicit scenarios list, sigma + count "
                "for generator mode, or an engine_native set."
            )
        if generator and self.count is None:
            raise ValueError("generator mode requires count to be set")
        return self

    def hash(self) -> str:
        if self.scenarios is not None:
            payload = {"explicit": [s.model_dump() for s in self.scenarios]}
        elif self.engine_native is not None:
            payload = {"engine_native": self.engine_native.hash()}
        else:
            payload = {
                "setup_sigma_mm": self.setup_sigma_mm,
                "range_sigma": self.range_sigma,
                "count": self.count,
            }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Weight payload
# ---------------------------------------------------------------------------

class WeightVector(BaseModel):
    """A vector of fluence-element weights, one per beam-model element.

    Either pass the values inline (``values``) for short vectors / tests,
    or point at a previously-stored vector via ``weights_uri`` (a URI
    that resolves to a NumPy ``.npy`` of float32 / float64). Optimizer
    services return URIs; ad-hoc dose computes can use ``values``.

    ``length`` is required either way and is cross-checked against the
    beam model's ``FluenceElementSet.total_count`` by the service before
    dispatch.
    """

    length: int = Field(..., ge=1, le=10_000_000)
    values: Optional[List[float]] = Field(default=None)
    weights_uri: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def _one_or_the_other(self) -> "WeightVector":
        if (self.values is None) == (self.weights_uri is None):
            raise ValueError(
                "WeightVector requires exactly one of: values, weights_uri."
            )
        if self.values is not None and len(self.values) != self.length:
            raise ValueError(
                f"values length {len(self.values)} does not match length={self.length}"
            )
        return self

    def hash(self) -> str:
        """Hash of the weight content for cache-key folding.

        For inline values we hash the actual numbers (rounded to 1e-9 to
        defang float-printing fluctuation). For URIs we hash the URI —
        callers that mutate the file under the same URI are responsible
        for changing the URI too.
        """
        if self.values is not None:
            blob = json.dumps(
                [round(v, 9) for v in self.values],
                separators=(",", ":"),
            )
        else:
            blob = self.weights_uri or ""
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

class DoseStage(str, Enum):
    """Stages a :meth:`DoseService.compute_dose` call passes through."""

    queued = "queued"
    loading_geometry = "loading_geometry"
    loading_beam_model = "loading_beam_model"
    validating_engine = "validating_engine"
    expanding_scenarios = "expanding_scenarios"
    computing_dose = "computing_dose"
    persisting = "persisting"
    done = "done"


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class DoseComputeRequest(BaseModel):
    """Input for ``POST /api/v1/dose/compute``.

    Caller supplies geometry id, beam model id, weights, optional scenario
    set, and an engine spec. The service resolves the modality from the
    beam model and rejects engines that don't claim that modality.
    """

    plan_id: Optional[str] = Field(default=None, max_length=36,
                                   description="Owning plan id (downstream ref only — not in cache key).")
    geometry_id: str = Field(..., min_length=1, max_length=36)
    beam_model_id: str = Field(..., min_length=1, max_length=36)
    engine: EngineSpec
    weights: WeightVector
    scenarios: Optional[ScenarioSetSpec] = Field(
        default=None,
        description="Robust scenario set. Null = nominal-only.",
    )
    rbe: Optional[float] = Field(
        default=None, gt=0.0, le=2.0,
        description="Relative biological effectiveness applied to the engine's physical dose; "
                    "null = 1.1 for protons, 1.0 for photons. The stored dose is in Gy(RBE) when it is not 1.",
    )

    def compute_cache_key(self) -> str:
        payload = {
            "geometry_id": self.geometry_id,
            "beam_model_id": self.beam_model_id,
            "engine": {
                "name": self.engine.name,
                "version": self.engine.key_version(),
                "params": self.engine.params,
            },
            "weights_hash": self.weights.hash(),
            "weights_length": self.weights.length,
            "scenarios_hash": self.scenarios.hash() if self.scenarios else None,
            "rbe": self.rbe,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class InfluenceBuildRequest(BaseModel):
    """Input for ``POST /api/v1/dose/influence``.

    No weights — influence is the *operator*, not a single dose. Optional
    scenario for robust influence matrices (Service 4 uses these).
    """

    plan_id: Optional[str] = Field(default=None, max_length=36)
    geometry_id: str = Field(..., min_length=1, max_length=36)
    beam_model_id: str = Field(..., min_length=1, max_length=36)
    engine: EngineSpec
    scenario: Optional[ScenarioSpec] = Field(
        default=None,
        description="Nominal influence if null; perturbed otherwise.",
    )
    rbe: Optional[float] = Field(
        default=None, gt=0.0, le=2.0,
        description="RBE applied to the influence matrix; null = 1.1 for protons, 1.0 for photons.",
    )

    def compute_cache_key(self) -> str:
        payload = {
            "geometry_id": self.geometry_id,
            "beam_model_id": self.beam_model_id,
            "engine": {
                "name": self.engine.name,
                "version": self.engine.key_version(),
                "params": self.engine.params,
            },
            "scenario_hash": self.scenario.hash() if self.scenario else None,
            "rbe": self.rbe,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class DoseStatistics(BaseModel):
    """Quick summary stats for a dose distribution.

    Cheap to compute (one pass over the grid). Useful for sanity checks
    and dashboards; the full distribution lives in the NIfTI artifact.
    """

    max_gy: float = Field(..., ge=0.0)
    mean_gy: float = Field(..., ge=0.0)
    p95_gy: float = Field(..., ge=0.0,
                          description="95th-percentile dose across non-zero voxels.")
    nonzero_voxel_count: int = Field(..., ge=0)


class DoseResult(ResearchArtifact):
    """Output of a completed nominal dose compute."""

    dose_id: str
    plan_id: Optional[str] = None
    geometry_id: str
    beam_model_id: str
    modality: Modality
    engine_name: str
    engine_version: str

    dose_grid_uri: str = Field(..., description="URI/path to the dose volume (NIfTI, float32, in dose_units).")
    statistics: DoseStatistics
    rbe_factor: float = Field(default=1.0, description="RBE multiplied into the stored dose (1.1 for protons by default).")
    dose_units: str = Field(default="Gy", description='"Gy" or "Gy(RBE)".')

    # Robust evaluation — populated only when the request carried a non-null
    # ScenarioSetSpec. Each entry mirrors a single scenario's stats.
    scenario_doses: Optional[List["ScenarioDoseEntry"]] = None
    mapped_from: Optional[Dict[str, str]] = Field(
        default=None, description="A dose mapped through a registration (R9): the source dose_id and the registration_id.")
    accumulated_from: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="A dose accumulated over phases (R9): each phase's dose_id, registration_id and weight.")

    cache_key: str
    created_at: Optional[datetime] = None


class ScenarioDoseEntry(BaseModel):
    """One per-scenario dose summary inside a DoseResult."""

    scenario_name: str
    scenario_hash: str
    dose_grid_uri: str
    statistics: DoseStatistics
    scenario: Optional[ScenarioSpec] = Field(default=None, description="The perturbation this dose was computed under.")


class InfluenceResult(ResearchArtifact):
    """Output of a completed influence-matrix build.

    The matrix itself is too large to inline — it lives on disk in a
    sparse format (CSR ``.npz``). The result row carries enough metadata
    for the optimizer (Service 4) to load it: dimensions, density (nnz),
    storage URI.
    """

    influence_id: str
    plan_id: Optional[str] = None
    geometry_id: str
    beam_model_id: str
    modality: Modality
    engine_name: str
    engine_version: str
    scenario: Optional[ScenarioSpec] = None

    influence_uri: str = Field(..., description="URI/path to the sparse Dij matrix (.npz), in dose_units per unit weight.")
    rbe_factor: float = Field(default=1.0)
    dose_units: str = Field(default="Gy")
    n_voxels: int = Field(..., ge=1, description="Rows in Dij — flattened grid size.")
    n_elements: int = Field(..., ge=1, description="Cols in Dij — beam-model element count.")
    nnz: int = Field(..., ge=0, description="Non-zero entries in Dij.")

    cache_key: str
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Async job tracking
# ---------------------------------------------------------------------------

class DoseJobStatus(BaseModel):
    """Status row for an async ``POST /dose/compute`` or ``/dose/influence``."""

    id: str
    cache_key: str
    kind: str = Field(default="dose",
                      description="'dose' or 'influence' — which kind of build.")
    state: JobState = JobState.queued
    progress: float = 0.0
    stage: Optional[DoseStage] = DoseStage.queued
    message: Optional[str] = None
    dose_id: Optional[str] = None        # populated when kind=='dose' and state=='succeeded'
    influence_id: Optional[str] = None   # populated when kind=='influence' and state=='succeeded'
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @field_validator("kind")
    @classmethod
    def _kind_valid(cls, v: str) -> str:
        if v not in {"dose", "influence"}:
            raise ValueError(f"kind must be 'dose' or 'influence', got {v!r}")
        return v


# Forward ref resolution for self-referential DoseResult.scenario_doses
DoseResult.model_rebuild()


__all__ = [
    "EngineSpec",
    "ScenarioSpec",
    "ScenarioSetSpec",
    "WeightVector",
    "DoseStage",
    "DoseComputeRequest",
    "InfluenceBuildRequest",
    "DoseStatistics",
    "DoseResult",
    "ScenarioDoseEntry",
    "InfluenceResult",
    "DoseJobStatus",
]
