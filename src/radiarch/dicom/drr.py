"""Digitally reconstructed radiographs by ray marching (roadmap R6).

For a beam at a gantry and couch angle the source sits ``SAD`` from the
isocenter along the beam axis; every pixel of a plane through the isocenter,
normal to the axis, is joined to the source and the CT is sampled along the
line (trilinear, ``scipy.ndimage.map_coordinates``) at a fixed step between
the ray's entry into and exit from the CT box. The pixel value is the line
integral of the relative linear attenuation ``max(0, 1 + HU / 1000)`` in
mm of water equivalent, so bone is bright and air dark, as DRRs are shown.

Frames follow radiarch's conventions (``services/spot_placement``): in the
patient (DICOM LPS) frame the beam at gantry 0 travels along ``+y``
(anterior to posterior for a head-first supine patient); the gantry turns
about ``z``, the couch about ``y``; the beam's-eye-view ``x`` lies along the
patient's ``x`` at gantry 0 and ``y`` along the patient's ``z``, which is the
IEC gantry system for that patient position. SimpleITK has no ray-cast
interpolator, hence numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np
from scipy import ndimage


def _rotate(vec: Sequence[float], angle_rad: float, axis: str) -> np.ndarray:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    x, y, z = (float(v) for v in vec)
    if axis == "y":
        return np.array([x * c + z * s, y, -x * s + z * c])
    if axis == "z":
        return np.array([x * c - y * s, x * s + y * c, z])
    raise ValueError(axis)


def beam_frame(gantry_deg: float, couch_deg: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(x_bev, y_bev, direction)`` unit vectors in the patient frame."""
    g, c = math.radians(gantry_deg), math.radians(couch_deg)
    x = _rotate(_rotate([1.0, 0.0, 0.0], g, "z"), c, "y")
    y = _rotate(_rotate([0.0, 0.0, 1.0], g, "z"), c, "y")
    d = _rotate(_rotate([0.0, 1.0, 0.0], g, "z"), c, "y")
    return x, y, d


@dataclass
class DRR:
    image: np.ndarray            # (rows, cols) float32, line integrals in mm water equivalent
    pixel_mm: Tuple[float, float]
    size_mm: Tuple[float, float]
    gantry_deg: float
    couch_deg: float
    sad_mm: float
    isocenter_mm: Tuple[float, float, float]

    @property
    def upper_left_mm(self) -> Tuple[float, float]:
        """BEV ``(x, y)`` of the centre of the upper-left pixel (rows run down ``-y``)."""
        rows, cols = self.image.shape
        return (-(cols - 1) / 2.0 * self.pixel_mm[0], (rows - 1) / 2.0 * self.pixel_mm[1])

    def to_uint16(self) -> np.ndarray:
        img = np.asarray(self.image, dtype=np.float64)
        top = float(img.max()) if img.size else 0.0
        if top <= 0.0:
            return np.zeros(img.shape, dtype=np.uint16)
        return np.rint(img / top * 65535.0).astype(np.uint16)


def compute_drr(ct_hu_zyx: np.ndarray, origin_mm: Sequence[float], spacing_mm: Sequence[float],
                isocenter_mm: Sequence[float], gantry_deg: float, couch_deg: float = 0.0, *, sad_mm: float = 1000.0,
                size_mm: Tuple[float, float] = (300.0, 300.0), pixel_mm: Tuple[float, float] = (1.0, 1.0),
                step_mm: float = 1.0, rows_per_chunk: int = 32) -> DRR:
    """The DRR of ``ct_hu_zyx`` for a beam; see the module docstring."""
    ct = np.asarray(ct_hu_zyx, dtype=np.float32)
    if ct.ndim != 3:
        raise ValueError("the CT must be a (z, y, x) volume")
    mu = np.clip(1.0 + ct / 1000.0, 0.0, None).astype(np.float32)
    origin = np.asarray(origin_mm, dtype=float)
    spacing = np.asarray(spacing_mm, dtype=float)
    nz, ny, nx = ct.shape
    box_lo = origin - 0.5 * spacing
    box_hi = origin + (np.array([nx, ny, nz]) - 0.5) * spacing

    x_bev, y_bev, direction = beam_frame(gantry_deg, couch_deg)
    iso = np.asarray(isocenter_mm, dtype=float)
    source = iso - float(sad_mm) * direction

    cols = max(1, int(round(size_mm[0] / pixel_mm[0])))
    rows = max(1, int(round(size_mm[1] / pixel_mm[1])))
    u = (np.arange(cols) - (cols - 1) / 2.0) * pixel_mm[0]
    v = ((rows - 1) / 2.0 - np.arange(rows)) * pixel_mm[1]        # rows run down -y
    image = np.zeros((rows, cols), dtype=np.float32)

    for r0 in range(0, rows, rows_per_chunk):
        vv = v[r0:r0 + rows_per_chunk]
        # pixel positions on the isocenter plane: (chunk_rows, cols, 3)
        P = iso[None, None, :] + u[None, :, None] * x_bev[None, None, :] + vv[:, None, None] * y_bev[None, None, :]
        D = P - source[None, None, :]
        L = np.linalg.norm(D, axis=-1, keepdims=True)
        D = D / L
        # slab intersection with the CT box
        with np.errstate(divide="ignore", invalid="ignore"):
            t_lo = (box_lo[None, None, :] - source[None, None, :]) / D
            t_hi = (box_hi[None, None, :] - source[None, None, :]) / D
        t_near = np.nanmax(np.minimum(t_lo, t_hi), axis=-1)
        t_far = np.nanmin(np.maximum(t_lo, t_hi), axis=-1)
        length = np.clip(t_far - t_near, 0.0, None)
        n_steps = int(max(2, math.ceil(float(length.max()) / step_mm))) if length.size else 2
        f = (np.arange(n_steps) + 0.5) / n_steps
        T = t_near[..., None] + length[..., None] * f[None, None, :]            # (cr, cols, n)
        pts = source[None, None, None, :] + T[..., None] * D[:, :, None, :]       # (cr, cols, n, 3)
        idx = (pts - origin[None, None, None, :]) / spacing[None, None, None, :]
        coords = np.stack([idx[..., 2].ravel(), idx[..., 1].ravel(), idx[..., 0].ravel()])
        samples = ndimage.map_coordinates(mu, coords, order=1, mode="constant", cval=0.0).reshape(T.shape)
        image[r0:r0 + rows_per_chunk] = (samples.sum(axis=-1) * (length / n_steps)).astype(np.float32)

    return DRR(image=image, pixel_mm=(float(pixel_mm[0]), float(pixel_mm[1])), size_mm=(cols * pixel_mm[0], rows * pixel_mm[1]),
               gantry_deg=float(gantry_deg), couch_deg=float(couch_deg), sad_mm=float(sad_mm),
               isocenter_mm=(float(iso[0]), float(iso[1]), float(iso[2])))


__all__ = ["DRR", "beam_frame", "compute_drr"]
