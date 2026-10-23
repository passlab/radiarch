"""Roadmap R8: VMAT arcs from sector fluence maps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pytest

from radiarch.models.vmat import ArcRequest, ArcSpec, sector_beams
from radiarch.services.dose_engines.pb_kernel import default_kernel_path
from radiarch.services.machine_model import load_photon_spec
from radiarch.services.sequencing import FluenceMap
from radiarch.services.vmat import arc_report, build_arc, interval_timing, optimize_interval_mu, sweep, with_metersets

needs_kernel = pytest.mark.skipif(not default_kernel_path().is_file(), reason="engines/pb kernel table missing")


def _map(values, x0=-30.0, dx=10.0):
    values = np.asarray(values, float)
    return FluenceMap(0, "B", list(range(30, 30 + values.shape[0])), x0 + dx * np.arange(values.shape[1] + 1), values, {})


def _delivered(states, mu, x_edges):
    """The fluence the states deliver per column (column centres inside the opening)."""
    xc = 0.5 * (x_edges[1:] + x_edges[:-1])
    out = np.zeros((states.shape[1], xc.size))
    for st, m in zip(states, mu):
        out += m * ((xc[None, :] > st[:, 0:1]) & (xc[None, :] < st[:, 1:2]))
    return out


class TestSweep:
    @pytest.mark.parametrize("reverse", [False, True])
    def test_reproduces_the_quantized_map_and_moves_one_way(self, reverse):
        vals = np.array([[0, 1, 3, 2, 0, 1], [2, 2, 2, 2, 2, 2], [0, 0, 0, 0, 0, 0]], float)
        fmap = _map(vals)
        states, mu = sweep(fmap, 6, reverse=reverse)
        assert states.shape == (6, 3, 2) and mu.shape == (6,)
        # six control points cannot hold six levels here (the first row would need eight apertures): four levels,
        # so the sweep delivers the map quantized in steps of 3/4, within half a step
        assert np.max(np.abs(_delivered(states, mu, fmap.x_edges_mm) - vals)) <= 0.5 * 3.0 / 4 + 1e-9
        tips = states[:, :2, :]                                 # rows with fluence
        steps = np.diff(tips, axis=0)
        assert np.all(steps <= 1e-9) if reverse else np.all(steps >= -1e-9)
        assert np.all(states[:, 2, 0] == states[:, 2, 1])      # the empty row stays closed

    def test_fewer_levels_when_the_rows_need_more_apertures(self):
        vals = np.array([[4, 0, 4, 0, 4, 0, 4]], float)          # 4 peaks: 16 rises at 4 levels
        states, mu = sweep(_map(vals, x0=-35.0), 8)
        assert states.shape[0] == 8
        delivered = _delivered(states, mu, _map(vals, x0=-35.0).x_edges_mm)
        assert np.corrcoef(delivered.ravel(), vals.ravel())[0, 1] > 0.99

    def test_empty_map(self):
        states, mu = sweep(_map(np.zeros((2, 3))), 4)
        assert np.all(mu == 0) and np.all(states[..., 0] == states[..., 1])


class TestArcSpec:
    def test_geometry(self):
        a = ArcSpec(arc_id="A", start_deg=181, stop_deg=179, direction="CW", sectors=12, control_point_spacing_deg=4.0)
        assert a.length_deg == pytest.approx(358.0) and a.spacing_deg <= 4.0
        cps = a.control_point_angles_deg()
        assert len(cps) == a.sectors * a.intervals_per_sector + 1
        assert cps[0] == pytest.approx(181.0) and cps[-1] == pytest.approx(179.0)
        assert a.sector_centres_deg()[0] == pytest.approx(181.0 + a.intervals_per_sector * a.spacing_deg / 2)
        full = ArcSpec(arc_id="F", start_deg=0, stop_deg=0, sectors=10)
        assert full.length_deg == 360.0
        cc = ArcSpec(arc_id="C", start_deg=30, stop_deg=330, direction="CC", sectors=3, control_point_spacing_deg=4.0)
        assert cc.length_deg == pytest.approx(60.0) and cc.sector_centres_deg()[0] == pytest.approx(20.0)
        assert [b for b, _, _, _ in sector_beams([cc])] == ["C-S01", "C-S02", "C-S03"]


class TestArcBuild:
    def test_build_time_and_metersets(self):
        machine = load_photon_spec("synthetic-120")
        spec = ArcSpec(arc_id="A", start_deg=330, stop_deg=30, sectors=3, control_point_spacing_deg=4.0)
        k = spec.intervals_per_sector
        maps = [_map(np.array([[0, 1, 2, 1], [1, 2, 2, 0]], float) * (s + 1)) for s in range(3)]
        beam, mu, issues = build_arc(spec, maps, machine.mlc, machine, isocenter_mm=(0, 0, 0), sad_mm=1000.0, energy_mv=6.0,
                                     beamlet_spacing_mm=(5.0, 5.0))
        arc = beam.arc
        assert len(arc.control_points) == 3 * k + 1 and len(beam.segments) == 3 * k
        assert arc.total_mu == pytest.approx(mu.sum()) and not issues
        assert len({cp.x_jaw_mm for cp in arc.control_points}) == 1              # jaws fixed for the arc
        t = interval_timing(beam, machine)
        rate_min = machine.energy(None).dose_rate_mu_min[0]
        assert np.allclose(t.min_time_s, np.maximum(t.angle_deg / machine.max_gantry_speed_deg_s,
                                                     t.leaf_travel_mm / machine.mlc.max_leaf_speed_mm_s))
        assert np.allclose(t.min_mu, rate_min / 60.0 * t.min_time_s)
        beam2 = with_metersets(beam, np.maximum(mu, t.min_mu))
        rep = arc_report(beam2, machine)
        assert rep.n_control_points == 3 * k + 1 and not rep.issues
        assert rep.gantry_speed_deg_s[1] <= machine.max_gantry_speed_deg_s + 1e-9
        low = arc_report(with_metersets(beam, t.min_mu * 0.5), machine)
        assert low.issues                                                         # below the dose-rate floor
        # a course of 3 fractions: the floor is on each fraction's meterset, the report is per fraction
        t3 = interval_timing(beam, machine, fractions=3)
        assert np.allclose(t3.min_mu, 3 * t.min_mu)
        course = with_metersets(beam, 3 * np.maximum(mu, t.min_mu))
        r3 = arc_report(course, machine, fractions=3)
        assert r3.fractions == 3 and r3.total_mu == pytest.approx(rep.total_mu) and r3.delivery_time_s == pytest.approx(rep.delivery_time_s)
        assert not r3.issues

    def test_interval_metersets_respect_their_floor(self):
        import scipy.sparse as sp
        S = sp.csr_matrix(np.array([[1.0, 0.0, 0.5], [0.0, 1.0, 0.5]]))
        target = np.array([1.0, 1.0])

        def cost(dose):
            r = dose.ravel() - target
            return float(r @ r), 2 * r.reshape(dose.shape)

        mu, _ = optimize_interval_mu(S, (2, 1, 1), cost, np.ones(3), np.array([0.0, 0.0, 0.8]), max_iterations=100)
        assert mu[2] >= 0.8 - 1e-9 and np.allclose(S @ mu, target, atol=1e-3)


# ---------------------------------------------------------------------------
# Through the services
# ---------------------------------------------------------------------------

@dataclass
class _Patient:
    name: str = "VMAT"


@dataclass
class _CT:
    imageArray: np.ndarray
    origin: Tuple[float, float, float]
    spacing: Tuple[float, float, float]
    patient: _Patient
    seriesInstanceUID: str = "1.2.3.4"
    studyInstanceUID: str = "1.2.3"
    frameOfReferenceUID: str = "1.2.3.9"


@dataclass
class _Mask:
    imageArray: np.ndarray


@dataclass
class _Contour:
    name: str
    mask: np.ndarray

    def getBinaryMask(self, origin, gridSize, spacing):
        return _Mask(self.mask)


def _loaded_ct():
    from radiarch.services.geometry import _LoadedCT

    n, sp = 24, 5.0
    xx, yy, zz = np.mgrid[:n, :n, :n]
    c = (n - 1) / 2.0
    ct = np.where((xx - c) ** 2 + (yy - c) ** 2 <= 10.5 ** 2, 0, -1000).astype(np.int16)   # a water cylinder in air
    ptv = (xx - c - 2) ** 2 + (yy - c) ** 2 + (zz - c) ** 2 <= 9
    oar = ((xx - c + 4) ** 2 + (yy - c) ** 2 <= 4) & (np.abs(zz - c) <= 4)
    vol = _CT(imageArray=ct, origin=(-c * sp, -c * sp, -c * sp), spacing=(sp, sp, sp), patient=_Patient())
    return _LoadedCT(ct=vol, patient=vol.patient, contours=[_Contour("PTV", ptv), _Contour("OAR", oar)])


@pytest.fixture
def env(monkeypatch, tmp_path):
    from radiarch.config import get_settings
    from radiarch.services.geometry import GeometryService

    for k, v in {"RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
                 "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://",
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path), "RADIARCH_API_KEY": ""}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr(GeometryService, "_load", lambda self, _req: _loaded_ct())
    yield tmp_path
    get_settings.cache_clear()


@needs_kernel
def test_arcs_through_the_services(env):
    from radiarch.models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from radiarch.models.dose import EngineSpec
    from radiarch.models.geometry import GeometryBuildRequest, PatientRef
    from radiarch.models.optimization import ObjectiveSpec, OptimizationRunRequest, SolverConfig
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.dose import DoseService
    from radiarch.services.geometry import GeometryService
    from radiarch.services.optimization import OptimizationService
    from radiarch.services.vmat import VMATService

    arc = ArcSpec(arc_id="A1", start_deg=300, stop_deg=60, direction="CW", sectors=4, control_point_spacing_deg=4.0)
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id="synthetic-120",
        beam_set=BeamSetSpec(isocenter_mm=(10.0, 0.0, 0.0), beams=[BeamSpec(beam_id=b, gantry_deg=g, collimator_deg=col) for b, g, _, col in sector_beams([arc])]),
        delivery_params=DeliveryParams(jaw_opening_mm=(40.0, 40.0), beamlet_size_mm=(5.0, 5.0))))
    objectives = [ObjectiveSpec(type="DUniform", structure_name="PTV", dose_gy=2.0, weight=1.0),
                  ObjectiveSpec(type="DMax", structure_name="OAR", dose_gy=0.8, weight=1.0)]
    opt = OptimizationService().run(OptimizationRunRequest(
        geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=EngineSpec(name="pb"),
        objectives=objectives, solver=SolverConfig(method="L-BFGS-B", max_iterations=60)))
    svc = VMATService()
    req = ArcRequest(objectives=objectives, arcs=[arc], max_iterations=60)
    res = svc.arcs(opt.optimization_id, req)
    assert res.engine_name == "pb" and res.n_control_points == arc.sectors * arc.intervals_per_sector + 1
    assert res.total_mu > 0 and len(res.arcs) == 1 and res.arcs[0].delivery_time_s > 0
    assert res.deliverable, res.arcs[0].issues
    plan = BeamModelService().store.load_plan(res.beam_model_id)
    assert plan.beams[0].arc is not None and plan.beams[0].arc.direction == "CW"
    dose = DoseService().dose_store.get_by_id(res.dose_id)
    assert dose is not None and dose.engine_name == "pb+arcs"
    import SimpleITK as sitk
    grid = sitk.GetArrayFromImage(sitk.ReadImage(dose.dose_grid_uri))
    ptv = _loaded_ct().contours[0].mask.transpose(2, 1, 0)       # the stub's masks are (x, y, z); doses (z, y, x)
    assert grid.shape == ptv.shape and grid[ptv].mean() == pytest.approx(2.0, rel=0.05)
    assert svc.arcs(opt.optimization_id, req).vmat_id == res.vmat_id                 # cached
    # beams that are not the arc's sectors are refused
    with pytest.raises(ValueError):
        svc.arcs(opt.optimization_id, ArcRequest(objectives=objectives, arcs=[arc.model_copy(update={"sectors": 5})]))


def test_the_collimator_reaches_the_sector_beams_and_must_match_the_arc():
    from radiarch.services.photon_beamlets import build_photon_plan
    from radiarch.services.vmat import plan_arcs
    arc = ArcSpec(arc_id="A", start_deg=0, stop_deg=40, sectors=2, collimator_deg=30.0)
    beams = sector_beams([arc])
    assert all(col == 30.0 for _, _, _, col in beams)
    plan = build_photon_plan([(g, c, col) for _, g, c, col in beams], (-20, 20), (-20, 20), 5.0, 1.0)
    assert all(b.segments[0].collimator_deg == 30.0 for b in plan.beams)
    flat = build_photon_plan([(g, c) for _, g, c, _ in beams], (-20, 20), (-20, 20), 5.0, 1.0)
    machine = load_photon_spec("synthetic-120")
    with pytest.raises(ValueError, match="collimator"):
        plan_arcs(flat, np.ones(flat.n_beamlets), [arc], np.ones((4, 4, 4), np.float32), (5, 5, 5), (0, 0, 0),
                  lambda d: (0.0, np.zeros_like(d)), machine, object())
