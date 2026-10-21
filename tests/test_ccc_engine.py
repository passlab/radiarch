"""The CCC photon engine (roadmap R1): file protocol, parity with OpenTPS's
IO, and physics sanity on water phantoms.

Three tiers: pure-Python protocol tests (always), parity with the vendored
OpenTPS writer/reader (skipped without OpenTPS), and runs of the real
``CCC_DoseEngine`` binary (skipped when it is not available)."""

from __future__ import annotations

import os
import struct
import types

import numpy as np
import pytest

from radiarch.services.dose_engines.ccc_driver import (
    BeamletGeometry,
    CCCDriver,
    EXIT_FAILURE,
    EXIT_SUCCESS,
    beamlet_geometry_from_plan,
    engine_index_to_rows,
    read_sparse_beamlets,
    rotated_versors,
    write_beamlet_specs,
    write_geometry,
)
from radiarch.services.photon_beamlets import build_photon_plan


needs_binary = pytest.mark.skipif(not CCCDriver().availability()[0], reason=CCCDriver().availability()[1])


def _numbers(path) -> list:
    out = []
    for line in open(path):
        for tok in line.split():
            try:
                out.append(float(tok))
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------------------
# Protocol, no engine
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_index_mapping_round_trip(self):
        nz, ny, nx = 3, 4, 5
        # engine index: C-order over (z, x, y)
        z, x, y = np.meshgrid(np.arange(nz), np.arange(nx), np.arange(ny), indexing="ij")
        flat = (z * nx + x) * ny + y
        rows = engine_index_to_rows(flat.ravel(), (nz, ny, nx))
        expect = ((z * ny + y) * nx + x).ravel()
        assert np.array_equal(rows, expect)
        assert len(set(rows.tolist())) == nz * ny * nx

    def test_geometry_files(self, tmp_path):
        d = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)   # (z, y, x)
        header, density = write_geometry(tmp_path, d, (1.0, 2.0, 3.0), (-10.0, -20.0, -30.0), (1.0, 2.0, 3.0))
        text = header.read_text().splitlines()
        assert text[1] == "3 4 2"                 # Xcount Ycount Zcount = ny nx nz
        assert text[3] == "-2.2 -1.1 -3.3"        # (oy-iy, ox-ix, oz-iz) in cm
        assert text[5] == "0.2 0.1 0.3"           # (sy, sx, sz) in cm
        assert text[7] == "-1.0 -2.0 -3.0"        # unshifted origin (x, y, z) in cm
        raw = np.fromfile(density, dtype=np.float32)
        assert np.array_equal(raw, d.transpose(0, 2, 1).ravel())

    def test_beamlet_specs_layout(self, tmp_path):
        g = BeamletGeometry(np.array([[10.0, -20.0]]), np.array([[5.0, 5.0]]),
                            np.array([[0.0, 0.0, 0.0]]), np.array([1000.0]))
        p = tmp_path / "specs.txt"
        write_beamlet_specs(p, g, first_number=7)
        lines = p.read_text().splitlines()
        assert lines[0:2] == ["beamnum:", "1"]
        assert lines[3:5] == ["num", "7"]
        assert lines[6].split() == ["100.000000", "1.000000", "-2.000000", "0.500000", "0.500000"]
        assert lines[8].split() == ["-100.000000", "-0.000000", "-0.000000"]   # source at -k·SAD, k = +x
        assert lines[14].split() == ["1.000000", "0.000000", "0.000000"]       # kp

    def test_versors_are_orthonormal_and_gantry_0_points_at_the_gantry(self):
        for g, c, col in [(0, 0, 0), (90, 0, 0), (37, 12, -20), (270, -45, 90)]:
            i, j, k = (np.array(v) for v in rotated_versors(g, c, col))
            assert np.allclose([i @ i, j @ j, k @ k], 1.0)
            assert np.allclose([i @ j, j @ k, i @ k], 0.0, atol=1e-12)
        _, _, k0 = rotated_versors(0, 0, 0)
        assert np.allclose(k0, [1.0, 0.0, 0.0])

    def test_read_sparse_beamlets_hand_made(self, tmp_path):
        nz, ny, nx = 2, 3, 4
        eng = lambda z, x, y: (z * nx + x) * ny + y      # engine: C-order over (z, x, y)
        row = lambda z, y, x: (z * ny + y) * nx + x      # radiarch: C-order over (z, y, x)
        payload = struct.pack("i", 2)
        payload += struct.pack("iiiii", 0, ny, nx, nz, 1) + struct.pack("i", eng(0, 1, 1)) + struct.pack("f", 2.5)
        payload += struct.pack("iiiii", 1, ny, nx, nz, 2) + struct.pack("ii", eng(1, 2, 2), eng(0, 0, 0)) + struct.pack("ff", 1.0, 0.5)
        p = tmp_path / "out.bin"; p.write_bytes(payload)
        m = read_sparse_beamlets(p, (nz, ny, nx)).toarray()
        assert m.shape == (nz * ny * nx, 2)
        assert m[row(0, 1, 1), 0] == 2.5
        assert m[row(1, 2, 2), 1] == 1.0
        assert m[row(0, 0, 0), 1] == 0.5
        assert m.sum() == pytest.approx(4.0)

    def test_read_sparse_beamlets_rejects_wrong_grid(self, tmp_path):
        from radiarch.services.dose_engines.protocol import EngineRuntimeError
        p = tmp_path / "out.bin"
        p.write_bytes(struct.pack("i", 1) + struct.pack("iiiii", 0, 9, 9, 9, 0))
        with pytest.raises(EngineRuntimeError, match="grid"):
            read_sparse_beamlets(p, (2, 3, 4))

    def test_plan_flattens_beam_by_beam(self):
        plan = build_photon_plan([(0.0, 0.0), (90.0, 10.0)], (-50.0, 50.0), (-50.0, 50.0), 10.0, 2.0, (10.0, 10.0))
        g = beamlet_geometry_from_plan(plan)
        assert len(g) == 200
        assert np.all(g.angles_deg[:100] == [0.0, 0.0, 0.0]) and np.all(g.angles_deg[100:] == [90.0, 10.0, 0.0])
        assert np.all(g.size_mm == 10.0) and np.all(g.sad_mm == 1000.0)
        assert np.array_equal(plan.beamlet_mu(), np.full(200, 2.0))


