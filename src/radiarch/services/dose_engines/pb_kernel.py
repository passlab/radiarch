"""Pencil kernels of the native photon engine (roadmap R8).

The kernel ``k(rho, d)`` is the dose per primary photon of an infinitely narrow
6 MV pencil entering water, at depth ``d`` and at distance ``rho`` from the
pencil's axis measured in the isocenter plane, with the inverse square
removed. A broad beam of primary fluence ``Phi`` (photons per mm^2 in the
isocenter plane) then gives

    D(u, w, d) = (SAD / z)^2 * (Phi (*) k(., d))(u, w)

where ``(u, w)`` is the point's projection onto the isocenter plane and ``z``
its distance from the source along the beam axis (Bortfeld, Schlegel and Rhein,
Med Phys 20:311, 1993). Writing the kernel as a sum of a few products,
``k(rho, d) ~ sum_i A_i(d) k_i(rho)``, makes the convolution depth independent:
each component is convolved once per field and the depth enters through the
weights ``A_i``.

Where the kernel comes from
---------------------------
:mod:`radiarch.validation.mc_reference` (``--pencil``) runs OpenGATE: the
Mohan 6 MV spectrum (the spectrum of the CCC kernels and of the R7
references) from a point source 1000 mm above a 400 x 400 x 300 mm water
box, collimated to a 0.5 mm pencil at the surface, scored on a 1 mm grid to
+-40 mm and a 5 mm grid to +-200 mm, 2 mm in depth. It writes annulus means
per depth. :func:`build_table` turns these into the table this module ships
(``engines/pb/pb_6mv_kernel.npz``):

1. per depth, a 2D kernel on a 1 mm grid to +-200 mm: the fine annuli
   inside 28 mm, the coarse annuli (interpolated in radius) beyond 36 mm,
   blended between;
2. moved to the isocenter plane (lengths divided by ``M = (SAD + d) / SAD``)
   by integrating the piecewise-constant kernel over each isocenter-plane
   cell, so every depth keeps its integral exactly;
3. averaged over radius bins of that grid (0.5 mm to 50 mm, 2 mm beyond),
   with the cell counts, so expanding the table back onto the grid
   conserves the integral too;
4. below the last 30 mm of the phantom (no backscatter there) each radius
   bin continues as an exponential fitted between 200 and 270 mm, to 500 mm.

The decomposition into components (:meth:`PBKernel.decompose`) is done when
the engine loads, by a singular value decomposition of the cumulative kernel
(the fraction of each depth's dose within a radius), so that truncating it
errs in field dose evenly over field sizes and depths.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

SAD_MM = 1000.0
GRID_MM = 1.0                     # isocenter-plane kernel grid
RADIUS_MM = 200.0                 # the kernel's extent (the Monte Carlo's coarse grid)
STITCH_MM = (28.0, 36.0)          # fine annuli inside, coarse beyond, blended between
FINE_BIN_MM, FINE_TO_MM, TAIL_BIN_MM = 0.5, 50.0, 2.0
TAIL_FIT_MM = (200.0, 270.0)      # exponential continuation fitted here ...
TAIL_FROM_MM, TAIL_TO_MM = 270.0, 500.0   # ... and used from here to here
DEFAULT_COMPONENTS = 3


# ---------------------------------------------------------------------------
# Building the table from the Monte Carlo tallies
# ---------------------------------------------------------------------------

def mc_bins(n: int, spacing_mm: float, bin_mm: float, r_max_mm: float) -> Tuple[np.ndarray, np.ndarray]:
    """The annulus index of every cell of an ``n x n`` grid and the cell count per annulus, exactly as
    :func:`radiarch.validation.mc_reference.radial_profiles` bins them (index ``nb`` = outside)."""
    c = (n - 1) / 2.0
    x = (np.arange(n) - c) * spacing_mm
    rr = np.hypot(x[:, None], x[None, :])
    edges = np.arange(0.0, r_max_mm + bin_mm, bin_mm)
    nb = len(edges) - 1
    idx = np.digitize(rr, edges) - 1
    counts = np.bincount(idx[idx < nb].ravel(), minlength=nb)[:nb]
    return idx, counts


def iso_bin_edges() -> np.ndarray:
    return np.concatenate([np.arange(0.0, FINE_TO_MM, FINE_BIN_MM), np.arange(FINE_TO_MM, RADIUS_MM + TAIL_BIN_MM / 2, TAIL_BIN_MM)])


def _grid(half_cells: int) -> np.ndarray:
    x = np.arange(-half_cells, half_cells + 1) * GRID_MM
    return np.hypot(x[:, None], x[None, :])


def _interp_matrix(edges: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Rows of linear-interpolation weights: ``W @ f(edges) = f(q)`` (``q`` within the edges)."""
    j = np.clip(np.searchsorted(edges, q, side="right") - 1, 0, len(edges) - 2)
    f = (q - edges[j]) / (edges[j + 1] - edges[j])
    w = np.zeros((len(q), len(edges)))
    w[np.arange(len(q)), j] = 1.0 - f
    w[np.arange(len(q)), j + 1] = f
    return w


