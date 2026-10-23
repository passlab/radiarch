"""Native photon pencil-beam engine (roadmap R8).

Radiarch's own photon dose engine: no binary and no subprocess, NumPy on the
CPU or CuPy on a GPU. Beside the collapsed cone (:mod:`.ccc`) it is the fast
engine for optimization and for recomputing VMAT segments, and the
independent second engine the roadmap asks for.

Model
-----
The dose at a point is (Bortfeld, Schlegel and Rhein, Med Phys 20:311, 1993;
matRad's photon engine uses the same scheme)

    D = F * (SAD / z)^2 * sum_i A_i(d_rad) * (Phi (*) k_i)(u, w)

* ``(u, w)``: the point projected onto the isocenter plane, in the beam's-eye
  view of IEC 61217 (:func:`.ccc_driver.iec_beam_frame`, the frame of the
  spot placer and the DRRs); ``z``: its distance from the source along the
  beam axis;
* ``d_rad``: the radiological depth, density relative to water integrated
  along the ray from the source (a divergent ray grid in the beam's-eye view,
  interpolated at the voxels);
* ``Phi``: the fluence in the isocenter plane on a 1 mm grid: beamlet
  rectangles times their weights (MU), or the apertures (MLC rows within the
  jaws) times their metersets;
* ``k_i``, ``A_i``: the kernel components of :mod:`.pb_kernel` (an OpenGATE
  pencil kernel of the Mohan 6 MV spectrum in water);
* ``F``: the output calibration, 1 cGy per MU at d_max of a 10 x 10 cm field
  at SSD 100 cm, computed from the same components.

Heterogeneities change the depth and, since 1.1.0, the lateral spread: the
kernel's short-range part (within ``lateral_near_mm`` of the axis, carried by
secondary electrons) is stretched by ``s = 1 / rho_eff`` with its integral
kept, where ``rho_eff`` is the density around the voxel (the body's density
smoothed by a Gaussian of ``lateral_sigma_mm``, clipped to at most 1). In
lung a narrow field's electrons leave the beam and its dose falls, which a
depth-only pencil beam misses (25 % too high inside lung for a 2 x 2 cm
field against Monte Carlo). The kernel is precomputed at a few scales from 1
to ``lateral_max_scale``, geometrically spaced, and each voxel interpolates
between the two nearest in log scale. Water and denser voxels use the
unscaled kernel, so water doses and the calibration are unchanged. The longer
range photon scatter is not scaled, and depth effects of the interfaces
(build-down and re-build-up) are not modelled.

Two paths
---------
* :meth:`PencilBeamEngine.influence_matrix`: one column per beamlet; the
  beamlet rectangle is convolved with each component once per beamlet size
  and evaluated within a lateral cutoff (``cutoff_mm``) of the beamlet.
* :meth:`PencilBeamEngine.compute_plan_dose`: each beam's fluence convolved
  with the full kernel (200 mm), no cutoff. ``fluence="beamlets"`` (default
  when weights are given) or ``"apertures"`` (default for the plan's own
  metersets: the leaf and jaw positions as they are, the dose a VMAT segment
  recomputation needs).

Parameters (``EngineSpec.params``): ``n_components`` (kernel components,
default 4), ``cutoff_mm`` (influence matrix, default 80),
``sampling_threshold`` (influence-matrix entries below this fraction of
their column's maximum are kept with probability value / threshold and set
to the threshold, an unbiased thinning as matRad's; default 0.003, 0 keeps
all; the numbers are a Weyl sequence over the beamlets, which halves the
noise of independent draws; ``seed`` shifts it), ``penumbra_fwhm_mm`` (a Gaussian fluence
penumbra for the source size and the collimator edges, applied to the
kernel), ``fluence``,
``device`` (``cpu``, ``gpu``, ``auto``), ``n_jobs``, ``min_density`` (voxels
below it get no dose unless a slice encloses them: air outside the body gets
none, airways and other cavities do; default 0.05 g/cm^3),
``ray_spacing_mm`` and ``ray_step_mm`` (the radiological-depth grid,
default the smallest voxel spacing but at least 2 mm, and half the
smallest spacing but at least 0.5 mm; rays coarsen beyond 40 million samples),
``output_factor_gy_per_unit``, ``kernel_path``, ``lateral_scaling`` (default true),
``lateral_near_mm``, ``lateral_sigma_mm``, ``lateral_exponent``, ``lateral_max_scale``, ``lateral_scales``.

Changing the kernel table in ``engines/pb`` changes doses: bump
:attr:`PencilBeamEngine.version` with it, so cached doses are not reused.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from loguru import logger

from ...models.dose import ScenarioSpec
from ...models.photon_plan import PhotonPlan, PhotonSegment
from .ccc_driver import iec_beam_frame
from .pb_kernel import GRID_MM, PBKernel, load_kernel
from .protocol import (
    BeamModelBundle,
    EngineParamError,
    EngineUnavailableError,
    GeometryBundle,
    InfluenceData,
    NominalDose,
)
from .registry import register_engine

DEFAULT_COMPONENTS = 4
DEFAULT_CUTOFF_MM = 80.0
DEFAULT_MIN_DENSITY = 0.05
DEFAULT_PENUMBRA_FWHM_MM = 4.0   # fitted to the OpenGATE 10 x 10 cm penumbra (80-20 %: 4.9 / 5.9 / 7.5 mm at 5 / 10 / 20 cm
                                 # against 4.9 / 5.9 / 7.1 mm), kernel f046d6a503757f17
DEFAULT_LATERAL_NEAR_MM = 30.0    # kernel radius stretched in low density (secondary electrons); beyond it, photon scatter
DEFAULT_LATERAL_SIGMA_MM = 5.0    # the neighbourhood whose density sets the stretch
DEFAULT_LATERAL_EXPONENT = 0.9    # stretch = rho_eff ** -exponent; with the near radius, fitted to the Monte Carlo lung slabs (2 x 2 and 10 x 10 cm within 2 %)
DEFAULT_LATERAL_MAX_SCALE = 5.0   # density 0.2 and below
DEFAULT_LATERAL_SCALES = 5        # precomputed scales from 1 to the maximum, geometric
DEFAULT_SAMPLING = 0.003          # influence-matrix entries below 0.3 % of their column's maximum are sampled
REFERENCE_HALF_FIELD_MM = 50.0
DOSE_AT_DMAX_GY_PER_MU = 0.01
RAY_CHUNK_SAMPLES = 2_000_000
RAY_GRID_MAX = 40_000_000     # samples of the radiological-depth grid; coarser rays beyond
VOXEL_CHUNK = 2_000_000


def _settings():
    from ...config import get_settings  # lazy: the registry imports without settings
    return get_settings()


# ---------------------------------------------------------------------------
# NumPy or CuPy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Backend:
    xp: Any
    ndimage: Any
    fftconvolve: Any
    gpu: bool

    def to_host(self, a) -> np.ndarray:
        return a.get() if self.gpu else np.asarray(a)


def _restore_thread_locale() -> None:
    """Put the calling thread back on the process locale. Initialising the CUDA context and launching the first
    kernel (driver 580) set the thread's locale to C, after which Python's preferred encoding is ASCII and any file read or written without
    an explicit encoding fails on non-ASCII text. Linux (glibc) only; elsewhere a no-op."""
    try:
        import ctypes
        libc = ctypes.CDLL(None)
        libc.uselocale.restype = ctypes.c_void_p
        libc.uselocale.argtypes = [ctypes.c_void_p]
        libc.uselocale(ctypes.c_void_p(-1))            # LC_GLOBAL_LOCALE
    except Exception:  # pragma: no cover
        pass


_PAD = 2


def _lookup(be: Backend, arr, coords, padded=None):
    """Linear interpolation of ``arr`` at ``coords`` (``(ndim, n)`` index coordinates), zero outside
    ``[0, size - 1]`` on every axis: ``map_coordinates(order=1, mode="constant", cval=0)``.

    On the GPU the array is padded with zeros first. CuPy 14's constant mode on a float32 array takes the
    cell from the coordinate rounded to float32 and the fraction from the float64 coordinate, so a coordinate
    just below the last index (461.999994 of 463) reads one element past the array with a small negative
    weight: rare, garbage doses (up to 1e30) that depend on whatever memory follows the array. ``padded``: the
    array already padded by :data:`_PAD` (to pad a large array once for many lookups)."""
    if not be.gpu:
        return be.ndimage.map_coordinates(arr, coords, order=1, mode="constant", cval=0.0, prefilter=False)
    xp = be.xp
    src = xp.pad(arr, _PAD) if padded is None else padded
    val = be.ndimage.map_coordinates(src, coords + _PAD, order=1, mode="constant", cval=0.0, prefilter=False)
    outside = xp.zeros(val.shape, dtype=bool)
    for axis, size in enumerate(arr.shape):
        outside |= (coords[axis] < 0) | (coords[axis] > size - 1)
    return xp.where(outside, xp.zeros((), dtype=val.dtype), val)


def backend(device: str = "cpu") -> Backend:
    """The array backend: NumPy, or CuPy for ``gpu`` (an error when CuPy or a CUDA device is missing)
    and ``auto`` (CuPy when it works, else NumPy)."""
    device = (device or "cpu").lower()
    if device not in ("cpu", "gpu", "auto"):
        raise EngineParamError(f"pb device must be 'cpu', 'gpu' or 'auto', not {device!r}")
    if device in ("gpu", "auto"):
        try:
            import cupy as cp
            import cupyx.scipy.ndimage as cnd
            from cupyx.scipy.signal import fftconvolve as cfft
            if cp.cuda.runtime.getDeviceCount() < 1:
                raise RuntimeError("no CUDA device")
            cp.ones(2).sum()                # initialise the CUDA context and launch a first kernel here, then undo
            _restore_thread_locale()        # the locale change both make
            return Backend(cp, cnd, cfft, True)
        except Exception as exc:
            if device == "gpu":
                raise EngineUnavailableError(f"pb device 'gpu' needs CuPy and a working CUDA device: {exc}") from exc
            logger.info("pb: no usable GPU ({}); running on the CPU", exc)
    import scipy.ndimage as nd
    from scipy.signal import fftconvolve
    return Backend(np, nd, fftconvolve, False)


# ---------------------------------------------------------------------------
# Plan geometry
# ---------------------------------------------------------------------------

@dataclass
class _SegmentColumns:
    first_column: int
    segment: PhotonSegment
    beamlets: np.ndarray          # (n, 4): x, y, dx, dy in the BEV at isocenter
    segment_index: int = 0        # beam by beam, segment by segment over the plan


@dataclass
class _Direction:
    """One source position: a gantry and couch angle with an isocenter, and the segments delivered there."""

    gantry_deg: float
    couch_deg: float
    isocenter_mm: np.ndarray
    sad_mm: float
    segments: List[_SegmentColumns] = field(default_factory=list)

    def frame(self, collimator_deg: float = 0.0):
        xb, yb, d = iec_beam_frame(self.gantry_deg, self.couch_deg, collimator_deg)
        return self.isocenter_mm - self.sad_mm * d, xb, yb, d


def plan_directions(plan: PhotonPlan, shift_mm: Optional[Sequence[float]] = None) -> List[_Direction]:
    """The plan's source positions with their segments and the Dij column of each segment's first beamlet
    (columns run beam by beam, segment by segment, as :meth:`PhotonPlan.beamlets`). A segment with its own
    ``gantry_deg`` (an arc's control point) is a direction of its own."""
    shift = np.zeros(3) if shift_mm is None else np.asarray(shift_mm, float)
    out: List[_Direction] = []
    col = 0
    seg_index = 0
    for beam in plan.beams:
        groups: Dict[Tuple[float, float], _Direction] = {}
        iso = np.asarray(beam.isocenter_mm, float) + shift
        for seg in beam.segments:
            g = getattr(seg, "gantry_deg", None)
            g = float(beam.gantry_deg if g is None else g)
            key = (round(g, 6), round(float(beam.couch_deg), 6))
            if key not in groups:
                groups[key] = _Direction(g, float(beam.couch_deg), iso, float(beam.sad_mm))
            b = seg.beamlets()
            groups[key].segments.append(_SegmentColumns(col, seg, b, seg_index))
            col += b.shape[0]
            seg_index += 1
        out.extend(groups.values())
    return out


def _segment_extent(seg: PhotonSegment, beamlets: np.ndarray, apertures: bool) -> float:
    """The largest distance from the beam axis that the segment's fluence reaches (mm, isocenter plane)."""
    if apertures:
        xs = np.array(seg.x_jaw_mm, float)
        ys = np.array(seg.y_jaw_mm, float)
        return float(np.hypot(np.abs(xs).max(), np.abs(ys).max()))
    if beamlets.shape[0] == 0:
        return 0.0
    return float(np.hypot(np.abs(beamlets[:, 0]) + beamlets[:, 2] / 2, np.abs(beamlets[:, 1]) + beamlets[:, 3] / 2).max())


# ---------------------------------------------------------------------------
# Radiological depth
# ---------------------------------------------------------------------------

def radiological_depth(be: Backend, density, spacing_mm, origin_mm, source, xb, yb, d, sad_mm,
                       u, w, t, ray_spacing_mm: float, ray_step_mm: float):
    """Water-equivalent depth (mm) at points given by their isocenter-plane coordinates ``(u, w)`` and
    distance ``t`` from the source along the axis. Rays from the source through a regular ``(u, w)`` grid
    are sampled every ``ray_step_mm`` (trilinear density, zero outside the volume), integrated by the
    trapezoid rule and interpolated at the points."""
    xp = be.xp
    sx, sy, sz = (float(v) for v in spacing_mm)
    ox, oy, oz = (float(v) for v in origin_mm)
    nz, ny, nx = density.shape
    lo = np.array([ox - sx / 2, oy - sy / 2, oz - sz / 2])
    hi = np.array([ox + (nx - 0.5) * sx, oy + (ny - 0.5) * sy, oz + (nz - 0.5) * sz])
    corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])])
    t_start = max(float(((corners - source) @ d).min()), 1.0)
    t_end = float(t.max()) + ray_step_mm
    nt = int(math.ceil((t_end - t_start) / ray_step_mm)) + 2
    while True:
        # rays on a lattice anchored at the beam axis: symmetric fields get symmetric depths
        u0 = (math.floor(float(u.min()) / ray_spacing_mm) - 1) * ray_spacing_mm
        w0 = (math.floor(float(w.min()) / ray_spacing_mm) - 1) * ray_spacing_mm
        nu = int(math.ceil((float(u.max()) - u0) / ray_spacing_mm)) + 2
        nw = int(math.ceil((float(w.max()) - w0) / ray_spacing_mm)) + 2
        if nu * nw * nt <= RAY_GRID_MAX:
            break
        ray_spacing_mm *= 1.25
    grid = xp.zeros((nu, nw, nt), dtype=xp.float32)
    tt = xp.asarray(t_start + np.arange(nt) * ray_step_mm)
    ww = xp.asarray(w0 + np.arange(nw) * ray_spacing_mm)
    xb_, yb_, d_, s_ = (xp.asarray(np.asarray(v, float)) for v in (xb, yb, d, source))
    rows = max(1, RAY_CHUNK_SAMPLES // (nw * nt))
    padded = xp.pad(density, _PAD) if be.gpu else None
    for i0 in range(0, nu, rows):
        i1 = min(nu, i0 + rows)
        uu = xp.asarray(u0 + np.arange(i0, i1) * ray_spacing_mm)
        dirs = d_[None, None, :] + (uu[:, None, None] * xb_[None, None, :] + ww[None, :, None] * yb_[None, None, :]) / sad_mm
        length = xp.sqrt((dirs ** 2).sum(axis=-1))
        p = s_[None, None, None, :] + tt[None, None, :, None] * dirs[:, :, None, :]
        coords = xp.stack([(p[..., 2] - oz) / sz, (p[..., 1] - oy) / sy, (p[..., 0] - ox) / sx])
        rho = _lookup(be, density, coords.reshape(3, -1), padded).reshape(coords.shape[1:])
        acc = xp.cumsum((rho[..., 1:] + rho[..., :-1]) * 0.5, axis=-1) * ray_step_mm
        grid[i0:i1, :, 1:] = (acc * length[..., None]).astype(xp.float32)
    out = xp.empty(u.shape[0], dtype=xp.float32)
    for k0 in range(0, u.shape[0], VOXEL_CHUNK):
        k1 = min(u.shape[0], k0 + VOXEL_CHUNK)
        c = xp.stack([(u[k0:k1] - u0) / ray_spacing_mm, (w[k0:k1] - w0) / ray_spacing_mm, (t[k0:k1] - t_start) / ray_step_mm])
        out[k0:k1] = be.ndimage.map_coordinates(grid, c, order=1, mode="nearest", prefilter=False)
    return out


def _body(density: np.ndarray, min_density: float) -> np.ndarray:
    """The voxels that get dose: at least ``min_density``, and the cavities they enclose in each axial slice
    (airways, sinuses, bowel gas), as a planning system's external contour would; air outside the patient
    gets none."""
    from scipy.ndimage import binary_fill_holes
    solid = density >= min_density
    return np.stack([binary_fill_holes(sl) for sl in solid]) if solid.ndim == 3 else solid


# ---------------------------------------------------------------------------
# Fluence on the isocenter-plane grid
# ---------------------------------------------------------------------------

def _cover(lo: float, hi: float, centres: np.ndarray) -> np.ndarray:
    """Fraction of each 1 mm cell (centred at ``centres``) inside ``[lo, hi]``."""
    g = GRID_MM / 2.0
    return np.clip(np.minimum(hi, centres + g) - np.maximum(lo, centres - g), 0.0, GRID_MM) / GRID_MM


class _FluenceGrid:
    """A fluence map on cells centred at whole millimetres of the isocenter plane, ``[w, u]``."""

    def __init__(self, u_lo: float, u_hi: float, w_lo: float, w_hi: float) -> None:
        self.u_first = math.floor(u_lo / GRID_MM) - 1
        self.w_first = math.floor(w_lo / GRID_MM) - 1
        nu = math.ceil(u_hi / GRID_MM) + 2 - self.u_first
        nw = math.ceil(w_hi / GRID_MM) + 2 - self.w_first
        self.phi = np.zeros((nw, nu))

    def add(self, x0: float, x1: float, y0: float, y1: float, weight: float) -> None:
        if x1 <= x0 or y1 <= y0 or weight == 0.0:
            return
        i0 = max(0, math.floor(x0 / GRID_MM) - self.u_first - 1)
        i1 = min(self.phi.shape[1], math.ceil(x1 / GRID_MM) - self.u_first + 2)
        j0 = max(0, math.floor(y0 / GRID_MM) - self.w_first - 1)
        j1 = min(self.phi.shape[0], math.ceil(y1 / GRID_MM) - self.w_first + 2)
        cu = _cover(x0, x1, (self.u_first + np.arange(i0, i1)) * GRID_MM)
        cw = _cover(y0, y1, (self.w_first + np.arange(j0, j1)) * GRID_MM)
        self.phi[j0:j1, i0:i1] += weight * np.outer(cw, cu)


def aperture_rectangles(seg: PhotonSegment) -> List[Tuple[float, float, float, float]]:
    """The open area of a segment as rectangles ``(x0, x1, y0, y1)``: each MLC row clipped by the jaws."""
    xj0, xj1 = seg.x_jaw_mm
    yj0, yj1 = seg.y_jaw_mm
    out = []
    for row in seg.aperture_rows():
        x0, x1 = max(row.x_left_mm, xj0), min(row.x_right_mm, xj1)
        y0, y1 = max(row.y_min_mm, yj0), min(row.y_max_mm, yj1)
        if x1 > x0 and y1 > y0:
            out.append((x0, x1, y0, y1))
    return out


# ---------------------------------------------------------------------------
# Kernel tables
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _planes(kernel_key: str, n: int, fwhm_mm: float) -> np.ndarray:
    """The components on the isocenter-plane grid, each convolved with a Gaussian of ``fwhm_mm``: the
    fluence penumbra of the source size and the collimator edges, which the pencil kernel (a point source,
    an ideal edge) does not have. Convolving the kernel instead of each fluence gives both paths the same
    edge."""
    planes = _KERNELS[kernel_key].planes(n)
    if fwhm_mm > 0:
        from scipy.ndimage import gaussian_filter
        sigma = fwhm_mm / (2.0 * math.sqrt(2.0 * math.log(2.0))) / GRID_MM
        planes = np.stack([gaussian_filter(p, sigma, mode="constant", truncate=5.0) for p in planes])
    return planes


_KERNELS: Dict[str, PBKernel] = {}


def lateral_scales(max_scale: float, count: int) -> Tuple[float, ...]:
    """The precomputed kernel stretches: ``count`` values from 1 to ``max_scale``, geometrically spaced."""
    if count <= 1 or max_scale <= 1.0:
        return (1.0,)
    return tuple(float(max_scale ** (q / (count - 1))) for q in range(count))


@lru_cache(maxsize=8)
def _scaled_planes(kernel_key: str, n: int, fwhm_mm: float, scales: Tuple[float, ...], near_mm: float) -> np.ndarray:
    """``(len(scales), n, 2h+1, 2h+1)``: the components with their part within ``near_mm`` (a cosine taper to
    1.5 ``near_mm``) stretched by each scale, ``k(r / s) / s^2``, the rest as it is; then the fluence penumbra
    as :func:`_planes`. Scale 1 is :func:`_planes` itself."""
    from scipy.ndimage import gaussian_filter, map_coordinates
    raw = _KERNELS[kernel_key].planes(n)
    h = (raw.shape[1] - 1) // 2
    x = np.arange(-h, h + 1) * GRID_MM
    rr = np.hypot(x[None, :], x[:, None])
    win = np.clip((1.5 * near_mm - rr) / (0.5 * near_mm), 0.0, 1.0)
    win = np.sin(0.5 * math.pi * win) ** 2
    near = raw * win[None]
    far = raw - near
    sigma = fwhm_mm / (2.0 * math.sqrt(2.0 * math.log(2.0))) / GRID_MM
    out = []
    for sc in scales:
        if abs(sc - 1.0) < 1e-9:
            p = raw.copy()
        else:
            yy, xx = np.meshgrid(x / sc / GRID_MM + h, x / sc / GRID_MM + h, indexing="ij")
            p = far + np.stack([map_coordinates(c, [yy, xx], order=1, mode="constant", cval=0.0) for c in near]) / sc ** 2
        if fwhm_mm > 0:
            p = np.stack([gaussian_filter(c, sigma, mode="constant", truncate=5.0) for c in p])
        out.append(p)
    return np.stack(out)


@lru_cache(maxsize=32)
def _beamlet_tables(kernel_key: str, n: int, fwhm_mm: float, bx: float, by: float, reach_mm: float,
                    scales: Tuple[float, ...] = (1.0,), near_mm: float = DEFAULT_LATERAL_NEAR_MM) -> Tuple[np.ndarray, int]:
    """Each component at each scale convolved with a ``bx x by`` rectangle, on the 1 mm grid out to
    ``reach_mm``: ``(tables (n_scales, n, 2h+1, 2h+1) indexed [w, u], h)``."""
    from scipy.signal import fftconvolve
    planes = _scaled_planes(kernel_key, n, fwhm_mm, scales, near_mm)
    h_plane = (planes.shape[-1] - 1) // 2
    h = min(int(math.ceil(reach_mm / GRID_MM)) + 1, h_plane)
    m = int(math.ceil(max(bx, by) / 2 / GRID_MM)) + 1
    x = np.arange(-m, m + 1) * GRID_MM
    rect = np.outer(_cover(-by / 2, by / 2, x), _cover(-bx / 2, bx / 2, x))
    out = np.stack([np.stack([fftconvolve(p, rect, mode="same")[h_plane - h:h_plane + h + 1, h_plane - h:h_plane + h + 1] for p in ps])
                    for ps in planes])
    return out * GRID_MM ** 2, h


_ALPHA = 0.7548776662466927      # 1/plastic number and 1/golden ratio: the R2 low-discrepancy sequence
_BETA = 0.5698402909980532


def _weyl(xp, voxel_index, column: int, seed: int, mode: str = "weyl"):
    """Uniform numbers for the influence-matrix roulette, one per (voxel, beamlet). ``weyl``: for a fixed
    voxel the numbers over the beamlets form a Weyl sequence ``frac(c_v + j * beta)``, so the entries kept
    for a voxel follow the sum of their probabilities closely (quasi-random: the error shrinks like 1/N, not
    1/sqrt(N)); ``random``: independent draws."""
    if mode == "random":
        rng = np.random.default_rng((seed, column))
        return xp.asarray(rng.random(int(voxel_index.shape[0]), dtype=np.float32))
    v = voxel_index.astype(xp.float64)
    return ((v * _ALPHA + (column + 1) * _BETA + seed * 0.1234567) % 1.0).astype(xp.float32)


def _bilinear(be: Backend, table, fw, fu):
    """``table[w, u]`` at fractional indices (inside the table)."""
    xp = be.xp
    j = xp.clip(xp.floor(fw).astype(xp.int32), 0, table.shape[0] - 2)
    i = xp.clip(xp.floor(fu).astype(xp.int32), 0, table.shape[1] - 2)
    a = fw - j
    b = fu - i
    return ((1 - a) * ((1 - b) * table[j, i] + b * table[j, i + 1]) + a * ((1 - b) * table[j + 1, i] + b * table[j + 1, i + 1]))


def _bilinear_scaled(be: Backend, tables, k, f, fw, fu):
    """``tables[s, w, u]`` at fractional indices, linear between scales ``k`` and ``k + 1`` by ``f``."""
    xp = be.xp
    j = xp.clip(xp.floor(fw).astype(xp.int32), 0, tables.shape[1] - 2)
    i = xp.clip(xp.floor(fu).astype(xp.int32), 0, tables.shape[2] - 2)
    a = fw - j
    b = fu - i

    def at(kk):
        return ((1 - a) * ((1 - b) * tables[kk, j, i] + b * tables[kk, j, i + 1])
                + a * ((1 - b) * tables[kk, j + 1, i] + b * tables[kk, j + 1, i + 1]))
    return (1 - f) * at(k) + f * at(k + 1)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class _Run:
    """The settings of one computation, resolved from params and settings."""

    be: Backend
    kernel: PBKernel
    kernel_key: str
    n: int
    cutoff_mm: float
    min_density: float
    n_jobs: int
    ray_spacing_mm: Optional[float]
    ray_step_mm: Optional[float]
    factor: float
    fwhm_mm: float = DEFAULT_PENUMBRA_FWHM_MM
    sampling: float = DEFAULT_SAMPLING
    seed: int = 0
    sampling_mode: str = "weyl"
    scales: Tuple[float, ...] = (1.0,)
    near_mm: float = DEFAULT_LATERAL_NEAR_MM
    sigma_mm: float = DEFAULT_LATERAL_SIGMA_MM
    exponent: float = DEFAULT_LATERAL_EXPONENT


@dataclass
class PencilBeamEngine:
    """Photon dose engine on singular-value-decomposed pencil kernels (NumPy, optional CuPy)."""

    name: str = "pb"
    version: str = "1.1.1"
    modalities: List[str] = field(default_factory=lambda: ["PHOTON_IMRT"])
    test_only: bool = False

    # ----- configuration ------------------------------------------------

    def kernel(self, params: Optional[dict] = None) -> PBKernel:
        path = (params or {}).get("kernel_path")
        k = load_kernel(str(path) if path else None)
        _KERNELS.setdefault(k.fingerprint, k)
        return k

    def _run(self, params: Optional[dict]) -> _Run:
        p = dict(params or {})
        s = _settings()
        kern = self.kernel(p)
        n = int(p.get("n_components") or getattr(s, "pb_components", 0) or DEFAULT_COMPONENTS)
        if not 1 <= n <= 12:
            raise EngineParamError(f"pb n_components must be 1-12, not {n}")
        cutoff = float(p.get("cutoff_mm") or getattr(s, "pb_cutoff_mm", 0.0) or DEFAULT_CUTOFF_MM)
        if cutoff <= 0 or cutoff > 150:
            raise EngineParamError(f"pb cutoff_mm must be in (0, 150], not {cutoff}")
        be = backend(str(p.get("device", getattr(s, "pb_device", "cpu"))))
        fwhm = float(p.get("penumbra_fwhm_mm", DEFAULT_PENUMBRA_FWHM_MM))
        if not 0.0 <= fwhm <= 20.0:
            raise EngineParamError(f"pb penumbra_fwhm_mm must be in [0, 20], not {fwhm}")
        sampling = float(p.get("sampling_threshold", DEFAULT_SAMPLING))
        if not 0.0 <= sampling < 0.5:
            raise EngineParamError(f"pb sampling_threshold must be in [0, 0.5), not {sampling}")
        factor = p.get("output_factor_gy_per_unit")
        factor = float(factor) if factor is not None else _output_factor(kern.fingerprint, n, fwhm)
        scales: Tuple[float, ...] = (1.0,)
        if bool(p.get("lateral_scaling", True)):
            max_scale = float(p.get("lateral_max_scale", DEFAULT_LATERAL_MAX_SCALE))
            if not 1.0 <= max_scale <= 10.0:
                raise EngineParamError(f"pb lateral_max_scale must be in [1, 10], not {max_scale}")
            scales = lateral_scales(max_scale, int(p.get("lateral_scales", DEFAULT_LATERAL_SCALES)))
        near = float(p.get("lateral_near_mm", DEFAULT_LATERAL_NEAR_MM))
        sigma = float(p.get("lateral_sigma_mm", DEFAULT_LATERAL_SIGMA_MM))
        if near <= 0 or sigma < 0:
            raise EngineParamError("pb lateral_near_mm must be positive and lateral_sigma_mm not negative")
        return _Run(be, kern, kern.fingerprint, n, cutoff, float(p.get("min_density", DEFAULT_MIN_DENSITY)),
                    int(p.get("n_jobs", getattr(s, "pb_n_jobs", 4))), p.get("ray_spacing_mm"), p.get("ray_step_mm"), factor,
                    fwhm, sampling, int(p.get("seed", 0)), str(p.get("sampling_mode", "weyl")), scales, near, sigma,
                    float(p.get("lateral_exponent", DEFAULT_LATERAL_EXPONENT)))

    def calibration(self, params: Optional[dict] = None) -> dict:
        """The output calibration: Gy per MU per unit kernel response, so that a 10 x 10 cm field at
        SSD 100 cm gives 1 cGy per MU at d_max on the axis (from the components, as the engine computes)."""
        r = self._run(params)
        d, cax = _reference_cax(r.kernel_key, r.n, r.fwhm_mm)
        k = int(np.argmax(cax))
        return {"factor_gy_per_unit": r.factor, "dmax_mm": float(d[k]), "n_components": r.n,
                "penumbra_fwhm_mm": r.fwhm_mm, "kernel_fingerprint": r.kernel_key}

    # ----- health / validation ------------------------------------------

    def availability(self, params: Optional[dict] = None) -> Tuple[bool, str]:
        try:
            self.kernel(params)
        except Exception as exc:
            return False, f"pb kernel table not readable: {exc}"
        return True, ""

    def health(self) -> dict:
        ok, reason = self.availability()
        diag: Dict[str, Any] = {"reason": reason}
        if ok:
            k = self.kernel()
            diag.update(kernel_fingerprint=k.fingerprint, kernel_source=k.meta.get("source", {}).get("file"),
                        default_components=DEFAULT_COMPONENTS, default_cutoff_mm=DEFAULT_CUTOFF_MM)
            try:
                diag["gpu"] = backend("auto").gpu
            except Exception:  # pragma: no cover
                diag["gpu"] = False
        return {"name": self.name, "version": self.version, "modalities": list(self.modalities),
                "available": ok, "test_only": False, "diagnostics": diag}

    def validate(self, geometry: GeometryBundle, beam_model: BeamModelBundle, params: dict) -> List[str]:
        issues: List[str] = []
        if beam_model.result.modality.value != "PHOTON_IMRT":
            issues.append(f"pb engine requires PHOTON_IMRT, got {beam_model.result.modality.value}")
        if geometry.density is None or np.asarray(geometry.density).ndim != 3:
            issues.append("geometry density must be 3D")
        if beam_model.result.fluence_elements.total_count < 1:
            issues.append("beam model has no fluence elements")
        if not isinstance(beam_model.plan, PhotonPlan):
            issues.append("beam model plan is not a radiarch PhotonPlan (built before R1); rebuild the beam model")
        if self._origin(geometry) is None:
            issues.append("geometry has no grid origin; the engine cannot place the isocenter")
        ok, reason = self.availability(params)
        if not ok:
            issues.append(reason)
        try:
            self._run(params)
        except (EngineParamError, EngineUnavailableError) as exc:
            issues.append(str(exc))
        return issues

    # ----- per-direction geometry ---------------------------------------

    def _direction_voxels(self, r: _Run, density_dev, density_np: np.ndarray, spacing, origin, cand_flat, cand_pos,
                          direction: _Direction, reach_mm: float):
        """The candidate voxels this direction reaches, with ``(u0, w0)`` (collimator 0), ``z``, the inverse
        square and the radiological depth."""
        xp = r.be.xp
        src, xb, yb, d = direction.frame(0.0)
        v = cand_pos - xp.asarray(src)
        t = v @ xp.asarray(d)
        ok = t > 1.0
        sad = direction.sad_mm
        u = xp.where(ok, (v @ xp.asarray(xb)) * sad / xp.where(ok, t, 1.0), 1e9)
        w = xp.where(ok, (v @ xp.asarray(yb)) * sad / xp.where(ok, t, 1.0), 1e9)
        keep = ok & (u * u + w * w <= reach_mm * reach_mm)
        sel = xp.nonzero(keep)[0]
        if int(sel.size) == 0:
            return None
        u, w, t = u[sel], w[sel], t[sel]
        smin = float(min(spacing))
        ray = float(r.ray_spacing_mm or max(smin, 2.0))
        step = float(r.ray_step_mm or max(smin / 2.0, 0.5))
        drad = radiological_depth(r.be, density_dev, spacing, origin, src, xb, yb, d, sad, u, w, t, ray, step)
        return {"flat": cand_flat[sel], "u0": u, "w0": w, "t": t, "isq": (sad / t) ** 2, "drad": drad}

    def _amplitudes(self, r: _Run, vox) -> Any:
        """``F * ISQ * A_i(d_rad)``, shape ``(n, n_voxels)``."""
        xp = r.be.xp
        a, _ = r.kernel.decompose(r.n)
        depth = xp.asarray(r.kernel.depth_mm)
        amp = xp.stack([xp.interp(vox["drad"].astype(xp.float64), depth, xp.asarray(a[:, i])) for i in range(r.n)])
        return (amp * (vox["isq"] * r.factor)[None, :]).astype(xp.float32)

    @staticmethod
    def _rotated(xp, vox, collimator_deg: float):
        c, s = math.cos(math.radians(collimator_deg)), math.sin(math.radians(collimator_deg))
        return c * vox["u0"] + s * vox["w0"], -s * vox["u0"] + c * vox["w0"]

    def _prepare(self, r: _Run, density_zyx, spacing_mm, origin_mm, scenario: Optional[ScenarioSpec]):
        xp = r.be.xp
        density = np.asarray(density_zyx, dtype=np.float32)
        shift = None
        if scenario is not None:
            if scenario.setup_shift_mm is not None:
                shift = np.asarray(scenario.setup_shift_mm, float)
            if scenario.density_scale is not None:
                density = density * np.float32(scenario.density_scale)
            if scenario.range_scale is not None:
                logger.warning("pb: range_scale {} ignored (no meaning for photons)", scenario.range_scale)
        body = _body(density, r.min_density)
        flat = np.flatnonzero(body.ravel()).astype(np.int64)
        iz, iy, ix = np.unravel_index(flat, density.shape)
        sx, sy, sz = (float(v) for v in spacing_mm)
        ox, oy, oz = (float(v) for v in origin_mm)
        pos = np.stack([ox + ix * sx, oy + iy * sy, oz + iz * sz], axis=1)
        lat = self._lateral_position(r, density, body, (sz, sy, sx))
        return density, xp.asarray(density), xp.asarray(flat), xp.asarray(pos), shift, lat

    @staticmethod
    def _lateral_position(r: _Run, density: np.ndarray, body: np.ndarray, spacing_zyx):
        """Per voxel (flattened grid, on the device), the kernel stretch as a fractional index into
        ``r.scales``; None when lateral scaling is off or no voxel is below water density."""
        if len(r.scales) < 2:
            return None
        from scipy.ndimage import gaussian_filter
        rho = np.where(body, density, 0.0).astype(np.float32)
        if r.sigma_mm > 0:
            sig = [r.sigma_mm / float(v) for v in spacing_zyx]
            num = gaussian_filter(rho, sig, mode="nearest", truncate=3.0)
            den = gaussian_filter(body.astype(np.float32), sig, mode="nearest", truncate=3.0)
            rho = np.where(den > 1e-3, num / np.maximum(den, 1e-3), rho)
        stretch = np.minimum(np.clip(rho, 1e-3, 1.0) ** -r.exponent, r.scales[-1])
        q = np.log(stretch) / math.log(r.scales[1] / r.scales[0])
        q = np.clip(q, 0.0, len(r.scales) - 1).astype(np.float32).ravel()
        if not np.any(q > 1e-4):
            return None
        return r.be.xp.asarray(q)

    @staticmethod
    def _attach_lateral(r: _Run, vox, lat) -> None:
        """The voxels' scale interval ``k`` and fraction ``f``; absent without lateral scaling."""
        if lat is None or vox is None:
            return
        xp = r.be.xp
        q = lat[vox["flat"]]
        k = xp.clip(xp.floor(q).astype(xp.int32), 0, len(r.scales) - 2)
        vox["k"] = k
        vox["f"] = (q - k).astype(xp.float32)

    # ----- the influence matrix -------------------------------------------

    def influence_matrix(self, density_zyx: np.ndarray, spacing_mm: Sequence[float], origin_mm: Sequence[float],
                         plan: PhotonPlan, scenario: Optional[ScenarioSpec] = None, params: Optional[dict] = None) -> sp.csr_matrix:
        """``(n_voxels, n_beamlets)`` CSR in Gy per MU, rows in ``(z, y, x)`` C-order, columns in the plan's
        beamlet order; each beamlet evaluated within ``cutoff_mm`` of its edges."""
        r = self._run(params)
        xp = r.be.xp
        density, density_dev, cand_flat, cand_pos, shift, lat = self._prepare(r, density_zyx, spacing_mm, origin_mm, scenario)
        n_cols = plan.n_beamlets
        if n_cols == 0:
            raise EngineParamError("photon plan has no beamlets")
        columns: List[Optional[Tuple[np.ndarray, np.ndarray]]] = [None] * n_cols
        for direction in plan_directions(plan, shift):
            segs = [s for s in direction.segments if s.beamlets.shape[0]]
            if not segs:
                continue
            reach = max(_segment_extent(s.segment, s.beamlets, False) for s in segs) + r.cutoff_mm * math.sqrt(2.0)
            vox = self._direction_voxels(r, density_dev, density, spacing_mm, origin_mm, cand_flat, cand_pos, direction, reach)
            if vox is None:
                continue
            self._attach_lateral(r, vox, lat)
            amp = self._amplitudes(r, vox)
            for s in segs:
                for bx, by in {(float(b[2]), float(b[3])) for b in s.beamlets}:
                    self._tables_dev(r, bx, by)          # built before the threads share them
                u, w = self._rotated(xp, vox, s.segment.collimator_deg)
                order = xp.argsort(u)
                u_sorted = u[order]
                jobs = [(s.first_column + k, *map(float, s.beamlets[k])) for k in range(s.beamlets.shape[0])]
                def work(chunk, u=u, w=w, order=order, u_sorted=u_sorted, vox=vox, amp=amp):
                    return [(c, *self._beamlet_column(r, c, x, y, bx, by, u, w, order, u_sorted, vox, amp)) for c, x, y, bx, by in chunk]
                if r.be.gpu or r.n_jobs <= 1 or len(jobs) < 16:
                    results = work(jobs)
                else:
                    size = max(1, math.ceil(len(jobs) / (4 * r.n_jobs)))
                    with ThreadPoolExecutor(max_workers=r.n_jobs) as pool:
                        results = [x for part in pool.map(work, [jobs[i:i + size] for i in range(0, len(jobs), size)]) for x in part]
                for c, rows, vals in results:
                    columns[c] = (rows, vals)
        lengths = np.array([0 if c is None else c[0].size for c in columns], dtype=np.int64)
        indptr = np.concatenate([[0], np.cumsum(lengths)])
        rows = np.concatenate([c[0] for c in columns if c is not None]) if lengths.sum() else np.zeros(0, np.int64)
        vals = np.concatenate([c[1] for c in columns if c is not None]) if lengths.sum() else np.zeros(0, np.float32)
        n_vox = int(np.prod(density.shape))
        csc = sp.csc_matrix((vals.astype(np.float32), rows.astype(np.int32 if n_vox < 2 ** 31 else np.int64), indptr), shape=(n_vox, n_cols))
        return csc.tocsr()

    def _beamlet_column(self, r: _Run, column: int, x, y, bx, by, u, w, order, u_sorted, vox, amp):
        xp = r.be.xp
        tables, h = self._tables_dev(r, bx, by)
        reach_u, reach_w = r.cutoff_mm + bx / 2.0, r.cutoff_mm + by / 2.0
        lo = int(xp.searchsorted(u_sorted, x - reach_u))
        hi = int(xp.searchsorted(u_sorted, x + reach_u, side="right"))
        if hi <= lo:
            return np.zeros(0, np.int64), np.zeros(0, np.float32)
        sub = order[lo:hi]
        dw = w[sub] - y
        m = xp.abs(dw) <= reach_w
        sel = sub[m]
        fu = (u[sel] - x) / GRID_MM + h
        fw = dw[m] / GRID_MM + h
        val = xp.zeros(sel.shape[0], dtype=xp.float32)
        if "k" in vox:
            k, f = vox["k"][sel], vox["f"][sel]
            for i in range(r.n):
                val += amp[i, sel] * _bilinear_scaled(r.be, tables[:, i], k, f, fw, fu).astype(xp.float32)
        else:
            for i in range(r.n):
                val += amp[i, sel] * _bilinear(r.be, tables[0, i], fw, fu).astype(xp.float32)
        keep = val > 0
        if r.sampling > 0 and int(val.size):
            # Russian roulette below the threshold (matRad's influence-matrix sampling): an entry v < T is kept
            # with probability v / T and set to T, so every voxel's expected dose is unchanged
            thr = float(val.max()) * r.sampling
            low = val < thr
            rand = _weyl(xp, vox["flat"][sel], column, r.seed, r.sampling_mode)
            keep = keep & (~low | (rand * thr < val))
            val = xp.where(low, xp.float32(thr), val)
        return r.be.to_host(vox["flat"][sel[keep]]), r.be.to_host(val[keep])

    def _tables_dev(self, r: _Run, bx: float, by: float):
        key = (r.kernel_key, r.n, r.fwhm_mm, round(bx, 6), round(by, 6), round(r.cutoff_mm, 6), r.be.gpu, r.scales, r.near_mm)
        cache = self.__dict__.setdefault("_table_cache", {})
        if key not in cache:
            tab, h = _beamlet_tables(r.kernel_key, r.n, r.fwhm_mm, round(bx, 6), round(by, 6),
                                     r.cutoff_mm * math.sqrt(2.0) + max(bx, by), r.scales, r.near_mm)
            cache[key] = (r.be.xp.asarray(tab.astype(np.float32)), h)
        return cache[key]

    # ----- dose by fluence convolution -----------------------------------

    def compute_plan_dose(self, density_zyx: np.ndarray, spacing_mm: Sequence[float], origin_mm: Sequence[float],
                          plan: PhotonPlan, weights: Optional[np.ndarray] = None, scenario: Optional[ScenarioSpec] = None,
                          params: Optional[dict] = None) -> np.ndarray:
        """Dose in Gy on the density grid. ``weights`` (per beamlet, MU) default to the plan's metersets;
        ``params["fluence"]`` is ``"beamlets"`` (the default with weights) or ``"apertures"`` (the default
        without: each segment's MLC rows within its jaws, times its meterset)."""
        r = self._run(params)
        xp = r.be.xp
        mode = str((params or {}).get("fluence", "beamlets" if weights is not None else "apertures")).lower()
        if mode not in ("beamlets", "apertures"):
            raise EngineParamError(f"pb fluence must be 'beamlets' or 'apertures', not {mode!r}")
        if mode == "apertures" and weights is not None:
            raise EngineParamError("pb fluence 'apertures' uses the segments' metersets; pass no weights")
        if mode == "beamlets":
            wts = plan.beamlet_mu() if weights is None else np.asarray(weights, float)
            if wts.shape != (plan.n_beamlets,):
                raise EngineParamError(f"weights shape {wts.shape} != ({plan.n_beamlets},)")
        density, density_dev, cand_flat, cand_pos, shift, lat = self._prepare(r, density_zyx, spacing_mm, origin_mm, scenario)
        planes = xp.asarray(_scaled_planes(r.kernel_key, r.n, r.fwhm_mm, r.scales, r.near_mm).astype(np.float32))
        h_plane = (planes.shape[-1] - 1) // 2
        dose = xp.zeros(int(np.prod(density.shape)), dtype=xp.float32)
        for direction in plan_directions(plan, shift):
            segs = direction.segments
            apertures = mode == "apertures"
            reach = max((_segment_extent(s.segment, s.beamlets, apertures) for s in segs), default=0.0) + h_plane * GRID_MM * math.sqrt(2.0)
            vox = self._direction_voxels(r, density_dev, density, spacing_mm, origin_mm, cand_flat, cand_pos, direction, reach)
            if vox is None:
                continue
            self._attach_lateral(r, vox, lat)
            amp = self._amplitudes(r, vox)
            by_collimator: Dict[float, List[_SegmentColumns]] = {}
            for s in segs:
                by_collimator.setdefault(round(float(s.segment.collimator_deg), 6), []).append(s)
            for col, group in by_collimator.items():
                fl = self._fluence(group, apertures, None if apertures else wts)
                if fl is None:
                    continue
                idx, acc = self._fluence_dose(r, vox, amp, planes, fl, col)
                if idx is not None:
                    dose[vox["flat"][idx]] += acc
        return r.be.to_host(dose).reshape(density.shape).astype(np.float32)

    def _fluence_dose(self, r: _Run, vox, amp, planes, fl: "_FluenceGrid", collimator_deg: float):
        """The dose of one fluence map at the direction's voxels: ``(voxel positions in vox, dose)`` or
        ``(None, None)`` when the convolved map reaches none."""
        xp = r.be.xp
        h_plane = (planes.shape[-1] - 1) // 2
        u, w = self._rotated(xp, vox, collimator_deg)
        phi = xp.asarray(fl.phi.astype(np.float32))
        fu = (u / GRID_MM) - (fl.u_first - h_plane)
        fw = (w / GRID_MM) - (fl.w_first - h_plane)
        inside = (fu >= 0) & (fw >= 0) & (fu <= phi.shape[1] + 2 * h_plane - 1) & (fw <= phi.shape[0] + 2 * h_plane - 1)
        idx = xp.nonzero(inside)[0]
        if int(idx.size) == 0:
            return None, None
        acc = xp.zeros(idx.shape[0], dtype=xp.float32)
        if "k" not in vox:
            for i in range(r.n):
                conv = r.be.fftconvolve(phi, planes[0, i], mode="full") * GRID_MM ** 2
                acc += amp[i, idx] * _lookup(r.be, conv.astype(xp.float32), xp.stack([fw[idx], fu[idx]]))
            return idx, acc
        # lateral scaling: each scale's convolution where voxels use it, weighted between the two nearest scales
        k, f = vox["k"][idx], vox["f"][idx]
        for q in range(planes.shape[0]):
            wq = xp.where(k == q, 1.0 - f, 0.0) + xp.where(k + 1 == q, f, 0.0)
            sel = xp.nonzero(wq > 0)[0]
            if int(sel.size) == 0:
                continue
            coords = xp.stack([fw[idx[sel]], fu[idx[sel]]])
            part = xp.zeros(sel.shape[0], dtype=xp.float32)
            for i in range(r.n):
                conv = r.be.fftconvolve(phi, planes[q, i], mode="full") * GRID_MM ** 2
                part += amp[i, idx[sel]] * _lookup(r.be, conv.astype(xp.float32), coords)
            acc[sel] += (wq[sel] * part).astype(xp.float32)
        return idx, acc

    def segment_dose_matrix(self, density_zyx: np.ndarray, spacing_mm: Sequence[float], origin_mm: Sequence[float],
                            plan: PhotonPlan, scenario: Optional[ScenarioSpec] = None, params: Optional[dict] = None) -> sp.csr_matrix:
        """``(n_voxels, n_segments)`` CSR: the dose in Gy of one MU through each segment's aperture (its MLC
        rows within its jaws), segments beam by beam, segment by segment, arc sectors at their own angles.
        As the beamlet matrix: within ``cutoff_mm`` of the aperture, small entries sampled (unbiased). The
        matrix VMAT re-optimizes segment metersets with."""
        r = self._run(params)
        xp = r.be.xp
        density, density_dev, cand_flat, cand_pos, shift, lat = self._prepare(r, density_zyx, spacing_mm, origin_mm, scenario)
        planes = xp.asarray(_scaled_planes(r.kernel_key, r.n, r.fwhm_mm, r.scales, r.near_mm).astype(np.float32))
        n_seg = sum(len(b.segments) for b in plan.beams)
        columns: List[Optional[Tuple[np.ndarray, np.ndarray]]] = [None] * n_seg
        for direction in plan_directions(plan, shift):
            segs = direction.segments
            reach = max(_segment_extent(s.segment, s.beamlets, True) for s in segs) + r.cutoff_mm * math.sqrt(2.0)
            vox = self._direction_voxels(r, density_dev, density, spacing_mm, origin_mm, cand_flat, cand_pos, direction, reach)
            if vox is None:
                continue
            self._attach_lateral(r, vox, lat)
            amp = self._amplitudes(r, vox)
            for s in segs:
                fl = self._fluence([s], True, None, unit=True)
                if fl is None:
                    continue
                idx, val = self._fluence_dose(r, vox, amp, planes, fl, float(s.segment.collimator_deg))
                if idx is None:
                    continue
                keep = val > 0
                if r.sampling > 0 and int(val.size):
                    thr = float(val.max()) * r.sampling
                    low = val < thr
                    rand = _weyl(xp, vox["flat"][idx], s.segment_index, r.seed, r.sampling_mode)
                    keep = keep & (~low | (rand * thr < val))
                    val = xp.where(low, xp.float32(thr), val)
                columns[s.segment_index] = (r.be.to_host(vox["flat"][idx[keep]]), r.be.to_host(val[keep]))
        lengths = np.array([0 if c is None else c[0].size for c in columns], dtype=np.int64)
        indptr = np.concatenate([[0], np.cumsum(lengths)])
        rows = np.concatenate([c[0] for c in columns if c is not None]) if lengths.sum() else np.zeros(0, np.int64)
        vals = np.concatenate([c[1] for c in columns if c is not None]) if lengths.sum() else np.zeros(0, np.float32)
        n_vox = int(np.prod(density.shape))
        return sp.csc_matrix((vals.astype(np.float32), rows.astype(np.int64), indptr), shape=(n_vox, n_seg)).tocsr()

    @staticmethod
    def _fluence(group: List[_SegmentColumns], apertures: bool, weights: Optional[np.ndarray], unit: bool = False) -> Optional[_FluenceGrid]:
        rects: List[Tuple[float, float, float, float, float]] = []
        for s in group:
            if apertures:
                mu = 1.0 if unit else float(s.segment.mu)
                rects += [(x0, x1, y0, y1, mu) for x0, x1, y0, y1 in aperture_rectangles(s.segment)]
            else:
                for k, (x, y, bx, by) in enumerate(s.beamlets):
                    wt = float(weights[s.first_column + k])
                    if wt != 0.0:
                        rects.append((x - bx / 2, x + bx / 2, y - by / 2, y + by / 2, wt))
        if not rects:
            return None
        arr = np.asarray(rects)
        fl = _FluenceGrid(arr[:, 0].min(), arr[:, 1].max(), arr[:, 2].min(), arr[:, 3].max())
        for x0, x1, y0, y1, wt in rects:
            fl.add(x0, x1, y0, y1, wt)
        return fl

    # ----- DoseEnginePlugin -------------------------------------------------

    @staticmethod
    def _origin(geometry: GeometryBundle) -> Optional[Tuple[float, float, float]]:
        origin = getattr(geometry, "origin_mm", None)
        if origin is None:
            try:
                origin = geometry.result.grid_spec.origin_mm
            except Exception:
                origin = None
        return None if origin is None else tuple(float(v) for v in origin)

    def _plan(self, beam_model: BeamModelBundle) -> PhotonPlan:
        plan = beam_model.plan
        if not isinstance(plan, PhotonPlan):
            raise EngineParamError("beam model plan is not a radiarch PhotonPlan (built before R1); rebuild the beam model")
        return plan

    def build_influence(self, geometry, beam_model, scenario=None, params=None) -> InfluenceData:
        plan = self._plan(beam_model)
        origin = self._origin(geometry)
        if origin is None:
            raise EngineParamError("geometry has no grid origin; the engine cannot place the isocenter")
        expected = beam_model.result.fluence_elements.total_count
        if plan.n_beamlets != expected:
            raise EngineParamError(f"plan has {plan.n_beamlets} beamlets but the beam model records {expected} fluence elements")
        csr = self.influence_matrix(geometry.density, geometry.spacing_mm, origin, plan, scenario, params)
        return InfluenceData(indptr=csr.indptr.astype(np.int64), indices=csr.indices.astype(np.int32),
                             data=csr.data.astype(np.float32), n_voxels=int(csr.shape[0]), n_elements=int(csr.shape[1]))

    def compute_dose(self, geometry, beam_model, weights, scenario=None, params=None) -> NominalDose:
        """The dose of beamlet weights by fluence convolution with the full kernel (no cutoff)."""
        plan = self._plan(beam_model)
        expected = beam_model.result.fluence_elements.total_count
        weights = np.asarray(weights, dtype=np.float32)
        if weights.shape != (expected,):
            raise EngineParamError(f"weights shape {weights.shape} != ({expected},)")
        origin = self._origin(geometry)
        if origin is None:
            raise EngineParamError("geometry has no grid origin; the engine cannot place the isocenter")
        p = dict(params or {})
        p.setdefault("fluence", "beamlets")
        dose = self.compute_plan_dose(geometry.density, geometry.spacing_mm, origin, plan, weights, scenario, p)
        return NominalDose(dose=dose)

    def apply_influence(self, influence: InfluenceData, weights: np.ndarray, grid_shape: tuple) -> NominalDose:
        weights = np.asarray(weights, dtype=np.float32)
        if weights.shape != (influence.n_elements,):
            raise EngineParamError(f"weights shape {weights.shape} != ({influence.n_elements},)")
        if int(np.prod(grid_shape)) != influence.n_voxels:
            raise EngineParamError(f"grid_shape {grid_shape} does not match influence.n_voxels {influence.n_voxels}")
        csr = sp.csr_matrix((influence.data, influence.indices, influence.indptr), shape=(influence.n_voxels, influence.n_elements))
        return NominalDose(dose=np.asarray(csr @ weights).reshape(grid_shape).astype(np.float32))

    def compute_grad(self, geometry, beam_model, weights, dL_dDose, scenario=None, params=None):
        raise EngineUnavailableError(
            "pb doesn't implement adjoint gradients. Build a Dij via build_influence() "
            "and compute the gradient as Dij.T @ dL_dDose in the optimizer."
        )


@lru_cache(maxsize=16)
def _reference_cax(fingerprint: str, n: int, fwhm_mm: float) -> Tuple[np.ndarray, np.ndarray]:
    """Central-axis response per unit fluence of the 10 x 10 cm reference field at SSD 100 cm, inverse
    square included, on a 0.25 mm depth grid from 2 to 60 mm, from the engine's own (blurred) planes."""
    kern = _KERNELS[fingerprint]
    planes = _planes(fingerprint, n, fwhm_mm)
    h = (planes.shape[1] - 1) // 2
    x = np.arange(-h, h + 1) * GRID_MM
    cover = _cover(-REFERENCE_HALF_FIELD_MM, REFERENCE_HALF_FIELD_MM, x)
    per_component = np.einsum("w,iwu,u->i", cover, planes, cover) * GRID_MM ** 2
    d = np.arange(2.0, 60.0, 0.25)
    cax = kern.weights_at(d, n).T @ per_component * (kern.sad_mm / (kern.sad_mm + d)) ** 2
    return d, cax


@lru_cache(maxsize=16)
def _output_factor(fingerprint: str, n: int, fwhm_mm: float) -> float:
    _, cax = _reference_cax(fingerprint, n, fwhm_mm)
    peak = float(cax.max())
    if peak <= 0:
        raise EngineUnavailableError("pb kernel gives no dose for the reference field")
    return DOSE_AT_DMAX_GY_PER_MU / peak


register_engine(PencilBeamEngine())


__all__ = ["PencilBeamEngine", "Backend", "backend", "plan_directions", "radiological_depth", "aperture_rectangles"]
