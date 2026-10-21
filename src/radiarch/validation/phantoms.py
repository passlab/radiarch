"""Synthetic phantoms for the validation cases.

Every phantom is returned as ``(density_zyx, spacing_mm, origin_mm)`` in
radiarch's grid convention: a ``(z, y, x)`` float32 array of mass density in
g/cm³, isotropic ``spacing_mm`` and the centre of voxel ``[0, 0, 0]`` as
``origin_mm``. Beams come from ``-y`` at gantry 0, so "depth" runs along ``y``
and the surface sits at ``y = 0`` unless stated otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

WATER = 1.0
LUNG = 0.26      # ICRU 44 inflated lung ≈ 0.26 g/cm³; CIRS 002LFC lung insert 0.21
BONE = 1.85      # ICRU cortical bone ≈ 1.85; CIRS bone insert 1.6
AIR = 0.0012


@dataclass(frozen=True)
class Phantom:
    density: np.ndarray            # (z, y, x) float32, g/cm³
    spacing_mm: Tuple[float, float, float]
    origin_mm: Tuple[float, float, float]
    name: str

    @property
    def shape(self) -> Tuple[int, int, int]:
        return tuple(int(v) for v in self.density.shape)

    def axis_mm(self, axis: str) -> np.ndarray:
        """Voxel-centre coordinates along ``x``, ``y`` or ``z``."""
        idx = {"z": 0, "y": 1, "x": 2}[axis]
        n = self.density.shape[idx]
        o = self.origin_mm[{"z": 2, "y": 1, "x": 0}[axis]]
        s = self.spacing_mm[{"z": 2, "y": 1, "x": 0}[axis]]
        return o + np.arange(n) * s

    def centre_index(self, axis: str) -> int:
        """Index of the voxel nearest the axis (x = 0 or z = 0)."""
        return int(np.argmin(np.abs(self.axis_mm(axis))))

    def depth_index(self, depth_mm: float) -> int:
        return int(np.argmin(np.abs(self.axis_mm("y") - depth_mm)))


def _lateral_axis(half_width_mm: float, spacing_mm: float) -> Tuple[int, float]:
    """Odd voxel count so one voxel is centred on the axis; returns (n, origin)."""
    n = 2 * int(round(half_width_mm / spacing_mm)) + 1
    return n, -((n - 1) / 2.0) * spacing_mm


def water_box(half_width_mm: float = 150.0, depth_mm: float = 300.0, spacing_mm: float = 2.5,
              surface_at_zero: bool = True) -> Phantom:
    """Water, lateral extent ±half_width, depth from the surface at y = 0."""
    n_lat, o_lat = _lateral_axis(half_width_mm, spacing_mm)
    n_depth = int(round(depth_mm / spacing_mm))
    density = np.full((n_lat, n_depth, n_lat), WATER, dtype=np.float32)
    oy = spacing_mm / 2.0 if surface_at_zero else -((n_depth - 1) / 2.0) * spacing_mm
    return Phantom(density, (spacing_mm,) * 3, (o_lat, oy, o_lat), "water_box")


def slab_phantom(layers: Sequence[Tuple[float, float]], half_width_mm: float = 150.0,
                 spacing_mm: float = 2.5, name: str = "slab") -> Phantom:
    """Stacked layers along the beam axis: ``[(thickness_mm, density), ...]``
    starting at the surface y = 0."""
    n_lat, o_lat = _lateral_axis(half_width_mm, spacing_mm)
    total = sum(t for t, _ in layers)
    n_depth = int(round(total / spacing_mm))
    density = np.empty((n_lat, n_depth, n_lat), dtype=np.float32)
    y = spacing_mm / 2.0 + np.arange(n_depth) * spacing_mm
    start = 0.0
    for thickness, rho in layers:
        sel = (y >= start) & (y < start + thickness)
        density[:, sel, :] = rho
        start += thickness
    return Phantom(density, (spacing_mm,) * 3, (o_lat, spacing_mm / 2.0, o_lat), name)


def lung_slab(spacing_mm: float = 2.5) -> Phantom:
    """MPPG 5.a-style heterogeneity: 3 cm water, 8 cm lung, water to 30 cm."""
    return slab_phantom([(30.0, WATER), (80.0, LUNG), (190.0, WATER)], spacing_mm=spacing_mm, name="lung_slab")


def bone_slab(spacing_mm: float = 2.5) -> Phantom:
    """3 cm water, 3 cm bone, water to 30 cm."""
    return slab_phantom([(30.0, WATER), (30.0, BONE), (240.0, WATER)], spacing_mm=spacing_mm, name="bone_slab")


def thorax_like(spacing_mm: float = 2.5) -> Phantom:
    """A CIRS 002LFC-like thorax: 30 × 30 cm water-equivalent body (300 mm deep),
    two lung cylinders (radius 45 mm) left and right of a spine cylinder
    (radius 15 mm, bone), all running along z. Isocenter at the body centre."""
    n_lat, o_lat = _lateral_axis(150.0, spacing_mm)
    n_depth = int(round(300.0 / spacing_mm))
    oy = -((n_depth - 1) / 2.0) * spacing_mm
    density = np.full((n_lat, n_depth, n_lat), WATER, dtype=np.float32)
    x = o_lat + np.arange(n_lat) * spacing_mm
    y = oy + np.arange(n_depth) * spacing_mm
    yy, xx = np.meshgrid(y, x, indexing="ij")          # (n_depth, n_lat)
    for cx, cy, r, rho in ((-75.0, 0.0, 45.0, LUNG), (75.0, 0.0, 45.0, LUNG), (0.0, 90.0, 15.0, BONE)):
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
        density[:, mask] = rho
    return Phantom(density, (spacing_mm,) * 3, (o_lat, oy, o_lat), "thorax_like")


def sphere_target(radius_mm: float = 16.0, half_width_mm: float = 40.0, spacing_mm: float = 2.0):
    """Water cube centred at the origin with a spherical target mask; returns
    ``(Phantom, mask_zyx)``. Used by the proton spot-placement cases."""
    n, o = _lateral_axis(half_width_mm, spacing_mm)
    density = np.full((n, n, n), WATER, dtype=np.float32)
    c = (n - 1) / 2.0
    zz, yy, xx = np.mgrid[:n, :n, :n]
    mask = ((zz - c) ** 2 + (yy - c) ** 2 + (xx - c) ** 2) * spacing_mm ** 2 <= radius_mm ** 2
    return Phantom(density, (spacing_mm,) * 3, (o, o, o), "sphere_target"), mask


__all__ = ["Phantom", "WATER", "LUNG", "BONE", "AIR", "water_box", "slab_phantom",
           "lung_slab", "bone_slab", "thorax_like", "sphere_target"]
