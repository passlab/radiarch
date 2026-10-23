"""Roadmap R8: the native photon pencil-beam engine ``pb``."""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.models.dose import ScenarioSpec
from radiarch.models.photon_plan import MLCRow, PhotonBeam, PhotonPlan, PhotonSegment
from radiarch.services.dose_engines import get_engine
from radiarch.services.dose_engines.pb import PencilBeamEngine, backend
from radiarch.services.dose_engines.pb_kernel import PBKernel, default_kernel_path, iso_bin_edges, to_isocenter_plane
from radiarch.services.dose_engines.protocol import EngineParamError, EngineUnavailableError
from radiarch.services.photon_beamlets import build_photon_plan

pytestmark = pytest.mark.skipif(not default_kernel_path().is_file(), reason="engines/pb kernel table missing")


@pytest.fixture(scope="module")
def eng():
    return PencilBeamEngine()


def _water(n_lat=41, n_depth=60, s=5.0, density=1.0):
    """Water, lateral voxel centres symmetric about the axis, surface at y = 0 (the isocenter plane)."""
    d = np.full((n_lat, n_depth, n_lat), density, np.float32)
    half = (n_lat - 1) / 2 * s
    return d, (s, s, s), (-half, s / 2, -half)


def _field(mm=100.0, gantry=0.0, couch=0.0, beamlet=5.0):
    h = mm / 2
    return build_photon_plan([(gantry, couch)], (-h, h), (-h, h), 10.0, 1.0, (beamlet, beamlet))


# ---------------------------------------------------------------------------
# Kernel
# ---------------------------------------------------------------------------