def to_isocenter_plane(plane_geo: np.ndarray, magnification: float) -> np.ndarray:
    """Divide the plane's lengths by ``magnification``, conserving its integral: the kernel is taken as
    constant in each 1 mm cell; the integral image is interpolated at the scaled cell corners (exact for
    piecewise-constant cells) and differenced."""
    n = plane_geo.shape[0]
    s = np.zeros((n + 1, n + 1))
    s[1:, 1:] = plane_geo.cumsum(0).cumsum(1) * GRID_MM ** 2
    edges = (np.arange(n + 1) - n / 2.0) * GRID_MM
    q = np.clip(edges * magnification, edges[0], edges[-1])
    w = _interp_matrix(edges, q)
    sq = w @ s @ w.T
    return (sq[1:, 1:] - sq[:-1, 1:] - sq[1:, :-1] + sq[:-1, :-1]) / GRID_MM ** 2


def build_table(mc: Dict[str, np.ndarray]) -> Tuple[Dict[str, np.ndarray], dict]:
    """The shipped table from the pencil Monte Carlo (``pencil_6mv.npz`` loaded as a dict)."""
    depth = np.asarray(mc["depth_mm"], float)
    sad = float(mc["sad_mm"])
    fine_idx, fine_counts = mc_bins(81, 1.0, 0.5, 40.0)
    coarse_idx, coarse_counts = mc_bins(81, 5.0, 5.0, 200.0)
    nb_fine = fine_counts.size
    if mc["fine_dose"].shape[1] != nb_fine or mc["coarse_dose"].shape[1] != coarse_counts.size:
        raise ValueError("the Monte Carlo tallies do not have the expected annuli (81 cells at 1 mm and at 5 mm)")
    half = int(round(RADIUS_MM / GRID_MM))
    r_big = _grid(half)
    n_big = 2 * half + 1
    # the fine grid sits at the centre of the big grid, cell for cell
    lo = half - 40
    fine_on_big = np.full((n_big, n_big), nb_fine)
    fine_on_big[lo:lo + 81, lo:lo + 81] = fine_idx
    inside_fine = fine_on_big < nb_fine
    w_coarse = np.clip((r_big - STITCH_MM[0]) / (STITCH_MM[1] - STITCH_MM[0]), 0.0, 1.0)
    w_coarse[~inside_fine] = 1.0
    coarse_r = np.asarray(mc["coarse_r_mm"], float)
    keep_c = coarse_counts > 0
    edges = iso_bin_edges()
    iso_idx = np.digitize(r_big, edges) - 1
    nbi = len(edges) - 1
    iso_idx[r_big >= RADIUS_MM] = nbi
    iso_counts = np.bincount(iso_idx[iso_idx < nbi].ravel(), minlength=nbi)[:nbi]

    table = np.zeros((depth.size, nbi))
    integral_mc = np.zeros(depth.size)
    integral_iso = np.zeros(depth.size)
    stitch_ratio = np.zeros(depth.size)
    for k, d in enumerate(depth):
        fine = np.asarray(mc["fine_dose"][k], float)
        coarse = np.asarray(mc["coarse_dose"][k], float)
        fvals = np.append(fine, 0.0)[np.minimum(fine_on_big, nb_fine)]
        cvals = np.interp(r_big, coarse_r[keep_c], coarse[keep_c], right=0.0)
        cvals[r_big >= RADIUS_MM] = 0.0
        plane = (1.0 - w_coarse) * fvals + w_coarse * cvals
        integral_mc[k] = float((coarse * coarse_counts).sum() * 25.0)
        ring = (r_big >= 20.0) & (r_big < STITCH_MM[1]) & inside_fine
        stitch_ratio[k] = float(fvals[ring].sum() / max(cvals[ring].sum(), 1e-300))
        iso = to_isocenter_plane(plane, (sad + d) / sad)
        sums = np.bincount(iso_idx.ravel(), weights=iso.ravel(), minlength=nbi + 1)[:nbi]
        table[k] = sums / np.maximum(iso_counts, 1)
        integral_iso[k] = float((table[k] * iso_counts).sum() * GRID_MM ** 2)

    # continue each bin exponentially below TAIL_FROM_MM (no backscatter in the last few cm of the phantom)
    fit = (depth >= TAIL_FIT_MM[0]) & (depth <= TAIL_FIT_MM[1])
    keep = depth < TAIL_FROM_MM
    step = float(np.median(np.diff(depth)))
    new_depth = np.arange(depth[keep][-1] + step, TAIL_TO_MM + step / 2, step)
    ext = np.zeros((new_depth.size, nbi))
    for b in range(nbi):
        y = table[fit, b]
        if np.all(y > 0):
            slope, icpt = np.polyfit(depth[fit], np.log(y), 1)
            slope = min(slope, 0.0)
            ext[:, b] = np.exp(icpt + slope * new_depth)
        else:
            ext[:, b] = max(float(y.mean()), 0.0) if y.size else 0.0
    out = {
        "depth_mm": np.concatenate([depth[keep], new_depth]),
        "bin_edges_mm": edges,
        "bin_counts": iso_counts.astype(np.int64),
        "table": np.concatenate([table[keep], ext]).astype(np.float64),
        "grid_mm": np.float64(GRID_MM),
        "sad_mm": np.float64(sad),
        "n_measured_depths": np.int64(int(keep.sum())),
    }
    rel = np.abs(integral_iso / np.maximum(integral_mc, 1e-300) - 1.0)
    check = {
        "integral_iso_vs_mc_max_rel": float(rel[depth >= 4.0].max()),
        "stitch_fine_over_coarse_20_36mm": {"min": float(stitch_ratio.min()), "max": float(stitch_ratio.max()),
                                            "median": float(np.median(stitch_ratio))},
    }
    return out, check


