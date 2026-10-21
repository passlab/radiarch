"""Leaf sequencing: optimized fluence → deliverable MLC apertures (roadmap R4).

The optimizer returns one weight per beamlet of an open-field plan. This
module turns those weights into step-and-shoot segments a machine can
deliver:

1. **Fluence maps.** Per beam, the beamlet weights are binned onto the
   machine's leaf pairs (a 10 mm leaf averages the two 5 mm beamlet rows it
   covers) and the beamlet columns.
2. **Sequencing** (Bortfeld, Boyer et al. 1994; the unidirectional
   sliding-window decomposition). The map is quantized to ``levels`` equal
   steps; in every row the i-th segment opens from the i-th rising edge to
   the i-th falling edge of the quantized profile, so any profile, convex or
   not, decomposes exactly into equal-weight segments. Segment i of every row
   is delivered together as one aperture.
3. **Machine limits.** Leaf tips are clipped to the retraction and
   overtravel limits, closed pairs are parked, the jaws are set around the
   open area, apertures smaller than the machine's minimum area are dropped,
   and interdigitation is reported when the machine forbids it.
4. **Segment weights.** Each aperture's dose is the beamlet doses it covers
   (fractional coverage of every beamlet, from the Dij of the open-field
   plan), so the segment metersets are re-optimized against the same
   objectives with the same solvers; segments under the minimum MU are
   removed and the weights re-optimized once more.
5. **Deliverability.** Segment count, MU per segment, areas, the largest leaf
   travel between consecutive segments and the beam-on and leaf-travel time
   per beam at the machine's dose-rate and leaf-speed limits.

Not modelled: leaf transmission, tongue-and-groove, rounded leaf ends, head
scatter of small apertures; the aperture dose is the sum of beamlet doses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from loguru import logger

from ..models.machine import MLCSpec, PhotonMachineSpec
from ..models.photon_plan import MLCRow, PhotonBeam, PhotonPlan, PhotonSegment


# ---------------------------------------------------------------------------
# Fluence maps on the machine's leaf pairs
# ---------------------------------------------------------------------------

@dataclass
class FluenceMap:
    beam_index: int
    beam_id: str
    pair_indices: List[int]                 # MLC leaf pairs (indices into the machine's boundaries) with beamlets
    x_edges_mm: np.ndarray                  # (n_cols + 1,) column edges
    values: np.ndarray                      # (n_rows, n_cols) fluence weight per cell
    beamlet_cells: Dict[int, Tuple[int, int]]  # beamlet index (within the beam) → (row, col)

    @property
    def x_centres_mm(self) -> np.ndarray:
        return 0.5 * (self.x_edges_mm[:-1] + self.x_edges_mm[1:])


def fluence_maps(plan: PhotonPlan, weights: np.ndarray, mlc: MLCSpec) -> List[FluenceMap]:
    """Per beam, the beamlet weights on the (leaf pair × column) grid."""
    weights = np.asarray(weights, dtype=np.float64).ravel()
    if weights.shape[0] != plan.n_beamlets:
        raise ValueError(f"{weights.shape[0]} weights for {plan.n_beamlets} beamlets")
    maps: List[FluenceMap] = []
    offset = 0
    for b, beam in enumerate(plan.beams):
        bl = beam.beamlets()
        n = bl.shape[0]
        w = weights[offset:offset + n]
        offset += n
        if n == 0:
            continue
        dx = float(np.median(bl[:, 2]))
        x_lo = float(np.min(bl[:, 0] - bl[:, 2] / 2.0))
        cols = np.rint((bl[:, 0] - bl[:, 2] / 2.0 - x_lo) / dx).astype(int)
        n_cols = int(cols.max()) + 1
        x_edges = x_lo + dx * np.arange(n_cols + 1)
        # a beamlet covers every leaf pair its y extent overlaps (a 10 mm beamlet
        # spans two 5 mm pairs); its centre pair is its cell
        bounds = np.asarray(mlc.leaf_boundaries_mm, dtype=float)
        centre_pairs = []
        hits: List[Tuple[int, int, float]] = []          # (pair, beamlet, weight)
        for i, (y, dy) in enumerate(zip(bl[:, 1], bl[:, 3])):
            p = mlc.pair_index(float(y))
            if p is None:
                raise ValueError(f"beam {beam.beam_id}: beamlet at y={y:.1f} mm lies outside the MLC bank {mlc.extent_mm}")
            centre_pairs.append(p)
            lo, hi = float(y) - float(dy) / 2.0 + 1e-9, float(y) + float(dy) / 2.0 - 1e-9
            for q in np.flatnonzero((bounds[:-1] < hi) & (bounds[1:] > lo)):
                hits.append((int(q), i, float(w[i])))
        pair_list = sorted({q for q, _, _ in hits})
        row_of = {p: r for r, p in enumerate(pair_list)}
        rows = np.asarray([row_of[q] for q, _, _ in hits])
        hit_cols = np.asarray([cols[i] for _, i, _ in hits])
        values = np.zeros((len(pair_list), n_cols))
        counts = np.zeros_like(values)
        np.add.at(values, (rows, hit_cols), np.asarray([ww for _, _, ww in hits]))
        np.add.at(counts, (rows, hit_cols), 1.0)
        values = np.where(counts > 0, values / np.maximum(counts, 1), 0.0)
        cells = {i: (int(row_of[centre_pairs[i]]), int(cols[i])) for i in range(n)}
        maps.append(FluenceMap(b, beam.beam_id, pair_list, x_edges, values, cells))
    return maps


# ---------------------------------------------------------------------------
# Sequencing
# ---------------------------------------------------------------------------

@dataclass
class Aperture:
    """One step-and-shoot segment: a tip pair per MLC leaf pair of the fluence map."""

    beam_index: int
    left_mm: np.ndarray      # (n_rows,) x of the left tip; closed pairs have left == right
    right_mm: np.ndarray
    level_weight: float      # the fluence step this segment delivers (before weight optimization)
    mu: float = 0.0
    issues: List[str] = field(default_factory=list)

    def open_rows(self) -> np.ndarray:
        return self.right_mm > self.left_mm

    def area_mm2(self, pair_heights_mm: np.ndarray) -> float:
        return float(np.sum((self.right_mm - self.left_mm) * pair_heights_mm))


def sequence_row(levels_row: np.ndarray, x_edges: np.ndarray) -> List[Tuple[float, float]]:
    """Segments of one leaf pair from its integer-level profile: the i-th segment
    opens at the i-th rising edge and closes at the i-th falling edge."""
    q = np.concatenate([[0], np.asarray(levels_row, dtype=int), [0]])
    diff = np.diff(q)                      # at edge j (between columns j-1 and j)
    ups = np.repeat(np.arange(diff.shape[0]), np.maximum(diff, 0))
    downs = np.repeat(np.arange(diff.shape[0]), np.maximum(-diff, 0))
    assert ups.shape == downs.shape
    return [(float(x_edges[u]), float(x_edges[d])) for u, d in zip(ups, downs)]


def sequence_map(fmap: FluenceMap, levels: int, max_weight: Optional[float] = None) -> List[Aperture]:
    """Bortfeld–Boyer decomposition of a fluence map into equal-weight apertures."""
    if levels < 1:
        raise ValueError("levels must be >= 1")
    top = float(np.max(fmap.values)) if max_weight is None else float(max_weight)
    if top <= 0:
        return []
    delta = top / levels
    q = np.rint(fmap.values / delta).astype(int)
    per_row = [sequence_row(q[r], fmap.x_edges_mm) for r in range(q.shape[0])]
    n_seg = max((len(s) for s in per_row), default=0)
    park = float(fmap.x_edges_mm[0])
    out: List[Aperture] = []
    for i in range(n_seg):
        left = np.full(q.shape[0], park)
        right = np.full(q.shape[0], park)
        for r, segs in enumerate(per_row):
            if i < len(segs):
                left[r], right[r] = segs[i]
        out.append(Aperture(fmap.beam_index, left, right, delta))
    return out


def apply_machine_limits(aperture: Aperture, mlc: MLCSpec, pair_indices: Sequence[int]) -> Aperture:
    """Clip the tips to the machine's travel limits and report interdigitation."""
    left = aperture.left_mm.copy()
    right = aperture.right_mm.copy()
    lo, hi = -float(mlc.max_leaf_position_mm), float(mlc.max_overtravel_mm)
    open_rows = right > left
    clipped = False
    # left tips retract to -max_leaf_position and overtravel to +max_overtravel; mirrored for right tips
    l_new = np.clip(left, lo, hi)
    r_new = np.clip(right, -hi, -lo)
    if np.any(l_new != left) or np.any(r_new != right):
        clipped = True
    left, right = l_new, r_new
    for r in np.flatnonzero(open_rows):
        if right[r] - left[r] < mlc.min_leaf_gap_mm:
            right[r] = left[r] = left[r]          # too narrow: closed
    issues = list(aperture.issues)
    if clipped:
        issues.append("leaf tips clipped to the travel limits")
    if not mlc.interdigitation:
        for r in range(len(left) - 1):
            if pair_indices[r + 1] != pair_indices[r] + 1:
                continue
            a_open, b_open = right[r] > left[r], right[r + 1] > left[r + 1]
            if a_open and b_open and (left[r] > right[r + 1] or left[r + 1] > right[r]):
                issues.append(f"interdigitation between leaf pairs {pair_indices[r]} and {pair_indices[r + 1]}")
    if mlc.max_tip_difference_mm is not None:
        opened = np.flatnonzero(right > left)
        if opened.size > 1:
            if np.max(np.abs(np.diff(left[opened]))) > mlc.max_tip_difference_mm or np.max(np.abs(np.diff(right[opened]))) > mlc.max_tip_difference_mm:
                issues.append("neighbouring tips farther apart than the machine allows")
    return Aperture(aperture.beam_index, left, right, aperture.level_weight, aperture.mu, issues)


