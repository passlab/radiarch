"""File-protocol driver for the MCsquare proton Monte Carlo engine (roadmap R14).

MCsquare (Apache-2.0, https://gitlab.com/openmcsquare/MCsquare) is a standalone
program driven entirely by files: a text configuration, the CT as an MHD
volume, HU-to-density and HU-to-material tables, a beam data library (BDL)
and a plan text file. It writes the dose as an MHD volume or, in beamlet mode,
one sparse column per spot. Radiarch never links or imports it: this module
writes those files, starts the engine as a subprocess through its own
launcher script (which picks the binary for the CPU and points the engine at
its material database) and reads the results back.

The file formats and the coordinate conventions below are a port of OpenTPS's
``mcsquareIO.py`` and ``mcsquareDoseCalculator.py`` (Apache-2.0), checked
against the inputs that copy writes (``tests/golden/mcsquare_inputs_simplefantom``).

Coordinate conventions
----------------------
Radiarch volumes are ``(z, y, x)`` C-order arrays on a grid with
``spacing_mm = (sx, sy, sz)`` and ``origin_mm = (ox, oy, oz)``, the centre of
voxel ``[0, 0, 0]`` in the patient (DICOM LPS) frame. MCsquare wants the
volume in ``(x, y, z)`` Fortran order with its ``y`` axis inverted and both
``x`` and ``y`` mirrored, and the MHD ``Offset`` at the corner of the first
voxel, so::

    written = flip(flip(transpose(volume, (2, 1, 0)), 0), 1)       # (x, y, z)
    offset  = (ox - sx/2,  -oy - sy*ny + sy/2,  oz - sz/2)

Doses come back in the same frame and are undone the same way. A beamlet
column indexes voxels in that written frame, Fortran-flattened; the
permutation :func:`native_row_permutation` turns it into radiarch's row
order. Isocenters are written in millimetres from the corner of the CT grid
with the same ``y`` inversion (:func:`isocenter_to_mcsquare`).

Units
-----
MCsquare scores energy per primary proton; multiplying by the number of
protons delivered (spot MU × protons per MU from the BDL at that energy) and
by ``1.602176e-19 J/eV × 1000 g/kg`` gives Gy, as OpenTPS does. Beamlet
columns are scaled per spot the same way at 1 MU, so ``Dij @ MU`` is Gy.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import struct
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from loguru import logger

from ...models.proton_plan import ProtonPlan

EV_PER_G_TO_GY = 1.602176e-19 * 1000.0  # eV/g per primary → Gy per proton (OpenTPS's factor)
TEMPLATE_PATH = Path(__file__).with_name("mcsquare_config_template.txt")
DEFAULT_SCANNER = "UCL_Toshiba"
DEFAULT_BDL = "BDL_default_DN_RangeShifter.txt"

Vec3 = Tuple[float, float, float]


def default_assets_dir() -> Path:
    """The MCsquare directory: binaries, launcher, Materials, BDL and Scanners.

    ``RADIARCH_MCSQUARE_DIR`` when set, else the copy vendored with OpenTPS
    core (``engines/mcsquare`` once R15 removes the vendored tree).
    """
    try:
        from ...config import get_settings
        configured = get_settings().mcsquare_dir
    except Exception:  # pragma: no cover — settings unavailable in odd test setups
        configured = ""
    if configured:
        return Path(configured)
    return engine_assets_dir("mcsquare")


def engine_assets_dir(name: str) -> Path:
    """``engines/<name>`` of the repository (``src/../engines``) or of an installed
    tree whose source root holds ``engines/`` (the container image: ``/app/engines``)."""
    here = Path(__file__).resolve()
    for root in (here.parents[4], here.parents[3]):
        candidate = root / "engines" / name
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "engines" / name


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MCsquareAssets:
    """Where the engine, its material database, beam data libraries and scanners live."""

    root: Path

    @property
    def launcher(self) -> Path:
        return self.root / "MCsquare"

    @property
    def materials_dir(self) -> Path:
        return self.root / "Materials"

    def binaries(self) -> List[Path]:
        return sorted(p for p in self.root.glob("MCsquare_linux*") if p.is_file())

    def bdl_path(self, name: str = DEFAULT_BDL) -> Path:
        p = Path(name)
        return p if p.is_absolute() else self.root / "BDL" / name

    def scanner_dir(self, name: str = DEFAULT_SCANNER) -> Path:
        p = Path(name)
        return p if p.is_absolute() else self.root / "Scanners" / name

    def availability(self) -> Tuple[bool, str]:
        if platform.system() != "Linux":
            return False, f"MCsquare binaries ship for Linux only (this is {platform.system()})"
        if not self.launcher.is_file():
            return False, f"launcher not found: {self.launcher}"
        if not any(os.access(b, os.X_OK) for b in self.binaries()):
            return False, f"no executable MCsquare_linux* binary under {self.root}"
        if not (self.materials_dir / "list.dat").is_file():
            return False, f"material database not found: {self.materials_dir}"
        if not self.bdl_path().is_file():
            return False, f"default beam data library not found: {self.bdl_path()}"
        if not self.scanner_dir().is_dir():
            return False, f"default scanner calibration not found: {self.scanner_dir()}"
        return True, "ok"

    def fingerprint(self) -> str:
        """Identifies the engine build: launcher text and the sizes and names of the binaries."""
        h = hashlib.sha256()
        if self.launcher.is_file():
            h.update(self.launcher.read_bytes())
        for b in self.binaries():
            h.update(f"{b.name}:{b.stat().st_size}".encode())
        return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Calibration tables and the beam data library
# ---------------------------------------------------------------------------

@dataclass
class CalibrationTables:
    """The two scanner files MCsquare reads: HU → mass density and HU → material id.

    Kept as text so a scanner shipped with the engine is written back verbatim;
    :meth:`scaled` rewrites the density column for density/range scenarios and
    :meth:`water` builds the water-only calibration a phantom test needs.
    """

    density_text: str
    material_text: str
    name: str = DEFAULT_SCANNER

    @classmethod
    def from_dir(cls, scanner_dir: Path) -> "CalibrationTables":
        scanner_dir = Path(scanner_dir)
        return cls(
            density_text=(scanner_dir / "HU_Density_Conversion.txt").read_text(),
            material_text=(scanner_dir / "HU_Material_Conversion.txt").read_text(),
            name=scanner_dir.name,
        )

    @classmethod
    def water(cls, density_g_cm3: float = 1.0, material_id: int = 17) -> "CalibrationTables":
        """Every HU is water: the calibration a water-phantom test must see (the
        clinical Schneider tables map HU 0 to a tissue blend 1-3 % denser in
        stopping power than water, which shortens ranges)."""
        return cls(
            density_text=f"# HU\tdensity (g/cm3): water everywhere\n-1000\t{density_g_cm3:.3f}\n0\t{density_g_cm3:.3f}\n3000\t{density_g_cm3:.3f}\n",
            material_text=f"# HU\tmaterial id: {material_id} = Water\n-1000\t{material_id}\n",
            name="water",
        )

    def density_table(self) -> np.ndarray:
        rows = []
        for line in self.density_text.splitlines():
            body = line.split("#", 1)[0].strip()
            if not body:
                continue
            parts = body.split()
            rows.append((float(parts[0]), float(parts[1])))
        return np.asarray(rows, dtype=np.float64)

    def scaled(self, density_scale: float) -> "CalibrationTables":
        """The same calibration with every mass density multiplied by ``density_scale``."""
        if density_scale == 1.0:
            return self
        out = []
        for line in self.density_text.splitlines():
            body, _, comment = line.partition("#")
            parts = body.split()
            if len(parts) >= 2:
                hu, rho = float(parts[0]), float(parts[1]) * density_scale
                line = f"{hu:g}\t{rho:.6g}" + (f"\t#{comment}" if comment else "")
            out.append(line)
        return CalibrationTables("\n".join(out) + "\n", self.material_text, f"{self.name}-x{density_scale:g}")

    def write(self, dest_dir: Path) -> Tuple[Path, Path]:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        d = dest_dir / "HU_Density_Conversion.txt"
        m = dest_dir / "HU_Material_Conversion.txt"
        d.write_text(self.density_text)
        m.write_text(self.material_text)
        return d, m


@dataclass
class BeamDataLibrary:
    """A BDL file: kept verbatim for the engine, parsed for protons per MU and range shifters."""

    text: str
    nominal_energy_mev: np.ndarray
    protons_per_mu: np.ndarray
    range_shifter_wet_mm: Dict[str, float] = field(default_factory=dict)
    name: str = DEFAULT_BDL

    @classmethod
    def load(cls, path: Path) -> "BeamDataLibrary":
        text = Path(path).read_text()
        if "--UPenn beam model (double gaussian)--" not in text.splitlines()[0] and "--Lookup table BDL format--" not in text.splitlines()[0]:
            raise ValueError(f"{path}: BDL format not supported")
        energies: List[float] = []
        protons: List[float] = []
        shifters: Dict[str, float] = {}
        columns: Optional[List[str]] = None
        current_rs: Optional[str] = None
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("RS_ID"):
                current_rs = line.split("=", 1)[1].strip()
            elif line.startswith("RS_WET") and current_rs is not None:
                shifters[current_rs] = float(line.split("=", 1)[1].strip())
            elif line.startswith("NominalEnergy"):
                columns = line.split()
            elif columns is not None:
                parts = line.split()
                if len(parts) < len(columns):
                    continue
                try:
                    row = [float(v) for v in parts[:len(columns)]]
                except ValueError:
                    continue
                energies.append(row[columns.index("NominalEnergy")])
                protons.append(row[columns.index("ProtonsMU")])
        if not energies:
            raise ValueError(f"{path}: no beam parameter table found")
        order = np.argsort(energies)
        return cls(text, np.asarray(energies)[order], np.asarray(protons)[order], shifters, Path(path).name)

    def mu_to_protons(self, energy_mev: float) -> float:
        return float(np.interp(energy_mev, self.nominal_energy_mev, self.protons_per_mu))

    def write(self, dest: Path) -> Path:
        Path(dest).write_text(self.text)
        return Path(dest)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def default_config() -> Dict[str, Any]:
    """The engine's defaults, as OpenTPS's ``MCsquareConfig`` sets them."""
    return {
        "WorkDir": None,
        "Num_Threads": 0, "RNG_Seed": 0, "Num_Primaries": 1e7,
        "E_Cut_Pro": 0.5, "D_Max": 0.2, "Epsilon_Max": 0.25, "Te_Min": 0.05,
        "CT_File": None, "ScannerDirectory": None,
        "HU_Density_Conversion_File": None, "HU_Material_Conversion_File": None,
        "BDL_Machine_Parameter_File": None, "BDL_Plan_File": None,
        "Simulate_Nuclear_Interactions": True, "Simulate_Secondary_Protons": True,
        "Simulate_Secondary_Deuterons": True, "Simulate_Secondary_Alphas": True,
        "4D_Mode": False, "4D_Dose_Accumulation": False, "Field_type": "Velocity",
        "Create_Ref_from_4DCT": False, "Create_4DCT_from_Ref": False, "Dynamic_delivery": False,
        "Breathing_period": 7.0, "CT_phases": 0,
        "Robustness_Mode": False, "Scenario_selection": "All", "Simulate_nominal_plan": True,
        "Num_Random_Scenarios": 100, "Systematic_Setup_Error": [0.25, 0.25, 0.25],
        "Random_Setup_Error": [0.1, 0.1, 0.1], "Systematic_Range_Error": 3.0,
        "Systematic_Amplitude_Error": 0, "Random_Amplitude_Error": 0,
        "Systematic_Period_Error": 0, "Random_Period_Error": 0,
        "Beamlet_Mode": False, "Beamlet_Parallelization": False, "Optimization_Mode": False,
        "Compute_stat_uncertainty": True, "Stat_uncertainty": 0, "Ignore_low_density_voxels": True,
        "Export_batch_dose": False, "Max_Num_Primaries": 0, "Max_Simulation_time": 0,
        "Output_Directory": "Outputs",
        "Energy_ASCII_Output": False, "Energy_MHD_Output": False, "Energy_Sparse_Output": False,
        "Dose_ASCII_Output": False, "Dose_MHD_Output": True, "Dose_Sparse_Output": False,
        "LET_ASCII_Output": False, "LET_MHD_Output": False, "LET_Sparse_Output": False,
        "Densities_Output": False, "Materials_Output": False, "Compute_DVH": False,
        "Dose_Sparse_Threshold": 0.0, "Energy_Sparse_Threshold": 0.0, "LET_Sparse_Threshold": 0.0,
        "Score_PromptGammas": False, "PG_LowEnergyCut": 0.0, "PG_HighEnergyCut": 50.0,
        "PG_Spectrum_NumBin": 150, "PG_Spectrum_Binning": 0.1,
        "LET_Calculation_Method": "StopPow", "Export_Beam_dose": False,
        "Dose_to_Water_conversion": "Disabled", "Dose_Segmentation": False,
        "Density_Threshold_for_Segmentation": 0.01,
        "Independent_scoring_grid": False, "Scoring_origin": [0.0, 0.0, 0.0],
        "Scoring_grid_size": [100, 100, 100], "Scoring_voxel_spacing": [0.15, 0.15, 0.15],
        "Dose_weighting_algorithm": "Volume",
    }


def render_config(values: Dict[str, Any], template_path: Path = TEMPLATE_PATH) -> str:
    """Fill the engine's configuration template exactly as OpenTPS does
    (``{KEY}`` placeholders, 3-vectors as ``a b c``, everything else ``str()``)."""
    text = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        if np.ndim(value) > 0:
            rendered = " ".join(str(v) for v in list(value)[:3])
        else:
            rendered = str(value)
        text = text.replace("{" + key.upper() + "}", rendered)
    left = sorted(set(re.findall(r"\{[A-Z0-9_]+\}", text)))
    if left:
        raise ValueError(f"MCsquare config template has unfilled placeholders: {left}")
    return text


# ---------------------------------------------------------------------------
# Grid conventions
# ---------------------------------------------------------------------------

def mcsquare_offset(origin_mm: Vec3, spacing_mm: Vec3, size_xyz: Tuple[int, int, int]) -> Vec3:
    """MHD ``Offset`` for a radiarch grid: corner of the first voxel, ``y`` inverted."""
    ox, oy, oz = (float(v) for v in origin_mm)
    sx, sy, sz = (float(v) for v in spacing_mm)
    ny = int(size_xyz[1])
    return (ox - sx / 2.0, -oy - sy * ny + sy / 2.0, oz - sz / 2.0)


def to_engine_frame(volume_zyx: np.ndarray) -> np.ndarray:
    """radiarch ``(z, y, x)`` → the ``(x, y, z)`` array MCsquare reads (x and y mirrored)."""
    arr = np.transpose(np.asarray(volume_zyx), (2, 1, 0))
    return np.flip(np.flip(arr, 0), 1)


def from_engine_frame(volume_xyz: np.ndarray) -> np.ndarray:
    """The inverse of :func:`to_engine_frame`, as a C-contiguous ``(z, y, x)`` array."""
    arr = np.flip(np.flip(np.asarray(volume_xyz), 0), 1)
    return np.ascontiguousarray(np.transpose(arr, (2, 1, 0)))


def native_row_permutation(shape_zyx: Tuple[int, int, int]) -> np.ndarray:
    """``perm`` such that ``rows_zyx = rows_native[perm]``: MCsquare's Fortran-flattened,
    mirrored voxel order → radiarch's C-order ``(z, y, x)``."""
    nz, ny, nx = (int(v) for v in shape_zyx)
    native = np.arange(nz * ny * nx, dtype=np.int64).reshape((nx, ny, nz), order="F")
    return from_engine_frame(native).ravel(order="C")