class TestKernel:
    def test_isocenter_plane_remap_conserves_the_integral(self):
        rng = np.random.default_rng(1)
        plane = rng.random((41, 41))
        for m in (1.0, 1.13, 1.3):
            assert to_isocenter_plane(plane, m).sum() == pytest.approx(plane.sum(), rel=1e-9)
        # a lengthening of 1.3 moves mass inwards
        r = np.hypot(*np.meshgrid(np.arange(-20, 21), np.arange(-20, 21)))
        iso = to_isocenter_plane(plane, 1.3)
        assert (iso * r).sum() < (plane * r).sum()

    def test_table_shape_and_bins(self):
        k = PBKernel.load()
        assert k.table.shape == (k.depth_mm.size, k.bin_counts.size)
        assert np.array_equal(k.bin_edges_mm, iso_bin_edges())
        assert k.depth_mm[-1] >= 450.0 and np.all(np.diff(k.depth_mm) > 0)
        integral = k.integral()
        assert np.all(integral > 0)
        # beyond the build-up the integral (the broad-beam dose) falls with depth (every 10 mm: Monte Carlo noise)
        d = np.arange(40.0, 450.0, 10.0)
        assert np.all(np.diff(np.interp(d, k.depth_mm, integral)) < 0)

    @pytest.mark.parametrize("n,tol", [(4, 0.012), (6, 0.006)])
    def test_decomposition_reproduces_square_field_doses(self, n, tol):
        k = PBKernel.load()
        d = np.arange(20.0, 300.0, 2.0)
        for hw in (15.0, 25.0, 50.0, 100.0, 150.0):
            full = k.field_dose(hw, d)
            assert np.max(np.abs(k.field_dose(hw, d, n) / full - 1.0)) < tol, hw

    def test_pdd_of_the_reference_field(self):
        k = PBKernel.load()
        d = np.arange(1.0, 300.0, 1.0)
        cax = k.field_dose(50.0, d)
        dmax = d[np.argmax(cax)]
        assert 10.0 <= dmax <= 22.0
        pdd10 = np.interp(100.0, d, cax) / cax.max() * 100
        assert 64.0 < pdd10 < 71.0                         # 6 MV, 10 x 10 at SSD 100


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class TestEngine:
    def test_registered_and_healthy(self, eng):
        assert get_engine("pb").name == "pb"
        h = eng.health()
        assert h["available"] and h["diagnostics"]["kernel_fingerprint"]

    def test_calibration_is_one_cgy_per_mu_at_dmax(self, eng):
        cal = eng.calibration()
        assert 10.0 <= cal["dmax_mm"] <= 22.0 and cal["factor_gy_per_unit"] > 0
        density, sp, org = _water(n_lat=61, n_depth=40, s=2.5)
        dose = eng.compute_plan_dose(density, sp, org, _field())
        c = 30
        cax = dose[c, :, c]
        assert cax.max() == pytest.approx(0.01, rel=0.02)

    def test_profile_is_symmetric_and_edges_are_geometric(self, eng):
        density, sp, org = _water(n_lat=61, n_depth=50, s=2.5)
        dose = eng.compute_plan_dose(density, sp, org, _field())
        c = 30
        k = int(round((100.0 - org[1]) / sp[1]))         # 10 cm deep
        prof = dose[c, k, :] / dose[c, k, c]
        assert np.allclose(prof, prof[::-1], rtol=1e-4, atol=1e-6)
        xs = org[0] + np.arange(61) * sp[0]
        edge = float(np.interp(0.5, prof[c:][::-1], xs[c:][::-1]))
        assert edge == pytest.approx(50.0 * 1.1, abs=1.5)       # the 50 % point at the divergent field edge

    @pytest.mark.parametrize("gantry,entrance", [(90.0, +1), (270.0, -1)])
    def test_iec_gantry_direction(self, eng, gantry, entrance):
        n, s = 31, 5.0
        density = np.ones((n, n, n), np.float32)
        org = (-(n - 1) / 2 * s,) * 3
        dose = eng.compute_plan_dose(density, (s, s, s), org, _field(60.0, gantry))
        c = n // 2
        line = dose[c, c, :]
        assert (line[c + 3:].mean() - line[:c - 2].mean()) * entrance > 0.1 * line.max()
        assert dose[c, :, c][c - 2:c + 3].std() / dose[c, :, c][c - 2:c + 3].mean() < 0.05

    def test_couch_turns_the_beam_about_the_vertical(self, eng):
        n, s = 31, 5.0
        density = np.ones((n, n, n), np.float32)
        org = (-(n - 1) / 2 * s,) * 3
        from radiarch.dicom.drr import beam_frame
        _, _, d = beam_frame(90.0, 90.0)                       # gantry 90, couch 90: along z
        assert abs(d[2]) == pytest.approx(1.0, abs=1e-9)
        dose = eng.compute_plan_dose(density, (s, s, s), org, _field(60.0, 90.0, 90.0))
        c = n // 2
        along_z = dose[:, c, c]
        upstream = along_z[:c - 2].mean() if d[2] > 0 else along_z[c + 3:].mean()
        downstream = along_z[c + 3:].mean() if d[2] > 0 else along_z[:c - 2].mean()
        assert upstream > 1.1 * downstream

    def test_influence_matrix_matches_the_dose(self, eng):
        density, sp, org = _water()
        plan = _field(60.0)
        dose = eng.compute_plan_dose(density, sp, org, plan, weights=plan.beamlet_mu())
        exact = eng.influence_matrix(density, sp, org, plan, params={"sampling_threshold": 0.0, "cutoff_mm": 150.0})
        sampled = eng.influence_matrix(density, sp, org, plan)
        inner = dose > 0.5 * dose.max()
        for dij, tol_mean, tol_max in ((exact, 0.003, 0.02), (sampled, 0.01, 0.06)):
            d2 = np.asarray(dij @ plan.beamlet_mu()).reshape(density.shape)
            ratio = d2[inner] / dose[inner]
            assert abs(ratio.mean() - 1) < tol_mean and np.abs(ratio - 1).max() < tol_max
        assert sampled.nnz < 0.6 * exact.nnz

    def test_apertures_and_beamlets_agree_for_an_aligned_open_field(self, eng):
        density, sp, org = _water()
        plan = _field(60.0)
        a = eng.compute_plan_dose(density, sp, org, plan, params={"fluence": "apertures"})
        b = eng.compute_plan_dose(density, sp, org, plan, params={"fluence": "beamlets"})
        m = a > 0.2 * a.max()
        assert np.allclose(a[m], b[m], rtol=0.01)

    def test_segment_dose_matrix(self, eng):
        density, sp, org = _water()
        rows = [MLCRow(y_min_mm=y, y_max_mm=y + 10, x_left_mm=-30 + abs(y) / 2, x_right_mm=20) for y in range(-30, 30, 10)]
        segs = [PhotonSegment(mu=mu, x_jaw_mm=(-30, 30), y_jaw_mm=(-30, 30), mlc_rows=rows if k else [], control_point_index=k)
                for k, mu in enumerate((40.0, 25.0))]
        plan = PhotonPlan(beams=[PhotonBeam(beam_id="A", gantry_deg=0.0, segments=segs),
                                 PhotonBeam(beam_id="B", gantry_deg=30.0, segments=[segs[0]])])
        S = eng.segment_dose_matrix(density, sp, org, plan)
        assert S.shape == (density.size, 3)
        dose = eng.compute_plan_dose(density, sp, org, plan, params={"fluence": "apertures"})
        d2 = np.asarray(S @ np.array([40.0, 25.0, 40.0])).reshape(density.shape)
        m = dose > 0.5 * dose.max()
        assert abs(np.mean(d2[m] / dose[m]) - 1) < 0.01

    def test_lung_slab_shortens_the_depth(self, eng):
        water, sp, org = _water()
        lung = water.copy()
        lung[:, 6:22, :] = 0.26                          # 30-110 mm
        plan = _field(100.0)
        dw = eng.compute_plan_dose(water, sp, org, plan)
        dl = eng.compute_plan_dose(lung, sp, org, plan)
        c = 20
        k = int(round((150.0 - org[1]) / sp[1]))
        assert dl[c, k, c] / dw[c, k, c] > 1.15            # 80 mm of lung is ~59 mm less water

    def test_scenarios(self, eng):
        density, sp, org = _water()
        plan = _field(60.0)
        base = eng.compute_plan_dose(density, sp, org, plan)
        shifted = eng.compute_plan_dose(density, sp, org, plan, scenario=ScenarioSpec(setup_shift_mm=(10.0, 0.0, 0.0)))
        c, k = 20, 10
        xs = org[0] + np.arange(density.shape[2]) * sp[0]
        edge = lambda d: float(np.interp(0.5, (d[c, k, c + 2:] / d[c, k, c + 2])[::-1], xs[c + 2:][::-1]))  # noqa: E731
        assert edge(shifted) - edge(base) == pytest.approx(10.0, abs=1.0)
        dense = eng.compute_plan_dose(density, sp, org, plan, scenario=ScenarioSpec(density_scale=1.1))
        assert dense[c, 40, c] < base[c, 40, c]

    def test_air_outside_gets_no_dose_and_cavities_do(self, eng):
        density, sp, org = _water()
        density[:, :4, :] = 0.001                        # air in front
        density[18:23, 20:24, 18:23] = 0.001             # an enclosed cavity on the axis
        dose = eng.compute_plan_dose(density, sp, org, _field(60.0))
        assert dose[:, :4, :].max() == 0.0 and dose.max() > 0
        assert dose[20, 22, 20] > 0.5 * dose[20, 30, 20]

    def test_params_are_checked(self, eng):
        with pytest.raises(EngineParamError):
            eng._run({"device": "tpu"})
        with pytest.raises(EngineParamError):
            eng._run({"cutoff_mm": 500})
        with pytest.raises(EngineParamError):
            eng._run({"sampling_threshold": 0.9})
        density, sp, org = _water()
        plan = _field(60.0)
        with pytest.raises(EngineParamError):
            eng.compute_plan_dose(density, sp, org, plan, weights=plan.beamlet_mu(), params={"fluence": "apertures"})

    def test_gpu_needs_cupy(self, eng):
        try:
            backend("gpu")
        except EngineUnavailableError:
            return                                           # no CuPy or no device: the error the API reports
        assert backend("gpu").gpu

    def test_cache_key_carries_the_engine_version(self):
        from radiarch.models.dose import EngineSpec
        assert EngineSpec(name="pb").key_version() == f"default={PencilBeamEngine().version}"


