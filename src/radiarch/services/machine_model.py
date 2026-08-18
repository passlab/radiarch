"""Pluggable equipment-specific calibration data.

The Beam Model Service needs equipment configuration to turn beam-set
specifications into deliverable plans:

* For protons, that's the Beam Data Library (BDL) — a per-machine,
  per-energy calibration table — plus the HU→density / HU→stopping-power
  CT calibration. Today these are loaded inline by ``_helpers.load_bdl``
  and ``_helpers.setup_calibration``; this module replaces that with a
  pluggable abstraction.
* For photons, that's the MLC leaf width, jaw extents, and beam quality.
  Today these are hard-coded inside ``photon_ccc.py``; this module
  extracts them.

Both are lazy-loaded — instantiating a ``ProtonMachineModel`` does no
disk I/O until you access ``.bdl`` or ``.calibration``.

Custom machine models (different LINAC, different proton system) load
from ``{settings.opentps_beam_library}/{machine_model_id}/`` if that
directory exists. ``machine_model_id=None`` means "use project default."
"""

from __future__ import annotations

import abc
import os
from typing import Any, Optional

from loguru import logger

from ..config import get_settings
from ..models.beam_model import Modality


class MachineModelError(RuntimeError):
    """Raised when a machine model cannot be loaded (missing files,
    unknown id, etc.)."""


# ---------------------------------------------------------------------------
# Default file-path resolution (proton)
# ---------------------------------------------------------------------------

def _default_mcsquare_path() -> str:
    """Path to the vendored MCsquare module — base for BDL + calibration."""
    import opentps.core.processing.doseCalculation.protons.MCsquare as MCsquareModule
    return str(MCsquareModule.__path__[0])


def _default_bdl_path() -> str:
    return os.path.join(
        _default_mcsquare_path(),
        "BDL",
        "BDL_default_DN_RangeShifter.txt",
    )


def _default_scanner_dir() -> str:
    return os.path.join(_default_mcsquare_path(), "Scanners", "UCL_Toshiba")


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class MachineModelBase(abc.ABC):
    """Common interface — every machine model knows its modality and id."""

    #: Symbolic id used to look this model up; "default" for the project default.
    machine_model_id: str

    @property
    @abc.abstractmethod
    def modality(self) -> Modality: ...


# ---------------------------------------------------------------------------
# Proton machine model
# ---------------------------------------------------------------------------

class ProtonMachineModel(MachineModelBase):
    """BDL + MCsquare CT calibration for a proton therapy system.

    Wraps the vendored OpenTPS data files. Properties are loaded lazily
    so constructing the object is cheap (good for cache-key hashing
    where we don't want to touch disk).
    """

    def __init__(
        self,
        machine_model_id: str = "default",
        *,
        bdl_path: Optional[str] = None,
        scanner_dir: Optional[str] = None,
    ) -> None:
        self.machine_model_id = machine_model_id
        self._bdl_path = bdl_path
        self._scanner_dir = scanner_dir
        # Lazy caches.
        self._bdl: Any = None
        self._calibration: Any = None

    @property
    def modality(self) -> Modality:
        return Modality.proton_pbs

    # ---- Classmethod constructors ------------------------------------

    @classmethod
    def from_default(cls) -> "ProtonMachineModel":
        """The project default — vendored BDL + UCL_Toshiba calibration."""
        return cls(
            machine_model_id="default",
            bdl_path=_default_bdl_path(),
            scanner_dir=_default_scanner_dir(),
        )

    @classmethod
    def from_id(cls, machine_model_id: str) -> "ProtonMachineModel":
        """Load a custom machine model from the configured beam library.

        Looks for ``{opentps_beam_library}/{id}/BDL.txt`` and
        ``{opentps_beam_library}/{id}/Scanner/`` — falls back to the
        default if those don't exist (with a logged warning).
        """
        settings = get_settings()
        base = os.path.join(settings.opentps_beam_library, machine_model_id)
        bdl = os.path.join(base, "BDL.txt")
        scanner = os.path.join(base, "Scanner")
        if not os.path.isfile(bdl):
            raise MachineModelError(
                f"Proton machine model {machine_model_id!r} not found at {base}"
            )
        return cls(
            machine_model_id=machine_model_id,
            bdl_path=bdl,
            scanner_dir=scanner,
        )

    # ---- Lazy properties ---------------------------------------------

    @property
    def bdl_path(self) -> str:
        return self._bdl_path or _default_bdl_path()

    @property
    def scanner_dir(self) -> str:
        return self._scanner_dir or _default_scanner_dir()

    @property
    def bdl(self) -> Any:
        """Loaded ``BDL`` object (an OpenTPS BeamModel instance)."""
        if self._bdl is None:
            from opentps.core.io import mcsquareIO  # lazy
            path = self.bdl_path
            if not os.path.isfile(path):
                raise MachineModelError(f"BDL file not found: {path}")
            self._bdl = mcsquareIO.readBDL(path)
        return self._bdl

    @property
    def calibration(self) -> Any:
        """Loaded ``MCsquareCTCalibration``."""
        if self._calibration is None:
            from opentps.core.data.CTCalibrations.MCsquareCalibration._mcsquareCTCalibration import (
                MCsquareCTCalibration,
            )
            scanner = self.scanner_dir
            mcsquare_path = _default_mcsquare_path()
            self._calibration = MCsquareCTCalibration.fromFiles(
                huDensityFile=os.path.join(scanner, "HU_Density_Conversion.txt"),
                huMaterialFile=os.path.join(scanner, "HU_Material_Conversion.txt"),
                materialsPath=os.path.join(mcsquare_path, "Materials"),
            )
        return self._calibration

    @property
    def mcsquare_path(self) -> str:
        return _default_mcsquare_path()

    @property
    def energy_range_mev(self) -> tuple:
        """(min, max) proton energy in MeV for this BDL.

        Walks the loaded BDL's energy entries. Falls back to the
        clinical-default range if the BDL doesn't expose energies in a
        way we can introspect.
        """
        try:
            energies = [layer.NominalEnergy for layer in self.bdl.layers]
            return (float(min(energies)), float(max(energies)))
        except (AttributeError, ValueError):
            # Conservative default for pencil-beam scanning systems.
            return (70.0, 230.0)


