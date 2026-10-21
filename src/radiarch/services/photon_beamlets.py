"""Generate a photon-IMRT beam model from a geometry + beam set.

Builds a :class:`radiarch.models.photon_plan.PhotonPlan` — radiarch's own
plan model, no OpenTPS involved — and summarizes its beamlets as fluence
elements. :func:`build_photon_plan` is the one place that assembles photon
plans; the legacy ``photon_ccc`` workflow uses it too.

v1 scope: each beam carries one segment, an open MLC aperture the size of
the jaw opening. Real multi-segment IMRT arrives with the machine model and
leaf sequencer (roadmap R4). Beamlet placement follows the half-pixel grid
OpenTPS used, so counts are unchanged: a 200 mm field at 5 mm gives 1600.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

from loguru import logger

from ..models.beam_model import (
    BeamSetSpec,
    DeliveryParams,
    FluenceElementSet,
    PerBeamElements,
)
from ..models.photon_plan import PhotonBeam, PhotonPlan, open_field_segment
from .machine_model import PhotonMachineModel


@dataclass
class PhotonBuildResult:
    """Internal bundle — the FluenceElementSet plus the plan."""

    fluence_elements: FluenceElementSet
    plan: PhotonPlan


def build_photon_plan(
    beams: Sequence[Tuple[float, float]],
    jaw_x_mm: Tuple[float, float],
    jaw_y_mm: Tuple[float, float],
    leaf_width_mm: float,
    mu_per_beam: float,
    beamlet_spacing_mm: Tuple[float, float] = (5.0, 5.0),
    isocenter_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    name: str = "PhotonPlan",
    beam_ids: Sequence[str] | None = None,
) -> PhotonPlan:
    """Assemble a plan of open fields.

    Parameters
    ----------
    beams
        ``(gantry_deg, couch_deg)`` per beam, in beam order.
    jaw_x_mm, jaw_y_mm
        Jaw positions as ``(min, max)`` at isocenter.
    leaf_width_mm
        MLC leaf width; defines the rows of the open aperture.
    mu_per_beam
        Meterset of the single segment of each beam.
    beamlet_spacing_mm
        Beamlet pixel size in the beam's-eye view.
    """
    ids = list(beam_ids) if beam_ids else [f"B{i + 1}" for i in range(len(beams))]
    if len(ids) != len(beams):
        raise ValueError("beam_ids must match beams")
    plan_beams: List[PhotonBeam] = []
    for beam_id, (gantry, couch) in zip(ids, beams):
        plan_beams.append(PhotonBeam(
            beam_id=beam_id,
            gantry_deg=float(gantry) % 360.0,
            couch_deg=float(couch),
            isocenter_mm=tuple(float(v) for v in isocenter_mm),
            segments=[open_field_segment(jaw_x_mm, jaw_y_mm, leaf_width_mm, mu_per_beam, beamlet_spacing_mm)],
        ))
    return PhotonPlan(name=name, beams=plan_beams)


def generate_photon_beamlets(
    ct: Any,
    patient: Any,
    machine_model: PhotonMachineModel,
    beam_set: BeamSetSpec,
    params: DeliveryParams,
    monitor_units_per_beam: float = 5000.0,
) -> PhotonBuildResult:
    """Build a photon plan of open fields and summarize its beamlets.

    ``ct`` and ``patient`` are kept for symmetry with the proton builder;
    open-field construction does not need them, dose calculation does.
    """
    del ct, patient
    jaw_x, jaw_y = _resolve_jaw_opening(params, machine_model)
    bx, by = params.beamlet_size_mm or (5.0, 5.0)
    leaf_width = float(params.mlc_leaf_width_mm or machine_model.mlc_leaf_width_mm)
    grid_dims = (max(1, math.ceil(jaw_x / bx)), max(1, math.ceil(jaw_y / by)))

    plan = build_photon_plan(
        beams=[(b.gantry_deg, b.couch_deg) for b in beam_set.beams],
        jaw_x_mm=(-jaw_x / 2.0, jaw_x / 2.0),
        jaw_y_mm=(-jaw_y / 2.0, jaw_y / 2.0),
        leaf_width_mm=leaf_width,
        mu_per_beam=monitor_units_per_beam,
        beamlet_spacing_mm=(float(bx), float(by)),
        isocenter_mm=tuple(beam_set.isocenter_mm),
        beam_ids=[b.beam_id for b in beam_set.beams],
    )
    logger.info(
        "Built photon plan: %d beams, jaw=%.1f×%.1f mm, leaf=%.1f mm, beamlet=%.1f×%.1f mm → %d beamlets",
        len(plan.beams), jaw_x, jaw_y, leaf_width, bx, by, plan.n_beamlets,
    )

    per_beam = [
        PerBeamElements(
            beam_id=beam.beam_id,
            element_count=beam.n_beamlets,
            grid_dims=grid_dims,
            active_beamlets=beam.n_beamlets,
        )
        for beam in plan.beams
    ]
    fluence = FluenceElementSet(total_count=plan.n_beamlets, per_beam=per_beam)
    return PhotonBuildResult(fluence_elements=fluence, plan=plan)


def _resolve_jaw_opening(
    params: DeliveryParams,
    machine_model: PhotonMachineModel,
) -> Tuple[float, float]:
    """Use the request override if present, else the machine default (square)."""
    if params.jaw_opening_mm is not None:
        return float(params.jaw_opening_mm[0]), float(params.jaw_opening_mm[1])
    default = float(machine_model.max_jaw_opening_mm)
    return default, default


__all__ = ["PhotonBuildResult", "build_photon_plan", "generate_photon_beamlets"]
