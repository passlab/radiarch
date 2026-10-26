"""Shorthands for structure operations (``Geometry.derive``) and objectives (``BeamModel.optimize``)."""

from __future__ import annotations

from typing import Optional

from ..models.geometry import StructureOperation
from ..models.optimization import ObjectiveSpec


# ----- structure operations ----------------------------------------------------------

def expand(name: str, source: str, margin_mm: float) -> StructureOperation:
    return StructureOperation(op="expand", name=name, source=source, margin_mm=margin_mm)


def erode(name: str, source: str, margin_mm: float) -> StructureOperation:
    return StructureOperation(op="erode", name=name, source=source, margin_mm=margin_mm)


def ring(name: str, source: str, inner_mm: float, outer_mm: float) -> StructureOperation:
    return StructureOperation(op="ring", name=name, source=source, inner_mm=inner_mm, outer_mm=outer_mm)


def union(name: str, *sources: str) -> StructureOperation:
    return StructureOperation(op="union", name=name, sources=list(sources))


def intersection(name: str, *sources: str) -> StructureOperation:
    return StructureOperation(op="intersection", name=name, sources=list(sources))


def subtract(name: str, source: str, *minus: str) -> StructureOperation:
    return StructureOperation(op="subtract", name=name, source=source, sources=list(minus))


def override(source: str, *, hu: Optional[float] = None, density_g_cm3: Optional[float] = None) -> StructureOperation:
    return StructureOperation(op="density_override", source=source, hu=hu, density_g_cm3=density_g_cm3)


# ----- objectives -------------------------------------------------------------------

def uniform(structure: str, dose_gy: float, weight: float = 100.0) -> ObjectiveSpec:
    return ObjectiveSpec(type="DUniform", structure_name=structure, dose_gy=dose_gy, weight=weight)


def minimum(structure: str, dose_gy: float, weight: float = 100.0) -> ObjectiveSpec:
    return ObjectiveSpec(type="DMin", structure_name=structure, dose_gy=dose_gy, weight=weight)


def maximum(structure: str, dose_gy: float, weight: float = 10.0) -> ObjectiveSpec:
    return ObjectiveSpec(type="DMax", structure_name=structure, dose_gy=dose_gy, weight=weight)


def dvh_max(structure: str, dose_gy: float, volume_fraction: float, weight: float = 10.0) -> ObjectiveSpec:
    """At most ``volume_fraction`` of the structure above ``dose_gy``."""
    return ObjectiveSpec(type="DVHMax", structure_name=structure, dose_gy=dose_gy, volume_fraction=volume_fraction, weight=weight)


def dvh_min(structure: str, dose_gy: float, volume_fraction: float, weight: float = 100.0) -> ObjectiveSpec:
    """At least ``volume_fraction`` of the structure at ``dose_gy`` or more."""
    return ObjectiveSpec(type="DVHMin", structure_name=structure, dose_gy=dose_gy, volume_fraction=volume_fraction, weight=weight)


__all__ = ["expand", "erode", "ring", "union", "intersection", "subtract", "override",
           "uniform", "minimum", "maximum", "dvh_max", "dvh_min"]
