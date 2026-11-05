"""Roadmap R4: leaf transmission, rounded leaf ends and tongue-and-groove in aperture doses
(``docs/reports/mlc-leaf-model.md``)."""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.models.photon_plan import LEAF_MODEL_VERSION, LeafModel, MLCRow, PhotonBeam, PhotonPlan, PhotonSegment
from radiarch.services import sequencing as S
from radiarch.services.machine_model import load_photon_spec
from radiarch.services.photon_beamlets import build_photon_plan

T, TJ, DLG, TG = 0.015, 0.002, 1.5, 0.5
MODEL = LeafModel(leaf_transmission=T, jaw_transmission=TJ, dosimetric_leaf_gap_mm=DLG, tongue_and_groove_mm=TG)


def _rows(tips, y0=-15.0, width=5.0):
    return [MLCRow(y_min_mm=y0 + k * width, y_max_mm=y0 + (k + 1) * width, x_left_mm=a, x_right_mm=b) for k, (a, b) in enumerate(tips)]


def _integral(rects, x0=-np.inf, x1=np.inf, y0=-np.inf, y1=np.inf):
    """The fluence of rectangles ``(x0, x1, y0, y1, factor)`` inside a window."""
    total = 0.0
    for a, b, c, d, f in rects:
        w = max(0.0, min(b, x1) - max(a, x0))
        h = max(0.0, min(d, y1) - max(c, y0))
        total += w * h * f
    return total


def _at(rects, x, y):
    """The fluence factor at a point (inside one rectangle at most: they are disjoint)."""
    hits = [f for a, b, c, d, f in rects if a < x < b and c < y < d]
    assert len(hits) <= 1
    return hits[0] if hits else 0.0


class TestFluence:
    def test_without_a_model_the_aperture_is_ideal(self):
        seg = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows([(-10, 10)] * 6))
        rects = seg.fluence_rectangles()
        assert all(f == 1.0 for *_, f in rects)
        assert _integral(rects) == pytest.approx(20.0 * 30.0)
        assert seg.fluence_rectangles(LeafModel()) and _integral(seg.fluence_rectangles(LeafModel())) == pytest.approx(600.0)

    def test_a_jaws_only_field_is_unchanged(self):
        seg = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15))
        assert seg.fluence_rectangles(MODEL) == seg.fluence_rectangles()

    def test_a_closed_pair_lets_through_the_transmission_and_the_gap_at_its_tips(self):
        """Inside the jaws a closed pair passes the leaf transmission, and its rounded tips one leaf gap at full fluence."""
        tips = [(-10, 10)] * 6
        tips[2] = (5.0, 5.0)                                 # the pair from y = -5 to 0 closed at x = 5
        seg = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows(tips))
        rects = seg.fluence_rectangles(MODEL)
        assert _at(rects, -12.0, -2.5) == pytest.approx(T)    # under the closed leaves
        assert _at(rects, 5.0, -2.5) == pytest.approx(1.0)    # between the rounded tips
        assert _at(rects, 15.0, -2.5) == pytest.approx(T)
        # the pair's band less its two tongue-and-groove strips: the gap at full fluence, the rest of the jaws' width at T
        band = (-5.0 + TG / 2, 0.0 - TG / 2)
        h = band[1] - band[0]
        assert _integral(rects, y0=band[0], y1=band[1]) == pytest.approx(h * (DLG + T * (40.0 - DLG)))

    def test_a_narrow_gap_acts_wider_by_the_leaf_gap(self):
        for gap in (2.0, 5.0, 10.0):
            seg = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows([(0.0, gap)] * 6))
            rects = seg.fluence_rectangles(MODEL.model_copy(update={"leaf_transmission": 0.0}))
            assert _integral(rects) == pytest.approx(30.0 * (gap + DLG))

    def test_tongue_and_groove_dips_between_complementary_segments(self):
        """Two segments, each opening one of two adjacent pairs: in the strip on their boundary the summed fluence
        is the transmission of both, not the open fluence."""
        a = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-5, 5), mlc_rows=_rows([(-10, 10), (-20, -20)], y0=-5.0))
        b = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-5, 5), mlc_rows=_rows([(-20, -20), (-10, 10)], y0=-5.0))
        ra, rb = a.fluence_rectangles(MODEL), b.fluence_rectangles(MODEL)
        total = lambda x, y: _at(ra, x, y) + _at(rb, x, y)  # noqa: E731
        assert total(0.0, -2.5) == pytest.approx(1.0 + T)       # each pair's own band
        assert total(0.0, 2.5) == pytest.approx(1.0 + T)
        assert total(0.0, 0.0) == pytest.approx(2.0 * T)        # the strip on the boundary
        dip = 20.0 * TG * (1.0 + T - 2.0 * T)                   # the open width times the strip, lost
        ideal = 2.0 * 20.0 * 5.0 + T * 2.0 * 20.0 * 5.0
        summed = _integral(ra, x0=-10, x1=10) + _integral(rb, x0=-10, x1=10)
        assert summed == pytest.approx(ideal - dip)

    def test_pairs_open_alike_have_no_stripe(self):
        seg = PhotonSegment(mu=1.0, x_jaw_mm=(-20, 20), y_jaw_mm=(-15, 15), mlc_rows=_rows([(-10, 10)] * 6))
        rects = seg.fluence_rectangles(MODEL)
        for y in np.arange(-14.9, 15.0, 0.1):
            assert _at(rects, 0.0, y) == pytest.approx(1.0)

    def test_the_opening_outside_the_jaws_passes_the_jaw_transmission(self):
        seg = PhotonSegment(mu=1.0, x_jaw_mm=(-5, 5), y_jaw_mm=(-15, 15), mlc_rows=_rows([(-10, 10)] * 6))
        rects = seg.fluence_rectangles(MODEL)
        assert _at(rects, 0.0, 2.5) == pytest.approx(1.0)
        assert _at(rects, 8.0, 2.5) == pytest.approx(TJ)        # open leaves, under the jaw
        assert _at(rects, 15.0, 2.5) == 0.0                      # under both: about T x TJ, left out


