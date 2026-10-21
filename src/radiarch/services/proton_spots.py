"""Generate a proton-PBS beam model from a geometry + beam set.

This is the adapter between Service 2's modality-neutral types
(:class:`BeamSetSpec`, :class:`DeliveryParams`, :class:`FluenceElementSet`)
and :func:`radiarch.services.spot_placement.place_spots`. The spots of the
returned :class:`~radiarch.models.proton_plan.ProtonPlan`, flattened beam by
beam and layer by layer, are the fluence elements the dose engines and the
optimizer work on; the plan is what the Beam Model Service persists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from loguru import logger

from ..models.beam_model import BeamSetSpec, DeliveryParams, FluenceElementSet, PerBeamElements
from ..models.proton_plan import ProtonPlan
from .geometry_bundle import GeometryArrays
from .machine_model import ProtonMachineModel
from .spot_placement import BeamGeometry, PlacementParams, place_spots


@dataclass
class ProtonBuildResult:
    """Internal bundle — the FluenceElementSet plus the plan."""

    fluence_elements: FluenceElementSet
    plan: ProtonPlan


def generate_proton_spots(
    geometry: GeometryArrays,
    machine_model: ProtonMachineModel,
    beam_set: BeamSetSpec,
    params: DeliveryParams,
    prescription_gy: float = 2.0,
    target_label: Optional[int] = None,
) -> ProtonBuildResult:
    """Place the spots of every beam on the geometry's target and summarize them.

    The target is the geometry's PTV (GTV, CTV, or a structure named like a
    target) unless ``target_label`` names one. The isocenter is the target's
    centre of mass. ``prescription_gy`` does not enter the placement; it is
    kept so callers can record it with the plan.
    """
    del prescription_gy
    if target_label is None:
        chosen = geometry.target()
        if chosen is None:
            raise ValueError(
                f"geometry {geometry.geometry_id!r} has no target structure "
                f"(PTV/GTV/CTV or a structure named Target) among {sorted(geometry.structure_index)}"
            )
        target_name, target_label = chosen
    else:
        target_name = next((n for n, l in geometry.structure_index.items() if int(l) == int(target_label)), str(target_label))

    placement = PlacementParams(
        spot_spacing_mm=float(params.spot_spacing_mm or 5.0),
        layer_spacing_mm=float(params.layer_spacing_mm or 5.0),
    )
    beams = [BeamGeometry(beam_id=b.beam_id, gantry_deg=float(b.gantry_deg), couch_deg=float(b.couch_deg), name=b.beam_id)
             for b in beam_set.beams]
    logger.info(
        "Building proton plan on {}: {} beams, target {!r}, spot_spacing={} mm, layer_spacing={} mm",
        geometry.geometry_id, len(beams), target_name, placement.spot_spacing_mm, placement.layer_spacing_mm,
    )
    rsp = machine_model.rsp_model.rsp(geometry.ct_hu_xyz(), 100.0)
    plan = place_spots(rsp, geometry.mask_xyz(target_label), geometry.origin_mm, geometry.spacing_mm, beams,
                       placement, name=f"plan[{geometry.geometry_id}]")
    return ProtonBuildResult(fluence_elements=summarize_proton_plan(plan, beam_set), plan=plan)


def summarize_proton_plan(plan: ProtonPlan, beam_set: BeamSetSpec) -> FluenceElementSet:
    """Energy layers and spots per layer of every beam, keyed by the request's beam ids."""
    per_beam: List[PerBeamElements] = []
    total = 0
    for idx, beam in enumerate(plan.beams):
        beam_id = beam_set.beams[idx].beam_id if idx < len(beam_set.beams) else (beam.beam_id or f"beam_{idx}")
        energies = [float(layer.energy_mev) for layer in beam.layers]
        spots = [int(layer.n_spots) for layer in beam.layers]
        total += sum(spots)
        per_beam.append(PerBeamElements(
            beam_id=beam_id, element_count=sum(spots),
            energy_layers=energies or None, spots_per_layer=spots or None,
        ))
    if not per_beam:
        per_beam = [PerBeamElements(beam_id=b.beam_id, element_count=0) for b in beam_set.beams]
    return FluenceElementSet(total_count=total, per_beam=per_beam)


__all__ = ["ProtonBuildResult", "generate_proton_spots", "summarize_proton_plan"]
