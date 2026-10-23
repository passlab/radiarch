"""Radiarch's own photon plan model (roadmap R1).

A photon plan is a list of beams; a beam is a gantry/couch position with an
isocenter and a list of segments (control points); a segment is a jaw
setting, an MLC aperture and a meterset. Beamlets — the fluence elements the
dose engines and the optimizer work with — are derived from a segment's
aperture on a regular grid in the beam's-eye view at isocenter.

The model is pydantic so a plan serializes to JSON, pickles, and validates
on load. Geometry conventions follow DICOM RT / IEC 61217: angles in degrees,
positions in millimetres, the BEV ``x`` axis across the leaves and ``y``
along the leaf travel... with ``(x, y)`` at isocenter, and the MLC described
as one row per leaf pair ``[y_min, y_max, x_left, x_right]``.

Beamlet placement reproduces the half-pixel grid OpenTPS uses
(``PlanPhotonSegment.createBeamletsFromSegments``), so a plan built here has
the same beamlets as the plans the vendored OpenTPS copy would build: a
200 mm × 200 mm open field at 5 mm gives 40 × 40 = 1600.
"""

from __future__ import annotations

import math
from typing import List, Literal, Optional, Sequence, Tuple

import numpy as np
from pydantic import BaseModel, Field, model_validator

from .common import DicomPlanProvenance


class MLCRow(BaseModel):
    """One leaf pair: its extent along the leaf bank and the two leaf tips."""

    y_min_mm: float
    y_max_mm: float
    x_left_mm: float
    x_right_mm: float

    @model_validator(mode="after")
    def _ordered(self) -> "MLCRow":
        if self.y_max_mm <= self.y_min_mm:
            raise ValueError("MLCRow needs y_max_mm > y_min_mm")
        if self.x_right_mm < self.x_left_mm:
            raise ValueError("MLCRow needs x_right_mm >= x_left_mm (closed leaves may touch)")
        return self

    @property
    def opening_mm(self) -> float:
        return self.x_right_mm - self.x_left_mm


