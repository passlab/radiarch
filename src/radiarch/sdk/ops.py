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


# trade-offs for multi-criteria planning (R11): convex, in Gy, zero when met; the weight is the MCO run's to set

def mean_dose(structure: str, level_gy: float = 0.0) -> ObjectiveSpec:
    """The structure's mean dose above ``level_gy`` (0: as low as possible)."""
    return ObjectiveSpec(type="MeanDose", structure_name=structure, dose_gy=level_gy, weight=1.0)


def eud_max(structure: str, a: float, level_gy: float = 0.0) -> ObjectiveSpec:
    """The gEUD (exponent ``a >= 1``) above ``level_gy``: an organ."""
    return ObjectiveSpec(type="EUDMax", structure_name=structure, dose_gy=level_gy, eud_a=a, weight=1.0)


def eud_min(structure: str, level_gy: float, a: float = -10.0) -> ObjectiveSpec:
    """The gEUD (exponent ``a <= 1``) below ``level_gy``: a target's cold spots."""
    return ObjectiveSpec(type="EUDMin", structure_name=structure, dose_gy=level_gy, eud_a=a, weight=1.0)


def rms_over(structure: str, level_gy: float) -> ObjectiveSpec:
    """Root mean square of the dose above ``level_gy``."""
    return ObjectiveSpec(type="RMSOver", structure_name=structure, dose_gy=level_gy, weight=1.0)


def rms_under(structure: str, level_gy: float) -> ObjectiveSpec:
    """Root mean square of the dose below ``level_gy``."""
    return ObjectiveSpec(type="RMSUnder", structure_name=structure, dose_gy=level_gy, weight=1.0)


def uniform_rms(structure: str, dose_gy: float) -> ObjectiveSpec:
    """Root mean square deviation from ``dose_gy``: a target's homogeneity."""
    return ObjectiveSpec(type="UniformRMS", structure_name=structure, dose_gy=dose_gy, weight=1.0)


def hard(structure: str, metric: str, op: str, value_gy: float, *, eud_a: Optional[float] = None, tolerance_gy: float = 0.1):
    """A hard constraint (``Dmax <=``, ``Dmin >=``, ``Dmean <=``, ``gEUD`` with ``eud_a``)."""
    from ..models.optimization import HardConstraint

    return HardConstraint(structure_name=structure, metric=metric, op=op, value_gy=value_gy, eud_a=eud_a, tolerance_gy=tolerance_gy)


__all__ = ["expand", "erode", "ring", "union", "intersection", "subtract", "override",
           "uniform", "minimum", "maximum", "dvh_max", "dvh_min",
           "mean_dose", "eud_max", "eud_min", "rms_over", "rms_under", "uniform_rms", "hard"]