# ---------------------------------------------------------------------------
# Segment dose columns and segment weights
# ---------------------------------------------------------------------------

def coverage_matrix(plan: PhotonPlan, maps: List[FluenceMap], apertures: List[Aperture], mlc: MLCSpec) -> sp.csc_matrix:
    """``(n_beamlets, n_segments)``: the fraction of every open-field beamlet inside each aperture.

    A beamlet wider than a leaf pair spans several pairs; its coverage is the
    sum over every pair it overlaps of (its share of y in that pair) × (the
    share of its x inside that pair's leaves), so a fully open aperture
    covers every beamlet exactly once whatever the beamlet-to-leaf ratio.
    """
    rows, cols, vals = [], [], []
    offsets = np.cumsum([0] + [b.n_beamlets for b in plan.beams])
    bounds = np.asarray(mlc.leaf_boundaries_mm, dtype=float)
    for k, ap in enumerate(apertures):
        fmap = maps[[m.beam_index for m in maps].index(ap.beam_index)]
        beam = plan.beams[ap.beam_index]
        bl = beam.beamlets()
        pair_lo = bounds[np.asarray(fmap.pair_indices)]
        pair_hi = bounds[np.asarray(fmap.pair_indices) + 1]
        for i in range(bl.shape[0]):
            x, y, dx, dy = bl[i]
            oy = np.clip(np.minimum(y + dy / 2, pair_hi) - np.maximum(y - dy / 2, pair_lo), 0.0, None) / dy
            ox = np.clip(np.minimum(x + dx / 2, ap.right_mm) - np.maximum(x - dx / 2, ap.left_mm), 0.0, None) / dx
            c = float(np.sum(ox * oy))
            if c > 1e-9:
                rows.append(offsets[ap.beam_index] + i); cols.append(k); vals.append(c)
    return sp.csc_matrix((vals, (rows, cols)), shape=(int(offsets[-1]), len(apertures)), dtype=np.float64)