class PhotonSegment(BaseModel):
    """A control point: jaws, MLC aperture and meterset."""

    control_point_index: int = Field(default=0, ge=0)
    mu: float = Field(..., ge=0.0, description="Meterset delivered through this aperture.")
    x_jaw_mm: Tuple[float, float] = Field(..., description="(X1, X2) jaw positions at isocenter.")
    y_jaw_mm: Tuple[float, float] = Field(..., description="(Y1, Y2) jaw positions at isocenter.")
    collimator_deg: float = 0.0
    mlc_rows: List[MLCRow] = Field(
        default_factory=list,
        description="One row per leaf pair, ordered by y. Empty = jaws-only open field.",
    )
    beamlet_spacing_mm: Tuple[float, float] = Field(
        default=(5.0, 5.0), description="Beamlet pixel size (x, y) in the BEV at isocenter."
    )
    gantry_deg: Optional[float] = Field(
        default=None, ge=0.0, lt=360.0,
        description="Gantry angle of an arc sector (the mid-angle of its control-point interval); None = the beam's.",
    )

    @model_validator(mode="after")
    def _jaws_ordered(self) -> "PhotonSegment":
        if self.x_jaw_mm[1] <= self.x_jaw_mm[0] or self.y_jaw_mm[1] <= self.y_jaw_mm[0]:
            raise ValueError("jaw tuples must be (min, max) with max > min")
        if self.beamlet_spacing_mm[0] <= 0 or self.beamlet_spacing_mm[1] <= 0:
            raise ValueError("beamlet_spacing_mm must be positive")
        return self

    def aperture_rows(self) -> List[MLCRow]:
        """The MLC rows, or a single row spanning the jaws for a jaws-only field."""
        if self.mlc_rows:
            return self.mlc_rows
        return [MLCRow(y_min_mm=self.y_jaw_mm[0], y_max_mm=self.y_jaw_mm[1],
                       x_left_mm=self.x_jaw_mm[0], x_right_mm=self.x_jaw_mm[1])]

    def beamlets(self) -> np.ndarray:
        """Beamlet centres and sizes inside the aperture: an ``(n, 4)`` array of
        ``x_mm, y_mm, dx_mm, dy_mm``.

        Same construction as OpenTPS: a square field of view spanning the MLC
        bank, beamlet centres on a half-pixel grid, a leaf pair contributes
        only when its opening exceeds one beamlet, and a beamlet is kept when
        its centre is strictly inside both the leaf opening and the jaws.
        """
        bx, by = float(self.beamlet_spacing_mm[0]), float(self.beamlet_spacing_mm[1])
        rows = self.aperture_rows()
        xj0, xj1 = self.x_jaw_mm
        yj0, yj1 = self.y_jaw_mm
        fov = abs(rows[0].y_min_mm) + abs(rows[-1].y_max_mm)
        n_x = math.ceil(fov / bx)
        n_y = math.ceil(fov / by)
        half_x, half_y = round(n_x / 2), round(n_y / 2)

        seen = set()
        out: List[Tuple[float, float, float, float]] = []
        for row in rows:
            if row.opening_mm <= bx:
                continue
            j_min = math.floor((row.y_min_mm + by / 2) / by + half_y)
            j_max = math.ceil((row.y_max_mm + by / 2) / by + half_y)
            for j in range(j_min, j_max + 1):
                y = (j - half_y) * by - by / 2
                if y < row.y_min_mm or y > row.y_max_mm or y < yj0 or y > yj1:
                    continue
                i_min = math.floor((row.x_left_mm + bx / 2) / bx + half_x)
                i_max = math.ceil((row.x_right_mm + bx / 2) / bx + half_x)
                for i in range(i_min, i_max + 1):
                    x = (i - half_x) * bx - bx / 2
                    if xj0 < x < xj1 and row.x_left_mm < x < row.x_right_mm:
                        key = (round(x, 6), round(y, 6))
                        if key in seen:      # a centre exactly on a leaf boundary
                            continue
                        seen.add(key)
                        out.append((x, y, bx, by))
        return np.asarray(out, dtype=float).reshape(-1, 4)

    def coverage_beamlets(self) -> np.ndarray:
        """Every beamlet cell the aperture touches, with the fraction of its area that is open: an
        ``(n, 5)`` array of ``x_mm, y_mm, dx_mm, dy_mm, fraction``.

        For recomputing a delivered plan (:meth:`radiarch.services.dose_engines.ccc.CCCEngine.compute_delivered_dose`):
        :meth:`beamlets` drops leaf pairs no wider than one beamlet and cells whose centre lies outside the
        opening, which loses most of a sliding-window arc's narrow apertures. Cells lie on the same lattice
        (edges on multiples of the spacing); the open area of a cell is the area of the leaf openings and the
        jaws that falls inside it. The optimizer's columns stay those of :meth:`beamlets`.
        """
        bx, by = float(self.beamlet_spacing_mm[0]), float(self.beamlet_spacing_mm[1])
        xj0, xj1 = self.x_jaw_mm
        yj0, yj1 = self.y_jaw_mm
        area: dict = {}
        for row in self.aperture_rows():
            x0, x1 = max(row.x_left_mm, xj0), min(row.x_right_mm, xj1)
            y0, y1 = max(row.y_min_mm, yj0), min(row.y_max_mm, yj1)
            if x1 <= x0 or y1 <= y0:
                continue
            for j in range(math.floor(y0 / by), math.ceil(y1 / by)):
                hy = min(y1, (j + 1) * by) - max(y0, j * by)
                if hy <= 0:
                    continue
                for i in range(math.floor(x0 / bx), math.ceil(x1 / bx)):
                    hx = min(x1, (i + 1) * bx) - max(x0, i * bx)
                    if hx > 0:
                        area[(i, j)] = area.get((i, j), 0.0) + hx * hy
        cells = sorted(area.items(), key=lambda kv: (kv[0][1], kv[0][0]))
        out = [((i + 0.5) * bx, (j + 0.5) * by, bx, by, min(a / (bx * by), 1.0)) for (i, j), a in cells if a > 1e-9 * bx * by]
        return np.asarray(out, dtype=float).reshape(-1, 5)

    @property
    def n_beamlets(self) -> int:
        return int(self.beamlets().shape[0])