def isocenter_to_mcsquare(isocenter_mm: Vec3, origin_mm: Vec3, spacing_mm: Vec3, size_xyz: Tuple[int, int, int]) -> Vec3:
    """DICOM isocenter → MCsquare's frame: from the CT corner, ``y`` inverted (port of OpenTPS)."""
    x = isocenter_mm[0] - origin_mm[0] + spacing_mm[0] / 2.0
    y = isocenter_mm[1] - origin_mm[1] + spacing_mm[1] / 2.0
    z = isocenter_mm[2] - origin_mm[2] + spacing_mm[2] / 2.0
    y = size_xyz[1] * spacing_mm[1] - y
    return (float(x), float(y), float(z))


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

_MHD_TYPES = {"MET_FLOAT": np.float32, "MET_DOUBLE": np.float64, "MET_SHORT": np.int16,
              "MET_USHORT": np.uint16, "MET_INT": np.int32, "MET_UCHAR": np.uint8, "MET_CHAR": np.int8}


def write_ct_mhd(ct_hu_zyx: np.ndarray, spacing_mm: Vec3, origin_mm: Vec3, path: Path) -> Path:
    """Write a radiarch CT as the MHD + raw pair MCsquare reads (float32, Fortran order)."""
    path = Path(path)
    arr = to_engine_frame(np.asarray(ct_hu_zyx, dtype=np.float32))
    nx, ny, nz = arr.shape
    offset = mcsquare_offset(origin_mm, spacing_mm, (nx, ny, nz))
    raw_name = path.with_suffix(".raw").name
    header = {
        "ObjectType": "Image", "NDims": 3, "ElementNumberOfChannels": 1,
        "DimSize": (nx, ny, nz), "ElementSpacing": tuple(float(s) for s in spacing_mm),
        "Offset": tuple(float(o) for o in offset), "BinaryData": True, "CompressedData": False,
        "ElementByteOrderMSB": False, "ElementType": "MET_FLOAT", "ElementDataFile": raw_name,
    }
    with open(path, "w") as fid:
        for key, value in header.items():
            fid.write(key + " = ")
            if isinstance(value, (list, tuple)):
                for element in value:
                    fid.write(str(element) + " ")
            else:
                fid.write(str(value))
            fid.write("\n")
    with open(path.with_suffix(".raw"), "wb") as fid:
        arr.reshape(arr.size, order="F").astype("<f4", copy=False).tofile(fid)
    return path