def optimize_segment_weights(
    segment_dose: sp.csr_matrix,
    grid_shape: Tuple[int, int, int],
    cost_terms: Callable[[np.ndarray], Tuple[float, np.ndarray]],
    w0: np.ndarray,
    method: str = "L-BFGS-B",
    max_iterations: int = 200,
    tol: float = 1e-9,
) -> Tuple[np.ndarray, object]:
    """Minimize the plan objectives over segment metersets ``w >= 0`` with ``dose = S @ w``."""
    from .optimization_solvers import get_solver

    S = segment_dose.tocsr()
    ST = S.T.tocsr()

    def cost_and_grad(w: np.ndarray) -> Tuple[float, np.ndarray]:
        dose = np.asarray(S @ np.asarray(w, dtype=np.float64)).reshape(grid_shape)
        loss, g_dose = cost_terms(dose)
        return float(loss), np.asarray(ST @ g_dose.ravel(order="C"), dtype=np.float64)

    solver = get_solver(method)
    w, conv = solver.run(cost_and_grad, np.asarray(w0, dtype=np.float64), max_iterations, tol)
    return np.clip(np.asarray(w, dtype=np.float64), 0.0, None), conv


# ---------------------------------------------------------------------------
# Plans and deliverability
# ---------------------------------------------------------------------------

def _pair_heights(mlc: MLCSpec, pair_indices: Sequence[int]) -> np.ndarray:
    b = np.asarray(mlc.leaf_boundaries_mm, dtype=float)
    return np.asarray([b[p + 1] - b[p] for p in pair_indices])


