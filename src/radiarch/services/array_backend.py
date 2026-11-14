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

    def matrix(self, csr, grid_shape: Tuple[int, ...]) -> "DeviceMatrix":
        return DeviceMatrix(csr, grid_shape, self)

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


class DeviceMatrix:
    """An influence matrix (voxels x weights) for the products a solve repeats: ``forward`` (weights to the dose on
    the grid, on the device) and ``backward`` (a dose gradient to the weights' gradient, on the host).

    On the CPU it is the SciPy matrix as given, and the products are those radiarch has always computed. On the GPU
    it and its transpose are kept in float64 CSR on the device (twice the host matrix's bytes per copy)."""

    def __init__(self, csr, grid_shape: Tuple[int, ...], device: OptimizerDevice):
        self.device, self.grid_shape = device, tuple(grid_shape)
        self.shape = csr.shape
        if device.gpu:
            import cupyx.scipy.sparse as csp
            self.mat = csp.csr_matrix(csr.astype(np.float64).tocsr())
            self.mat_t = csp.csr_matrix(csr.T.tocsr().astype(np.float64))
        else:
            self.mat = csr
            self.mat_t = None

    def forward(self, w) -> Any:
        """The dose on the grid for the weights ``w`` (host or device), in float64, on the device."""
        if not self.device.gpu:
            return np.asarray(self.mat @ np.asarray(w, dtype=np.float64).ravel()).reshape(self.grid_shape, order="C")
        xp = self.device.xp
        return (self.mat @ xp.asarray(w, dtype=xp.float64).ravel()).reshape(self.grid_shape)

    def backward(self, grad_dose) -> np.ndarray:
        """``matrix.T @ grad_dose`` on the host, in float64."""
        if not self.device.gpu:
            return np.asarray(self.mat.T @ np.asarray(grad_dose).ravel(order="C"), dtype=np.float64)
        xp = self.device.xp
        return to_host(self.mat_t @ xp.asarray(grad_dose, dtype=xp.float64).ravel())


__all__ = ["DEVICES", "array_module", "to_host", "DeviceUnavailableError", "OptimizerDevice", "CPU", "device_cache_key",
           "optimizer_device", "DeviceMatrix"]