class TestExitCodes:
    """The engine's defs.h says SUCCESS 1, FAILURE 0."""

    @staticmethod
    def _fake_run(returncode):
        def run(cmd, **kw):
            out = cmd[-1]
            if returncode == EXIT_SUCCESS:
                open(out, "wb").write(struct.pack("i", 0))
            return types.SimpleNamespace(returncode=returncode, stdout="log", stderr="")
        return run

    def _driver(self, tmp_path):
        eng = tmp_path / "engine"
        (eng / "CCC_DoseEngine").mkdir(parents=True)
        b = eng / "CCC_DoseEngine" / "CCC_DoseEngine"; b.write_text("#!/bin/sh\n"); b.chmod(0o755)
        (eng / "Kernels_differentFluence").mkdir(); (eng / "Kernels_differentFluence" / "kernel_header.txt").write_text("x")
        return CCCDriver(engine_dir=eng)

    def test_zero_is_failure(self, tmp_path, monkeypatch):
        import radiarch.services.dose_engines.ccc_driver as mod
        from radiarch.services.dose_engines.protocol import EngineRuntimeError
        monkeypatch.setattr(mod.subprocess, "run", self._fake_run(EXIT_FAILURE))
        g = BeamletGeometry(np.zeros((1, 2)), np.ones((1, 2)), np.zeros((1, 3)), np.array([1000.0]))
        with pytest.raises(EngineRuntimeError, match="failure"):
            self._driver(tmp_path).run(np.ones((2, 2, 2), np.float32), (1, 1, 1), (0, 0, 0), (0, 0, 0), g)

    def test_other_codes_are_crashes(self, tmp_path, monkeypatch):
        import radiarch.services.dose_engines.ccc_driver as mod
        from radiarch.services.dose_engines.protocol import EngineRuntimeError
        monkeypatch.setattr(mod.subprocess, "run", self._fake_run(139))
        g = BeamletGeometry(np.zeros((1, 2)), np.ones((1, 2)), np.zeros((1, 3)), np.array([1000.0]))
        with pytest.raises(EngineRuntimeError, match="1 is success"):
            self._driver(tmp_path).run(np.ones((2, 2, 2), np.float32), (1, 1, 1), (0, 0, 0), (0, 0, 0), g)


