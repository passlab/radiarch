"""File-protocol driver for the WiscPlan collapsed-cone photon engine.

``CCC_DoseEngine`` is a standalone GPLv2 program (see NOTICE). Radiarch never
links or imports it: this module writes the files it reads, starts it as a
subprocess, and parses the sparse beamlet matrices it writes. The protocol
was taken from the engine's sources (``convolution.cpp``, ``parse_func.cpp``)
and from OpenTPS's ``CCCdoseEngineIO.py`` (Apache-2.0), of which the versor
rotation and the record layouts below are a port.

Command line::

    CCC_DoseEngine kernelPaths.txt geometryFilePath.txt pencilBeamSpecs.txt out.bin

The engine's process exit code follows its own ``defs.h``: **1 means
success, 0 means failure** (the opposite of the shell convention).

Coordinate conventions
----------------------
Radiarch volumes are ``(z, y, x)`` C-order arrays on a grid given by
``spacing_mm = (sx, sy, sz)`` and ``origin_mm = (ox, oy, oz)`` (the centre
of voxel ``[0, 0, 0]``), in the patient frame of the CT. The engine reads a
density volume in C-order over ``(Z, X_ot, Y_ot)`` — ``z`` slowest, then the
patient ``x`` axis, then ``y`` fastest — with the counts and starts written
in the order ``(y, x, z)``: in the engine's frame ``X`` points at the gantry
(the patient ``y`` axis for gantry 0) and ``Z`` runs along the couch.
Positions are in centimetres and the isocenter is at the engine's origin, so
the grid origin is written shifted by minus the isocenter.

Each beamlet is written with its centre ``(xp, yp)`` and size in the BEV at
isocenter, the SAD, the source position ``-k · SAD`` and three versors
``(ip, jp, kp)`` obtained by rotating the engine's reference frame by the
collimator, gantry and couch angles.

The output is, per beamlet, five ``int32`` (beamlet number, X, Y, Z counts,
non-zero count), the non-zero voxel indices (``int32``, C-order over
``(Z, X_ot, Y_ot)``) and their values (``float32``, dose per unit beamlet
weight, in the engine's own units). Fluence per beamlet scales with its area,
so a uniform field delivers the same dose whatever beamlet size is chosen.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from loguru import logger

from .protocol import EngineRuntimeError, EngineUnavailableError

BINARY_NAME = "CCC_DoseEngine"
KERNEL_DIR_NAME = "Kernels_differentFluence"
EXIT_SUCCESS = 1   # defs.h: #define SUCCESS 1
EXIT_FAILURE = 0   # defs.h: #define FAILURE 0


def default_engine_dir() -> Path:
    """The vendored OpenTPS photon directory (binary + kernels), unless configured."""
    try:
        from ...config import get_settings
        configured = get_settings().ccc_engine_dir
    except Exception:  # pragma: no cover — settings unavailable in odd test setups
        configured = ""
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "opentps" / "core" / "processing" / "doseCalculation" / "photons"


# ---------------------------------------------------------------------------
# Beamlet geometry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BeamletGeometry:
    """What the engine needs per beamlet, as parallel arrays of length n."""

    xy_mm: np.ndarray         # (n, 2) centre in the BEV at isocenter
    size_mm: np.ndarray       # (n, 2) beamlet width along x and y
    angles_deg: np.ndarray    # (n, 3) gantry, couch, collimator
    sad_mm: np.ndarray        # (n,)

    def __post_init__(self) -> None:
        n = self.xy_mm.shape[0]
        if self.xy_mm.shape != (n, 2) or self.size_mm.shape != (n, 2) \
                or self.angles_deg.shape != (n, 3) or self.sad_mm.shape != (n,):
            raise ValueError("BeamletGeometry arrays have inconsistent shapes")

    def __len__(self) -> int:
        return int(self.xy_mm.shape[0])

    def subset(self, start: int, stop: int) -> "BeamletGeometry":
        return BeamletGeometry(self.xy_mm[start:stop], self.size_mm[start:stop],
                               self.angles_deg[start:stop], self.sad_mm[start:stop])


def beamlet_geometry_from_plan(plan) -> BeamletGeometry:
    """Flatten a :class:`radiarch.models.photon_plan.PhotonPlan` beam by beam,
    segment by segment — the column order of the Dij."""
    xy, size, angles, sad = [], [], [], []
    for beam in plan.beams:
        for seg in beam.segments:
            b = seg.beamlets()
            if b.shape[0] == 0:
                continue
            xy.append(b[:, :2])
            size.append(b[:, 2:])
            angles.append(np.tile([beam.gantry_deg, beam.couch_deg, seg.collimator_deg], (b.shape[0], 1)))
            sad.append(np.full(b.shape[0], float(beam.sad_mm)))
    if not xy:
        return BeamletGeometry(np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 3)), np.zeros(0))
    return BeamletGeometry(np.concatenate(xy), np.concatenate(size), np.concatenate(angles), np.concatenate(sad))


# ---------------------------------------------------------------------------
# Writers (one function per file the engine reads)
# ---------------------------------------------------------------------------

def _rotate(vec: Sequence[float], angle_rad: float, axis: str) -> List[float]:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    x, y, z = vec
    if axis == "x":
        return [x, y * c - z * s, y * s + z * c]
    if axis == "y":
        return [x * c + z * s, y, -x * s + z * c]
    return [x * c - y * s, x * s + y * c, z]


def rotated_versors(gantry_deg: float, couch_deg: float, collimator_deg: float):
    """The engine's beam frame ``(i, j, k)`` for a gantry/couch/collimator
    setting. In its reference frame ``x`` points at the gantry and ``z`` runs
    along the couch; the collimator and couch rotate about ``x``, the gantry
    about ``z``."""
    g, c, col = map(math.radians, (gantry_deg, couch_deg, collimator_deg))
    i = _rotate(_rotate(_rotate([0.0, 1.0, 0.0], col, "x"), g, "z"), c, "x")
    j = _rotate(_rotate(_rotate([0.0, 0.0, 1.0], col, "x"), g, "z"), c, "x")
    k = _rotate(_rotate([1.0, 0.0, 0.0], g, "z"), c, "x")
    return i, j, k


def write_kernel_paths(path: Path, kernel_dir: Path) -> None:
    """``name`` / ``path`` line pairs for every kernel file; the text header
    keeps its base name, binary tables get a ``kernel_`` prefix."""
    lines = []
    for fn in sorted(os.listdir(kernel_dir)):
        base, ext = os.path.splitext(fn)
        lines.append((base if ext == ".txt" else "kernel_" + base) + "\n")
        lines.append(str(kernel_dir / fn) + "\n")
    Path(path).write_text("".join(lines))


def write_geometry(
    geometry_dir: Path,
    density_zyx: np.ndarray,
    spacing_mm: Sequence[float],
    origin_mm: Sequence[float],
    isocenter_mm: Sequence[float],
) -> Tuple[Path, Path]:
    """Write ``CT.bin`` (float32 densities) and ``CT_HeaderFile.txt``.

    Returns ``(header_path, density_path)``. ``spacing_mm`` and ``origin_mm``
    are ``(x, y, z)``; the array is ``(z, y, x)``.
    """
    geometry_dir = Path(geometry_dir)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    d = np.asarray(density_zyx, dtype=np.float32)
    if d.ndim != 3:
        raise ValueError("density must be a 3-D (z, y, x) array")
    nz, ny, nx = d.shape
    sx, sy, sz = (float(v) / 10.0 for v in spacing_mm)
    ox, oy, oz = (float(v) / 10.0 for v in origin_mm)
    ix, iy, iz = (float(v) / 10.0 for v in isocenter_mm)

    density_path = geometry_dir / "CT.bin"
    # Engine order: z slowest, then patient x, then patient y fastest.
    np.ascontiguousarray(d.transpose(0, 2, 1)).tofile(density_path)

    header_path = geometry_dir / "CT_HeaderFile.txt"
    header_path.write_text(
        "Xcount Ycount Zcount\n"
        f"{ny} {nx} {nz}\n"
        "Xstart Ystart Zstart\n"
        f"{oy - iy} {ox - ix} {oz - iz}\n"
        "dx dy dz\n"
        f"{sy} {sx} {sz}\n"
        "Xorigin Yorigin Yorigin\n"
        f"{ox} {oy} {oz}\n"
    )
    return header_path, density_path


def write_geometry_index(path: Path, header_path: Path, density_path: Path) -> None:
    Path(path).write_text(
        f"geometry_header\n{header_path}\ngeometry_density\n{density_path}\n"
    )


def write_beamlet_specs(path: Path, beamlets: BeamletGeometry, first_number: int = 0) -> None:
    """One ``pencilBeamSpecs`` file: all quantities in centimetres."""
    out = [f"beamnum:\n{len(beamlets)}\n \n"]
    cache = {}
    for n in range(len(beamlets)):
        g, c, col = (float(v) for v in beamlets.angles_deg[n])
        key = (g, c, col)
        if key not in cache:
            cache[key] = rotated_versors(g, c, col)
        i, j, k = cache[key]
        sad = float(beamlets.sad_mm[n]) / 10.0
        x, y = (float(v) / 10.0 for v in beamlets.xy_mm[n])
        dx, dy = (float(v) / 10.0 for v in beamlets.size_mm[n])
        src = [-v * sad for v in k]
        out.append(
            f"num\n{first_number + n}\n"
            "SAD xp yp del_xp del_yp\n"
            f"{sad:f} {x:f} {y:f} {dx:f} {dy:f}\n"
            "y_vec\n"
            f"{src[0]:f} {src[1]:f} {src[2]:f}\n"
            "ip\n"
            f"{i[0]:f} {i[1]:f} {i[2]:f}\n"
            "jp\n"
            f"{j[0]:f} {j[1]:f} {j[2]:f}\n"
            "kp\n"
            f"{k[0]:f} {k[1]:f} {k[2]:f}\n"
            "\n \n"
        )
    Path(path).write_text("".join(out))


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

def engine_index_to_rows(flat: np.ndarray, shape_zyx: Tuple[int, int, int]) -> np.ndarray:
    """Map the engine's voxel indices (C-order over ``(z, x, y)``) to rows of a
    ``(z, y, x)`` C-order flatten."""
    nz, ny, nx = shape_zyx
    f = np.asarray(flat, dtype=np.int64)
    z = f // (nx * ny)
    rem = f % (nx * ny)
    x = rem // ny
    y = rem % ny
    return (z * ny + y) * nx + x


def read_sparse_beamlets(path: Path, shape_zyx: Tuple[int, int, int]) -> sp.csc_matrix:
    """Parse one output file into a ``(n_voxels, n_beamlets)`` CSC matrix."""
    buf = np.fromfile(path, dtype=np.uint8)
    if buf.size < 4:
        raise EngineRuntimeError(f"CCC output {path} is empty")
    n_beamlets = int(np.frombuffer(buf[:4].tobytes(), dtype=np.int32)[0])
    nz, ny, nx = shape_zyx
    n_voxels = nz * ny * nx
    pos = 4
    rows, cols, vals = [], [], []
    for b in range(n_beamlets):
        head = np.frombuffer(buf[pos:pos + 20].tobytes(), dtype=np.int32)
        pos += 20
        if head.size != 5:
            raise EngineRuntimeError(f"CCC output {path}: truncated beamlet header at beamlet {b}")
        xcount, ycount, zcount, nnz = (int(v) for v in head[1:])
        if (xcount, ycount, zcount) != (ny, nx, nz):
            raise EngineRuntimeError(
                f"CCC output {path}: grid {(xcount, ycount, zcount)} != expected {(ny, nx, nz)}"
            )
        idx = np.frombuffer(buf[pos:pos + 4 * nnz].tobytes(), dtype=np.int32)
        pos += 4 * nnz
        val = np.frombuffer(buf[pos:pos + 4 * nnz].tobytes(), dtype=np.float32)
        pos += 4 * nnz
        if idx.size != nnz or val.size != nnz:
            raise EngineRuntimeError(f"CCC output {path}: truncated data at beamlet {b}")
        rows.append(engine_index_to_rows(idx, shape_zyx))
        cols.append(np.full(nnz, b, dtype=np.int64))
        vals.append(val)
    if n_beamlets == 0:
        return sp.csc_matrix((n_voxels, 0), dtype=np.float32)
    r = np.concatenate(rows); c = np.concatenate(cols); v = np.concatenate(vals)
    if r.size and (r.min() < 0 or r.max() >= n_voxels):
        raise EngineRuntimeError(f"CCC output {path}: voxel index out of range")
    return sp.csc_matrix((v, (r, c)), shape=(n_voxels, n_beamlets), dtype=np.float32)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

class CCCDriver:
    """Run the engine for one geometry and one set of beamlets."""

    def __init__(self, engine_dir: Optional[Path] = None, n_jobs: int = 1, keep_workdir: bool = False) -> None:
        self.engine_dir = Path(engine_dir) if engine_dir else default_engine_dir()
        self.n_jobs = max(1, int(n_jobs))
        self.keep_workdir = keep_workdir

    @property
    def binary(self) -> Path:
        return self.engine_dir / BINARY_NAME / BINARY_NAME

    @property
    def kernel_dir(self) -> Path:
        return self.engine_dir / KERNEL_DIR_NAME

    def availability(self) -> Tuple[bool, str]:
        if not self.binary.is_file():
            return False, f"CCC binary not found at {self.binary}"
        if not os.access(self.binary, os.X_OK):
            return False, f"CCC binary is not executable: {self.binary}"
        if not self.kernel_dir.is_dir() or not any(self.kernel_dir.iterdir()):
            return False, f"CCC kernels not found at {self.kernel_dir}"
        return True, "ok"

    def kernel_fingerprint(self) -> str:
        """Short SHA-256 over the kernel files; part of every calibration key."""
        h = hashlib.sha256()
        for fn in sorted(os.listdir(self.kernel_dir)):
            h.update(fn.encode())
            h.update((self.kernel_dir / fn).read_bytes())
        return h.hexdigest()[:16]

    def run(
        self,
        density_zyx: np.ndarray,
        spacing_mm: Sequence[float],
        origin_mm: Sequence[float],
        isocenter_mm: Sequence[float],
        beamlets: BeamletGeometry,
        workdir: Optional[Path] = None,
    ) -> sp.csr_matrix:
        """Return the ``(n_voxels, n_beamlets)`` CSR beamlet dose matrix
        (engine units per unit weight) in radiarch's ``(z, y, x)`` row order."""
        ok, reason = self.availability()
        if not ok:
            raise EngineUnavailableError(reason)
        if len(beamlets) == 0:
            raise EngineRuntimeError("no beamlets to compute")

        own_workdir = workdir is None
        work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="radiarch-ccc-"))
        try:
            geom_dir, beam_dir, out_dir = work / "Geometry", work / "BeamSpecs", work / "Outputs"
            for d in (geom_dir, beam_dir, out_dir):
                d.mkdir(parents=True, exist_ok=True)
            header, density = write_geometry(geom_dir, density_zyx, spacing_mm, origin_mm, isocenter_mm)
            write_geometry_index(work / "geometryFilePath.txt", header, density)
            write_kernel_paths(work / "kernelPaths.txt", self.kernel_dir)

            n = len(beamlets)
            n_batches = max(1, min(self.n_jobs, n))
            bounds = np.linspace(0, n, n_batches + 1).astype(int)
            batches = [(b, int(bounds[b]), int(bounds[b + 1])) for b in range(n_batches) if bounds[b + 1] > bounds[b]]
            for b, start, stop in batches:
                write_beamlet_specs(beam_dir / f"pencilBeamSpecs_batch{b}.txt", beamlets.subset(start, stop), start)

            def _one(batch):
                b, start, stop = batch
                cmd = [str(self.binary), str(work / "kernelPaths.txt"), str(work / "geometryFilePath.txt"),
                       str(beam_dir / f"pencilBeamSpecs_batch{b}.txt"), str(out_dir / f"sparseBeamletMatrix_batch{b}.bin")]
                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work))
                return b, start, stop, proc

            logger.info("CCC: {} beamlets in {} batch(es) on a {} grid", n, len(batches), tuple(np.asarray(density_zyx).shape))
            with ThreadPoolExecutor(max_workers=len(batches)) as pool:
                results = list(pool.map(_one, batches))

            parts = []
            shape = tuple(int(v) for v in np.asarray(density_zyx).shape)
            for b, start, stop, proc in results:
                tail = (proc.stdout or "")[-400:]
                if proc.returncode == EXIT_FAILURE:
                    raise EngineRuntimeError(f"CCC batch {b} reported failure: {tail!r} {proc.stderr[-200:]!r}")
                if proc.returncode != EXIT_SUCCESS:
                    raise EngineRuntimeError(
                        f"CCC batch {b} exited with {proc.returncode} (1 is success, 0 failure): "
                        f"{tail!r} {proc.stderr[-200:]!r}"
                    )
                out = out_dir / f"sparseBeamletMatrix_batch{b}.bin"
                if not out.is_file():
                    raise EngineRuntimeError(f"CCC batch {b} produced no output file")
                m = read_sparse_beamlets(out, shape)
                if m.shape[1] != stop - start:
                    raise EngineRuntimeError(
                        f"CCC batch {b} returned {m.shape[1]} beamlets, expected {stop - start}"
                    )
                parts.append(m)
            return sp.hstack(parts, format="csr").astype(np.float32)
        finally:
            if own_workdir and not self.keep_workdir:
                shutil.rmtree(work, ignore_errors=True)


__all__ = [
    "BeamletGeometry",
    "CCCDriver",
    "beamlet_geometry_from_plan",
    "default_engine_dir",
    "engine_index_to_rows",
    "read_sparse_beamlets",
    "rotated_versors",
    "write_beamlet_specs",
    "write_geometry",
    "write_geometry_index",
    "write_kernel_paths",
]
