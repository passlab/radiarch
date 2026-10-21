"""Pydantic I/O models for the Evaluation Service (Service 6).

Evaluation is the read-only end of the pipeline: it consumes a computed dose
volume (from Service 3 or the final dose of Service 4) plus the geometry's
structure masks and turns them into clinician-readable metrics — dose-volume
histograms (DVH), plan-quality indices (conformity, homogeneity, coverage), and
an optional gamma comparison against a reference dose.

It performs no engine or solver work; it's pure array analysis, so the only
external dependencies are the dose NIfTI and the geometry masks. The cache key
mirrors the other services: SHA256 of a normalized JSON view, excluding transient
fields (timestamps).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .job import JobState
from .common import ResearchArtifact


class GammaSpec(BaseModel):
    """Gamma-analysis criteria, comparing the dose against a reference.

    ``dose_percent`` / ``distance_mm`` are the standard dose-difference /
    distance-to-agreement tolerances (e.g. 3%/3mm). ``threshold_pct`` is the
    low-dose cutoff: voxels below this fraction of the reference max are excluded
    from the pass-rate (they're noise). ``local`` selects local vs global dose
    normalization for the dose-difference term.
    """

    reference_dose_id: Optional[str] = Field(default=None)
    reference_dose_uri: Optional[str] = Field(default=None)
    dose_percent: float = Field(default=3.0, gt=0.0, le=100.0)
    distance_mm: float = Field(default=3.0, gt=0.0)
    threshold_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    local: bool = Field(default=False)

    @model_validator(mode="after")
    def _check_ref(self) -> "GammaSpec":
        if not self.reference_dose_id and not self.reference_dose_uri:
            raise ValueError(
                "gamma requires reference_dose_id or reference_dose_uri"
            )
        return self

    def hash(self) -> str:
        payload = {
            "reference_dose_id": self.reference_dose_id,
            "reference_dose_uri": self.reference_dose_uri,
            "dose_percent": round(self.dose_percent, 6),
            "distance_mm": round(self.distance_mm, 6),
            "threshold_pct": round(self.threshold_pct, 6),
            "local": self.local,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]


class EvaluationStage(str, Enum):
    """Stages an :meth:`EvaluationService.run` call passes through."""

    queued = "queued"
    loading = "loading"
    computing_dvh = "computing_dvh"
    computing_indices = "computing_indices"
    computing_gamma = "computing_gamma"
    persisting = "persisting"
    done = "done"


class EvaluationRequest(BaseModel):
    """Input for ``POST /api/v1/evaluate/run``.

    Exactly one of ``dose_id`` / ``dose_ref_uri`` identifies the dose to
    evaluate. ``prescription_gy`` + ``target_structure`` drive the plan-quality
    indices; ``structures`` limits which DVHs are computed (default: all).
    """

    plan_id: Optional[str] = Field(default=None, max_length=36)
    dose_id: Optional[str] = Field(default=None, max_length=36)
    dose_ref_uri: Optional[str] = Field(default=None)
    geometry_id: str = Field(..., min_length=1, max_length=36)
    prescription_gy: float = Field(..., gt=0.0)
    target_structure: Optional[str] = Field(default=None)
    structures: Optional[List[str]] = Field(default=None, max_length=128)
    dvh_bins: int = Field(default=100, ge=2, le=10_000)
    gamma: Optional[GammaSpec] = Field(default=None)
    include_scenarios: bool = Field(
        default=True,
        description="When the dose carries scenario doses, report DVH bands and worst-case metrics over them (R3).",
    )

    @model_validator(mode="after")
    def _check_dose(self) -> "EvaluationRequest":
        if not self.dose_id and not self.dose_ref_uri:
            raise ValueError("provide dose_id or dose_ref_uri")
        return self

    def compute_cache_key(self) -> str:
        payload = {
            "dose_id": self.dose_id,
            "dose_ref_uri": self.dose_ref_uri,
            "geometry_id": self.geometry_id,
            "prescription_gy": round(self.prescription_gy, 6),
            "target_structure": self.target_structure,
            "structures": sorted(self.structures) if self.structures else None,
            "dvh_bins": self.dvh_bins,
            "gamma": self.gamma.hash() if self.gamma else None,
            "include_scenarios": self.include_scenarios,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class DVHMetrics(BaseModel):
    """Scalar dose statistics extracted from one structure's DVH."""

    mean_gy: float
    max_gy: float
    min_gy: float
    d2_gy: float = Field(..., description="Dose received by 2% of the volume (near-max).")
    d50_gy: float = Field(..., description="Median dose.")
    d95_gy: float = Field(..., description="Dose received by 95% of the volume.")
    d98_gy: float = Field(..., description="Dose received by 98% of the volume (near-min).")
    v_prescription_pct: float = Field(
        ..., description="% of structure volume receiving ≥ prescription dose."
    )
    volume_cc: float = Field(..., description="Structure volume in cubic centimetres.")


class DVHCurve(BaseModel):
    """Cumulative DVH for one structure (dose bins → % volume at/above)."""

    structure_name: str
    dose_bins_gy: List[float]
    volume_pct: List[float]
    metrics: DVHMetrics


class DoseIndices(BaseModel):
    """Plan-quality indices for the target structure."""

    target_structure: str
    prescription_gy: float
    homogeneity_index: float = Field(..., description="(D2 − D98) / D50; lower is more uniform.")
    conformity_index: float = Field(..., description="Paddick conformity index; 1.0 is ideal.")
    coverage_pct: float = Field(..., description="% of target receiving ≥ prescription.")
    hotspot_gy: float = Field(..., description="Global max dose anywhere in the grid.")


class DVHBand(BaseModel):
    """The DVH envelope of one structure over the nominal and scenario doses."""

    structure_name: str
    dose_bins_gy: List[float]
    nominal_pct: List[float]
    min_pct: List[float] = Field(..., description="Lowest volume fraction at each dose over all scenarios.")
    max_pct: List[float] = Field(..., description="Highest volume fraction at each dose over all scenarios.")
    n_scenarios: int = Field(..., ge=1, description="Scenario doses in the band, the nominal excluded.")


class RobustStructureMetrics(BaseModel):
    """DVH metrics of one structure under every scenario, with the envelope."""

    structure_name: str
    nominal: DVHMetrics
    lowest: DVHMetrics = Field(..., description="Per-metric minimum over the nominal and every scenario.")
    highest: DVHMetrics = Field(..., description="Per-metric maximum over the nominal and every scenario.")
    per_scenario: Dict[str, DVHMetrics] = Field(default_factory=dict)


class RobustIndices(BaseModel):
    """Worst-case plan-quality goals of the target over the scenarios."""

    target_structure: str
    prescription_gy: float
    n_scenarios: int
    worst_coverage_pct: float = Field(..., description="Lowest % of the target at or above the prescription.")
    worst_d95_gy: float
    worst_d98_gy: float
    worst_d2_gy: float = Field(..., description="Highest near-maximum dose.")
    worst_hotspot_gy: float = Field(..., description="Highest global maximum.")
    worst_homogeneity_index: float = Field(..., description="Highest (D2 − D98) / D50.")
    worst_conformity_index: float = Field(..., description="Lowest Paddick conformity index.")
    worst_scenario: Optional[str] = Field(default=None, description="The scenario with the lowest coverage.")


class GammaResult(BaseModel):
    """Gamma-analysis summary vs the reference dose."""

    dose_percent: float
    distance_mm: float
    threshold_pct: float
    local: bool
    pass_rate_pct: float
    mean_gamma: float
    evaluated_voxels: int


class EvaluationResult(ResearchArtifact):
    """Output of a completed evaluation."""

    evaluation_id: str
    cache_key: str
    dvh_curves: List[DVHCurve] = Field(default_factory=list)
    indices: Optional[DoseIndices] = None
    gamma: Optional[GammaResult] = None
    dvh_bands: List[DVHBand] = Field(default_factory=list, description="Per-structure DVH envelopes when the dose has scenarios.")
    robust_metrics: List[RobustStructureMetrics] = Field(default_factory=list)
    robust_indices: Optional[RobustIndices] = None
    n_scenarios: int = Field(default=0, description="Scenario doses evaluated (the nominal excluded).")
    dose_units: str = Field(default="Gy", description='"Gy" or "Gy(RBE)", from the dose result when known.')
    dose_id: Optional[str] = None
    geometry_id: str
    compute_time_s: float = Field(..., ge=0.0)
    created_at: Optional[datetime] = None


class EvaluationJobStatus(BaseModel):
    """Status row for an async ``POST /evaluate/run``."""

    id: str
    cache_key: str
    state: JobState = JobState.queued
    progress: float = 0.0
    stage: Optional[EvaluationStage] = EvaluationStage.queued
    message: Optional[str] = None
    evaluation_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


__all__ = [
    "GammaSpec",
    "EvaluationStage",
    "EvaluationRequest",
    "DVHMetrics",
    "DVHCurve",
    "DoseIndices",
    "GammaResult",
    "EvaluationResult",
    "EvaluationJobStatus",
]
