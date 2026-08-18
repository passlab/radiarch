"""Generate a photon-IMRT beam model from a geometry + beam set.

Adapter between Service 2's modality-neutral types and OpenTPS's
``PhotonPlan`` construction. The function below is the only place that
knows how to call OpenTPS for photon plan assembly; the rest of the
service treats beamlets as opaque "fluence elements."

v1 scope: each beam carries one ``PlanPhotonSegment`` (one MLC aperture
shape). The "fluence element" count for that beam is the number of
beamlets that fit inside the jaw opening at the beamlet pixel size.
True multi-segment IMRT (multiple MLC apertures per beam, computed by
an inverse planner) is a v2 enhancement.

Beamlet grid math: beamlets are square-ish pixels in beam's-eye-view
(BEV) coordinates at isocenter. The grid extent is the jaw opening; the
per-pixel size comes from ``DeliveryParams.beamlet_size_mm``. So a
20×20 cm jaw with 5×5 mm beamlets gives a 40×40 = 1600 element grid.
After MLC clipping (open beamlets only, no shielded regions in v1)
``active_beamlets`` is the same as ``element_count`` for now — when
multi-segment / inverse-planning lands, this will diverge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from loguru import logger

from ..models.beam_model import (
    BeamSetSpec,
    DeliveryParams,
    FluenceElementSet,
    Modality,
    PerBeamElements,
)
from .machine_model import PhotonMachineModel


@dataclass
class PhotonBuildResult:
    """Internal bundle — the FluenceElementSet plus the OpenTPS plan."""

    fluence_elements: FluenceElementSet
    plan: Any  # OpenTPS PhotonPlan (or test double)


def generate_photon_beamlets(
    ct: Any,
    patient: Any,
    machine_model: PhotonMachineModel,
    beam_set: BeamSetSpec,
    params: DeliveryParams,
    monitor_units_per_beam: float = 5000.0,
) -> PhotonBuildResult:
    """Build a photon plan and summarize its beamlet grid.

    Parameters
    ----------
    ct, patient
        Loaded OpenTPS objects (kept in the signature for symmetry with
        the proton builder; v1 photon construction doesn't need patient
        contours, but downstream dose calculation will).
    machine_model
        Resolved :class:`PhotonMachineModel` — supplies the default jaw
        opening when the request doesn't override it.
    beam_set
        Geometric beam configuration.
    params
        :class:`DeliveryParams` carrying ``beamlet_size_mm`` and
        ``jaw_opening_mm``.
    monitor_units_per_beam
        MU per beam. Default 5000 — clinical norm. Same value used by
        the existing photon_ccc workflow.
    """
    # Lazy import — OpenTPS is heavy.
    from opentps.core.data.plan._photonPlan import PhotonPlan
    from opentps.core.data.plan._planPhotonBeam import PlanPhotonBeam
    from opentps.core.data.plan._planPhotonSegment import PlanPhotonSegment

    # Resolve the actual jaw opening: request → machine default.
    jaw_x, jaw_y = _resolve_jaw_opening(params, machine_model)
    bx, by = params.beamlet_size_mm or (5.0, 5.0)
    grid_dims = (
        max(1, math.ceil(jaw_x / bx)),
        max(1, math.ceil(jaw_y / by)),
    )
    elements_per_beam = grid_dims[0] * grid_dims[1]

    logger.info(
        "Building photon plan: %d beams, jaw=%.1f×%.1f mm, "
        "beamlet=%.1f×%.1f mm → grid %s (%d elements/beam)",
        len(beam_set.beams), jaw_x, jaw_y, bx, by, grid_dims, elements_per_beam,
    )

    photon_plan = PhotonPlan()
    per_beam: List[PerBeamElements] = []

    for beam_spec in beam_set.beams:
        beam = PlanPhotonBeam()
        beam.gantryAngle = beam_spec.gantry_deg
        beam.couchAngle = beam_spec.couch_deg

        segment = PlanPhotonSegment()
        segment.monitorUnits = monitor_units_per_beam
        # OpenTPS expects [-half, +half] for jaw opening — convert from
        # an absolute opening size centered on isocenter.
        segment.jawOpeningMM = [-jaw_x / 2.0, jaw_x / 2.0]
        beam.segments = [segment]

        photon_plan.beams.append(beam)
        per_beam.append(
            PerBeamElements(
                beam_id=beam_spec.beam_id,
                element_count=elements_per_beam,
                grid_dims=grid_dims,
                active_beamlets=elements_per_beam,  # see module docstring
            )
        )

    fluence = FluenceElementSet(
        total_count=elements_per_beam * len(beam_set.beams),
        per_beam=per_beam,
    )
    return PhotonBuildResult(fluence_elements=fluence, plan=photon_plan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_jaw_opening(
    params: DeliveryParams,
    machine_model: PhotonMachineModel,
) -> Tuple[float, float]:
    """Use request override if present, else machine default.

    Treats the machine's ``max_jaw_opening_mm`` as a square default.
    Real LINACs have rectangular jaws — when a custom machine model
    starts carrying x/y separately, this resolves separately too.
    """
    if params.jaw_opening_mm is not None:
        # The request gives [-half, +half] semantics or [width_x, width_y]?
        # The Pydantic field is a Tuple[float, float]; we treat both
        # entries as positive widths in mm.
        return float(params.jaw_opening_mm[0]), float(params.jaw_opening_mm[1])
    default = float(machine_model.max_jaw_opening_mm)
    return default, default


__all__ = ["PhotonBuildResult", "generate_photon_beamlets"]
