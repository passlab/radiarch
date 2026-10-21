"""Machine models (roadmap R4): what a plan must respect to be deliverable.

A :class:`PhotonMachineSpec` describes a synthetic linac: its energies with
their output calibration, the MLC (leaf boundaries along the bank, travel
limits, speed, transmission), the jaws, gantry and dose-rate limits, and the
deliverability thresholds the sequencer enforces. Two synthetic machines ship
with radiarch (``machines/``); custom ones live in
``{beam_library_dir}/{id}/machine.json``. A :class:`ProtonMachineSpec` is read
from the beam data library the MCsquare engine uses.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field, model_validator


class PhotonEnergy(BaseModel):
    nominal_mv: float = Field(..., gt=0.0)
    flattening_filter_free: bool = False
    output_cgy_per_mu: float = Field(default=1.0, gt=0.0, description="Dose per MU at the reference conditions.")
    reference_depth_mm: float = Field(default=100.0, gt=0.0)
    reference_field_mm: float = Field(default=100.0, gt=0.0, description="Side of the square reference field at isocenter.")
    reference_ssd_mm: float = Field(default=1000.0, gt=0.0)
    dose_rate_mu_min: Tuple[float, float] = Field(default=(100.0, 600.0), description="(min, max) dose rate.")

    @model_validator(mode="after")
    def _rates(self) -> "PhotonEnergy":
        if not 0 < self.dose_rate_mu_min[0] <= self.dose_rate_mu_min[1]:
            raise ValueError("dose_rate_mu_min must be (min, max) with 0 < min <= max")
        return self


class MLCSpec(BaseModel):
    """A multileaf collimator: leaf pairs along y, tips moving along x (BEV at isocenter)."""

    name: str = "MLC"
    leaf_boundaries_mm: List[float] = Field(..., min_length=2, description="n_pairs + 1 ascending y positions of the leaf edges.")
    max_leaf_position_mm: float = Field(default=200.0, gt=0.0, description="Farthest a tip can retract from the centreline.")
    max_overtravel_mm: float = Field(default=150.0, ge=0.0, description="Farthest a tip can cross the centreline.")
    max_tip_difference_mm: Optional[float] = Field(default=None, gt=0.0, description="Largest allowed gap between neighbouring tips of one bank; null = no limit.")
    min_leaf_gap_mm: float = Field(default=0.5, ge=0.0, description="Smallest opening of a pair that is not closed.")
    interdigitation: bool = Field(default=True, description="A left leaf may pass the right leaf of a neighbouring pair.")
    max_leaf_speed_mm_s: float = Field(default=25.0, gt=0.0)
    leaf_transmission: float = Field(default=0.015, ge=0.0, le=0.2)

    @model_validator(mode="after")
    def _ascending(self) -> "MLCSpec":
        b = np.asarray(self.leaf_boundaries_mm, dtype=float)
        if np.any(np.diff(b) <= 0):
            raise ValueError("leaf_boundaries_mm must be strictly ascending")
        return self

    @property
    def n_pairs(self) -> int:
        return len(self.leaf_boundaries_mm) - 1

    @property
    def leaf_widths_mm(self) -> List[float]:
        b = self.leaf_boundaries_mm
        return [float(b[i + 1] - b[i]) for i in range(len(b) - 1)]

    @property
    def extent_mm(self) -> Tuple[float, float]:
        return (float(self.leaf_boundaries_mm[0]), float(self.leaf_boundaries_mm[-1]))

    def pair_index(self, y_mm: float) -> Optional[int]:
        """The leaf pair covering ``y_mm`` (lower edge inclusive), or None outside the bank."""
        b = self.leaf_boundaries_mm
        if y_mm < b[0] or y_mm >= b[-1]:
            return None
        return int(np.searchsorted(np.asarray(b, dtype=float), y_mm, side="right") - 1)


class JawSpec(BaseModel):
    x_range_mm: Tuple[float, float] = Field(default=(-200.0, 200.0), description="Farthest X1 and X2 positions.")
    y_range_mm: Tuple[float, float] = Field(default=(-200.0, 200.0), description="Farthest Y1 and Y2 positions.")
    max_jaw_overtravel_mm: float = Field(default=20.0, ge=0.0, description="How far a jaw can cross the centreline.")
    max_jaw_speed_mm_s: float = Field(default=20.0, gt=0.0)
    jaw_transmission: float = Field(default=0.002, ge=0.0, le=0.1)


class PhotonMachineSpec(BaseModel):
    machine_id: str = Field(..., min_length=1, max_length=64)
    name: str = ""
    kind: str = Field(default="synthetic", description='"synthetic": a made-up machine; "commissioned": from site data.')
    sad_mm: float = Field(default=1000.0, gt=0.0)
    energies: List[PhotonEnergy] = Field(..., min_length=1)
    mlc: MLCSpec
    jaws: JawSpec = Field(default_factory=JawSpec)
    default_field_mm: float = Field(default=200.0, gt=0.0, description="Side of the open field the beam-model builder uses when the request gives no jaw opening.")
    max_gantry_speed_deg_s: float = Field(default=6.0, gt=0.0)
    gantry_range_deg: Tuple[float, float] = Field(default=(0.0, 360.0))
    couch_range_deg: Tuple[float, float] = Field(default=(-90.0, 90.0))
    min_mu_per_segment: float = Field(default=2.0, ge=0.0)
    min_segment_area_mm2: float = Field(default=400.0, ge=0.0, description="Smallest aperture the sequencer keeps.")
    max_segments_per_beam: int = Field(default=40, ge=1)
    notes: str = ""

    @property
    def default_energy(self) -> PhotonEnergy:
        return self.energies[0]

    def energy(self, nominal_mv: Optional[float]) -> PhotonEnergy:
        if nominal_mv is None:
            return self.default_energy
        for e in self.energies:
            if abs(e.nominal_mv - float(nominal_mv)) < 1e-6:
                return e
        raise ValueError(f"machine {self.machine_id!r} has no {nominal_mv} MV energy; it has {[e.nominal_mv for e in self.energies]}")


class ProtonRangeShifter(BaseModel):
    shifter_id: str
    water_equivalent_thickness_mm: float


class ProtonMachineSpec(BaseModel):
    """What the beam data library says about the proton system."""

    machine_id: str
    bdl_name: str
    energies_mev: List[float]
    protons_per_mu: List[float]
    range_shifters: List[ProtonRangeShifter] = Field(default_factory=list)
    nozzle_to_isocenter_mm: Optional[float] = None
    smx_to_isocenter_mm: Optional[float] = None
    smy_to_isocenter_mm: Optional[float] = None

    @property
    def energy_range_mev(self) -> Tuple[float, float]:
        return (float(min(self.energies_mev)), float(max(self.energies_mev)))


__all__ = ["PhotonEnergy", "MLCSpec", "JawSpec", "PhotonMachineSpec", "ProtonRangeShifter", "ProtonMachineSpec"]