# ---------------------------------------------------------------------------
# The kernel at run time
# ---------------------------------------------------------------------------

def default_kernel_path() -> Path:
    from .mcsquare_driver import engine_assets_dir
    return engine_assets_dir("pb") / "pb_6mv_kernel.npz"


@dataclass
class PBKernel:
    depth_mm: np.ndarray
    bin_edges_mm: np.ndarray
    bin_counts: np.ndarray
    table: np.ndarray            # (n_depth, n_bins): cell-mean dose per primary, inverse square removed
    grid_mm: float
    sad_mm: float
    fingerprint: str
    meta: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "PBKernel":
        path = Path(path) if path else default_kernel_path()
        raw = path.read_bytes()
        z = np.load(path)
        meta_path = path.with_suffix(".json")
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        return cls(np.asarray(z["depth_mm"], float), np.asarray(z["bin_edges_mm"], float), np.asarray(z["bin_counts"], np.int64),
                   np.asarray(z["table"], float), float(z["grid_mm"]), float(z["sad_mm"]),
                   hashlib.sha256(raw).hexdigest()[:16], meta)

    @property
    def half_cells(self) -> int:
        return int(round(float(self.bin_edges_mm[-1]) / self.grid_mm))

    def cell_bins(self, half_cells: Optional[int] = None) -> np.ndarray:
        """The radius bin of every cell of the ``(2h+1)^2`` isocenter-plane grid; ``n_bins`` beyond the table."""
        h = self.half_cells if half_cells is None else int(half_cells)
        r = _grid(h) * (self.grid_mm / GRID_MM)
        nb = self.bin_counts.size
        idx = np.digitize(r, self.bin_edges_mm) - 1
        idx[(r >= self.bin_edges_mm[-1]) | (idx < 0)] = nb
        return idx

    def integral(self) -> np.ndarray:
        """Per depth, the kernel's integral over the isocenter plane (Gy mm^2 per primary)."""
        return (self.table * self.bin_counts).sum(axis=1) * self.grid_mm ** 2

    def decompose(self, n: int = DEFAULT_COMPONENTS) -> Tuple[np.ndarray, np.ndarray]:
        """``(A, k)``: weights ``A`` of shape ``(n_depth, n)`` and radial components ``k`` of shape
        ``(n, n_bins)`` with ``table ~ A @ k``. The decomposition is of the cumulative kernel, the
        fraction of each depth's dose within radius ``R``, which is the dose of a circular field of radius
        ``R`` up to a constant: truncating it errs in field dose, evenly over field sizes and depths. (An
        SVD of the kernel itself errs point by point and those errors add up over a broad field: with
        three components, 6 % at 20 cm and 30 % in the build-up of a 30 cm field.)"""
        return _decompose(self, int(n))

    def planes(self, n: int = DEFAULT_COMPONENTS, half_cells: Optional[int] = None) -> np.ndarray:
        """The components as ``(n, 2h+1, 2h+1)`` planes on the isocenter-plane grid."""
        _, comps = self.decompose(n)
        idx = self.cell_bins(half_cells)
        padded = np.concatenate([comps, np.zeros((comps.shape[0], 1))], axis=1)
        return padded[:, idx].astype(np.float64)

    def weights_at(self, depth_mm: np.ndarray, n: int = DEFAULT_COMPONENTS) -> np.ndarray:
        """``A_i(d)`` at radiological depths ``d`` (mm), linear between table depths, the first depth's
        value above it and the last depth's below it: shape ``(n, len(d))``."""
        a, _ = self.decompose(n)
        d = np.asarray(depth_mm, float)
        return np.stack([np.interp(d, self.depth_mm, a[:, i]) for i in range(a.shape[1])])

    def field_dose(self, half_width_mm: float, depth_mm: np.ndarray, n: Optional[int] = None) -> np.ndarray:
        """Central-axis dose per unit fluence of a square field (side ``2 * half_width``) at SSD = SAD, inverse
        square included: the full table, or the ``n``-component decomposition."""
        h = self.half_cells
        x = np.arange(-h, h + 1) * self.grid_mm
        cover = np.clip(np.minimum(half_width_mm, x + self.grid_mm / 2) - np.maximum(-half_width_mm, x - self.grid_mm / 2), 0.0, self.grid_mm) / self.grid_mm
        mask = np.outer(cover, cover)
        idx = self.cell_bins()
        nb = self.bin_counts.size
        per_bin = np.bincount(idx.ravel(), weights=mask.ravel(), minlength=nb + 1)[:nb] * self.grid_mm ** 2
        d = np.asarray(depth_mm, float)
        if n is None:
            vals = self.table @ per_bin
            col = np.interp(d, self.depth_mm, vals)
        else:
            a, comps = self.decompose(n)
            col = self.weights_at(d, n).T @ (comps @ per_bin)
        return col * (self.sad_mm / (self.sad_mm + d)) ** 2


