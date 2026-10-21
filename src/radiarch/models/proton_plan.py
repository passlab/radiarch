"""Radiarch's own proton pencil-beam-scanning plan model (roadmap R14).

A proton plan is a list of beams; a beam is a gantry/couch position with an
isocenter, an optional range shifter and a list of energy layers; a layer is
a nominal energy and its scanned spots, each with a position in the beam's-eye
view at isocenter and a meterset. The spots, flattened beam by beam and layer
by layer, are the plan's fluence elements: the order the dose engines and the
optimizer use for weight vectors and influence-matrix columns.

The model is pydantic so a plan serializes to JSON, pickles, and validates on
load. Conventions follow DICOM RT Ion Plan: angles in degrees, positions in
millimetres in the patient (DICOM LPS) frame for the isocenter and in the
IEC beam-limiting-device frame for the spots, metersets in MU.

``ProtonPlan.from_opentps`` adapts the ``ProtonPlan`` objects the vendored
OpenTPS copy builds (duck-typed, no OpenTPS import) so the beam models
persisted before R15 keep working; R15's spot placement builds this model
directly.
"""

from __future__ import annotations

from typing import Any, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from pydantic import BaseModel, Field, model_validator


class ProtonSpot(BaseModel):
    """One scanned spot: BEV position at isocenter and its meterset."""

    x_mm: float
    y_mm: float
    mu: float = Field(..., ge=0.0, description="Meterset of this spot (MU).")
    start_time_s: Optional[float] = Field(
        default=None, description="Delivery start time, when the plan carries timings (interplay studies)."
    )


class RangeShifterSetting(BaseModel):
    """Per-layer range-shifter state, as written to the MCsquare plan file."""

    setting: str = Field(default="IN", description='"IN" or "OUT" for a binary range shifter.')
    isocenter_to_range_shifter_mm: float = 0.0
    water_equivalent_thickness_mm: Optional[float] = Field(
        default=None, description="None = take the WET of the range shifter from the beam data library."
    )


class ProtonLayer(BaseModel):
    """An energy layer: nominal energy and its spots."""

    energy_mev: float = Field(..., gt=0.0)
    spots: List[ProtonSpot] = Field(default_factory=list)
    range_shifter: Optional[RangeShifterSetting] = None

    @property
    def n_spots(self) -> int:
        return len(self.spots)

    @property
    def meterset(self) -> float:
        return float(sum(s.mu for s in self.spots))

    @property
    def has_timings(self) -> bool:
        return bool(self.spots) and all(s.start_time_s is not None for s in self.spots)


class ProtonBeam(BaseModel):
    """A field: gantry and couch angles, isocenter, optional range shifter, layers."""

    beam_id: str = Field(default="", max_length=64)
    name: str = ""
    gantry_deg: float = 0.0
    couch_deg: float = 0.0
    isocenter_mm: Tuple[float, float, float] = Field(
        ..., description="Isocenter in the patient (DICOM LPS) frame, mm."
    )
    range_shifter_id: Optional[str] = Field(
        default=None, description="ID of a range shifter defined in the beam data library; None = none."
    )
    layers: List[ProtonLayer] = Field(default_factory=list)

    @property
    def n_spots(self) -> int:
        return sum(layer.n_spots for layer in self.layers)

    @property
    def meterset(self) -> float:
        return float(sum(layer.meterset for layer in self.layers))

    @property
    def energies_mev(self) -> List[float]:
        return [layer.energy_mev for layer in self.layers]


