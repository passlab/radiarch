"""Equipment-specific calibration data.

The Beam Model Service needs equipment configuration to turn beam-set
specifications into deliverable plans:

* For protons, the beam data library (BDL: protons per MU and the optics
  per energy, range shifters) and the scanner's CT calibration (HU → mass
  density, HU → material), read from the MCsquare engine assets through the
  driver's own parsers (:mod:`radiarch.services.dose_engines.mcsquare_driver`);
  the HU → relative stopping power model on top of them is
  :class:`radiarch.services.proton_rsp.HUToRSP`.
* For photons, the MLC leaf width, jaw extents and beam quality.

Both are lazy: constructing a model does no disk I/O until a table is used.

Custom machine models load from ``{settings.beam_library_dir}/{machine_model_id}/``
(``BDL.txt`` and a ``Scanner/`` directory). ``machine_model_id=None`` means
the project default: the engine's default BDL and ``UCL_Toshiba`` scanner.
"""

from __future__ import annotations

import abc
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from ..config import get_settings
from ..models.beam_model import Modality


class MachineModelError(RuntimeError):
    """Raised when a machine model cannot be loaded (missing files, unknown id, etc.)."""


class MachineModelBase(abc.ABC):
    """Common interface — every machine model knows its modality and id."""

    machine_model_id: str

    @property
    @abc.abstractmethod
    def modality(self) -> Modality: ...


# ---------------------------------------------------------------------------
# Proton machine model
# ---------------------------------------------------------------------------

class ProtonMachineModel(MachineModelBase):
    """BDL + CT calibration of a proton therapy system, on the MCsquare engine assets."""

    def __init__(
        self,
        machine_model_id: str = "default",
        *,
        bdl_path: Optional[str] = None,
        scanner_dir: Optional[str] = None,
        mcsquare_dir: Optional[str] = None,
    ) -> None:
        self.machine_model_id = machine_model_id
        self._bdl_path = bdl_path
        self._scanner_dir = scanner_dir
        self._mcsquare_dir = mcsquare_dir
        self._bdl: Any = None
        self._calibration: Any = None
        self._rsp_model: Any = None

    @property
    def modality(self) -> Modality:
        return Modality.proton_pbs

    # ---- constructors ------------------------------------------------

    @classmethod
    def from_default(cls) -> "ProtonMachineModel":
        """The project default: the engine's default BDL and UCL_Toshiba scanner."""
        return cls(machine_model_id="default")

    @classmethod
    def from_id(cls, machine_model_id: str) -> "ProtonMachineModel":
        """A custom machine model from the configured beam library.

        Looks for ``{beam_library_dir}/{id}/BDL.txt`` and ``{beam_library_dir}/{id}/Scanner/``.
        """
        settings = get_settings()
        base = os.path.join(settings.beam_library_dir, machine_model_id)
        bdl = os.path.join(base, "BDL.txt")
        scanner = os.path.join(base, "Scanner")
        if not os.path.isfile(bdl):
            raise MachineModelError(f"Proton machine model {machine_model_id!r} not found at {base}")
        return cls(machine_model_id=machine_model_id, bdl_path=bdl, scanner_dir=scanner)

    # ---- paths ---------------------------------------------------------

    def _assets(self):
        from .dose_engines.mcsquare_driver import MCsquareAssets, default_assets_dir  # lazy
        return MCsquareAssets(Path(self._mcsquare_dir) if self._mcsquare_dir else default_assets_dir())

    @property
    def mcsquare_dir(self) -> str:
        return str(self._assets().root)

    @property
    def bdl_path(self) -> str:
        return self._bdl_path or str(self._assets().bdl_path())

    @property
    def scanner_dir(self) -> str:
        return self._scanner_dir or str(self._assets().scanner_dir())

    @property
    def materials_dir(self) -> str:
        return str(self._assets().materials_dir)

    # ---- tables (lazy) -------------------------------------------------

    @property
    def bdl(self):
        """The beam data library (:class:`BeamDataLibrary`)."""
        if self._bdl is None:
            from .dose_engines.mcsquare_driver import BeamDataLibrary  # lazy
            path = self.bdl_path
            if not os.path.isfile(path):
                raise MachineModelError(f"BDL file not found: {path}")
            self._bdl = BeamDataLibrary.load(Path(path))
        return self._bdl

    @property
    def calibration(self):
        """The scanner's HU → density and HU → material tables (:class:`CalibrationTables`)."""
        if self._calibration is None:
            from .dose_engines.mcsquare_driver import CalibrationTables  # lazy
            scanner = Path(self.scanner_dir)
            if not scanner.is_dir():
                raise MachineModelError(f"scanner calibration directory not found: {scanner}")
            self._calibration = CalibrationTables.from_dir(scanner)
        return self._calibration

    @property
    def rsp_model(self):
        """HU → relative proton stopping power (:class:`HUToRSP`) on the calibration and the material database."""
        if self._rsp_model is None:
            from .proton_rsp import HUToRSP, MaterialDatabase  # lazy
            self._rsp_model = HUToRSP(self.calibration, MaterialDatabase(Path(self.materials_dir)))
        return self._rsp_model

    @property
    def energy_range_mev(self) -> Tuple[float, float]:
        """(min, max) nominal energy of the BDL; a conservative PBS default if it has none."""
        try:
            energies = self.bdl.nominal_energy_mev
            if len(energies):
                return (float(energies.min()), float(energies.max()))
        except (MachineModelError, ValueError, OSError):
            pass
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
        """The project default — a 6 MV LINAC with a 10 mm MLC."""
        return cls(machine_model_id="default")

    @classmethod
    def from_id(cls, machine_model_id: str) -> "PhotonMachineModel":
        """Only "default" is recognized; unknown ids raise rather than falling back silently."""
        if machine_model_id == "default":
            return cls.from_default()
        raise MachineModelError(
            f"Photon machine model {machine_model_id!r} not found. Only 'default' is recognized in v1."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_machine_model(modality: Modality, machine_model_id: Optional[str] = None) -> MachineModelBase:
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


__all__ = ["MachineModelBase", "MachineModelError", "PhotonMachineModel", "ProtonMachineModel", "get_machine_model"]