# ---------------------------------------------------------------------------
# Physics sanity with the real binary
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(monkeypatch, tmp_path):
    """A CCCEngine whose calibration cache lives under tmp and runs at 5 mm."""
    monkeypatch.setenv("RADIARCH_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("RADIARCH_CCC_CALIBRATION_SPACING_MM", "5.0")
    monkeypatch.setenv("RADIARCH_CCC_N_JOBS", str(min(4, os.cpu_count() or 1)))
    from radiarch.config import get_settings
    get_settings.cache_clear()
    from radiarch.services.dose_engines.ccc import CCCEngine
    yield CCCEngine()
    get_settings.cache_clear()


def _water_slab(n_lat=33, n_depth=40, s=4.0):
    """Water, surface at y = 0 (isocenter plane); ``n_lat`` is odd so one lateral voxel sits on the axis."""
    assert n_lat % 2 == 1
    density = np.ones((n_lat, n_depth, n_lat), np.float32)
    half = (n_lat - 1) / 2 * s
    return density, (s, s, s), (-half, s / 2, -half)


@needs_binary
class TestPhysics:
    def test_calibration_gives_one_cgy_per_mu_at_dmax(self, engine):
        rec = engine.calibration().record()
        assert 10.0 <= rec.dmax_mm <= 25.0                    # 6 MV build-up
        assert rec.factor_gy_per_unit > 0
        # A second call is served from the cache (same record object).
        assert engine.calibration().record() is rec

    def test_reference_field_on_a_slab(self, engine):
        density, spacing, origin = _water_slab()
        plan = build_photon_plan([(0.0, 0.0)], (-50.0, 50.0), (-50.0, 50.0), 10.0, 1.0, (5.0, 5.0))
        dose = engine.compute_plan_dose(density, spacing, origin, plan)
        c = (density.shape[0] - 1) // 2
        cax = dose[c, :, c]
        k = int(np.argmax(cax))
        # 1 MU → ~1 cGy at d_max (slab is narrower than the calibration phantom: a few %).
        assert abs(cax[k] - 0.01) / 0.01 < 0.06
        assert 5.0 <= origin[1] + k * spacing[1] <= 25.0
        assert np.all(np.diff(cax[k + 2:]) < 0)              # falls off beyond d_max
        prof = dose[c, int(round((100 - origin[1]) / spacing[1])), :]   # lateral profile at 10 cm depth
        xs = origin[0] + np.arange(prof.size) * spacing[0]
        core = np.abs(xs) <= 40.0                                        # inside the 10 cm field, off the penumbra
        assert np.allclose(prof[core], prof[core][::-1], rtol=0.02)      # symmetric (the collapsed cones leave
        assert prof[core].std() / prof[core].mean() < 0.03               #  the penumbra slightly asymmetric)
        assert prof[0] < 0.05 * prof[c] and prof[-1] < 0.05 * prof[c]    # little dose outside the field

    def test_gantry_90_enters_along_x(self, engine):
        n, s = 32, 4.0
        density = np.ones((n, n, n), np.float32); origin = (-(n - 1) / 2 * s,) * 3
        plan = build_photon_plan([(90.0, 0.0)], (-30.0, 30.0), (-30.0, 30.0), 10.0, 1.0, (10.0, 10.0))
        dose = engine.compute_plan_dose(density, spacing_mm=(s, s, s), origin_mm=origin, plan=plan)
        c = n // 2
        along_x = dose[c, c, :]; along_y = dose[c, :, c]
        # The beam axis is x: dose varies strongly along x (entrance side higher) and is flat along y inside the field.
        assert along_x[:c].mean() != pytest.approx(along_x[c:].mean(), rel=0.05)
        inside = along_y[c - 3:c + 4]
        assert inside.std() / inside.mean() < 0.05

    def test_dij_and_dose_agree_and_scenarios_behave(self, engine):
        from radiarch.models.dose import ScenarioSpec
        density, spacing, origin = _water_slab()
        plan = build_photon_plan([(0.0, 0.0)], (-30.0, 30.0), (-30.0, 30.0), 10.0, 2.0, (10.0, 10.0))
        dij = engine.influence_matrix(density, spacing, origin, plan)
        w = plan.beamlet_mu()
        dose = engine.compute_plan_dose(density, spacing, origin, plan, weights=w)
        assert np.allclose(np.asarray(dij @ w.astype(np.float32)).reshape(density.shape), dose)
        c = (density.shape[0] - 1) // 2
        k10 = int(round((100 - origin[1]) / spacing[1]))
        # lighter medium → more dose at depth
        light = engine.compute_plan_dose(density, spacing, origin, plan, scenario=ScenarioSpec(density_scale=0.5))
        assert light[c, k10, c] > dose[c, k10, c]
        # a +20 mm x setup shift moves the field by +20 mm in x
        shifted = engine.compute_plan_dose(density, spacing, origin, plan, scenario=ScenarioSpec(setup_shift_mm=(20.0, 0.0, 0.0)))
        xs = origin[0] + np.arange(density.shape[2]) * spacing[0]
        def centroid(d):
            p = d[c, k10, :]; return float((xs * p).sum() / p.sum())
        assert centroid(shifted) - centroid(dose) == pytest.approx(20.0, abs=spacing[0])

    def test_plugin_surface(self, engine):
        """build_influence / compute_dose / apply_influence through the DoseEnginePlugin bundles."""
        from radiarch.models.beam_model import Modality
        from radiarch.services.dose_engines.protocol import BeamModelBundle, GeometryBundle

        density, spacing, origin = _water_slab(n_lat=25, n_depth=24, s=5.0)
        plan = build_photon_plan([(0.0, 0.0)], (-25.0, 25.0), (-25.0, 25.0), 10.0, 1.0, (10.0, 10.0))
        fl = types.SimpleNamespace(total_count=plan.n_beamlets)
        geometry = GeometryBundle(result=types.SimpleNamespace(grid_spec=types.SimpleNamespace(origin_mm=origin)),
                                  density=density, masks=np.zeros(density.shape, np.uint16), spacing_mm=spacing, origin_mm=origin)
        beam_model = BeamModelBundle(result=types.SimpleNamespace(modality=Modality.photon_imrt, fluence_elements=fl), plan=plan)
        assert engine.validate(geometry, beam_model, {}) == []
        inf = engine.build_influence(geometry, beam_model)
        assert (inf.n_voxels, inf.n_elements) == (density.size, plan.n_beamlets) and inf.nnz > 0
        w = np.ones(plan.n_beamlets, np.float32)
        a = engine.apply_influence(inf, w, density.shape).dose
        b = engine.compute_dose(geometry, beam_model, w).dose
        assert np.allclose(a, b) and a.max() > 0
        assert engine.health()["available"] is True and engine.health()["test_only"] is False