class TestThreePathsAgree:
    """The sequencing coverage, the pencil beam's rectangles and CCC's coverage cells integrate to the same fluence."""

    def test_one_segment(self):
        from radiarch.services.dose_engines.pb import aperture_rectangles

        machine = load_photon_spec("synthetic-120")
        plan = build_photon_plan([(0.0, 0.0)], (-50, 50), (-50, 50), 5.0, 1.0, (5.0, 5.0))
        rng = np.random.default_rng(7)
        w = rng.random(plan.n_beamlets) * 10
        maps = S.fluence_maps(plan, w, machine.mlc)
        ap = S.sequence_map(maps[0], levels=4)[1]
        model = machine.leaf_model()
        seg = S.aperture_segment(ap, maps[0], machine.mlc, machine, 1.0, (5.0, 5.0), 0)
        rects = seg.fluence_rectangles(model)
        assert any(f == pytest.approx(model.leaf_transmission) for *_, f in rects)
        pb = sum((x1 - x0) * (y1 - y0) * f for x0, x1, y0, y1, f in aperture_rectangles(seg, model))
        cells = seg.coverage_beamlets(model)
        ccc = float((cells[:, 2] * cells[:, 3] * cells[:, 4]).sum())
        cov = S.coverage_matrix(plan, maps, [ap], machine.mlc, machine, model)
        bl = plan.beams[0].beamlets()
        seq = float(np.asarray(cov[:, 0].todense()).ravel() @ (bl[:, 2] * bl[:, 3]))
        assert pb == pytest.approx(_integral(rects), rel=1e-9)
        assert ccc == pytest.approx(pb, rel=1e-9)
        # the coverage has the open field's beamlets only: a tip at the field's edge, under the jaw, reaches past them
        assert seq == pytest.approx(_integral(rects, -50, 50, -50, 50), rel=1e-9)
        assert seq == pytest.approx(pb, rel=1e-3)
        # the ideal leaves give the open area only
        open_area = _integral(seg.fluence_rectangles())
        assert pb > open_area