def mid_angle_deg(g0: float, g1: float, direction: str) -> float:
    """The angle halfway from ``g0`` to ``g1`` turning in ``direction`` (``CW``: increasing angles)."""
    return (g0 + 0.5 * arc_step_deg(g0, g1, direction)) % 360.0


def arc_step_deg(g0: float, g1: float, direction: str) -> float:
    """The signed rotation from ``g0`` to ``g1`` in ``direction``: positive for ``CW``, negative for ``CC``."""
    if direction == "CW":
        return (g1 - g0) % 360.0
    return -((g0 - g1) % 360.0)


class ArcControlPoint(BaseModel):
    """A control point of an arc: the gantry angle, jaws and leaves when the beam's cumulative meterset
    reaches ``cumulative_mu``. Between control points the gantry turns, the leaves and jaws move linearly and
    the meterset difference is delivered (DICOM RT Plan, a DYNAMIC beam)."""

    gantry_deg: float = Field(..., ge=0.0, lt=360.0)
    cumulative_mu: float = Field(..., ge=0.0)
    x_jaw_mm: Tuple[float, float]
    y_jaw_mm: Tuple[float, float]
    mlc_rows: List[MLCRow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _jaws_ordered(self) -> "ArcControlPoint":
        if self.x_jaw_mm[1] < self.x_jaw_mm[0] or self.y_jaw_mm[1] < self.y_jaw_mm[0]:
            raise ValueError("arc control point jaws must be (min, max)")
        return self


class PhotonArc(BaseModel):
    """A volumetric-modulated arc: control points every few degrees, turning in one direction.

    Its dose is computed sector by sector (:meth:`sectors`): each control-point interval becomes one static
    segment at the interval's mid-angle, with the mean of the two control points' leaves and jaws and the
    interval's meterset, the usual approximation for intervals of 2-4 degrees."""

    direction: Literal["CW", "CC"]
    collimator_deg: float = 0.0
    control_points: List[ArcControlPoint] = Field(..., min_length=2)

    @model_validator(mode="after")
    def _consistent(self) -> "PhotonArc":
        cps = self.control_points
        if abs(cps[0].cumulative_mu) > 1e-9:
            raise ValueError("an arc's first control point has cumulative_mu 0")
        total_turn = 0.0
        for a, b in zip(cps, cps[1:]):
            if b.cumulative_mu < a.cumulative_mu - 1e-9:
                raise ValueError("cumulative_mu must not decrease along the arc")
            step = abs(arc_step_deg(a.gantry_deg, b.gantry_deg, self.direction))
            if step <= 1e-6 or step > 30.0:
                raise ValueError(f"control points {a.gantry_deg:g} -> {b.gantry_deg:g} deg: each interval must turn "
                                 f"the gantry by more than 0 and at most 30 degrees in the arc's direction")
            total_turn += step
        if total_turn > 360.0 + 1e-6:
            raise ValueError("an arc turns at most 360 degrees")
        shapes = {tuple((round(r.y_min_mm, 6), round(r.y_max_mm, 6)) for r in cp.mlc_rows) for cp in cps}
        if len(shapes) > 1:
            raise ValueError("all control points of an arc must have the same leaf pairs")
        return self

    @property
    def total_mu(self) -> float:
        return float(self.control_points[-1].cumulative_mu)

    @property
    def start_deg(self) -> float:
        return float(self.control_points[0].gantry_deg)

    @property
    def stop_deg(self) -> float:
        return float(self.control_points[-1].gantry_deg)

    @property
    def length_deg(self) -> float:
        cps = self.control_points
        return float(sum(abs(arc_step_deg(a.gantry_deg, b.gantry_deg, self.direction)) for a, b in zip(cps, cps[1:])))

    def sectors(self, beamlet_spacing_mm: Tuple[float, float] = (5.0, 5.0)) -> List[PhotonSegment]:
        """One static segment per control-point interval (see the class docstring)."""
        out: List[PhotonSegment] = []
        cps = self.control_points
        for k, (a, b) in enumerate(zip(cps, cps[1:])):
            rows = [MLCRow(y_min_mm=ra.y_min_mm, y_max_mm=ra.y_max_mm,
                           x_left_mm=0.5 * (ra.x_left_mm + rb.x_left_mm), x_right_mm=0.5 * (ra.x_right_mm + rb.x_right_mm))
                    for ra, rb in zip(a.mlc_rows, b.mlc_rows)]
            xj = (0.5 * (a.x_jaw_mm[0] + b.x_jaw_mm[0]), 0.5 * (a.x_jaw_mm[1] + b.x_jaw_mm[1]))
            yj = (0.5 * (a.y_jaw_mm[0] + b.y_jaw_mm[0]), 0.5 * (a.y_jaw_mm[1] + b.y_jaw_mm[1]))
            if xj[1] <= xj[0]:
                xj = (xj[0] - 0.5, xj[0] + 0.5)      # closed jaws: a sliver, the sector delivers nothing anyway
            if yj[1] <= yj[0]:
                yj = (yj[0] - 0.5, yj[0] + 0.5)
            out.append(PhotonSegment(
                control_point_index=k, mu=max(0.0, b.cumulative_mu - a.cumulative_mu), x_jaw_mm=xj, y_jaw_mm=yj,
                collimator_deg=self.collimator_deg, mlc_rows=rows,
                beamlet_spacing_mm=(float(beamlet_spacing_mm[0]), float(beamlet_spacing_mm[1])),
                gantry_deg=mid_angle_deg(a.gantry_deg, b.gantry_deg, self.direction),
            ))
        return out


class PhotonBeam(BaseModel):
    """A gantry/couch position with its isocenter and control points; or an arc (``arc`` set), whose
    ``segments`` are the arc's sectors and whose ``gantry_deg`` is the arc's start."""

    beam_id: str = Field(..., min_length=1, max_length=64)
    gantry_deg: float = Field(..., ge=0.0, lt=360.0)
    couch_deg: float = Field(default=0.0, ge=-180.0, le=180.0)
    isocenter_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    sad_mm: float = Field(default=1000.0, gt=0.0)
    energy_mv: Optional[float] = Field(default=None, description="Nominal beam energy (MV) when known; the engines use their own beam model.")
    segments: List[PhotonSegment] = Field(..., min_length=1)
    arc: Optional[PhotonArc] = Field(default=None, description="Set for a VMAT arc: the control points; segments are its sectors.")

    @model_validator(mode="after")
    def _arc_sectors(self) -> "PhotonBeam":
        if self.arc is not None:
            if len(self.segments) != len(self.arc.control_points) - 1:
                raise ValueError("an arc beam has one segment per control-point interval (PhotonBeam.from_arc builds them)")
            if any(seg.gantry_deg is None for seg in self.segments):
                raise ValueError("an arc beam's segments carry their sector angles")
        return self

    @classmethod
    def from_arc(cls, beam_id: str, arc: PhotonArc, couch_deg: float = 0.0,
                 isocenter_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0), sad_mm: float = 1000.0,
                 energy_mv: Optional[float] = None, beamlet_spacing_mm: Tuple[float, float] = (5.0, 5.0)) -> "PhotonBeam":
        return cls(beam_id=beam_id, gantry_deg=arc.start_deg, couch_deg=couch_deg, isocenter_mm=isocenter_mm, sad_mm=sad_mm,
                   energy_mv=energy_mv, segments=arc.sectors(beamlet_spacing_mm), arc=arc)

    def segment_gantry_deg(self, seg: "PhotonSegment") -> float:
        """The gantry angle a segment is delivered at: its own (an arc sector) or the beam's."""
        return float(self.gantry_deg if seg.gantry_deg is None else seg.gantry_deg)

    def beamlets(self) -> np.ndarray:
        parts = [s.beamlets() for s in self.segments]
        return np.concatenate(parts, axis=0) if parts else np.zeros((0, 4))

    def beamlet_segment_index(self) -> np.ndarray:
        return np.concatenate([np.full(s.n_beamlets, k, dtype=np.int32)
                               for k, s in enumerate(self.segments)]) if self.segments else np.zeros(0, np.int32)

    def beamlet_mu(self) -> np.ndarray:
        """Meterset carried by each beamlet: its segment's MU (OpenTPS convention)."""
        return np.concatenate([np.full(s.n_beamlets, float(s.mu))
                               for s in self.segments]) if self.segments else np.zeros(0)

    @property
    def n_beamlets(self) -> int:
        return sum(s.n_beamlets for s in self.segments)

    @property
    def meterset(self) -> float:
        return float(sum(s.mu for s in self.segments))


