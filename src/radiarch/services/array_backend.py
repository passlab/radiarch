"""Where the optimizer evaluates doses and objectives: NumPy on the CPU, or CuPy on a GPU.

The CPU is the default and its path is the one radiarch has always run; the GPU is used only when the setting
``optimizer_device`` (``RADIARCH_OPTIMIZER_DEVICE``: ``cpu``, ``gpu`` or ``auto``) asks for it
(``docs/reports/engine-performance.md``). On the GPU the influence matrices, the structures' masks and the objective
terms live on the device; the solver (SciPy's L-BFGS-B) stays on the host and exchanges only the weights and their
gradient with it. The dose is computed in float64 on both, so the cost is not a staircase in the weights (R11.8).

Objectives and hard-constraint terms are written once for both: :func:`array_module` gives the module of the array
they are handed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional, Tuple

import numpy as np
from loguru import logger

DEVICES = ("cpu", "gpu", "auto")


def array_module(a) -> Any:
    """``cupy`` for a CuPy array, else ``numpy`` (without importing CuPy where it is not installed)."""
    if type(a).__module__.split(".")[0] == "cupy":
        import cupy
        return cupy
    return np


def to_host(a) -> np.ndarray:
    """A NumPy array of ``a``, copied from the device when it is a CuPy array."""
    return a.get() if type(a).__module__.split(".")[0] == "cupy" else np.asarray(a)


class DeviceUnavailableError(RuntimeError):
    """``gpu`` was asked for and CuPy or a CUDA device is missing."""


@dataclass(frozen=True)
class OptimizerDevice:
    """The optimizer's array backend: ``xp`` (NumPy or CuPy) and helpers to move data to it."""

    xp: Any
    gpu: bool

    @property
    def name(self) -> str:
        return "gpu" if self.gpu else "cpu"

    def asarray(self, a, dtype=np.float64):
        """``a`` on this device (no copy on the CPU when it is already a float64 array)."""
        return self.xp.asarray(a, dtype=dtype)

    def matrix(self, csr, grid_shape: Tuple[int, ...], base=None) -> "DeviceMatrix":
        return DeviceMatrix(csr, grid_shape, self, base)

    def free_bytes(self) -> int:
        """The GPU's free memory (0 on the CPU)."""
        return int(self.xp.cuda.Device().mem_info[0]) if self.gpu else 0


CPU = OptimizerDevice(np, False)


def _setting(device: Optional[str]) -> str:
    if device is None:
        from ..config import get_settings
        device = getattr(get_settings(), "optimizer_device", "cpu")
    device = (device or "cpu").lower()
    if device not in DEVICES:
        raise ValueError(f"optimizer device must be one of {DEVICES}, not {device!r}")
    return device


def device_cache_key(cache_key: str, device: Optional[str] = None) -> str:
    """``cache_key`` for the setting ``optimizer_device``: unchanged for ``cpu``, so earlier results keep their keys;
    its own for ``gpu`` and ``auto``. It follows the setting, not the hardware, so the API (which may have no GPU) and
    the worker compute the same key."""
    device = _setting(device)
    return cache_key if device == "cpu" else hashlib.sha256(f"{cache_key}:optimizer-{device}".encode()).hexdigest()


def optimizer_device(device: Optional[str] = None) -> OptimizerDevice:
    """The device for ``device`` or, when None, the setting ``optimizer_device``: ``cpu``; ``gpu`` (an error when CuPy
    or a CUDA device is missing); ``auto`` (the GPU when it works, else the CPU)."""
    device = _setting(device)
    if device == "cpu":
        return CPU
    try:
        import cupy as cp
        import cupyx.scipy.sparse  # noqa: F401  (the sparse products)
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError("no CUDA device")
        cp.ones(2).sum()
        from .dose_engines.pb import _restore_thread_locale
        _restore_thread_locale()        # the first kernel sets the thread's locale to C (driver 580), as in pb
        return OptimizerDevice(cp, True)
    except Exception as exc:
        if device == "gpu":
            raise DeviceUnavailableError(f"optimizer device 'gpu' needs CuPy and a working CUDA device: {exc}") from exc
        logger.info("optimizer: no usable GPU ({}); running on the CPU", exc)
        return CPU


def device_bytes(matrices) -> int:
    """What the matrices and their transposes take on the device: float64 values and int32 indices, twice."""
    return sum(24 * m.nnz for m in matrices)


def device_for(matrices, device: Optional[OptimizerDevice] = None) -> OptimizerDevice:
    """``device`` (by default the setting's) when ``matrices`` fit in 80 % of its free memory, else the CPU, with a
    warning."""
    device = device if device is not None else optimizer_device()
    if not device.gpu:
        return device
    need, free = device_bytes(matrices), device.free_bytes()
    if need > 0.8 * free:
        logger.warning("optimizer: the matrices need {:.1f} GB on the GPU and {:.1f} GB are free; solving on the CPU",
                       need / 1e9, free / 1e9)
        return CPU
    return device


