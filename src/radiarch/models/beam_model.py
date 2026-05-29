"""Pydantic I/O models for the Beam Model Service (Service 2).

A "beam model" is the modality-specific representation of deliverable
radiation elements for a treatment plan:

* For protons (PROTON_PBS), one element is a *spot* — a discrete
  ``(x, y, energy)`` triple in beam's-eye-view coordinates, organized
  into energy layers and scanned across the target.
* For photons (PHOTON_IMRT), one element is a *beamlet* — a 2D pixel
  in a regular grid in beam's-eye-view, modulated by an MLC aperture.

These two physical concepts are unified under the ``FluenceElementSet``
abstraction: each element produces one independent unit of dose deposit
downstream, and the dose engine doesn't need to know which modality
made it.

See ``docs/tps_services_implementation_plan.md`` (Service 2) for the
full specification.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

from .job import JobState


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Modality(str, Enum):
    """Supported treatment modalities.

    PHOTON_IMRT  — Intensity-Modulated Radiation Therapy with photons,
                   delivered as a fluence grid through an MLC.
    PROTON_PBS   — Pencil-Beam Scanning with protons, delivered as a
                   discrete spot map in energy layers.
    """

    photon_imrt = "PHOTON_IMRT"
    proton_pbs = "PROTON_PBS"


class BeamModelStage(str, Enum):
    """Stages a :class:`BeamModelService.build` call passes through.

    Reported via the ``stage`` field on ``BeamModelJobStatus`` so
    clients polling ``GET /beam-model/jobs/{id}`` can render progress.
    """

    queued = "queued"
    loading_geometry = "loading_geometry"
    loading_machine_model = "loading_machine_model"
    building_beams = "building_beams"
    computing_elements = "computing_elements"
    persisting = "persisting"
    done = "done"


# ---------------------------------------------------------------------------
# Beam set specification
# ---------------------------------------------------------------------------

class BeamSpec(BaseModel):
    """One beam in a treatment plan — gantry, couch, collimator angles."""

    beam_id: str = Field(..., min_length=1, max_length=64)
    gantry_deg: float = Field(..., ge=0.0, lt=360.0,
                              description="IEC 61217 gantry angle, [0, 360).")
    couch_deg: float = Field(default=0.0, ge=-180.0, le=180.0,
                             description="IEC 61217 couch angle, [-180, 180].")
    collimator_deg: float = Field(default=0.0, ge=-180.0, le=180.0,
                                  description="Collimator rotation, [-180, 180].")


class BeamSetSpec(BaseModel):
    """The geometric beam configuration for a plan.

    ``isocenter_mm`` is in patient LPS coordinates. ``beams`` carries one
    entry per delivery direction (1–9 beams supported, matching the
    existing PlanRequest constraint).
    """

    isocenter_mm: Tuple[float, float, float]
    beams: List[BeamSpec] = Field(..., min_length=1, max_length=9)

    @field_validator("beams")
    @classmethod
    def _unique_beam_ids(cls, beams: List[BeamSpec]) -> List[BeamSpec]:
        ids = [b.beam_id for b in beams]
        if len(set(ids)) != len(ids):
            raise ValueError(f"beam_id values must be unique, got {ids}")
        return beams


# ---------------------------------------------------------------------------
# Delivery parameters (modality-tagged union, expressed as nullable union)
# ---------------------------------------------------------------------------

class DeliveryParams(BaseModel):
    """Delivery-system parameters. Modality determines which fields apply.

    For PROTON_PBS the proton fields are honored and photon fields are
    ignored (and excluded from the cache key). For PHOTON_IMRT the
    inverse holds. Defaults below match the existing project conventions
    (5 mm spot/layer spacing for protons, 5×5 mm beamlets for photons).
    """

    # ---- PROTON_PBS ------------------------------------------------------
    spot_spacing_mm: Optional[float] = Field(default=5.0, gt=0)
    layer_spacing_mm: Optional[float] = Field(default=5.0, gt=0)
    energy_range: Optional[Tuple[float, float]] = Field(
        default=None,
        description="MeV range. None → derived from target depth.",
    )

    # ---- PHOTON_IMRT -----------------------------------------------------
    beamlet_size_mm: Optional[Tuple[float, float]] = Field(
        default=(5.0, 5.0),
        description="Beamlet pixel size in BEV (x, y) mm.",
    )
    mlc_leaf_width_mm: Optional[float] = Field(default=None, gt=0)
    jaw_opening_mm: Optional[Tuple[float, float]] = Field(default=None)

    # ---- Helpers ---------------------------------------------------------

    def for_modality(self, modality: Modality) -> Dict[str, Any]:
        """Return only the fields that affect dose for ``modality``.

        This is what gets folded into the cache key — so a default
        photon param change doesn't invalidate proton cached results.
        """
        if modality is Modality.proton_pbs:
            return {
                "spot_spacing_mm": self.spot_spacing_mm,
                "layer_spacing_mm": self.layer_spacing_mm,
                "energy_range": list(self.energy_range) if self.energy_range else None,
            }
        if modality is Modality.photon_imrt:
            return {
                "beamlet_size_mm": list(self.beamlet_size_mm) if self.beamlet_size_mm else None,
                "mlc_leaf_width_mm": self.mlc_leaf_width_mm,
                "jaw_opening_mm": list(self.jaw_opening_mm) if self.jaw_opening_mm else None,
            }
        raise ValueError(f"Unhandled modality: {modality!r}")


# ---------------------------------------------------------------------------
# Build request
# ---------------------------------------------------------------------------

class BeamModelBuildRequest(BaseModel):
    """Input payload for POST /api/v1/beam-model/build."""

    plan_id: Optional[str] = Field(default=None, max_length=36)
    geometry_id: str = Field(..., min_length=1, max_length=36,
                             description="ID returned by Geometry Service.")
    modality: Modality
    machine_model_id: Optional[str] = Field(
        default=None,
        description="Custom machine model identifier; null = project default.",
    )
    beam_set: BeamSetSpec
    delivery_params: DeliveryParams = Field(default_factory=DeliveryParams)

    # ---- Cache key -------------------------------------------------------

    def compute_cache_key(self) -> str:
        """Deterministic sha256 over the inputs that affect output content.

        Excludes ``plan_id`` (a downstream reference, not an input to the
        physics) and excludes the modality-irrelevant subset of
        ``delivery_params``.
        """
        # Sort beams by beam_id so equivalent BeamSetSpecs hash the same
        # regardless of insertion order.
        sorted_beams = sorted(
            (
                {
                    "beam_id": b.beam_id,
                    "gantry_deg": b.gantry_deg,
                    "couch_deg": b.couch_deg,
                    "collimator_deg": b.collimator_deg,
                }
                for b in self.beam_set.beams
            ),
            key=lambda b: b["beam_id"],
        )
        payload = {
            "geometry_id": self.geometry_id,
            "modality": self.modality.value,
            "machine_model_id": self.machine_model_id,
            "isocenter_mm": list(self.beam_set.isocenter_mm),
            "beams": sorted_beams,
            "delivery_params": self.delivery_params.for_modality(self.modality),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class PerBeamElements(BaseModel):
    """Per-beam fluence-element breakdown.

    The proton fields (``energy_layers``, ``spots_per_layer``) are
    populated for PROTON_PBS results. The photon fields (``grid_dims``,
    ``active_beamlets``) are populated for PHOTON_IMRT. The other set is
    ``None`` — same model serves both modalities.
    """

    beam_id: str
    element_count: int = Field(..., ge=0)

    # PROTON_PBS extras
    energy_layers: Optional[List[float]] = None
    spots_per_layer: Optional[List[int]] = None

    # PHOTON_IMRT extras
    grid_dims: Optional[Tuple[int, int]] = None
    active_beamlets: Optional[int] = None

    @model_validator(mode="after")
    def _spot_arrays_align(self) -> "PerBeamElements":
        """If both proton arrays are populated, their lengths must match."""
        if self.energy_layers is not None and self.spots_per_layer is not None:
            if len(self.energy_layers) != len(self.spots_per_layer):
                raise ValueError(
                    "energy_layers and spots_per_layer must have the same length"
                )
        return self


class FluenceElementSet(BaseModel):
    """Aggregate fluence-element summary across all beams.

    ``total_count`` is the sum of ``per_beam[i].element_count`` —
    validated on construction so the two views can't drift.
    """

    total_count: int = Field(..., ge=0)
    per_beam: List[PerBeamElements]

    @model_validator(mode="after")
    def _totals_match(self) -> "FluenceElementSet":
        s = sum(pb.element_count for pb in self.per_beam)
        if s != self.total_count:
            raise ValueError(
                f"total_count={self.total_count} does not match "
                f"sum(per_beam.element_count)={s}"
            )
        return self


class BeamModelResult(BaseModel):
    """Output of a completed beam-model build."""

    beam_model_id: str
    geometry_id: str
    modality: Modality
    fluence_elements: FluenceElementSet
    beam_model_ref_uri: str = Field(
        ..., description="URI/path to the serialized OpenTPS plan artifact."
    )
    machine_model_id: str = Field(
        ..., description="Resolved machine model id (never None on output)."
    )
    cache_key: str
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Async job tracking
# ---------------------------------------------------------------------------

class BeamModelJobStatus(BaseModel):
    """Tracks an async ``POST /beam-model/build`` invocation.

    Identified by its own ``id``. Carries ``cache_key`` so a second
    request for the same inputs can short-circuit (or reuse an in-flight
    job, in a future enhancement). ``beam_model_id`` is populated when
    the job succeeds.
    """

    id: str
    cache_key: str
    state: JobState = JobState.queued
    progress: float = 0.0
    stage: Optional[BeamModelStage] = BeamModelStage.queued
    message: Optional[str] = None
    beam_model_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