class PhotonPlan(BaseModel):
    """The plan: beams in delivery order. Beamlets flatten beam by beam,
    segment by segment, in the order ``beamlets()`` returns them — that is
    the column order of every Dij built from this plan."""

    name: str = "PhotonPlan"
    modality: Literal["PHOTON_IMRT"] = "PHOTON_IMRT"
    beams: List[PhotonBeam] = Field(..., min_length=1)
    dicom: Optional[DicomPlanProvenance] = Field(default=None, description="Set when the plan was read from a DICOM RT Plan.")

    def beamlets(self) -> np.ndarray:
        return np.concatenate([b.beamlets() for b in self.beams], axis=0)

    def beamlet_beam_index(self) -> np.ndarray:
        return np.concatenate([np.full(b.n_beamlets, k, dtype=np.int32)
                               for k, b in enumerate(self.beams)])

    def beamlet_mu(self) -> np.ndarray:
        return np.concatenate([b.beamlet_mu() for b in self.beams])

    @property
    def n_beamlets(self) -> int:
        return sum(b.n_beamlets for b in self.beams)

    @property
    def isocenter_mm(self) -> Tuple[float, float, float]:
        """The first beam's isocenter (all beams share it in v1)."""
        return tuple(float(v) for v in self.beams[0].isocenter_mm)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> "PhotonPlan":
        return cls.model_validate_json(text)


