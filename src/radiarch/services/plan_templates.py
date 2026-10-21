"""Plan templates: beam sets built from the geometry (roadmap R3).

A template turns a geometry and a few parameters into a :class:`BeamSetSpec`
the Beam Model Service can build. The first one is craniospinal irradiation
with protons: a long target (brain plus the whole spinal canal) split into
fields along the patient's z axis, each with its own isocenter and a
field-specific target slab; neighbouring slabs overlap by the junction length,
so the optimizer feathers the junctions (a dose gradient over the overlap
rather than a hard match line) and a robust optimization over setup
scenarios keeps them safe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
from loguru import logger

from ..models.beam_model import BeamSetSpec, BeamSpec
from .geometry_bundle import GeometryArrays

MAX_FIELD_LENGTH_MM = 400.0      # the field of view of the spot grid (spot_placement.FIELD_OF_VIEW_MM)

# Presets (decision of 2026-10-21, ADR 0009): the research default treats the brain slab with
# one posterior field; the clinical preset with a posterior-oblique pair at ±15°, the usual
# proton practice for the cranial part (lens sparing, lower skin dose).
CRANIOSPINAL_PRESETS = {
    "research": {"brain_oblique_deg": 0.0},
    "clinical": {"brain_oblique_deg": 15.0},
}


@dataclass
class CraniospinalField:
    beam_id: str
    z_range_mm: Tuple[float, float]
    isocenter_mm: Tuple[float, float, float]
    n_target_voxels: int


@dataclass
class CraniospinalTemplate:
    beam_set: BeamSetSpec
    fields: List[CraniospinalField]
    target_name: str
    target_z_extent_mm: Tuple[float, float]
    junctions_mm: List[Tuple[float, float]]


def target_z_profile(mask_zyx: np.ndarray, origin_mm, spacing_mm) -> Tuple[np.ndarray, np.ndarray]:
    """Per-slice voxel counts of a (z, y, x) mask and the slice z coordinates."""
    counts = mask_zyx.reshape(mask_zyx.shape[0], -1).sum(axis=1)
    z = float(origin_mm[2]) + float(spacing_mm[2]) * np.arange(mask_zyx.shape[0])
    return counts, z


def split_extent(z_lo: float, z_hi: float, field_length_mm: float, overlap_mm: float) -> List[Tuple[float, float]]:
    """Split ``[z_lo, z_hi]`` into the fewest slabs of at most ``field_length_mm``
    that overlap their neighbours by ``overlap_mm``; superior slab first."""
    length = z_hi - z_lo
    if length <= field_length_mm:
        return [(z_lo, z_hi)]
    if overlap_mm >= field_length_mm:
        raise ValueError("overlap_mm must be smaller than field_length_mm")
    n = int(math.ceil((length - overlap_mm) / (field_length_mm - overlap_mm)))
    # equal slabs of length L with n-1 overlaps: n L - (n-1) overlap = length
    slab = (length + (n - 1) * overlap_mm) / n
    slabs = []
    top = z_hi
    for _ in range(n):
        bottom = max(z_lo, top - slab)
        slabs.append((bottom, top))
        top = bottom + overlap_mm
    slabs[-1] = (z_lo, slabs[-1][1])
    return slabs


def craniospinal_template(
    geometry: GeometryArrays,
    target_structure: Optional[str] = None,
    *,
    field_length_mm: float = 300.0,
    overlap_mm: float = 40.0,
    gantry_deg: float = 180.0,
    couch_deg: float = 0.0,
    brain_oblique_deg: Optional[float] = None,
    preset: str = "research",
    beam_prefix: str = "CSI",
) -> CraniospinalTemplate:
    """Posterior fields along the craniospinal target, superior to inferior.

    ``field_length_mm`` is the longest slab one field covers (the spot grid's
    field of view is 400 mm; 300 mm leaves room for the margin and for the
    setup scenarios); ``overlap_mm`` is the junction length shared by two
    neighbouring fields. Every field gets the centre of mass of its slab as
    isocenter. With ``brain_oblique_deg`` > 0 the most superior slab (the
    brain) is treated by a pair of posterior-oblique fields at
    ``gantry_deg ± brain_oblique_deg`` sharing one isocenter instead of a
    single posterior field; ``preset`` ("research": single field,
    "clinical": the pair at 15°) sets it when it is not given.
    """
    if preset not in CRANIOSPINAL_PRESETS:
        raise ValueError(f"preset must be one of {sorted(CRANIOSPINAL_PRESETS)}, got {preset!r}")
    if brain_oblique_deg is None:
        brain_oblique_deg = float(CRANIOSPINAL_PRESETS[preset]["brain_oblique_deg"])
    if not 0.0 <= brain_oblique_deg < 90.0:
        raise ValueError("brain_oblique_deg must be in [0, 90)")
    if not 0.0 < field_length_mm <= MAX_FIELD_LENGTH_MM:
        raise ValueError(f"field_length_mm must be in (0, {MAX_FIELD_LENGTH_MM}]")
    if overlap_mm < 0.0:
        raise ValueError("overlap_mm must be non-negative")
    if target_structure is None:
        chosen = geometry.target()
        if chosen is None:
            raise ValueError(f"geometry {geometry.geometry_id!r} has no target structure")
        target_name, label = chosen
    else:
        label = geometry.label_of(target_structure)
        if label is None:
            raise ValueError(f"structure {target_structure!r} not in the geometry ({sorted(geometry.structure_index)})")
        target_name = target_structure
    mask = geometry.mask_zyx(label)
    counts, z = target_z_profile(mask, geometry.origin_mm, geometry.spacing_mm)
    present = np.flatnonzero(counts > 0)
    if present.size == 0:
        raise ValueError(f"target {target_name!r} is empty")
    z_lo, z_hi = float(z[present[0]]), float(z[present[-1]])
    slabs = split_extent(z_lo, z_hi, float(field_length_mm), float(overlap_mm))

    spacing = np.asarray(geometry.spacing_mm, dtype=float)
    origin = np.asarray(geometry.origin_mm, dtype=float)
    fields: List[CraniospinalField] = []
    beams: List[BeamSpec] = []
    for i, (lo, hi) in enumerate(slabs):
        keep = (z >= lo - 1e-6) & (z <= hi + 1e-6)
        slab_mask = np.zeros_like(mask)
        slab_mask[keep] = mask[keep]
        idx = np.argwhere(slab_mask)
        if idx.size == 0:
            raise ValueError(f"field {i + 1}: no target voxels between z={lo:.1f} and {hi:.1f} mm")
        com_zyx = idx.mean(axis=0)
        iso = tuple(float(v) for v in origin + com_zyx[::-1] * spacing)
        beam_id = f"{beam_prefix}{i + 1}"
        if i == 0 and brain_oblique_deg > 0.0:
            for tag, sign in (("L", +1.0), ("R", -1.0)):
                bid = f"{beam_id}{tag}"
                fields.append(CraniospinalField(bid, (lo, hi), iso, int(idx.shape[0])))
                beams.append(BeamSpec(beam_id=bid, gantry_deg=(float(gantry_deg) + sign * float(brain_oblique_deg)) % 360.0,
                                      couch_deg=float(couch_deg), isocenter_mm=iso, target_z_range_mm=(lo, hi)))
            continue
        fields.append(CraniospinalField(beam_id, (lo, hi), iso, int(idx.shape[0])))
        beams.append(BeamSpec(beam_id=beam_id, gantry_deg=float(gantry_deg) % 360.0, couch_deg=float(couch_deg),
                              isocenter_mm=iso, target_z_range_mm=(lo, hi)))
    junctions = [(slabs[i + 1][1] if slabs[i + 1][1] < slabs[i][0] else slabs[i][0], slabs[i + 1][1])
                 for i in range(len(slabs) - 1)]
    junctions = [(min(a, b), max(a, b)) for a, b in junctions]
    logger.info("craniospinal template on {!r}: z {:.1f}..{:.1f} mm → {} field(s), junctions {}",
                target_name, z_lo, z_hi, len(beams), junctions)
    return CraniospinalTemplate(BeamSetSpec(beams=beams), fields, target_name, (z_lo, z_hi), junctions)


__all__ = ["MAX_FIELD_LENGTH_MM", "CRANIOSPINAL_PRESETS", "CraniospinalField", "CraniospinalTemplate", "target_z_profile", "split_extent",
           "craniospinal_template"]