# Both products row by row in a fixed order: one warp per row, its 32 lanes summing strided entries, then a fixed
# tree of shuffles. cuSPARSE's product splits long rows and adds the parts in an order that varies from run to run
# (a voxel inside many beamlets, a weight's column of the transpose), so the same solve could end on another plan (two
# runs of the lung protocol case: the cord maximum 16.5 and 19.1 Gy); this sum is the same every run.
_ROW_SUMS_SRC = r'''
extern "C" __global__ void csr_row_dot(const long long* indptr, const int* indices, const double* data,
        const double* x, double* y, const long long nrows) {
    long long row = ((long long)blockIdx.x * blockDim.x + threadIdx.x) / 32;
    int lane = threadIdx.x & 31;
    if (row >= nrows) return;                       /* a warp shares its row, so it returns whole */
    double s = 0.0;
    for (long long k = indptr[row] + lane; k < indptr[row + 1]; k += 32)
        s += data[k] * x[indices[k]];
    for (int off = 16; off > 0; off >>= 1)
        s += __shfl_down_sync(0xffffffffu, s, off);
    if (lane == 0) y[row] = s;
}
'''
_ROW_SUMS: list = []


def _row_sums(xp, csr, indptr64, x):
    """``csr @ x`` by :data:`_ROW_SUMS_SRC` (float64, on the device)."""
    if not _ROW_SUMS:
        _ROW_SUMS.append(xp.RawKernel(_ROW_SUMS_SRC, "csr_row_dot"))
    n = int(csr.shape[0])
    out = xp.empty(n, dtype=xp.float64)
    if n:
        _ROW_SUMS[0](((n * 32 + 255) // 256,), (256,), (indptr64, csr.indices, csr.data,
                                                       xp.ascontiguousarray(x, dtype=xp.float64), out, np.int64(n)))
    return out


class DeviceMatrix:
    """An influence matrix (voxels x weights) for the products a solve repeats: ``forward`` (weights to the dose,
    on the device, plus an optional fixed ``base`` dose) and ``backward`` (a dose gradient to the weights' gradient, on
    the host). ``grid_shape`` is the dose's shape: the grid, or the rows alone.

    On the CPU it is the SciPy matrix as given, and the products are those radiarch has always computed. On the GPU
    it and its transpose are kept in float64 CSR on the device (twice the host matrix's bytes per copy), and both
    products are :data:`_ROW_SUMS_SRC`'s, so they repeat bit for bit from run to run."""

    def __init__(self, csr, grid_shape: Tuple[int, ...], device: OptimizerDevice, base=None):
        self.device, self.grid_shape = device, tuple(grid_shape)
        self.shape = csr.shape
        if device.gpu:
            import cupyx.scipy.sparse as csp
            self.mat = csp.csr_matrix(csr.astype(np.float64).tocsr())
            self.mat_t = csp.csr_matrix(csr.T.tocsr().astype(np.float64))
            for m in (self.mat, self.mat_t):
                m.indices = m.indices.astype(np.int32, copy=False)
            self._indptr = self.mat.indptr.astype(np.int64)
            self._indptr_t = self.mat_t.indptr.astype(np.int64)
            self.base = None if base is None else device.xp.asarray(base, dtype=np.float64).ravel()
        else:
            self.mat = csr
            self.mat_t = None
            self.base = None if base is None else np.asarray(base, dtype=np.float64).ravel()

    def forward(self, w) -> Any:
        """The dose for the weights ``w`` (host or device), in float64, on the device."""
        if not self.device.gpu:
            d = np.asarray(self.mat @ np.asarray(w, dtype=np.float64).ravel())
            return (d if self.base is None else self.base + d).reshape(self.grid_shape, order="C")
        xp = self.device.xp
        d = _row_sums(xp, self.mat, self._indptr, xp.asarray(w, dtype=xp.float64).ravel())
        return (d if self.base is None else self.base + d).reshape(self.grid_shape)

    def backward(self, grad_dose) -> np.ndarray:
        """``matrix.T @ grad_dose`` on the host, in float64."""
        if not self.device.gpu:
            return np.asarray(self.mat.T @ np.asarray(grad_dose).ravel(order="C"), dtype=np.float64)
        xp = self.device.xp
        return to_host(_row_sums(xp, self.mat_t, self._indptr_t, xp.asarray(grad_dose, dtype=xp.float64).ravel()))


__all__ = ["DEVICES", "array_module", "to_host", "DeviceUnavailableError", "OptimizerDevice", "CPU", "device_cache_key",
           "optimizer_device", "device_bytes", "device_for", "DeviceMatrix"]