def open_field_mlc_rows(
    jaw_x_mm: Tuple[float, float],
    jaw_y_mm: Tuple[float, float],
    leaf_width_mm: float,
) -> List[MLCRow]:
    """Leaf pairs parked at the X jaws, tiling the Y jaw opening."""
    y_min, y_max = float(jaw_y_mm[0]), float(jaw_y_mm[1])
    x_min, x_max = float(jaw_x_mm[0]), float(jaw_x_mm[1])
    n = max(1, math.ceil((y_max - y_min) / float(leaf_width_mm)))
    rows = []
    for k in range(n):
        y0 = y_min + k * float(leaf_width_mm)
        y1 = min(y0 + float(leaf_width_mm), y_max)
        rows.append(MLCRow(y_min_mm=y0, y_max_mm=y1, x_left_mm=x_min, x_right_mm=x_max))
    return rows


def open_field_segment(
    jaw_x_mm: Tuple[float, float],
    jaw_y_mm: Tuple[float, float],
    leaf_width_mm: float,
    mu: float,
    beamlet_spacing_mm: Tuple[float, float] = (5.0, 5.0),
    control_point_index: int = 0,
    collimator_deg: float = 0.0,
) -> PhotonSegment:
    """One open aperture the size of the jaw opening."""
    return PhotonSegment(
        control_point_index=control_point_index,
        mu=mu,
        collimator_deg=float(collimator_deg),
        x_jaw_mm=(float(jaw_x_mm[0]), float(jaw_x_mm[1])),
        y_jaw_mm=(float(jaw_y_mm[0]), float(jaw_y_mm[1])),
        mlc_rows=open_field_mlc_rows(jaw_x_mm, jaw_y_mm, leaf_width_mm),
        beamlet_spacing_mm=(float(beamlet_spacing_mm[0]), float(beamlet_spacing_mm[1])),
    )


__all__ = [
    "MLCRow",
    "PhotonSegment",
    "ArcControlPoint",
    "PhotonArc",
    "arc_step_deg",
    "mid_angle_deg",
    "PhotonBeam",
    "PhotonPlan",
    "open_field_mlc_rows",
    "open_field_segment",
]