@lru_cache(maxsize=16)
def _decompose_cached(fingerprint: str, n: int, table_bytes: bytes, counts_bytes: bytes, shape: Tuple[int, int]):
    table = np.frombuffer(table_bytes, dtype=np.float64).reshape(shape)
    counts = np.frombuffer(counts_bytes, dtype=np.int64).astype(float)
    integral = (table * counts).sum(axis=1)
    cumulative = np.cumsum(table * counts, axis=1) / integral[:, None]     # fraction of the dose within each bin's outer radius
    u, s, vt = np.linalg.svd(cumulative, full_matrices=False)
    n = min(n, s.size)
    a = u[:, :n] * s[:n] * integral[:, None]
    comps = np.diff(np.concatenate([np.zeros((n, 1)), vt[:n]], axis=1), axis=1) / np.where(counts > 0, counts, 1.0)
    comps[:, counts == 0] = 0.0
    for i in range(n):                         # the sign that makes the component's integral positive
        if vt[i, -1] < 0:
            comps[i] *= -1.0
            a[:, i] *= -1.0
    return a, comps


def _decompose(kernel: PBKernel, n: int):
    t = np.ascontiguousarray(kernel.table, dtype=np.float64)
    c = np.ascontiguousarray(kernel.bin_counts, dtype=np.int64)
    return _decompose_cached(kernel.fingerprint, n, t.tobytes(), c.tobytes(), t.shape)