# ---------------------------------------------------------------------------
# The second-engine check against the collapsed cone
# ---------------------------------------------------------------------------

class TestLateralScaling:
    """Density-scaled lateral kernels (pb 1.1.0): a narrow field loses dose in lung, water is untouched."""

    @staticmethod
    def _slab(s=2.5):
        d, sp_, org = _water(n_lat=61, n_depth=80, s=s)
        d[:, int(30 / s):int(110 / s), :] = 0.26             # lung 3-11 cm deep, as the Monte Carlo slab
        return d, sp_, org

    @staticmethod
    def _cax(dose, s=2.5):
        c = dose.shape[0] // 2
        return dose[c, :, c]

    def test_water_is_unchanged(self, eng):
        d, sp_, org = _water(n_lat=61, n_depth=60, s=2.5)
        plan = _field(20.0)
        on = eng.compute_plan_dose(d, sp_, org, plan)
        off = eng.compute_plan_dose(d, sp_, org, plan, params={"lateral_scaling": False})
        assert np.array_equal(on, off)

    def test_narrow_field_in_lung_loses_dose(self, eng):
        d, sp_, org = self._slab()
        j = int(80 / 2.5)                                     # 8 cm deep, in the lung
        for mm, lo, hi in ((20.0, 0.70, 0.85), (100.0, 0.95, 1.0)):
            plan = _field(mm)
            on = self._cax(eng.compute_plan_dose(d, sp_, org, plan))
            off = self._cax(eng.compute_plan_dose(d, sp_, org, plan, params={"lateral_scaling": False}))
            assert lo < on[j] / off[j] < hi, (mm, on[j] / off[j])
            assert on[2] == pytest.approx(off[2], rel=0.02)   # the water above the lung barely changes

    def test_influence_matrix_matches_the_full_dose(self, eng):
        d, sp_, org = self._slab()
        plan = _field(20.0)
        full = eng.compute_plan_dose(d, sp_, org, plan, weights=plan.beamlet_mu(), params={"fluence": "beamlets"})
        dij = eng.influence_matrix(d, sp_, org, plan, params={"sampling_threshold": 0})
        dd = np.asarray(dij @ plan.beamlet_mu()).reshape(full.shape)
        hi = full > 0.5 * full.max()
        assert np.median(dd[hi] / full[hi]) == pytest.approx(1.0, abs=0.01)

    def test_parameters_are_checked(self, eng):
        d, sp_, org = _water()
        with pytest.raises(EngineParamError):
            eng.compute_plan_dose(d, sp_, org, _field(), params={"lateral_max_scale": 0.5})