def aperture_segment(ap: Aperture, fmap: FluenceMap, mlc: MLCSpec, machine: PhotonMachineSpec, mu: float,
                     beamlet_spacing_mm: Tuple[float, float], control_point_index: int) -> PhotonSegment:
    """A :class:`PhotonSegment` for an aperture: one MLC row per leaf pair, jaws around the open area."""
    bounds = np.asarray(mlc.leaf_boundaries_mm, dtype=float)
    rows = []
    open_rows = ap.right_mm > ap.left_mm
    for r, pair in enumerate(fmap.pair_indices):
        rows.append(MLCRow(y_min_mm=float(bounds[pair]), y_max_mm=float(bounds[pair + 1]),
                           x_left_mm=float(ap.left_mm[r]), x_right_mm=float(max(ap.right_mm[r], ap.left_mm[r]))))
    if open_rows.any():
        x1 = float(np.min(ap.left_mm[open_rows])); x2 = float(np.max(ap.right_mm[open_rows]))
        y1 = float(min(bounds[fmap.pair_indices[r]] for r in np.flatnonzero(open_rows)))
        y2 = float(max(bounds[fmap.pair_indices[r] + 1] for r in np.flatnonzero(open_rows)))
    else:
        x1, x2 = float(fmap.x_edges_mm[0]), float(fmap.x_edges_mm[1])
        y1, y2 = float(bounds[fmap.pair_indices[0]]), float(bounds[fmap.pair_indices[0] + 1])
    jx, jy = machine.jaws.x_range_mm, machine.jaws.y_range_mm
    x1, x2 = max(x1, jx[0]), min(x2, jx[1])
    y1, y2 = max(y1, jy[0]), min(y2, jy[1])
    if x2 <= x1:
        x2 = x1 + float(beamlet_spacing_mm[0])
    if y2 <= y1:
        y2 = y1 + float(beamlet_spacing_mm[1])
    return PhotonSegment(control_point_index=control_point_index, mu=float(mu), x_jaw_mm=(x1, x2), y_jaw_mm=(y1, y2),
                         mlc_rows=rows, beamlet_spacing_mm=beamlet_spacing_mm)


@dataclass
class BeamDeliverability:
    beam_id: str
    n_segments: int
    total_mu: float
    min_segment_mu: float
    min_segment_area_mm2: float
    max_leaf_travel_mm: float
    beam_on_time_s: float
    leaf_travel_time_s: float
    issues: List[str] = field(default_factory=list)


def deliverability(plan: PhotonPlan, machine: PhotonMachineSpec, energy_mv: Optional[float] = None) -> List[BeamDeliverability]:
    """Per beam: counts, MU, areas, leaf travel and time at the machine's limits."""
    energy = machine.energy(energy_mv)
    out: List[BeamDeliverability] = []
    for beam in plan.beams:
        issues: List[str] = []
        mus = [s.mu for s in beam.segments]
        areas = []
        travel = 0.0
        prev = None
        for s in beam.segments:
            rows = s.aperture_rows()
            areas.append(sum(r.opening_mm * (r.y_max_mm - r.y_min_mm) for r in rows))
            tips = np.asarray([[r.x_left_mm, r.x_right_mm] for r in rows])
            if prev is not None and prev.shape == tips.shape:
                travel += float(np.max(np.abs(tips - prev)))
            prev = tips
        for k, (mu, area) in enumerate(zip(mus, areas)):
            if mu < machine.min_mu_per_segment:
                issues.append(f"segment {k}: {mu:.2f} MU below the minimum {machine.min_mu_per_segment}")
            if area < machine.min_segment_area_mm2:
                issues.append(f"segment {k}: {area:.0f} mm² below the minimum {machine.min_segment_area_mm2:.0f}")
        if len(beam.segments) > machine.max_segments_per_beam:
            issues.append(f"{len(beam.segments)} segments exceed the machine's {machine.max_segments_per_beam} per beam")
        out.append(BeamDeliverability(
            beam_id=beam.beam_id, n_segments=len(beam.segments), total_mu=float(sum(mus)),
            min_segment_mu=float(min(mus)) if mus else 0.0, min_segment_area_mm2=float(min(areas)) if areas else 0.0,
            max_leaf_travel_mm=float(travel), beam_on_time_s=float(sum(mus)) / energy.dose_rate_mu_min[1] * 60.0,
            leaf_travel_time_s=float(travel) / machine.mlc.max_leaf_speed_mm_s, issues=issues,
        ))
    return out


# ---------------------------------------------------------------------------
# The whole step
# ---------------------------------------------------------------------------