@lru_cache(maxsize=4)
def load_kernel(path: Optional[str] = None) -> PBKernel:
    return PBKernel.load(Path(path) if path else None)


# ---------------------------------------------------------------------------
# Command line: build the shipped table from the Monte Carlo
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the native photon engine's kernel table from the pencil Monte Carlo")
    ap.add_argument("--mc", type=Path, required=True, help="pencil_6mv.npz written by radiarch.validation.mc_reference --pencil")
    ap.add_argument("--out", type=Path, default=None, help="default: engines/pb/pb_6mv_kernel.npz")
    args = ap.parse_args(argv)
    mc = dict(np.load(args.mc))
    table, check = build_table(mc)
    out = args.out or default_kernel_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **table)
    mc_meta_path = args.mc.with_suffix(".json")
    mc_meta = json.loads(mc_meta_path.read_text()) if mc_meta_path.is_file() else {}
    kern = PBKernel.load(out)
    meta = {
        "kernel": "6 MV pencil kernel in water, isocenter-plane radius, inverse square removed; Gy per primary photon",
        "source": {"file": args.mc.name, "sha256": hashlib.sha256(args.mc.read_bytes()).hexdigest()[:16],
                   "primaries": int(mc["primaries"]), **{k: mc_meta.get(k) for k in ("spectrum", "physics", "opengate_version", "date") if k in mc_meta}},
        "construction": {"grid_mm": GRID_MM, "radius_mm": RADIUS_MM, "stitch_mm": list(STITCH_MM),
                         "bins": f"{FINE_BIN_MM} mm to {FINE_TO_MM} mm, {TAIL_BIN_MM} mm to {RADIUS_MM} mm",
                         "tail": f"exponential per bin fitted over {TAIL_FIT_MM[0]:g}-{TAIL_FIT_MM[1]:g} mm, used from {TAIL_FROM_MM:g} to {TAIL_TO_MM:g} mm",
                         "measured_depths": int(table["n_measured_depths"])},
        "checks": check,
        "fingerprint": kern.fingerprint,
        "built": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(f"wrote {out} (fingerprint {kern.fingerprint}); checks {json.dumps(check)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