# ---------------------------------------------------------------------------
# Photon machine model
# ---------------------------------------------------------------------------

class PhotonMachineModel(MachineModelBase):
    """MLC + jaw + beam-quality config for a photon LINAC."""

    def __init__(
        self,
        machine_model_id: str = "default",
        *,
        mlc_leaf_width_mm: float = 10.0,
        max_jaw_opening_mm: float = 200.0,
        beam_quality_mv: float = 6.0,
    ) -> None:
        self.machine_model_id = machine_model_id
        self.mlc_leaf_width_mm = mlc_leaf_width_mm
        self.max_jaw_opening_mm = max_jaw_opening_mm
        self.beam_quality_mv = beam_quality_mv

    @property
    def modality(self) -> Modality:
        return Modality.photon_imrt

    @classmethod
    def from_default(cls) -> "PhotonMachineModel":
        """The project default — Varian-class 6 MV LINAC, 10 mm MLC."""
        return cls(machine_model_id="default")

    @classmethod
    def from_id(cls, machine_model_id: str) -> "PhotonMachineModel":
        """Load a custom photon machine config.

        v1: only "default" is recognized (the spec leaves photon machine
        configs as a future enhancement). Unknown ids raise rather than
        falling back silently.
        """
        if machine_model_id == "default":
            return cls.from_default()
        raise MachineModelError(
            f"Photon machine model {machine_model_id!r} not found. "
            "Only 'default' is recognized in v1."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_machine_model(
    modality: Modality,
    machine_model_id: Optional[str] = None,
) -> MachineModelBase:
    """Resolve a machine model instance for ``modality``.

    ``machine_model_id=None`` (or "default") returns the project default.
    Any other id is looked up in the beam library; missing ids raise
    :class:`MachineModelError` so the caller can surface a clean 404.
    """
    if modality is Modality.proton_pbs:
        if machine_model_id in (None, "default"):
            return ProtonMachineModel.from_default()
        return ProtonMachineModel.from_id(machine_model_id)
    if modality is Modality.photon_imrt:
        if machine_model_id in (None, "default"):
            return PhotonMachineModel.from_default()
        return PhotonMachineModel.from_id(machine_model_id)
    raise MachineModelError(f"Unsupported modality: {modality!r}")


__all__ = [
    "MachineModelBase",
    "MachineModelError",
    "PhotonMachineModel",
    "ProtonMachineModel",
    "get_machine_model",
]