class TestPlans:
    def test_a_sequenced_plan_carries_the_machines_leaf_model(self):
        machine = load_photon_spec("synthetic-120")
        plan = build_photon_plan([(0.0, 0.0)], (-30, 30), (-30, 30), 5.0, 1.0, (5.0, 5.0))
        w = np.random.default_rng(2).random(plan.n_beamlets) * 5
        dij = np.eye(plan.n_beamlets)
        target = np.asarray(dij @ w)

        def terms(dose):
            d = dose.ravel()
            return float(np.sum((d - target) ** 2)), (2 * (d - target)).reshape(dose.shape)

        import scipy.sparse as sp
        res = S.sequence_plan(plan, w, sp.csr_matrix(dij), (plan.n_beamlets, 1, 1), terms, machine.model_copy(update={"min_segment_area_mm2": 0.0, "min_mu_per_segment": 0.0}),
                              levels=4)
        assert res.plan.leaf_model == machine.leaf_model()
        # the plan's dose through its apertures is what the weights were optimized for: the coverage matrix of its segments
        seg = res.plan.beams[0].segments[0]
        assert seg.fluence_rectangles(res.plan.leaf_model) != seg.fluence_rectangles()

    def test_the_pencil_beam_lets_the_transmission_through_closed_leaves(self):
        from radiarch.services.dose_engines.pb import PencilBeamEngine
        from radiarch.services.dose_engines.pb_kernel import default_kernel_path
        if not default_kernel_path().is_file():
            pytest.skip("engines/pb kernel table missing")
        eng = PencilBeamEngine()
        d = np.full((25, 30, 25), 1.0, np.float32)
        sp_, org = (5.0, 5.0, 5.0), (-60.0, 2.5, -60.0)
        rows = [MLCRow(y_min_mm=y, y_max_mm=y + 5, x_left_mm=-40, x_right_mm=-40) for y in range(-50, 50, 5)]
        closed = PhotonSegment(mu=100.0, x_jaw_mm=(-50, 50), y_jaw_mm=(-50, 50), mlc_rows=rows)
        opened = PhotonSegment(mu=100.0, x_jaw_mm=(-50, 50), y_jaw_mm=(-50, 50))
        beam = lambda s: PhotonBeam(beam_id="A", gantry_deg=0.0, segments=[s])  # noqa: E731
        p = {"fluence": "apertures"}
        d_open = eng.compute_plan_dose(d, sp_, org, PhotonPlan(beams=[beam(opened)], leaf_model=MODEL), params=p)
        d_ideal = eng.compute_plan_dose(d, sp_, org, PhotonPlan(beams=[beam(closed)]), params=p)
        d_leaf = eng.compute_plan_dose(d, sp_, org, PhotonPlan(beams=[beam(closed)], leaf_model=MODEL), params=p)
        c = 12 + 4                                                 # x = +20 mm, 60 mm from the closed tips
        ratio = d_leaf[12, 6, c] / d_open[12, 6, c]
        assert d_ideal[12, 6, c] == pytest.approx(0.0, abs=1e-6 * d_open.max())
        assert T <= ratio < T + 0.005                              # the transmission, plus scatter from the tips' gap


def test_the_leaf_model_version_is_in_the_cache_keys(monkeypatch):
    """Sequences, arcs and deliverable plans cached under another leaf model are not reused."""
    import radiarch.models.apertures as apertures
    import radiarch.models.mco as mco
    import radiarch.models.vmat as vmat
    from radiarch.models.optimization import ObjectiveSpec

    objectives = [ObjectiveSpec(type="DUniform", structure_name="PTV", dose_gy=2.0, weight=1.0)]
    seq = apertures.SequenceRequest(objectives=objectives)
    arc = vmat.ArcRequest(objectives=objectives, arcs=[vmat.ArcSpec(arc_id="A1", start_deg=181.0, stop_deg=179.0, direction="CW")])
    dlv = mco.DeliverableRequest()
    before = (seq.compute_cache_key("o"), arc.compute_cache_key("o"), dlv.compute_cache_key("m", [1.0]))
    for mod in (apertures, vmat, mco):
        monkeypatch.setattr(mod, "LEAF_MODEL_VERSION", "test")
    after = (seq.compute_cache_key("o"), arc.compute_cache_key("o"), dlv.compute_cache_key("m", [1.0]))
    assert all(a != b for a, b in zip(before, after))