class ProtonPlan(BaseModel):
    """A PBS plan: beams in delivery order; spots flattened beam by beam, layer by layer."""

    name: str = "ProtonPlan"
    n_fractions: int = Field(default=1, ge=1)
    beams: List[ProtonBeam] = Field(default_factory=list)

    @model_validator(mode="after")
    def _needs_one_spot(self) -> "ProtonPlan":
        if self.beams and self.n_spots == 0:
            raise ValueError("ProtonPlan has beams but no spots")
        return self

    # ----- fluence-element view ---------------------------------------

    @property
    def n_spots(self) -> int:
        return sum(beam.n_spots for beam in self.beams)

    @property
    def meterset(self) -> float:
        return float(sum(beam.meterset for beam in self.beams))

    def iter_spots(self) -> Iterator[Tuple[int, int, int, ProtonSpot]]:
        """Yield ``(beam_index, layer_index, spot_index, spot)`` in fluence-element order."""
        for b, beam in enumerate(self.beams):
            for l, layer in enumerate(beam.layers):
                for s, spot in enumerate(layer.spots):
                    yield b, l, s, spot

    @property
    def spot_mus(self) -> np.ndarray:
        """All spot metersets in fluence-element order."""
        return np.array([spot.mu for *_, spot in self.iter_spots()], dtype=np.float32)

    @property
    def spot_energies_mev(self) -> np.ndarray:
        """The nominal energy of every spot, in fluence-element order."""
        return np.array(
            [self.beams[b].layers[l].energy_mev for b, l, _, _ in self.iter_spots()], dtype=np.float32
        )

    def with_spot_mus(self, mus: Sequence[float]) -> "ProtonPlan":
        """A copy of the plan with the spot metersets replaced, in fluence-element order."""
        mus = np.asarray(mus, dtype=np.float64).ravel()
        if mus.shape != (self.n_spots,):
            raise ValueError(f"expected {self.n_spots} spot metersets, got {mus.shape}")
        plan = self.model_copy(deep=True)
        for i, (b, l, s, _) in enumerate(plan.iter_spots()):
            plan.beams[b].layers[l].spots[s].mu = float(mus[i])
        return plan

    def shifted(self, shift_mm: Sequence[float]) -> "ProtonPlan":
        """A copy with every isocenter moved by ``shift_mm`` (a setup-error scenario)."""
        dx, dy, dz = (float(v) for v in shift_mm)
        plan = self.model_copy(deep=True)
        for beam in plan.beams:
            x, y, z = beam.isocenter_mm
            beam.isocenter_mm = (x + dx, y + dy, z + dz)
        return plan

    # ----- adapters ---------------------------------------------------

    @classmethod
    def from_opentps(cls, plan: Any, name: Optional[str] = None) -> "ProtonPlan":
        """Build from an OpenTPS ``ProtonPlan`` (duck-typed; nothing is imported).

        Reads ``plan.beams[*]`` (``gantryAngle``, ``couchAngle``,
        ``isocenterPosition``, ``rangeShifter``), ``beam.layers[*]``
        (``nominalEnergy``, ``spotXY``, ``spotMUs``, ``spotTimings``,
        ``rangeShifterSettings``) and ``plan.numberOfFractionsPlanned``.
        """
        beams: List[ProtonBeam] = []
        for b, ob in enumerate(plan.beams):
            rs = getattr(ob, "rangeShifter", None)
            if isinstance(rs, (list, tuple)):
                rs = rs[0] if rs else None
            rs_id = getattr(rs, "ID", None) if rs is not None else None
            layers: List[ProtonLayer] = []
            for ol in ob.layers:
                xy = np.asarray(list(ol.spotXY), dtype=np.float64).reshape(-1, 2)
                mus = np.asarray(ol.spotMUs, dtype=np.float64).ravel()
                raw_timings = getattr(ol, "spotTimings", None)
                timings = (np.asarray(raw_timings, dtype=np.float64).ravel()
                           if raw_timings is not None else np.zeros(0))
                if mus.shape[0] != xy.shape[0]:
                    raise ValueError(f"layer {ol.nominalEnergy} MeV: {xy.shape[0]} spots but {mus.shape[0]} metersets")
                spots = [
                    ProtonSpot(
                        x_mm=float(xy[i, 0]), y_mm=float(xy[i, 1]), mu=float(mus[i]),
                        start_time_s=(float(timings[i]) if timings.shape[0] == xy.shape[0] else None),
                    )
                    for i in range(xy.shape[0])
                ]
                rs_setting = None
                settings = getattr(ol, "rangeShifterSettings", None)
                if rs_id is not None and settings is not None:
                    rs_setting = RangeShifterSetting(
                        setting=str(getattr(settings, "rangeShifterSetting", "IN")),
                        isocenter_to_range_shifter_mm=float(getattr(settings, "isocenterToRangeShifterDistance", 0.0) or 0.0),
                        water_equivalent_thickness_mm=(
                            None if getattr(settings, "rangeShifterWaterEquivalentThickness", None) is None
                            else float(settings.rangeShifterWaterEquivalentThickness)
                        ),
                    )
                layers.append(ProtonLayer(energy_mev=float(ol.nominalEnergy), spots=spots, range_shifter=rs_setting))
            iso = tuple(float(v) for v in np.asarray(ob.isocenterPosition, dtype=np.float64).ravel()[:3])
            beams.append(ProtonBeam(
                beam_id=str(getattr(ob, "id", b)), name=str(getattr(ob, "name", "") or ""),
                gantry_deg=float(ob.gantryAngle), couch_deg=float(ob.couchAngle),
                isocenter_mm=iso, range_shifter_id=(str(rs_id) if rs_id is not None else None), layers=layers,
            ))
        return cls(
            name=name or str(getattr(plan, "name", "") or "ProtonPlan"),
            n_fractions=int(getattr(plan, "numberOfFractionsPlanned", 1) or 1),
            beams=beams,
        )


__all__ = ["ProtonSpot", "RangeShifterSetting", "ProtonLayer", "ProtonBeam", "ProtonPlan"]
