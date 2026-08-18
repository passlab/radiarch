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

* :class:`StoichiometricModel` — wraps the vendored MCsquare CT calibration
  (``opentps.core.data.CTCalibrations.MCsquareCalibration``). The MCsquare
  calibration is the gold-standard for proton dose in this project; this
  model delegates to it for density lookup.

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
    """HU → density via the vendored MCsquare CT calibration.

    The MCsquare calibration stores an HU→density table derived from tissue
    stoichiometry. We defer the actual math to OpenTPS's
    ``MCsquareCTCalibration.convertHU2MassDensity``; this class is a thin,
    cache-friendly adapter so the rest of the service stays decoupled from
    OpenTPS internals.

    Constructed lazily: loading the calibration pulls in the vendored
    MCsquare package, which we don't want to import at module-load time
    when callers only need the Linear/Schneider variants.
    """

    name = HUDensityModel.stoichiometric.value

    def __init__(self, calibration: Optional[object] = None) -> None:
        # ``calibration`` is an MCsquareCTCalibration; typed loosely to
        # avoid importing opentps here. Loaded on demand if not supplied.
        self._calibration = calibration

    def _ensure_calibration(self):
        if self._calibration is None:
            # Deferred import — keeps module-load cheap and lets us unit-test
            # Schneider/Linear without the opentps tree on sys.path.
            from ..core.workflows._helpers import setup_calibration

            calibration, _ = setup_calibration()
            self._calibration = calibration
        return self._calibration

    def convert(self, hu: np.ndarray) -> np.ndarray:
        cal = self._ensure_calibration()
        # MCsquareCTCalibration.convertHU2MassDensity accepts either a
        # scalar or an array; returns the same shape.
        rho = np.asarray(cal.convertHU2MassDensity(hu), dtype=np.float32)
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
