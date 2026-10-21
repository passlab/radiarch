"""Equipment-specific calibration data.

The Beam Model Service needs equipment configuration to turn beam-set
specifications into deliverable plans:

* For protons, the beam data library (BDL: protons per MU and the optics
  per energy, range shifters) and the scanner's CT calibration (HU → mass
  density, HU → material), read from the MCsquare engine assets through the
  driver's own parsers (:mod:`radiarch.services.dose_engines.mcsquare_driver`);
  the HU → relative stopping power model on top of them is
  :class:`radiarch.services.proton_rsp.HUToRSP`.
* For photons, a :class:`radiarch.models.machine.PhotonMachineSpec`: energies
  with output calibration, the MLC (leaf boundaries, travel, speed), jaws,
  gantry and dose-rate limits, deliverability thresholds (R4). Two synthetic
  machines ship in ``radiarch/machines/``; ``default`` is ``synthetic-120``.

Both are lazy: constructing a model does no disk I/O until a table is used.

Custom machine models load from ``{settings.beam_library_dir}/{machine_model_id}/``
(protons: ``BDL.txt`` and a ``Scanner/`` directory; photons: ``machine.json``).
``machine_model_id=None`` means the project default.
"""

from __future__ import annotations

import abc
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_settings
from ..models.beam_model import Modality
from ..models.machine import PhotonMachineSpec, ProtonMachineSpec, ProtonRangeShifter

MACHINES_DIR = Path(__file__).resolve().parent.parent / "machines"
DEFAULT_PHOTON_MACHINE = "synthetic-120"


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

    @property
    def spec(self) -> ProtonMachineSpec:
        """What the beam data library says about the system (energies, protons per MU, range shifters, nozzle)."""
        bdl = self.bdl
        distances: Dict[str, Optional[float]] = {"Nozzle exit to Isocenter distance": None, "SMX to Isocenter distance": None,
                                                 "SMY to Isocenter distance": None}
        lines = [l.strip() for l in bdl.text.splitlines()]
        for key in list(distances):
            if key in lines:
                i = lines.index(key)
                for cand in lines[i + 1:i + 3]:
                    try:
                        distances[key] = float(cand)
                        break
                    except ValueError:
                        continue
        return ProtonMachineSpec(
            machine_id=self.machine_model_id, bdl_name=bdl.name,
            energies_mev=[float(e) for e in bdl.nominal_energy_mev], protons_per_mu=[float(p) for p in bdl.protons_per_mu],
            range_shifters=[ProtonRangeShifter(shifter_id=k, water_equivalent_thickness_mm=float(v)) for k, v in bdl.range_shifter_wet_mm.items()],
            nozzle_to_isocenter_mm=distances["Nozzle exit to Isocenter distance"],
            smx_to_isocenter_mm=distances["SMX to Isocenter distance"], smy_to_isocenter_mm=distances["SMY to Isocenter distance"],
        )


# ---------------------------------------------------------------------------
# Photon machine model
# ---------------------------------------------------------------------------

def builtin_photon_machines() -> Dict[str, Path]:
    """The synthetic machines shipped with radiarch: id → json path."""
    return {p.stem: p for p in sorted(MACHINES_DIR.glob("*.json"))}


def load_photon_spec(machine_model_id: str) -> PhotonMachineSpec:
    """A photon machine spec: a built-in id, or ``{beam_library_dir}/{id}/machine.json``."""
    mid = DEFAULT_PHOTON_MACHINE if machine_model_id in (None, "default") else str(machine_model_id)
    builtin = builtin_photon_machines()
    path = builtin.get(mid)
    if path is None:
        candidate = Path(get_settings().beam_library_dir) / mid / "machine.json"
        if candidate.is_file():
            path = candidate
    if path is None:
        raise MachineModelError(
            f"Photon machine model {machine_model_id!r} not found; built-in: {sorted(builtin)}, "
            f"custom: {get_settings().beam_library_dir}/<id>/machine.json"
        )
    try:
        data = json.loads(Path(path).read_text())
        spec = PhotonMachineSpec.model_validate(data)
    except Exception as exc:
        raise MachineModelError(f"invalid machine file {path}: {exc}") from exc
    return spec


class PhotonMachineModel(MachineModelBase):
    """A photon linac: its :class:`PhotonMachineSpec` plus the three legacy numbers
    (``mlc_leaf_width_mm``, ``max_jaw_opening_mm``, ``beam_quality_mv``) the open-field
    builder reads, derived from the spec unless given."""

    def __init__(
        self,
        machine_model_id: str = "default",
        *,
        spec: Optional[PhotonMachineSpec] = None,
        mlc_leaf_width_mm: Optional[float] = None,
        max_jaw_opening_mm: Optional[float] = None,
        beam_quality_mv: Optional[float] = None,
    ) -> None:
        self.machine_model_id = machine_model_id
        self._spec = spec
        self._mlc_leaf_width_mm = mlc_leaf_width_mm
        self._max_jaw_opening_mm = max_jaw_opening_mm
        self._beam_quality_mv = beam_quality_mv

    @property
    def modality(self) -> Modality:
        return Modality.photon_imrt

    @property
    def spec(self) -> PhotonMachineSpec:
        if self._spec is None:
            self._spec = load_photon_spec(self.machine_model_id)
        return self._spec

    @property
    def mlc_leaf_width_mm(self) -> float:
        """The width of the central leaves (the smallest width of the bank)."""
        if self._mlc_leaf_width_mm is not None:
            return float(self._mlc_leaf_width_mm)
        return float(min(self.spec.mlc.leaf_widths_mm))

    @property
    def max_jaw_opening_mm(self) -> float:
        """The open-field size the beam-model builder uses by default (``spec.default_field_mm``)."""
        if self._max_jaw_opening_mm is not None:
            return float(self._max_jaw_opening_mm)
        return float(self.spec.default_field_mm)

    @property
    def beam_quality_mv(self) -> float:
        if self._beam_quality_mv is not None:
            return float(self._beam_quality_mv)
        return float(self.spec.default_energy.nominal_mv)

    @classmethod
    def from_default(cls) -> "PhotonMachineModel":
        """The project default: the synthetic 120-leaf 6 MV machine."""
        return cls(machine_model_id="default")

    @classmethod
    def from_id(cls, machine_model_id: str) -> "PhotonMachineModel":
        """A built-in synthetic machine or a custom ``machine.json``; unknown ids raise."""
        if machine_model_id == "default":
            return cls.from_default()
        spec = load_photon_spec(machine_model_id)     # raises MachineModelError when unknown
        return cls(machine_model_id=machine_model_id, spec=spec)


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


__all__ = ["MachineModelBase", "MachineModelError", "PhotonMachineModel", "ProtonMachineModel", "get_machine_model",
           "builtin_photon_machines", "load_photon_spec", "DEFAULT_PHOTON_MACHINE"]
