"""Pluggable Hounsfield-unit → mass-density models.

Three models behind a common ``HUToDensity`` interface:

* :class:`SchneiderModel` — piecewise-linear Schneider-2000 calibration,
  the published reference for proton therapy. Four-segment piecewise-linear
  HU → ρ (g/cc):

    (-1000, 0.00121)   air
    (  -98, 0.93)      fat
    (   14, 1.03)      soft tissue
    (   23, 1.03)      muscle
    ( 2000, 2.88)      cortical bone (extrapolated)

  Values are interpolated linearly between breakpoints and clamped at
  the endpoints.

* :class:`StoichiometricModel` — the scanner's HU → mass density table of the
  MCsquare engine assets (``Scanners/<name>/HU_Density_Conversion.txt``, the
  stoichiometric calibration the proton engine itself uses), interpolated
  piecewise-linearly with linear extrapolation beyond the table.

* :class:`LinearModel` — ρ = max(0, 1 + HU/1000). Used for synthetic / test
  modes where we just need a smooth density surrogate.

Units: HU is dimensionless; density is g/cm³ (a.k.a. g/cc). Downstream dose
engines expect float32.
"""

from __future__ import annotations

import abc
from typing import Optional

import numpy as np

from ..models.geometry import HUDensityModel


class HUToDensity(abc.ABC):
    """Abstract base: HU array → density array (g/cc, float32)."""

    #: Symbolic name matching the :class:`HUDensityModel` enum value.
    name: str

    @abc.abstractmethod
    def convert(self, hu: np.ndarray) -> np.ndarray:
        """Return a float32 density array the same shape as ``hu``."""
        ...

    def __call__(self, hu: np.ndarray) -> np.ndarray:
        return self.convert(hu)


# ---------------------------------------------------------------------------
# Schneider (2000)
# ---------------------------------------------------------------------------

# Published breakpoints — (HU, density g/cc). Extended at both ends so we
# can clamp without a separate branch.
_SCHNEIDER_BREAKPOINTS = np.array(
    [
        [-1000.0, 0.00121],   # air
        [-98.0, 0.93],        # adipose / fat
        [14.0, 1.03],         # soft tissue
        [23.0, 1.03],         # muscle plateau
        [100.0, 1.065],       # connective tissue
        [400.0, 1.21],        # trabecular bone
        [1000.0, 1.60],       # low-density cortical bone
        [2000.0, 2.88],       # dense cortical bone (extrapolation cap)
    ],
    dtype=np.float64,
)


class SchneiderModel(HUToDensity):
    """Piecewise-linear HU → density per Schneider et al. 2000."""

    name = HUDensityModel.schneider.value

    def __init__(self) -> None:
        self._hu = _SCHNEIDER_BREAKPOINTS[:, 0]
        self._rho = _SCHNEIDER_BREAKPOINTS[:, 1]

    def convert(self, hu: np.ndarray) -> np.ndarray:
        rho = np.interp(hu, self._hu, self._rho).astype(np.float32, copy=False)
        # np.interp already clamps at the endpoints, but guard against
        # negative densities from upstream HU corruption.
        np.clip(rho, 0.0, None, out=rho)
        return rho


# ---------------------------------------------------------------------------
# Stoichiometric (MCsquare-backed)
# ---------------------------------------------------------------------------

class StoichiometricModel(HUToDensity):
    """HU → density via the scanner calibration of the proton engine assets.

    ``table`` is an ``(HU, density)`` array; by default the density table of
    the default machine model's scanner (``UCL_Toshiba``), read on first use so
    that callers of the Linear/Schneider variants never touch the engine
    assets.
    """

    name = HUDensityModel.stoichiometric.value

    def __init__(self, table: Optional[np.ndarray] = None) -> None:
        self._table = None if table is None else np.asarray(table, dtype=np.float64)

    def _ensure_table(self) -> np.ndarray:
        if self._table is None:
            from .machine_model import ProtonMachineModel  # lazy

            self._table = np.asarray(ProtonMachineModel.from_default().calibration.density_table(), dtype=np.float64)
        return self._table

    def convert(self, hu: np.ndarray) -> np.ndarray:
        from .proton_rsp import hu_to_mass_density  # lazy

        rho = hu_to_mass_density(self._ensure_table(), hu).astype(np.float32)
        np.clip(rho, 0.0, None, out=rho)
        return rho


# ---------------------------------------------------------------------------
# Linear (trivial surrogate)
# ---------------------------------------------------------------------------

class LinearModel(HUToDensity):
    """ρ = max(0, 1 + HU/1000). Smooth, monotone, zero deps."""

    name = HUDensityModel.linear.value

    def convert(self, hu: np.ndarray) -> np.ndarray:
        hu_arr = np.asarray(hu, dtype=np.float32)
        rho = 1.0 + hu_arr / 1000.0
        np.clip(rho, 0.0, None, out=rho)
        return rho


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_model(model: HUDensityModel | str) -> HUToDensity:
    """Return a fresh instance of the requested HU→density model.

    Accepts the enum value or the string form for convenience.
    """
    if isinstance(model, str):
        try:
            model = HUDensityModel(model)
        except ValueError as exc:
            raise ValueError(
                f"Unknown HU density model {model!r}. "
                f"Valid: {[m.value for m in HUDensityModel]}"
            ) from exc

    if model is HUDensityModel.schneider:
        return SchneiderModel()
    if model is HUDensityModel.stoichiometric:
        return StoichiometricModel()
    if model is HUDensityModel.linear:
        return LinearModel()

    # Exhaustive; mypy would flag if a new enum value is added.
    raise ValueError(f"Unhandled HU density model: {model!r}")


__all__ = [
    "HUToDensity",
    "SchneiderModel",
    "StoichiometricModel",
    "LinearModel",
    "get_model",
]
