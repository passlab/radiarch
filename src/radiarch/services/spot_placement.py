"""Proton pencil-beam-scanning spot placement (roadmap R15).

For each beam a hexagonal spot grid (5 mm default, 400 mm field of view) is
laid out in the beam's-eye view at the isocenter, rotated into the patient
frame (gantry about z, couch about y), pushed back to the CT border and
ray-marched through the relative-stopping-power image until it enters the
target dilated by the margin. A spot that never reaches the target is
dropped. The remaining spots are marched on through the target; every time
the water-equivalent depth crosses a layer boundary (``min WET + k × layer
spacing``) inside the target a layer at that depth is recorded. One
proximal and one distal layer are added per spot by default, layer depths
become energies with the Grevillot range–energy fit, spots within 0.05 MeV
join one layer and the layers are sorted by decreasing energy.

This is the algorithm of OpenTPS 3.0.1 (``BeamInitializer`` and
``libRayTracing.c``, Apache-2.0), reproduced including its single-precision
marching, so that beam models built before R15 rebuild identically
(``tests/golden/proton_spots_simplefantom.json``). The marching is
vectorized over spots; the arithmetic follows the C code step for step.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import SimpleITK as sitk
from loguru import logger
from scipy import ndimage

from ..models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot, RangeShifterSetting

FIELD_OF_VIEW_MM = 400.0          # the largest field of a PBS nozzle (30 × 40 cm)
LAYER_ENERGY_TOLERANCE_MEV = 0.05
MAX_RANGE_MM = 550.0


# ---------------------------------------------------------------------------
# Range ↔ energy (Grevillot et al. 2010, 2011; fits to NIST/ICRU)
# ---------------------------------------------------------------------------

def range_to_energy_mev(r80_cm: float) -> float:
    """Water-equivalent range (r80, cm) → nominal energy (MeV)."""
    if r80_cm <= 0.0:
        return 0.0
    lr = math.log(r80_cm)
    return math.exp(3.464048 + 0.561372013 * lr - 0.004900892 * lr * lr + 0.001684756748 * lr * lr * lr)


def energy_to_range_cm(energy_mev: float) -> float:
    """Nominal energy (MeV) → water-equivalent range (r80, cm)."""
    if energy_mev <= 0.0:
        return 0.0
    le = math.log(energy_mev)
    return math.exp(-5.5064 + 1.2193 * le + 0.15248 * le * le - 0.013296 * le * le * le)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class BeamGeometry:
    beam_id: str
    gantry_deg: float
    couch_deg: float = 0.0
    name: str = ""
    range_shifter_id: Optional[str] = None
    range_shifter_wet_mm: float = 0.0


@dataclass
class PlacementParams:
    spot_spacing_mm: float = 5.0
    layer_spacing_mm: float = 5.0
    target_margin_mm: float = 5.0
    proximal_layers: int = 1
    distal_layers: int = 1
    layers_to_spacing_alignment: bool = False


def rotate(vec: Sequence[float], angle_rad: float, axis: str) -> List[float]:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    x, y, z = vec
    if axis == "x":
        return [x, y * c - z * s, y * s + z * c]
    if axis == "y":
        return [x * c + z * s, y, -x * s + z * c]
    if axis == "z":
        return [x * c - y * s, x * s + y * c, z]
    raise ValueError(axis)


def beam_direction(gantry_deg: float, couch_deg: float) -> List[float]:
    """Unit direction of travel of the protons in the patient frame."""
    d = rotate([1e-10, 1.0, 1e-10], math.radians(gantry_deg), "z")
    return rotate(d, math.radians(couch_deg), "y")


def dilate_mask(mask_xyz: np.ndarray, spacing: Sequence[float], radius_mm: float) -> np.ndarray:
    """Binary dilation by a ball of ``radius_mm`` (voxel radius rounded per axis)."""
    if radius_mm <= 0:
        return mask_xyz.astype(bool)
    radius = np.round(float(radius_mm) / np.asarray(spacing, dtype=float)).astype(int).tolist()
    if all(r <= 0 for r in radius):
        return mask_xyz.astype(bool)
    img = sitk.GetImageFromArray(np.swapaxes(mask_xyz.astype(np.uint8), 0, 2))
    f = sitk.BinaryDilateImageFilter()
    f.SetKernelType(sitk.sitkBall)
    f.SetBackgroundValue(0)
    f.SetKernelRadius([max(0, r) for r in radius])
    out = sitk.GetArrayFromImage(f.Execute(img))
    return np.swapaxes(out, 0, 2).astype(bool)


def center_of_mass_mm(mask_xyz: np.ndarray, origin: Sequence[float], spacing: Sequence[float]) -> np.ndarray:
    com = np.array(ndimage.center_of_mass(mask_xyz))
    return com * np.asarray(spacing, dtype=float) + np.asarray(origin, dtype=float)


# ---------------------------------------------------------------------------
# Ray marching (single precision, as the engine's C library did it)
# ---------------------------------------------------------------------------

_F32 = np.float32


_TINY_DIRECTION = 1e-6


def _next_boundary_distance(p: np.ndarray, off: np.float32, sp: np.float32, d: np.float32) -> np.ndarray:
    """|((floor((p-off)/sp) + (d>0)) * sp + off - p) / d| with the C code's mixed precision.

    A direction component below ``_TINY_DIRECTION`` is treated as zero: the
    beam does not travel along that axis, so no boundary is ahead on it. The
    C code kept the ``1e-10`` placeholder components, and for a negative one
    a spot sitting on a voxel boundary was always "at" its next boundary: it
    crawled through the image in 1 µm steps (a posterior beam on a 1 mm grid
    took 200 000 steps per spot). Single-precision accumulation over so many
    tiny steps is what those spots' depths differed by; nothing else changes.
    """
    if abs(float(d)) < _TINY_DIRECTION:
        return np.full(p.shape[0], np.inf, dtype=_F32)
    q = np.floor((p - off) / sp).astype(np.float64)
    val = ((q + (1.0 if d > 0 else 0.0)) * np.float64(sp) + np.float64(off) - p.astype(np.float64)) / np.float64(d)
    return np.abs(val).astype(_F32)


def _step(p: np.ndarray, off: np.ndarray, sp: np.ndarray, d: np.ndarray) -> np.ndarray:
    dist = [_next_boundary_distance(p[:, a], off[a], sp[a], d[a]) for a in range(3)]
    m = np.minimum(np.minimum(dist[0], dist[1]), dist[2]).astype(np.float64)
    return (m + 1e-3).astype(_F32)


def _flat_index(p: np.ndarray, off: np.ndarray, sp: np.ndarray, grid: np.ndarray) -> np.ndarray:
    ids = np.floor((p - off[None, :]) / sp[None, :]).astype(np.int64)
    return ids[:, 2] + int(grid[2]) * (ids[:, 1] + int(grid[1]) * ids[:, 0])


def _exited(p: np.ndarray, borders: np.ndarray, d: np.ndarray) -> np.ndarray:
    out = np.zeros(p.shape[0], dtype=bool)
    for a in range(3):
        if d[a] < 0:
            out |= p[:, a] < borders[0, a]
        elif d[a] > 0:
            out |= p[:, a] > borders[1, a]
    return out


def march_to_target(rsp_flat: np.ndarray, mask_flat: np.ndarray, off: np.ndarray, sp: np.ndarray, grid: np.ndarray,
                    positions: np.ndarray, direction: np.ndarray, max_iter: int = 1_000_000) -> Tuple[np.ndarray, np.ndarray]:
    """Move every spot along ``direction`` until it enters the target.

    Returns the positions where the spots stopped and their water-equivalent
    depth; a depth of -1 marks a spot that left the image without reaching
    the target.
    """
    n_vox = int(np.prod(grid))
    borders = np.stack([off, off + grid.astype(_F32) * sp]).astype(_F32)
    p = np.ascontiguousarray(positions, dtype=_F32).copy()
    wet = np.zeros(p.shape[0], dtype=_F32)
    active = np.ones(p.shape[0], dtype=bool)
    for _ in range(max_iter):
        idx = np.flatnonzero(active)
        if idx.size == 0:
            break
        pa = p[idx]
        gone = _exited(pa, borders, direction)
        wet[idx[gone]] = -1.0
        active[idx[gone]] = False
        idx, pa = idx[~gone], pa[~gone]
        if idx.size == 0:
            continue
        flat = _flat_index(pa, off, sp, grid)
        valid = (flat > 0) & (flat < n_vox)
        hit = np.zeros(idx.size, dtype=bool)
        hit[valid] = mask_flat[flat[valid]]
        active[idx[hit]] = False
        move = ~hit
        idx, pa, flat, valid = idx[move], pa[move], flat[move], valid[move]
        if idx.size == 0:
            continue
        step = _step(pa, off, sp, direction)
        spr = np.full(idx.size, _F32(0.001), dtype=_F32)
        spr[valid] = rsp_flat[flat[valid]]
        wet[idx] += spr * step
        p[idx] = pa + step[:, None] * direction[None, :]
    else:
        raise RuntimeError("spot marching did not terminate")
    return p, wet


def march_inside_target(rsp_flat: np.ndarray, mask_flat: np.ndarray, off: np.ndarray, sp: np.ndarray, grid: np.ndarray,
                        positions: np.ndarray, wet: np.ndarray, direction: np.ndarray, min_wet: np.float32,
                        layer_spacing: np.float32, max_iter: int = 1_000_000) -> List[List[np.float32]]:
    """Continue every spot through the target, recording the layer depths it crosses inside it."""
    n_vox = int(np.prod(grid))
    borders = np.stack([off, off + grid.astype(_F32) * sp]).astype(_F32)
    p = np.ascontiguousarray(positions, dtype=_F32).copy()
    w = np.ascontiguousarray(wet, dtype=_F32).copy()
    n = p.shape[0]
    num_layer = np.ceil((w - min_wet) / layer_spacing).astype(np.int64)
    layer_wet = (min_wet + num_layer.astype(_F32) * layer_spacing).astype(_F32)
    layers: List[List[np.float32]] = [[] for _ in range(n)]
    active = np.ones(n, dtype=bool)
    for _ in range(max_iter):
        idx = np.flatnonzero(active)
        if idx.size == 0:
            break
        pa = p[idx]
        gone = _exited(pa, borders, direction)
        active[idx[gone]] = False
        idx, pa = idx[~gone], pa[~gone]
        if idx.size == 0:
            break
        flat = _flat_index(pa, off, sp, grid)
        valid = (flat >= 0) & (flat < n_vox)
        active[idx[~valid]] = False
        idx, pa, flat = idx[valid], pa[valid], flat[valid]
        if idx.size == 0:
            break
        crossed = w[idx] >= layer_wet[idx]
        if np.any(crossed):
            c_idx = idx[crossed]
            inside = mask_flat[flat[crossed]]
            for i, ok in zip(c_idx[inside], inside[inside]):
                layers[int(i)].append(layer_wet[int(i)])
            num_layer[c_idx] += 1
            layer_wet[c_idx] = (min_wet + num_layer[c_idx].astype(_F32) * layer_spacing).astype(_F32)
        step = np.minimum(_step(pa, off, sp, direction), layer_spacing).astype(_F32)
        spr = rsp_flat[flat]
        w[idx] += spr * step
        p[idx] = pa + step[:, None] * direction[None, :]
    else:
        raise RuntimeError("spot marching did not terminate")
    return layers


# ---------------------------------------------------------------------------
# Spot grid
# ---------------------------------------------------------------------------

def hexagonal_spot_grid(spot_spacing: float, isocenter: Sequence[float], gantry_deg: float, couch_deg: float,
                        fov_mm: float = FIELD_OF_VIEW_MM) -> Tuple[np.ndarray, np.ndarray]:
    """BEV (x, y) and patient-frame (x, y, z) positions of the hexagonal grid at the isocenter."""
    n_x = math.ceil(fov_mm / spot_spacing)
    n_y = math.ceil(fov_mm / (spot_spacing * math.cos(math.pi / 6)))
    half_x, half_y = round(n_x / 2), round(n_y / 2)
    g, c = math.radians(gantry_deg), math.radians(couch_deg)
    bev = np.zeros((n_x * n_y, 2), dtype=np.float64)
    xyz = np.zeros((n_x * n_y, 3), dtype=np.float64)
    k = 0
    for i in range(n_x):
        for j in range(n_y):
            bx = (i - half_x + (j % 2) * 0.5) * spot_spacing
            by = (j - half_y) * spot_spacing * math.cos(math.pi / 6)
            v = rotate([bx, 0.0, by], g, "z")
            v = rotate(v, c, "y")
            bev[k] = (bx, by)
            xyz[k] = (v[0] + isocenter[0], v[1] + isocenter[1], v[2] + isocenter[2])
            k += 1
    return bev, xyz


def push_to_border(xyz: np.ndarray, direction: Sequence[float], origin: np.ndarray, grid: np.ndarray, spacing: np.ndarray) -> np.ndarray:
    """Translate every spot back along the beam to the CT border (double precision, as before)."""
    borders = np.stack([origin, origin + grid * spacing])          # (2, 3) float64
    out = xyz.copy()
    for s in range(xyz.shape[0]):
        t = np.array([(xyz[s, a] - borders[int(direction[a] < 0), a]) / direction[a] for a in range(3)])
        t = t.min()
        out[s] = xyz[s] - t * np.asarray(direction)
    return out


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------

def place_beam(rsp_xyz: np.ndarray, target_xyz: np.ndarray, origin: Sequence[float], spacing: Sequence[float],
               beam: BeamGeometry, isocenter: Sequence[float], params: PlacementParams) -> ProtonBeam:
    origin64 = np.asarray(origin, dtype=np.float64)
    spacing64 = np.asarray(spacing, dtype=np.float64)
    grid = np.asarray(rsp_xyz.shape, dtype=np.int32)
    off32, sp32 = origin64.astype(_F32), spacing64.astype(_F32)
    rsp_flat = np.ascontiguousarray(rsp_xyz, dtype=_F32).ravel()
    mask_flat = np.ascontiguousarray(target_xyz, dtype=bool).ravel()

    bev, xyz = hexagonal_spot_grid(params.spot_spacing_mm, isocenter, beam.gantry_deg, beam.couch_deg)
    direction = beam_direction(beam.gantry_deg, beam.couch_deg)
    xyz = push_to_border(xyz, direction, origin64, grid.astype(np.float64), spacing64)
    d32 = np.asarray(direction, dtype=_F32)

    positions, wet = march_to_target(rsp_flat, mask_flat, off32, sp32, grid, xyz.astype(_F32), d32)
    reached = wet >= 0
    bev, positions, wet = bev[reached], positions[reached], wet[reached]
    if bev.shape[0] == 0:
        logger.warning("beam {}: no spot reaches the target", beam.beam_id)
        return ProtonBeam(beam_id=beam.beam_id, name=beam.name, gantry_deg=beam.gantry_deg, couch_deg=beam.couch_deg,
                          isocenter_mm=tuple(float(v) for v in isocenter), range_shifter_id=beam.range_shifter_id)

    wet64 = wet.astype(np.float64)
    min_wet = 9999999.0
    for s in range(wet64.shape[0]):
        if beam.range_shifter_wet_mm > 0.0:
            wet64[s] += beam.range_shifter_wet_mm
        if wet64[s] < min_wet:
            min_wet = wet64[s]
        if params.layers_to_spacing_alignment:
            min_wet = round(min_wet / params.layer_spacing_mm) * params.layer_spacing_mm
    depth_layers = march_inside_target(rsp_flat, mask_flat, off32, sp32, grid, positions, wet64.astype(_F32), d32,
                                       _F32(min_wet), _F32(params.layer_spacing_mm))

    layers: List[ProtonLayer] = []
    layer_energies: List[float] = []
    ls = float(params.layer_spacing_mm)
    for s in range(bev.shape[0]):
        energies = [range_to_energy_mev(float(d / _F32(10))) for d in depth_layers[s]]
        if not energies:
            continue
        if params.proximal_layers > 0:
            w = energy_to_range_cm(min(energies)) * 10
            for _ in range(params.proximal_layers):
                w -= ls
                energies.append(range_to_energy_mev(w / 10))
        if params.distal_layers > 0:
            w = energy_to_range_cm(max(energies)) * 10
            for _ in range(params.distal_layers):
                w += ls
                energies.append(range_to_energy_mev(w / 10))
        for energy in energies:
            if energy <= 0:
                continue
            spot = ProtonSpot(x_mm=float(bev[s, 0]), y_mm=float(bev[s, 1]), mu=1.0)
            found = False
            for layer, e in zip(layers, layer_energies):
                if abs(e - energy) < LAYER_ENERGY_TOLERANCE_MEV:
                    layer.spots.append(spot.model_copy())
                    found = True
            if not found:
                rs = None
                if beam.range_shifter_wet_mm > 0.0:
                    rs = RangeShifterSetting(setting="IN", isocenter_to_range_shifter_mm=300.0,
                                             water_equivalent_thickness_mm=beam.range_shifter_wet_mm)
                layers.append(ProtonLayer(energy_mev=energy, spots=[spot], range_shifter=rs))
                layer_energies.append(energy)
    order = np.argsort(layer_energies)[::-1]
    layers = [layers[i] for i in order]
    return ProtonBeam(beam_id=beam.beam_id, name=beam.name, gantry_deg=beam.gantry_deg, couch_deg=beam.couch_deg,
                      isocenter_mm=tuple(float(v) for v in isocenter), range_shifter_id=beam.range_shifter_id, layers=layers)


def place_spots(rsp_xyz: np.ndarray, target_xyz: np.ndarray, origin: Sequence[float], spacing: Sequence[float],
                beams: Sequence[BeamGeometry], params: Optional[PlacementParams] = None,
                isocenter_mm: Optional[Sequence[float]] = None, name: str = "ProtonPlan") -> ProtonPlan:
    """Build a plan with unit-weight spots on ``target_xyz`` for every beam.

    ``rsp_xyz`` is the relative stopping power at 100 MeV and ``target_xyz``
    the target mask, both ``(x, y, z)`` on the same grid. The isocenter is
    the target's centre of mass unless given; the target is dilated by the
    margin before the spots are placed.
    """
    params = params or PlacementParams()
    target_xyz = np.asarray(target_xyz, dtype=bool)
    if not target_xyz.any():
        raise ValueError("the target mask is empty")
    iso = np.asarray(isocenter_mm, dtype=np.float64) if isocenter_mm is not None else center_of_mass_mm(target_xyz, origin, spacing)
    dilated = dilate_mask(target_xyz, spacing, params.target_margin_mm)
    plan_beams = [place_beam(rsp_xyz, dilated, origin, spacing, b, iso, params) for b in beams]
    n = sum(b.n_spots for b in plan_beams)
    logger.info("placed {} spots in {} beams ({} layers)", n, len(plan_beams), sum(len(b.layers) for b in plan_beams))
    return ProtonPlan(name=name, beams=plan_beams)


__all__ = ["BeamGeometry", "PlacementParams", "FIELD_OF_VIEW_MM", "range_to_energy_mev", "energy_to_range_cm",
           "beam_direction", "dilate_mask", "center_of_mass_mm", "hexagonal_spot_grid", "push_to_border",
           "march_to_target", "march_inside_target", "place_beam", "place_spots"]