def _ccc_available():
    try:
        from radiarch.services.dose_engines.ccc import CCCEngine
        return CCCEngine().driver().availability()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _ccc_available(), reason="CCC binary not available")
def test_pb_and_ccc_agree_in_water(eng, monkeypatch, tmp_path):
    """The cross-engine gamma of the roadmap: a 10 x 10 cm field at SSD 100 cm, 10 mm beamlets (the
    configuration R7 validated CCC in), 3 %/3 mm global above 20 %."""
    from radiarch.config import get_settings
    from radiarch.services.dose_engines.ccc import CCCEngine
    from radiarch.services.gamma import gamma_index

    monkeypatch.setenv("RADIARCH_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("RADIARCH_CCC_CALIBRATION_SPACING_MM", "5.0")
    get_settings.cache_clear()
    try:
        density, sp, org = _water(n_lat=41, n_depth=50, s=5.0)
        plan = _field(100.0, beamlet=10.0)
        ccc = CCCEngine().compute_plan_dose(density, sp, org, plan)
        pb = eng.compute_plan_dose(density, sp, org, plan, weights=plan.beamlet_mu())
    finally:
        get_settings.cache_clear()
    g = gamma_index(pb, ccc, (sp[2], sp[1], sp[0]), 3.0, 3.0, threshold_pct=20.0)
    assert g.pass_rate_pct >= 95.0, g


def _gpu_ok():
    try:
        return backend("gpu").gpu
    except Exception:
        return False


@pytest.mark.skipif(not _gpu_ok(), reason="CuPy or a CUDA device not available")
def test_gpu_matches_cpu(eng):
    density, sp, org = _water()
    density[:, 10:20, :] = 0.26
    plan = _field(60.0, gantry=30.0)
    cpu = eng.compute_plan_dose(density, sp, org, plan, params={"device": "cpu"})
    gpu = eng.compute_plan_dose(density, sp, org, plan, params={"device": "gpu"})
    m = cpu > 0.05 * cpu.max()
    assert np.allclose(gpu[m], cpu[m], rtol=1e-4)
    w = plan.beamlet_mu()
    d_cpu = np.asarray(eng.influence_matrix(density, sp, org, plan, params={"device": "cpu"}) @ w)
    d_gpu = np.asarray(eng.influence_matrix(density, sp, org, plan, params={"device": "gpu"}) @ w)
    mm = d_cpu > 0.2 * d_cpu.max()
    assert np.max(np.abs(d_gpu[mm] / d_cpu[mm] - 1)) < 0.01      # roulette entries at the threshold may round differently


def test_gpu_backend_keeps_the_locale():
    """Initialising CUDA sets the thread's locale to C; the backend puts it back, so text files keep their encoding."""
    import locale
    from radiarch.services.dose_engines.pb import backend
    before = locale.getpreferredencoding(False)
    try:
        be = backend("gpu")
    except Exception:
        pytest.skip("no CuPy or CUDA device")
    be.xp.ones(4).sum()
    assert locale.getpreferredencoding(False) == before


def test_gpu_lookup_stays_inside_the_array():
    """CuPy 14's constant-mode interpolation on float32 reads one element past the array for a coordinate just
    below the last index; the engine's lookup pads, so the memory after the array cannot leak into doses."""
    from scipy.ndimage import map_coordinates
    from radiarch.services.dose_engines.pb import _lookup
    try:
        be = backend("gpu")
    except Exception:
        pytest.skip("no CuPy or CUDA device")
    xp, n = be.xp, 463
    buf = xp.full(n + 64, 1e30, dtype=xp.float32)               # poison right after the array
    buf[:n] = xp.arange(1, n + 1, dtype=xp.float32)
    coords = np.array([[n - 1 - 6e-6, n - 1.0, n - 1.5, n - 0.5, -6e-6, 0.0, 3.25]])
    got = be.to_host(_lookup(be, buf[:n], xp.asarray(coords)))
    want = map_coordinates(np.arange(1, n + 1, dtype=np.float32), coords, order=1, mode="constant", cval=0.0, prefilter=False)
    assert np.allclose(got, want, rtol=1e-5, atol=1e-6)        # CuPy's mixed precision: weights off by ~1e-5, no garbage

