"""HU → relative proton stopping power from the MCsquare material database (roadmap R15).

The scanner calibration MCsquare reads has two tables: HU → mass density
(piecewise linear) and HU → material (a step function: the material whose
HU threshold is the largest not above the voxel's HU). A material's stopping
power at an energy comes from its ``G4_Stop_Pow.dat`` table in the engine's
``Materials/`` database; the relative stopping power of a voxel is
``density(HU) × S_material(E) / S_water(E)``. This is OpenTPS's
``MCsquareCTCalibration.convertHU2RSP`` (Apache-2.0), reproduced so the spot
placement of R15 ray-traces the same water-equivalent depths as before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .dose_engines.mcsquare_driver import CalibrationTables, MCsquareAssets, default_assets_dir

WATER_MATERIAL_ID = 17


@dataclass
class Material:
    number: int
    name: str
    density_g_cm3: float
    sp_energy_mev: np.ndarray
    sp_mev_cm2_g: np.ndarray

    def stopping_power(self, energy_mev: float = 100.0) -> float:
        return float(np.interp(energy_mev, self.sp_energy_mev, self.sp_mev_cm2_g))


class MaterialDatabase:
    """The engine's ``Materials/`` directory: ``list.dat`` plus one folder per material."""

    def __init__(self, materials_dir: Optional[Path] = None) -> None:
        self.root = Path(materials_dir) if materials_dir else MCsquareAssets(default_assets_dir()).materials_dir
        self._folders: Dict[int, str] = {}
        for line in (self.root / "list.dat").read_text().splitlines():
            body = line.split("#", 1)[0].strip()
            parts = body.split()
            if len(parts) >= 2 and parts[0].isdigit():
                self._folders[int(parts[0])] = parts[1]
        self._cache: Dict[int, Material] = {}

    def folder(self, number: int) -> Path:
        if number not in self._folders:
            raise KeyError(f"material {number} is not in {self.root / 'list.dat'}")
        return self.root / self._folders[number]

    def load(self, number: int) -> Material:
        if number in self._cache:
            return self._cache[number]
        folder = self.folder(number)
        density = 0.0
        name = self._folders[number]
        for line in (folder / "Material_Properties.dat").read_text().splitlines():
            parts = line.split()
            if not parts or parts[0] == "#":
                continue
            if re.search(r"Name", line) and parts[0] != "#":
                name = parts[1]
            elif re.search(r"Electron_Density", line):
                continue
            elif re.search(r"Density", line):
                density = float(parts[1])
        table = np.loadtxt(folder / "G4_Stop_Pow.dat")
        mat = Material(number, name, density, table[:, 0].astype(float), table[:, 1].astype(float))
        self._cache[number] = mat
        return mat


def hu_to_mass_density(table: np.ndarray, hu) -> np.ndarray:
    """Piecewise-linear HU → mass density (g/cm³) from an ``(HU, density)`` table,
    linearly extrapolated beyond its ends and clipped at zero (the engine's rule)."""
    table = np.asarray(table, dtype=np.float64)
    xp, fp = table[:, 0], table[:, 1]
    hu_arr = np.asarray(hu, dtype=np.float64)
    flat = hu_arr.ravel()
    density = np.interp(flat, xp, fp)
    below = flat < xp[0]
    if np.any(below):
        slope = (fp[1] - fp[0]) / (xp[1] - xp[0])
        density[below] = fp[0] + slope * (flat[below] - xp[0])
    above = flat > xp[-1]
    if np.any(above):
        slope = (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
        density[above] = fp[-1] + slope * (flat[above] - xp[-1])
    density[density < 0] = 0
    return density.reshape(hu_arr.shape)


class HUToRSP:
    """HU → mass density, material stopping power and relative stopping power."""

    def __init__(self, calibration: CalibrationTables, materials: Optional[MaterialDatabase] = None) -> None:
        self.calibration = calibration
        self.materials = materials or MaterialDatabase()
        self._density_table = np.asarray(calibration.density_table(), dtype=np.float64)
        self._hu_material: List[float] = []
        self._material: List[Material] = []
        for line in calibration.material_text.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0] == "#":
                continue
            self._hu_material.append(float(parts[0]))
            self._material.append(self.materials.load(int(parts[1])))
        if not self._material:
            raise ValueError("HU → material table is empty")

    # ----- mass density (piecewise linear with linear extrapolation) -----

    def mass_density(self, hu) -> np.ndarray:
        return hu_to_mass_density(self._density_table, hu)

    # ----- material stopping power (step function on the HU thresholds) -----

    def material_stopping_power(self, hu, energy_mev: float = 100.0) -> np.ndarray:
        hu_arr = np.asarray(hu, dtype=np.float64)
        sp_ref = np.array([m.stopping_power(energy_mev) for m in self._material])
        thresholds = np.asarray(self._hu_material, dtype=np.float64)
        # the material whose threshold is the largest not above HU; HU below every threshold → the first
        idx = np.searchsorted(thresholds, hu_arr.ravel(), side="right") - 1
        idx[idx < 0] = 0
        return sp_ref[idx].reshape(hu_arr.shape)

    def water_stopping_power(self, energy_mev: float = 100.0) -> float:
        return self.materials.load(WATER_MATERIAL_ID).stopping_power(energy_mev)

    def rsp(self, hu, energy_mev: float = 100.0) -> np.ndarray:
        return self.mass_density(hu) * self.material_stopping_power(hu, energy_mev) / self.water_stopping_power(energy_mev)


__all__ = ["WATER_MATERIAL_ID", "Material", "MaterialDatabase", "hu_to_mass_density", "HUToRSP"]