@dataclass
class SequencingResult:
    plan: PhotonPlan
    segment_mu: np.ndarray
    segment_beam: np.ndarray
    coverage: sp.csc_matrix
    dose: np.ndarray
    convergence: object
    dropped_segments: int
    deliverability: List[BeamDeliverability]
    n_levels: int


def sequence_plan(
    plan: PhotonPlan,
    weights: np.ndarray,
    dij: sp.csr_matrix,
    grid_shape: Tuple[int, int, int],
    cost_terms: Callable[[np.ndarray], Tuple[float, np.ndarray]],
    machine: PhotonMachineSpec,
    *,
    levels: int = 10,
    method: str = "L-BFGS-B",
    max_iterations: int = 200,
    energy_mv: Optional[float] = None,
    name: Optional[str] = None,
) -> SequencingResult:
    """Fluence → apertures → machine limits → segment weights → deliverable plan."""
    mlc = machine.mlc
    maps = fluence_maps(plan, weights, mlc)
    apertures: List[Aperture] = []
    for fmap in maps:
        for ap in sequence_map(fmap, levels):
            ap = apply_machine_limits(ap, mlc, fmap.pair_indices)
            heights = _pair_heights(mlc, fmap.pair_indices)
            if ap.area_mm2(heights) < machine.min_segment_area_mm2:
                continue
            apertures.append(ap)
    if not apertures:
        raise ValueError("no aperture survived the machine's minimum area; lower it or raise the fluence levels")
    dropped = 0
    cov = coverage_matrix(plan, maps, apertures, mlc)
    S = (dij.tocsr() @ cov.tocsc()).tocsr()
    w0 = np.asarray([ap.level_weight for ap in apertures])
    mu, conv = optimize_segment_weights(S, grid_shape, cost_terms, w0, method, max_iterations)
    # segments under the minimum MU are removed and the rest re-optimized, a few rounds at most
    for _ in range(5):
        keep = mu >= machine.min_mu_per_segment
        if keep.all() or not keep.any():
            break
        dropped += int((~keep).sum())
        apertures = [ap for ap, k in zip(apertures, keep) if k]
        cov = cov[:, np.flatnonzero(keep)]
        S = (dij.tocsr() @ cov.tocsc()).tocsr()
        mu, conv = optimize_segment_weights(S, grid_shape, cost_terms, mu[keep], method, max_iterations)
    keep = mu >= machine.min_mu_per_segment
    if not keep.any():
        raise ValueError("every segment fell under the machine's minimum MU; the fluence is too low for this machine")
    if not keep.all():
        dropped += int((~keep).sum())
        apertures = [ap for ap, k in zip(apertures, keep) if k]
        cov = cov[:, np.flatnonzero(keep)]
        S = (dij.tocsr() @ cov.tocsc()).tocsr()
        mu = mu[keep]
    dose = np.asarray(S @ mu).reshape(grid_shape).astype(np.float32)

    beams: List[PhotonBeam] = []
    seg_beam = np.asarray([ap.beam_index for ap in apertures])
    for b, beam in enumerate(plan.beams):
        fmap = next((m for m in maps if m.beam_index == b), None)
        idx = np.flatnonzero(seg_beam == b)
        if fmap is None or idx.size == 0:
            logger.warning("beam {} has no segment after sequencing; it is left out of the plan", beam.beam_id)
            continue
        spacing = beam.segments[0].beamlet_spacing_mm
        segments = [aperture_segment(apertures[k], fmap, mlc, machine, float(mu[k]), spacing, j) for j, k in enumerate(idx)]
        beams.append(PhotonBeam(beam_id=beam.beam_id, gantry_deg=beam.gantry_deg, couch_deg=beam.couch_deg,
                                isocenter_mm=beam.isocenter_mm, sad_mm=beam.sad_mm,
                                energy_mv=beam.energy_mv or machine.energy(energy_mv).nominal_mv, segments=segments))
    if not beams:
        raise ValueError("no beam kept a segment")
    new_plan = PhotonPlan(name=name or f"{plan.name}-segments", beams=beams)
    report = deliverability(new_plan, machine, energy_mv)
    for ap in apertures:
        for issue in ap.issues:
            report[[r.beam_id for r in report].index(plan.beams[ap.beam_index].beam_id)].issues.append(issue)
    return SequencingResult(new_plan, mu, seg_beam, cov, dose, conv, dropped, report, levels)


__all__ = ["FluenceMap", "Aperture", "fluence_maps", "sequence_row", "sequence_map", "apply_machine_limits",
           "coverage_matrix", "optimize_segment_weights", "aperture_segment", "BeamDeliverability", "deliverability",
           "SequencingResult", "sequence_plan"]