def read_mhd(path: Path) -> Tuple[np.ndarray, Vec3, Vec3]:
    """Read an MHD volume MCsquare wrote; returns ``(volume_zyx, spacing_mm, offset)``."""
    path = Path(path)
    header: Dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            header[k.strip()] = v.strip()
    size = tuple(int(v) for v in header["DimSize"].split())
    spacing = tuple(float(v) for v in header["ElementSpacing"].split())
    offset = tuple(float(v) for v in header.get("Offset", "0 0 0").split())
    dtype = _MHD_TYPES[header.get("ElementType", "MET_FLOAT")]
    raw = np.fromfile(path.parent / header["ElementDataFile"], dtype=dtype)
    if header.get("ElementByteOrderMSB", "False") == "True":
        raw = raw.byteswap()
    if raw.size != int(np.prod(size)):
        raise ValueError(f"{path}: {raw.size} values for DimSize {size}")
    return from_engine_frame(raw.reshape(size, order="F")), spacing, offset


def write_plan_pencil(plan: ProtonPlan, path: Path, origin_mm: Vec3, spacing_mm: Vec3,
                      size_xyz: Tuple[int, int, int], bdl: Optional[BeamDataLibrary] = None) -> Path:
    """Write the plan in MCsquare's PBS text format (byte-for-byte what OpenTPS writes)."""
    path = Path(path)
    lines: List[str] = []
    w = lines.append
    w("#TREATMENT-PLAN-DESCRIPTION")
    w("#PlanName")
    w(path.stem)
    w("#NumberOfFractions")
    w("%d" % plan.n_fractions)
    w("##FractionID")
    w("1")
    w("##NumberOfFields")
    w("%d" % len(plan.beams))
    for i in range(len(plan.beams)):
        w("###FieldsID")
        w("%d" % (i + 1))
    w("#TotalMetersetWeightOfAllFields")
    w("%f" % plan.meterset)

    cumulative_fields = 0.0
    for i, beam in enumerate(plan.beams):
        cumulative = 0.0
        w("")
        w("#FIELD-DESCRIPTION")
        w("###FieldID")
        w("%d" % (i + 1))
        w("###FinalCumulativeMeterSetWeight")
        cumulative_fields += beam.meterset
        w("%f" % cumulative_fields)
        w("###GantryAngle")
        w("%f" % beam.gantry_deg)
        w("###PatientSupportAngle")
        w("%f" % beam.couch_deg)
        w("###IsocenterPosition")
        w("%f\t %f\t %f" % isocenter_to_mcsquare(beam.isocenter_mm, origin_mm, spacing_mm, size_xyz))
        if beam.range_shifter_id is not None:
            w("###RangeShifterID")
            w("%s" % beam.range_shifter_id)
            w("###RangeShifterType")
            w("binary")
        w("###NumberOfControlPoints")
        w("%d" % len(beam.layers))
        w("")
        w("#SPOTS-DESCRIPTION")
        for j, layer in enumerate(beam.layers):
            w("####ControlPointIndex")
            w("%d" % (j + 1))
            w("####SpotTunnedID")
            w("1")
            w("####CumulativeMetersetWeight")
            cumulative += layer.meterset
            w("%f" % cumulative)
            w("####Energy (MeV)")
            w("%f" % layer.energy_mev)
            if beam.range_shifter_id is not None:
                rs = layer.range_shifter
                w("####RangeShifterSetting")
                w("%s" % (rs.setting if rs is not None else "OUT"))
                w("####IsocenterToRangeShifterDistance")
                w("%f" % (rs.isocenter_to_range_shifter_mm if rs is not None else 0.0))
                w("####RangeShifterWaterEquivalentThickness")
                wet = rs.water_equivalent_thickness_mm if rs is not None else None
                if wet is None:
                    if bdl is None or beam.range_shifter_id not in bdl.range_shifter_wet_mm:
                        raise ValueError(f"range shifter {beam.range_shifter_id!r}: WET not in the plan nor in the BDL")
                    wet = bdl.range_shifter_wet_mm[beam.range_shifter_id]
                w("%f" % wet)
            w("####NbOfScannedSpots")
            w("%d" % layer.n_spots)
            w("####X Y Weight")
            with_timings = layer.has_timings
            for spot in layer.spots:
                if with_timings:
                    w("%f %f %f %f " % (spot.x_mm, spot.y_mm, spot.mu, spot.start_time_s))
                else:
                    w("%f %f %f" % (spot.x_mm, spot.y_mm, spot.mu))
    path.write_text("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def read_sparse_beamlets(header_path: Path) -> Tuple[sp.csc_matrix, Dict[str, Any]]:
    """Read MCsquare's sparse beamlet output: ``(matrix, header)`` with one column per
    spot and rows in the engine's native (Fortran, mirrored) voxel order."""
    header_path = Path(header_path)
    header: Dict[str, Any] = {"SimulationMode": []}
    for line in header_path.read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, val = (s.strip() for s in line.split("=", 1))
        if key == "NbrSpots":
            header[key] = int(val)
        elif key == "ImageSize":
            header[key] = tuple(int(v) for v in val.split())
        elif key in ("VoxelSpacing", "Offset"):
            header[key] = tuple(float(v) for v in val.split())
        elif key == "SimulationMode":
            header[key].append(val)
        elif key == "BinaryFile":
            header[key] = str(header_path.parent / val)
        else:
            header[key] = val
    if not any("Beamlet" in m for m in header["SimulationMode"]):
        raise ValueError(f"{header_path}: not a beamlet file ({header['SimulationMode']})")
    n_vox = int(np.prod(header["ImageSize"]))
    n_spots = int(header["NbrSpots"])

    buf = Path(header["BinaryFile"]).read_bytes()
    pos = 0
    rows: List[np.ndarray] = []
    cols: List[np.ndarray] = []
    vals: List[np.ndarray] = []
    spots_meta: List[Tuple[int, int, float, float]] = []
    u32 = struct.Struct("<I")
    for spot in range(n_spots):
        nonzero, beam_id, layer_id = struct.unpack_from("<III", buf, pos)
        x, y = struct.unpack_from("<ff", buf, pos + 12)
        pos += 20
        spots_meta.append((int(beam_id), int(layer_id), float(x), float(y)))
        read = 0
        while read < nonzero:
            count, first = struct.unpack_from("<II", buf, pos)
            pos += 8
            run = np.frombuffer(buf, dtype="<f4", count=count, offset=pos)
            pos += 4 * count
            rows.append(np.arange(first, first + count, dtype=np.int64))
            cols.append(np.full(count, spot, dtype=np.int64))
            vals.append(run.astype(np.float32))
            read += count
    if pos != len(buf):
        logger.warning("MCsquare sparse file: {} trailing bytes after {} spots", len(buf) - pos, n_spots)
    if rows:
        r = np.concatenate(rows); c = np.concatenate(cols); v = np.concatenate(vals)
    else:
        r = c = np.zeros(0, dtype=np.int64); v = np.zeros(0, dtype=np.float32)
    if r.size and int(r.max()) >= n_vox:
        raise ValueError(f"{header_path}: voxel index {int(r.max())} outside ImageSize {header['ImageSize']}")
    header["spots"] = spots_meta
    return sp.csc_matrix((v, (r, c)), shape=(n_vox, n_spots), dtype=np.float32), header


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------

@dataclass
class MCsquareRun:
    """What one engine run produced: the work directory and the files in it."""

    workdir: Path
    config_path: Path
    stdout_path: Path
    returncode: int


class MCsquareDriver:
    """Write the engine's inputs, run it, read the results."""

    def __init__(self, assets: Optional[MCsquareAssets] = None, work_root: Optional[Path] = None,
                 n_threads: int = 0, seed: int = 0, keep_workdir: bool = False,
                 scanner: str = DEFAULT_SCANNER, bdl: str = DEFAULT_BDL) -> None:
        self.assets = assets or MCsquareAssets(default_assets_dir())
        self.work_root = Path(work_root) if work_root else None
        self.n_threads = int(n_threads)
        self.seed = int(seed)
        self.keep_workdir = bool(keep_workdir)
        self.scanner = scanner
        self.bdl_name = bdl
        self._bdl: Optional[BeamDataLibrary] = None
        self._calibration: Optional[CalibrationTables] = None

    # ----- assets -----------------------------------------------------

    def availability(self) -> Tuple[bool, str]:
        return self.assets.availability()

    def fingerprint(self) -> str:
        return self.assets.fingerprint()

    def bdl(self) -> BeamDataLibrary:
        if self._bdl is None:
            self._bdl = BeamDataLibrary.load(self.assets.bdl_path(self.bdl_name))
        return self._bdl

    def calibration(self) -> CalibrationTables:
        if self._calibration is None:
            self._calibration = CalibrationTables.from_dir(self.assets.scanner_dir(self.scanner))
        return self._calibration

    # ----- work directories -------------------------------------------

    def new_workdir(self) -> Path:
        if self.work_root is not None:
            self.work_root.mkdir(parents=True, exist_ok=True)
            work = self.work_root / f"mcsquare-{uuid.uuid4().hex[:12]}"
            work.mkdir()
            return work
        return Path(tempfile.mkdtemp(prefix="radiarch-mcsquare-"))

    def cleanup(self, work: Path) -> None:
        if not self.keep_workdir:
            shutil.rmtree(work, ignore_errors=True)

    # ----- inputs -----------------------------------------------------

    def prepare(self, work: Path, ct_hu_zyx: np.ndarray, spacing_mm: Vec3, origin_mm: Vec3, plan: ProtonPlan,
                *, nb_primaries: float, beamlets: bool = False, stat_uncertainty: float = 0.0,
                calibration: Optional[CalibrationTables] = None, bdl: Optional[BeamDataLibrary] = None,
                config_overrides: Optional[Dict[str, Any]] = None) -> Path:
        """Write every input file for one run into ``work``; returns the config path.

        The layout is the one OpenTPS uses, so the files can be compared with
        the frozen goldens: ``CT.mhd``/``CT.raw``, ``Scanner/``, ``bdl.txt``,
        ``PlanPencil.txt``, ``config.txt``; results land in ``Outputs/``.
        """
        work = Path(work)
        work.mkdir(parents=True, exist_ok=True)
        ct_hu_zyx = np.asarray(ct_hu_zyx)
        if ct_hu_zyx.ndim != 3:
            raise ValueError("ct_hu_zyx must be a 3-D (z, y, x) array")
        nz, ny, nx = ct_hu_zyx.shape
        bdl = bdl or self.bdl()
        calibration = calibration or self.calibration()

        ct_path = write_ct_mhd(ct_hu_zyx, spacing_mm, origin_mm, work / "CT.mhd")
        density_path, material_path = calibration.write(work / "Scanner")
        bdl_path = bdl.write(work / "bdl.txt")
        plan_path = write_plan_pencil(plan, work / "PlanPencil.txt", origin_mm, spacing_mm, (nx, ny, nz), bdl)

        cfg = default_config()
        cfg.update({
            "Num_Threads": self.n_threads, "RNG_Seed": self.seed,
            "Num_Primaries": int(nb_primaries), "Stat_uncertainty": float(stat_uncertainty),
            "WorkDir": str(work), "CT_File": str(ct_path), "ScannerDirectory": str(work / "Scanner"),
            "HU_Density_Conversion_File": str(density_path), "HU_Material_Conversion_File": str(material_path),
            "BDL_Machine_Parameter_File": str(bdl_path), "BDL_Plan_File": str(plan_path),
            "Dose_to_Water_conversion": "OnlineSPR",
        })
        if beamlets:
            cfg.update({
                "Compute_stat_uncertainty": False, "Beamlet_Mode": True, "Beamlet_Parallelization": True,
                "Dose_MHD_Output": False, "Dose_Sparse_Output": True, "Dose_Sparse_Threshold": 20000.0,
            })
        if config_overrides:
            cfg.update(config_overrides)
        config_path = work / "config.txt"
        config_path.write_text(render_config(cfg), encoding="utf-8")
        return config_path

    # ----- running ----------------------------------------------------

    def run(self, work: Path, config_path: Optional[Path] = None) -> MCsquareRun:
        """Run the engine in ``work`` through its launcher; raises on a non-zero exit."""
        ok, reason = self.availability()
        if not ok:
            raise RuntimeError(f"MCsquare is not available: {reason}")
        work = Path(work)
        config_path = Path(config_path) if config_path else work / "config.txt"
        stdout_path = work / "mcsquare.log"
        env = dict(os.environ)
        env["MCsquare_Materials_Dir"] = str(self.assets.materials_dir)
        with open(stdout_path, "w") as log:
            proc = subprocess.run(
                ["sh", str(self.assets.launcher), str(config_path)],
                cwd=str(work), stdout=log, stderr=subprocess.STDOUT, env=env, check=False,
            )
        if proc.returncode != 0:
            tail = stdout_path.read_text()[-2000:]
            raise RuntimeError(f"MCsquare exited with {proc.returncode} in {work}:\n{tail}")
        return MCsquareRun(work, config_path, stdout_path, proc.returncode)

    # ----- results ----------------------------------------------------

    @staticmethod
    def delivered_protons(plan: ProtonPlan, bdl: BeamDataLibrary) -> float:
        return float(sum(layer.meterset * bdl.mu_to_protons(layer.energy_mev)
                         for beam in plan.beams for layer in beam.layers))

    def read_dose(self, work: Path, plan: ProtonPlan, bdl: Optional[BeamDataLibrary] = None,
                  shape_zyx: Optional[Tuple[int, int, int]] = None) -> np.ndarray:
        """``Outputs/Dose.mhd`` → ``(z, y, x)`` float32 in Gy for the plan's metersets and fractions."""
        bdl = bdl or self.bdl()
        dose, _, _ = read_mhd(Path(work) / "Outputs" / "Dose.mhd")
        if shape_zyx is not None and tuple(dose.shape) != tuple(shape_zyx):
            raise ValueError(f"MCsquare dose grid {dose.shape} differs from the CT grid {tuple(shape_zyx)}")
        scale = self.delivered_protons(plan, bdl) * EV_PER_G_TO_GY * plan.n_fractions
        return (dose.astype(np.float64) * scale).astype(np.float32)

    def read_beamlets(self, work: Path, plan: ProtonPlan, shape_zyx: Tuple[int, int, int],
                      bdl: Optional[BeamDataLibrary] = None) -> sp.csr_matrix:
        """``Outputs/Sparse_Dose.txt`` → CSR ``(n_voxels, n_spots)``: rows in radiarch's
        ``(z, y, x)`` C-order, columns in the plan's fluence-element order, Gy per MU."""
        bdl = bdl or self.bdl()
        native, header = read_sparse_beamlets(Path(work) / "Outputs" / "Sparse_Dose.txt")
        nz, ny, nx = (int(v) for v in shape_zyx)
        if tuple(header["ImageSize"]) != (nx, ny, nz):
            raise ValueError(f"MCsquare beamlet grid {header['ImageSize']} differs from the CT grid (x, y, z) {(nx, ny, nz)}")
        if native.shape[1] != plan.n_spots:
            raise ValueError(f"MCsquare wrote {native.shape[1]} beamlets; the plan has {plan.n_spots} spots")
        per_spot = np.array([bdl.mu_to_protons(e) for e in plan.spot_energies_mev], dtype=np.float64) * EV_PER_G_TO_GY
        scaled = native @ sp.diags(per_spot.astype(np.float32), format="csc")
        perm = native_row_permutation((nz, ny, nx))
        return sp.csr_matrix(scaled.tocsr()[perm, :], dtype=np.float32)

    # ----- one-call conveniences ---------------------------------------

    def compute_dose(self, ct_hu_zyx: np.ndarray, spacing_mm: Vec3, origin_mm: Vec3, plan: ProtonPlan,
                     *, nb_primaries: float, stat_uncertainty: float = 0.0,
                     calibration: Optional[CalibrationTables] = None,
                     config_overrides: Optional[Dict[str, Any]] = None) -> np.ndarray:
        work = self.new_workdir()
        try:
            cfg = self.prepare(work, ct_hu_zyx, spacing_mm, origin_mm, plan, nb_primaries=nb_primaries,
                               stat_uncertainty=stat_uncertainty, calibration=calibration,
                               config_overrides=config_overrides)
            self.run(work, cfg)
            return self.read_dose(work, plan, shape_zyx=tuple(np.asarray(ct_hu_zyx).shape))
        finally:
            self.cleanup(work)

    def compute_beamlets(self, ct_hu_zyx: np.ndarray, spacing_mm: Vec3, origin_mm: Vec3, plan: ProtonPlan,
                         *, nb_primaries: float, calibration: Optional[CalibrationTables] = None,
                         config_overrides: Optional[Dict[str, Any]] = None) -> sp.csr_matrix:
        """Influence matrix: every spot at 1 MU, one column per spot, Gy per MU."""
        unit = plan.with_spot_mus(np.ones(plan.n_spots))
        work = self.new_workdir()
        try:
            cfg = self.prepare(work, ct_hu_zyx, spacing_mm, origin_mm, unit, nb_primaries=nb_primaries,
                               beamlets=True, calibration=calibration, config_overrides=config_overrides)
            self.run(work, cfg)
            return self.read_beamlets(work, unit, tuple(np.asarray(ct_hu_zyx).shape))
        finally:
            self.cleanup(work)


__all__ = [
    "EV_PER_G_TO_GY", "DEFAULT_SCANNER", "DEFAULT_BDL", "default_assets_dir",
    "MCsquareAssets", "CalibrationTables", "BeamDataLibrary",
    "default_config", "render_config", "mcsquare_offset", "to_engine_frame", "from_engine_frame",
    "native_row_permutation", "isocenter_to_mcsquare", "write_ct_mhd", "read_mhd",
    "write_plan_pencil", "read_sparse_beamlets", "MCsquareRun", "MCsquareDriver",
]
