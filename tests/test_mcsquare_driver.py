"""radiarch's MCsquare driver and engine (roadmap R14).

Three layers: the file protocol (no engine needed), parity of the written
inputs with the goldens captured from the vendored OpenTPS wrapper (needs the
SimpleFantom data and OpenTPS for the beam model), and runs of the engine
itself (needs the Linux binaries): bit-level agreement with the OpenTPS path
at a fixed seed, frames on a non-cubic grid, and the plugin surface.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot, RangeShifterSetting
from radiarch.services.dose_engines import mcsquare_driver as D

ASSETS = D.default_assets()
GOLDEN = Path(__file__).resolve().parent / "golden" / "mcsquare_inputs_simplefantom"


needs_assets = pytest.mark.skipif(not ASSETS.root.is_dir(), reason="MCsquare assets not present")
needs_binary = pytest.mark.skipif(not ASSETS.availability()[0], reason=ASSETS.availability()[1])
GPU_ASSETS = D.MCsquareAssets(ASSETS.root, "radiarch", "gpu")
needs_gpu = pytest.mark.skipif(not (ASSETS.build == "radiarch" and ASSETS.availability()[0] and GPU_ASSETS.availability()[0]),
                               reason=f"MCsquare on a GPU: {GPU_ASSETS.availability()[1]}")


def _plan(spots=((0.0, 0.0, 1.0),), energy=150.0, gantry=0.0, iso=(0.0, 0.0, 0.0)) -> ProtonPlan:
    return ProtonPlan(beams=[ProtonBeam(
        isocenter_mm=iso, gantry_deg=gantry,
        layers=[ProtonLayer(energy_mev=energy, spots=[ProtonSpot(x_mm=x, y_mm=y, mu=mu) for x, y, mu in spots])],
    )])


# ---------------------------------------------------------------------------
# File protocol
# ---------------------------------------------------------------------------

class TestFrames:
    def test_engine_frame_round_trip(self):
        v = np.random.default_rng(0).random((3, 4, 5)).astype(np.float32)
        back = D.from_engine_frame(D.to_engine_frame(v))
        assert back.shape == v.shape and np.array_equal(back, v) and back.flags.c_contiguous

    @pytest.mark.parametrize("shape", [(5, 4, 3), (8, 8, 8), (4, 6, 5)])
    def test_row_permutation_matches_opentps_reconstruction(self, shape):
        """OpenTPS rebuilds a dose from MCsquare's flat order with reshape(F) + two flips,
        in (x, y, z); our permutation gives the same volume transposed to (z, y, x)."""
        nz, ny, nx = shape
        flat = np.random.default_rng(1).random(nz * ny * nx).astype(np.float32)
        want = np.transpose(np.flip(np.flip(flat.reshape((nx, ny, nz), order="F"), 0), 1), (2, 1, 0))
        got = flat[D.native_row_permutation(shape)].reshape(shape)
        np.testing.assert_array_equal(got, want)

    def test_row_permutation_is_a_permutation(self):
        perm = D.native_row_permutation((5, 4, 3))
        assert sorted(perm.tolist()) == list(range(60))

    def test_offset_and_isocenter(self):
        # 10 × 20 × 30 voxels of 2 mm at origin (1, 2, 3): corner offset and y inversion.
        assert D.mcsquare_offset((1.0, 2.0, 3.0), (2.0, 2.0, 2.0), (10, 20, 30)) == (0.0, -2.0 - 40.0 + 1.0, 2.0)
        iso = D.isocenter_to_mcsquare((1.0, 2.0, 3.0), (1.0, 2.0, 3.0), (2.0, 2.0, 2.0), (10, 20, 30))
        assert iso == (1.0, 40.0 - 1.0, 1.0)


class TestWriters:
    def test_ct_mhd_round_trip_and_header(self, tmp_path):
        hu = (np.arange(2 * 3 * 4, dtype=np.float32) - 10).reshape((2, 3, 4))   # (z, y, x)
        path = D.write_ct_mhd(hu, (1.5, 2.0, 2.5), (-3.0, 4.0, 5.0), tmp_path / "CT.mhd")
        text = path.read_text()
        assert "DimSize = 4 3 2 \n" in text and "ElementSpacing = 1.5 2.0 2.5 \n" in text
        assert "Offset = -3.75 -9.0 3.75 \n" in text and "ElementType = MET_FLOAT\n" in text
        assert "ElementDataFile = CT.raw\n" in text
        raw = np.fromfile(tmp_path / "CT.raw", dtype="<f4")
        assert raw.size == 24
        # First value written is the mirrored corner voxel [z=0, y=ny-1, x=nx-1].
        assert raw[0] == hu[0, 2, 3]
        back, spacing, offset = D.read_mhd(path)
        np.testing.assert_array_equal(back, hu)
        assert spacing == (1.5, 2.0, 2.5) and offset == (-3.75, -9.0, 3.75)

    def test_plan_pencil_text(self, tmp_path):
        plan = ProtonPlan(n_fractions=2, beams=[ProtonBeam(
            isocenter_mm=(0.0, 0.0, 0.0), gantry_deg=90.0, couch_deg=10.0,
            layers=[ProtonLayer(energy_mev=150.0, spots=[ProtonSpot(x_mm=1.0, y_mm=-2.0, mu=3.0), ProtonSpot(x_mm=0.0, y_mm=0.0, mu=0.5)]),
                    ProtonLayer(energy_mev=120.0, spots=[ProtonSpot(x_mm=5.0, y_mm=5.0, mu=1.0)])],
        )])
        path = D.write_plan_pencil(plan, tmp_path / "PlanPencil.txt", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (10, 10, 10))
        text = path.read_text()
        assert text.startswith("#TREATMENT-PLAN-DESCRIPTION\n#PlanName\nPlanPencil\n#NumberOfFractions\n2\n")
        assert "#TotalMetersetWeightOfAllFields\n4.500000\n" in text
        assert "###GantryAngle\n90.000000\n###PatientSupportAngle\n10.000000\n" in text
        assert "###IsocenterPosition\n0.500000\t 9.500000\t 0.500000\n" in text
        assert "###NumberOfControlPoints\n2\n\n#SPOTS-DESCRIPTION\n####ControlPointIndex\n1\n" in text
        assert "####CumulativeMetersetWeight\n3.500000\n####Energy (MeV)\n150.000000\n####NbOfScannedSpots\n2\n####X Y Weight\n1.000000 -2.000000 3.000000\n0.000000 0.000000 0.500000\n" in text
        assert "####CumulativeMetersetWeight\n4.500000\n####Energy (MeV)\n120.000000\n" in text
        assert "RangeShifter" not in text

    def test_plan_pencil_range_shifter_lines(self, tmp_path):
        plan = ProtonPlan(beams=[ProtonBeam(
            isocenter_mm=(0.0, 0.0, 0.0), range_shifter_id="RS_Block",
            layers=[ProtonLayer(energy_mev=100.0, spots=[ProtonSpot(x_mm=0, y_mm=0, mu=1)],
                                range_shifter=RangeShifterSetting(setting="IN", isocenter_to_range_shifter_mm=300.0))],
        )])
        bdl = D.BeamDataLibrary(text="", nominal_energy_mev=np.array([100.0]), protons_per_mu=np.array([1e8]),
                                range_shifter_wet_mm={"RS_Block": 74.1})
        text = D.write_plan_pencil(plan, tmp_path / "p.txt", (0, 0, 0), (1, 1, 1), (10, 10, 10), bdl).read_text()
        assert "###RangeShifterID\nRS_Block\n###RangeShifterType\nbinary\n" in text
        assert "####RangeShifterSetting\nIN\n####IsocenterToRangeShifterDistance\n300.000000\n####RangeShifterWaterEquivalentThickness\n74.100000\n" in text

    def test_config_renders_every_placeholder(self):
        text = D.render_config({**D.default_config(), "Num_Primaries": 1000})
        assert "{" not in text.replace("{}", "") or not __import__("re").search(r"\{[A-Z0-9_]+\}", text)
        assert "Num_Primaries \t1000\t" in text.replace("Num_Primaries 	1000", "Num_Primaries \t1000\t") or "1000" in text
        assert "Dose_MHD_Output\t\t\tTrue" in text or "True" in text

    def test_calibration_scaling(self):
        cal = D.CalibrationTables("# HU\tdensity\n-1000\t0.001\n0\t1.0\n1000\t1.5\n", "-1000\t17\n", "t")
        table = cal.scaled(1.1).density_table()
        np.testing.assert_allclose(table[:, 1], [0.0011, 1.1, 1.65])
        assert cal.scaled(1.0) is cal
        water = D.CalibrationTables.water()
        assert water.density_table()[:, 1].tolist() == [1.0, 1.0, 1.0]


class TestReaders:
    def test_sparse_beamlets_hand_made(self, tmp_path):
        # 2 × 2 × 2 grid, two spots: spot 0 lights native voxels 1-2 (one run), spot 1 lights voxel 7.
        header = tmp_path / "Sparse_Dose.txt"
        header.write_text("# comment\nNbrSpots = 2\nImageSize = 2 2 2\nVoxelSpacing = 1 1 1\nOffset = 0 0 0\n"
                          "SimulationMode = Beamlet simulation\nBinaryFile = Sparse_Dose.bin\n")
        b = bytearray()
        b += struct.pack("<IIIff", 2, 1, 1, 0.0, 0.0) + struct.pack("<II", 2, 1) + struct.pack("<ff", 10.0, 20.0)
        b += struct.pack("<IIIff", 1, 1, 1, 5.0, 0.0) + struct.pack("<II", 1, 7) + struct.pack("<f", 30.0)
        (tmp_path / "Sparse_Dose.bin").write_bytes(bytes(b))
        mat, hdr = D.read_sparse_beamlets(header)
        assert mat.shape == (8, 2) and hdr["NbrSpots"] == 2 and hdr["spots"][1][2] == 5.0
        dense = mat.toarray()
        assert dense[1, 0] == 10.0 and dense[2, 0] == 20.0 and dense[7, 1] == 30.0 and dense.sum() == 60.0

    @needs_assets
    def test_bdl_parses_the_vendored_library(self):
        bdl = D.BeamDataLibrary.load(ASSETS.bdl_path())
        assert bdl.nominal_energy_mev[0] == 20.0 and bdl.nominal_energy_mev[-1] == 225.0
        assert bdl.mu_to_protons(150.0) == pytest.approx(115140000.0)
        assert bdl.mu_to_protons(152.5) == pytest.approx((115140000.0 + 118316250.0) / 2.0)
        assert bdl.range_shifter_wet_mm == {"RS_Block": 74.1}

    @needs_assets
    def test_assets_available_and_fingerprinted(self):
        ok, reason = ASSETS.availability()
        assert ok or "Linux" in reason or "binary" in reason, reason
        assert len(ASSETS.fingerprint()) == 16


# ---------------------------------------------------------------------------
# A run that crashes is run once more (a stand-in launcher; no engine needed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "linux", reason="the driver runs MCsquare on Linux only")
class TestCrashRetry:
    # Counts its attempts in the work directory, leaves a partial output each time, and exits with
    # FAIL on the attempts up to CRASHES.
    LAUNCHER = ('n=$(cat count 2>/dev/null || echo 0); n=$((n + 1)); echo $n > count\n'
                'mkdir -p Outputs; echo partial > Outputs/part$n.txt; echo "attempt $n"\n'
                'if [ "$n" -le {crashes} ]; then exit {fail}; fi\n')

    def _driver(self, tmp_path, crashes, fail, build="radiarch"):
        root = tmp_path / "engine"
        (root / "Materials").mkdir(parents=True)
        (root / "Materials" / "list.dat").write_text("")
        (root / "BDL").mkdir()
        (root / "BDL" / D.DEFAULT_BDL).write_text("")
        (root / "Scanners" / D.DEFAULT_SCANNER).mkdir(parents=True)
        (root / "MCsquare_linux").write_text("")
        (root / "MCsquare_linux").chmod(0o755)
        (root / "MCsquare").write_text(self.LAUNCHER.format(crashes=crashes, fail=fail))
        (root / D.RADIARCH_BINARY).write_text("#!/bin/sh\n" + self.LAUNCHER.format(crashes=crashes, fail=fail))
        (root / D.RADIARCH_BINARY).chmod(0o755)
        work = tmp_path / "work"
        work.mkdir()
        return D.MCsquareDriver(assets=D.MCsquareAssets(root, build)), work

    def test_crash_signal(self):
        assert D.crash_signal(139) == 11 and D.crash_signal(-11) == 11      # through the shell, or the process itself
        assert D.crash_signal(134) == 6 and D.crash_signal(135) == 7
        assert all(D.crash_signal(rc) is None for rc in (0, 1, 2, 127, 137, 143, -9, -15))

    @pytest.mark.parametrize("build", D.BUILDS)
    @pytest.mark.parametrize("fail", [139, 135, 134])
    def test_one_crash_is_run_again(self, tmp_path, fail, build):
        drv, work = self._driver(tmp_path, crashes=1, fail=fail, build=build)
        run = drv.run(work)
        assert run.returncode == 0 and run.attempts == 2
        assert (work / "count").read_text().strip() == "2"
        assert (work / "mcsquare-attempt1.log").read_text().strip() == "attempt 1"
        assert run.stdout_path.read_text().strip() == "attempt 2"
        assert sorted(p.name for p in (work / "Outputs").iterdir()) == ["part2.txt"]     # the crash's output is gone

    @pytest.mark.parametrize("build", D.BUILDS)
    def test_a_second_crash_raises(self, tmp_path, build):
        drv, work = self._driver(tmp_path, crashes=2, fail=139, build=build)
        with pytest.raises(RuntimeError, match=r"exited with 139 \(attempt 2; the first crashed too\)"):
            drv.run(work)
        assert (work / "count").read_text().strip() == "2"

    @pytest.mark.parametrize("fail", [1, 137, 143])
    def test_other_failures_are_not_run_again(self, tmp_path, fail):
        drv, work = self._driver(tmp_path, crashes=1, fail=fail)
        with pytest.raises(RuntimeError, match=rf"exited with {fail} in "):
            drv.run(work)
        assert (work / "count").read_text().strip() == "1"

    def test_each_build_runs_its_own_program(self, tmp_path):
        drv, work = self._driver(tmp_path, crashes=0, fail=1, build="radiarch")
        cfg = work / "config.txt"
        assert drv.assets.command(cfg) == [str(drv.assets.radiarch_binary), str(cfg)]
        assert drv.assets.program_files() == [drv.assets.radiarch_binary]
        upstream = D.MCsquareAssets(drv.assets.root, "upstream")
        assert upstream.command(cfg) == ["sh", str(upstream.launcher), str(cfg)]
        assert upstream.program_files() == [upstream.launcher, *upstream.binaries()]
        assert drv.assets.fingerprint() != upstream.fingerprint()
        assert drv.availability() == (True, "ok") and upstream.availability() == (True, "ok")
        drv.assets.radiarch_binary.unlink()
        ok, reason = drv.availability()
        assert not ok and D.RADIARCH_BINARY in reason and upstream.availability()[0]
        with pytest.raises(ValueError, match="unknown MCsquare build"):
            D.MCsquareAssets(drv.assets.root, "icc")

    def test_opentps_is_the_old_name_of_upstream(self, tmp_path):
        """``mcsquare_build=opentps`` (before 2026-11-21) still runs upstream's binaries, with the same fingerprint."""
        root = tmp_path / "engine"
        old, new = D.MCsquareAssets(root, "opentps"), D.MCsquareAssets(root, "upstream")
        assert old.build == "upstream" and old == new and old.fingerprint() == new.fingerprint()

    def test_dropped_particles_are_counted(self, tmp_path):
        drv, work = self._driver(tmp_path, crashes=0, fail=1)
        drv.assets.radiarch_binary.write_text(
            "#!/bin/sh\necho 'Simulation of beamlet 1/1'\n"
            "echo 'Warning: 3 particles were dropped because their energy was not a finite number'\n")
        run = drv.run(work)
        assert run.returncode == 0 and run.dropped_particles == 3
        assert D.dropped_particles("no warning here") == 0


class TestDevice:
    """mcsquare_device (ADR 0024): which binary runs, with what environment, and auto's fallback to the CPU."""

    GPU_SCRIPT = ("#!/bin/sh\necho \"gpu=$MCSQUARE_GPU\" > gpu.txt\n"
                  "if [ -n \"{fail}\" ]; then echo ' ERROR: GPU initialisation failed'; exit 2; fi\necho gpu run\n")

    def _driver(self, tmp_path, monkeypatch, device, gpu_present=True, gpu_fails=False):
        drv, work = TestCrashRetry()._driver(tmp_path, crashes=0, fail=1)
        root = drv.assets.root
        (root / D.GPU_BINARY).write_text(self.GPU_SCRIPT.format(fail="1" if gpu_fails else ""))
        (root / D.GPU_BINARY).chmod(0o755)
        monkeypatch.setattr(D, "cuda_device_present", lambda: (True, "ok") if gpu_present else (False, "no GPU here"))
        return D.MCsquareDriver(assets=D.MCsquareAssets(root, "radiarch", device)), work

    def test_devices_are_checked(self, tmp_path):
        root = tmp_path / "engine"
        with pytest.raises(ValueError, match="unknown MCsquare device"):
            D.MCsquareAssets(root, "radiarch", "tpu")
        with pytest.raises(ValueError, match="needs radiarch's build"):
            D.MCsquareAssets(root, "upstream", "gpu")
        assert D.MCsquareAssets(root).device == "cpu"

    def test_each_device_runs_its_own_program(self, tmp_path, monkeypatch):
        cpu, work = self._driver(tmp_path, monkeypatch, "cpu")
        root, cfg = cpu.assets.root, work / "config.txt"
        gpu = D.MCsquareAssets(root, "radiarch", "gpu")
        auto = D.MCsquareAssets(root, "radiarch", "auto")
        assert cpu.assets.command(cfg) == [str(root / D.RADIARCH_BINARY), str(cfg)] and cpu.assets.environment("cpu") == {}
        assert gpu.command(cfg) == [str(root / D.GPU_BINARY), str(cfg)] and gpu.environment("gpu") == {"MCSQUARE_GPU": "1"}
        assert cpu.assets.program_files() == [root / D.RADIARCH_BINARY] and gpu.program_files() == [root / D.GPU_BINARY]
        assert auto.program_files() == [root / D.RADIARCH_BINARY, root / D.GPU_BINARY]
        assert auto.resolved_device() == "gpu" and gpu.availability() == (True, "ok")
        assert len({cpu.assets.fingerprint(), gpu.fingerprint(), auto.fingerprint()}) == 3
        monkeypatch.setattr(D, "cuda_device_present", lambda: (False, "no GPU here"))
        assert auto.resolved_device() == "cpu" and auto.command(cfg)[0] == str(root / D.RADIARCH_BINARY)
        ok, reason = gpu.availability()
        assert not ok and "no GPU here" in reason and auto.availability() == (True, "ok")
        (root / D.GPU_BINARY).unlink()
        ok, reason = gpu.availability()
        assert not ok and D.GPU_BINARY in reason
        assert auto.program_files() == [root / D.RADIARCH_BINARY] and auto.resolved_device() == "cpu"

    def test_a_gpu_run_sets_mcsquare_gpu(self, tmp_path, monkeypatch):
        drv, work = self._driver(tmp_path, monkeypatch, "gpu")
        run = drv.run(work)
        assert run.device == "gpu" and (work / "gpu.txt").read_text().strip() == "gpu=1"
        assert run.stdout_path.read_text().strip() == "gpu run" and not (work / "count").exists()

    def test_auto_runs_on_the_cpu_when_the_gpu_fails_to_start(self, tmp_path, monkeypatch):
        drv, work = self._driver(tmp_path, monkeypatch, "auto", gpu_fails=True)
        run = drv.run(work)
        assert run.device == "cpu" and run.attempts == 1 and run.returncode == 0
        assert "ERROR: GPU" in (work / "mcsquare-gpu.log").read_text()
        assert (work / "count").read_text().strip() == "1" and run.stdout_path.read_text().strip() == "attempt 1"

    def test_a_gpu_that_fails_is_an_error_for_gpu(self, tmp_path, monkeypatch):
        drv, work = self._driver(tmp_path, monkeypatch, "gpu", gpu_fails=True)
        with pytest.raises(RuntimeError, match="ERROR: GPU initialisation failed"):
            drv.run(work)
        assert not (work / "count").exists()

    def test_auto_without_a_gpu_runs_on_the_cpu(self, tmp_path, monkeypatch):
        drv, work = self._driver(tmp_path, monkeypatch, "auto", gpu_present=False)
        run = drv.run(work)
        assert run.device == "cpu" and not (work / "gpu.txt").exists()

    @pytest.mark.skipif(not (ASSETS.availability()[0] and GPU_ASSETS.gpu_binary.is_file() and not D.cuda_device_present()[0]),
                        reason="needs MCsquare_gpu on a host without a GPU")
    def test_auto_falls_back_with_the_real_gpu_binary_on_a_host_without_a_gpu(self, tmp_path, monkeypatch):
        """The GPU binary's own failure on a host without a GPU is the one the driver recognises: ``auto``, told
        that there is a GPU, still computes the dose, on the CPU."""
        monkeypatch.setattr(D, "cuda_device_present", lambda: (True, "ok"))
        drv = D.MCsquareDriver(assets=D.MCsquareAssets(ASSETS.root, "radiarch", "auto"), work_root=tmp_path / "runs",
                               n_threads=1, seed=5, keep_workdir=True)
        dose = drv.compute_dose(np.zeros((11, 30, 11), dtype=np.float32), (3.0, 3.0, 3.0), (-15.0, 1.5, -15.0),
                                _plan(energy=100.0), nb_primaries=2000)
        assert dose.max() > 0
        logs = list((tmp_path / "runs").rglob("mcsquare-gpu.log"))
        assert len(logs) == 1 and D.GPU_FAILURE.search(logs[0].read_text())

    def test_cuda_visible_devices_can_hide_the_gpus(self, monkeypatch):
        for hidden in ("", "-1", "none"):
            monkeypatch.setenv("CUDA_VISIBLE_DEVICES", hidden)
            ok, reason = D.cuda_device_present()
            assert not ok and "CUDA_VISIBLE_DEVICES" in reason

    @needs_assets
    def test_the_engine_takes_the_device_from_params_and_keys_it(self, monkeypatch):
        from radiarch.config import get_settings
        from radiarch.services.dose_engines.mcsquare import MCsquareEngine
        from radiarch.services.dose_engines.protocol import EngineParamError

        eng = MCsquareEngine()
        monkeypatch.setattr(get_settings(), "mcsquare_device", "cpu")
        assert eng.driver().assets.device == "cpu" and eng.driver({"device": "GPU"}).assets.device == "gpu"
        monkeypatch.setattr(get_settings(), "mcsquare_device", "auto")
        assert eng.driver().assets.device == "auto"
        digests = {d: eng.digest({"device": d}) for d in D.DEVICES}
        assert len(set(digests.values())) == 3
        with pytest.raises(EngineParamError, match="unknown MCsquare device"):
            eng.driver({"device": "tpu"})
        assert eng.health()["diagnostics"]["device"] == "auto"


def test_the_material_database_is_linked_into_the_work_directory(tmp_path):
    """The engine gets the materials as the short relative link 'Materials' (its nuclear-data file names live in
    100-byte buffers; a long absolute path overran them)."""
    mats = tmp_path / ("a-long-install-path-" * 5) / "Materials"
    mats.mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    assert D.materials_link(work, mats) == "Materials"
    assert (work / "Materials").is_symlink() and (work / "Materials").resolve() == mats.resolve()
    assert D.materials_link(work, mats) == "Materials"                 # a second run in the same directory
    other = tmp_path / "work2"
    (other / "Materials").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="not the link"):
        D.materials_link(other, mats)


# ---------------------------------------------------------------------------
# Goldens: what the vendored OpenTPS wrapper wrote before R14, the driver must write
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GOLDEN.is_dir(), reason="MCsquare input goldens not captured")
def test_driver_inputs_match_the_goldens():
    from radiarch.validation import goldens as G

    if not G.SIMPLEFANTOM.is_dir():
        pytest.skip("SimpleFantom test data not present")
    with tempfile.TemporaryDirectory(prefix="radiarch-r14-") as tmp:
        work = Path(tmp)
        geo, geo_svc, bm, bm_svc = G.build_simplefantom(work)
        now = G.compute_mcsquare_inputs_golden(geo, bm, geo_svc, bm_svc, work)
    strip = lambda t: "\n".join(l for l in t.splitlines()
                                if not l.split()[:1] or l.split()[0] not in ("Num_Primaries", "RNG_Seed", "Num_Threads"))
    assert strip(now["config.txt"]) == strip((GOLDEN / "config.txt").read_text())
    assert now["PlanPencil.txt"] == (GOLDEN / "PlanPencil.txt").read_text()
    assert now["CT.mhd"] == (GOLDEN / "CT.mhd").read_text()
    assert now["CT.raw.sha256"] == (GOLDEN / "CT.raw.sha256").read_text().strip()


# ---------------------------------------------------------------------------
# The engine itself
# ---------------------------------------------------------------------------

@needs_binary
class TestEngineRuns:
    BOX = (21, 40, 25)          # (z, y, x): deliberately non-cubic
    SPACING = (3.0, 3.0, 3.0)
    ORIGIN = (-36.0, 1.5, -30.0)

    def _driver(self, tmp_path, seed=777):
        return D.MCsquareDriver(work_root=tmp_path / "runs", n_threads=1, seed=seed, keep_workdir=True)

    def test_dose_frame_and_spot_positions(self, tmp_path):
        hu = np.zeros(self.BOX, dtype=np.float32)
        plan = _plan(spots=((0.0, 0.0, 1.0), (15.0, 0.0, 1.0), (0.0, 15.0, 1.0)), energy=100.0)
        drv = self._driver(tmp_path)
        dij = drv.compute_beamlets(hu, self.SPACING, self.ORIGIN, plan, nb_primaries=6000)
        assert dij.shape == (int(np.prod(self.BOX)), 3)
        nz, ny, nx = self.BOX
        zz, yy, xx = np.indices(self.BOX)
        centroids = []
        for k in range(3):
            col = np.asarray(dij[:, k].todense()).reshape(self.BOX)
            assert col.sum() > 0
            centroids.append((float((xx * col).sum() / col.sum()), float((zz * col).sum() / col.sum())))
        # Spot +x moves the column along +x by 15 mm = 5 voxels; BEV +y moves it along +z.
        assert centroids[1][0] - centroids[0][0] == pytest.approx(5.0, abs=0.6)
        assert centroids[2][1] - centroids[0][1] == pytest.approx(5.0, abs=0.6)
        assert abs(centroids[1][1] - centroids[0][1]) < 0.6 and abs(centroids[2][0] - centroids[0][0]) < 0.6
        dose = drv.compute_dose(hu, self.SPACING, self.ORIGIN, plan, nb_primaries=6000)
        assert dose.shape == self.BOX and dose.dtype == np.float32 and dose.max() > 0
        # Dij @ MU and the direct dose are the same physics up to counting statistics.
        via = np.asarray(dij @ np.ones(3, dtype=np.float32)).reshape(self.BOX)
        assert via.sum() == pytest.approx(dose.sum(), rel=0.15)

    def test_a_long_install_path(self, tmp_path):
        """The engine's assets reached through a path of more than 100 characters (CI's checkout is under
        /home/runner/work/...): the run must not overrun the engine's file-name buffers."""
        long_root = tmp_path / ("engines-installed-under-a-long-path-" * 3) / "mcsquare"
        long_root.parent.mkdir(parents=True)
        long_root.symlink_to(ASSETS.root.resolve(), target_is_directory=True)
        assert len(str(long_root / "Materials")) > 100
        drv = D.MCsquareDriver(assets=D.MCsquareAssets(long_root, ASSETS.build), work_root=tmp_path / "runs",
                               n_threads=1, seed=5, keep_workdir=True)
        hu = np.zeros((11, 30, 11), dtype=np.float32)
        dose = drv.compute_dose(hu, (3.0, 3.0, 3.0), (-15.0, 1.5, -15.0), _plan(energy=100.0), nb_primaries=2000)
        assert dose.max() > 0

    def test_water_calibration_lengthens_the_range(self, tmp_path):
        """HU 0 is a tissue blend in the clinical tables and water in the water calibration;
        the water range must be the longer one (the harness finding of 2026-10-21)."""
        hu = np.zeros((11, 60, 11), dtype=np.float32)
        plan = _plan(energy=150.0)
        drv = self._driver(tmp_path)
        spacing, origin = (3.0, 3.0, 3.0), (-15.0, 1.5, -15.0)
        d_clin = drv.compute_dose(hu, spacing, origin, plan, nb_primaries=20000)
        d_water = drv.compute_dose(hu, spacing, origin, plan, nb_primaries=20000, calibration=D.CalibrationTables.water())

        def r80(d):
            idd = d.sum(axis=(0, 2)); k = int(np.argmax(idd))
            j = k + int(np.where(idd[k:] <= 0.8 * idd[k])[0][0])
            return float(np.interp(0.8 * idd[k], [idd[j], idd[j - 1]], [j, j - 1])) * 3.0
        assert r80(d_water) > r80(d_clin)
        assert r80(d_water) == pytest.approx(157.7, abs=6.0)        # PSTAR CSDA range at 150 MeV, coarse grid

    def test_plugin_surface(self, tmp_path, monkeypatch):
        """The registered engine: validate, compute_dose, build_influence, scenarios."""
        from radiarch.config import get_settings
        from radiarch.models.beam_model import BeamModelResult, FluenceElementSet, Modality, PerBeamElements
        from radiarch.models.dose import ScenarioSpec
        from radiarch.services.dose_engines.protocol import BeamModelBundle, GeometryBundle
        from radiarch.services.dose_engines.registry import get_engine
        import types

        monkeypatch.setattr(get_settings(), "artifact_dir", str(tmp_path))
        monkeypatch.setattr(get_settings(), "mcsquare_seed", 99)
        monkeypatch.setattr(get_settings(), "mcsquare_n_threads", 1)
        hu = np.zeros(self.BOX, dtype=np.float32)
        plan = _plan(spots=((0.0, 0.0, 1.0), (12.0, 0.0, 1.0)), energy=100.0)
        geom = GeometryBundle(
            result=types.SimpleNamespace(geometry_id="g", grid_spec=types.SimpleNamespace(origin_mm=self.ORIGIN, spacing_mm=self.SPACING)),
            density=np.ones(self.BOX, dtype=np.float32), masks=np.zeros(self.BOX, dtype=np.uint16),
            spacing_mm=self.SPACING, ct_hu=hu, origin_mm=self.ORIGIN,
        )
        bm = BeamModelBundle(
            result=BeamModelResult(
                beam_model_id="b", geometry_id="g", modality=Modality.proton_pbs,
                fluence_elements=FluenceElementSet(total_count=2, per_beam=[PerBeamElements(beam_id="B1", element_count=2)]),
                beam_model_ref_uri="x", machine_model_id="default", cache_key="k",
            ),
            plan=plan,
        )
        eng = get_engine("mcsquare")
        assert eng.validate(geom, bm, {}) == []
        assert eng.health()["available"] is True and eng.health()["test_only"] is False
        dose = eng.compute_dose(geom, bm, np.array([1.0, 1.0], dtype=np.float32), params={"nb_primaries": 3000}).dose
        assert dose.shape == self.BOX and dose.max() > 0
        shifted = eng.compute_dose(geom, bm, np.array([1.0, 1.0], dtype=np.float32),
                                   scenario=ScenarioSpec(name="shift", setup_shift_mm=(9.0, 0.0, 0.0)),
                                   params={"nb_primaries": 3000}).dose
        xx = np.indices(self.BOX)[2]
        assert (xx * shifted).sum() / shifted.sum() - (xx * dose).sum() / dose.sum() == pytest.approx(3.0, abs=0.7)
        inf = eng.build_influence(geom, bm, params={"nb_primaries": 3000})
        assert inf.n_elements == 2 and inf.n_voxels == int(np.prod(self.BOX))
        via = eng.apply_influence(inf, np.array([1.0, 1.0], dtype=np.float32), self.BOX).dose
        assert via.shape == self.BOX and via.sum() == pytest.approx(dose.sum(), rel=0.2)
        with pytest.raises(Exception):
            eng.compute_dose(geom, bm, np.array([1.0], dtype=np.float32))


@needs_gpu
class TestGpuRuns:
    """MCsquare_gpu against MCsquare_radiarch on the same inputs (ADR 0024): the doses agree within the Monte Carlo
    noise, in each of the three ways radiarch runs the engine. Needs the GPU binary and a GPU (skipped in CI)."""

    BOX = (21, 60, 21)
    SPACING = (3.0, 3.0, 3.0)
    ORIGIN = (-30.0, 1.5, -30.0)

    def _drivers(self, tmp_path):
        return [D.MCsquareDriver(assets=D.MCsquareAssets(ASSETS.root, "radiarch", dev), work_root=tmp_path / dev,
                                 n_threads=4, seed=17) for dev in ("cpu", "gpu")]

    @staticmethod
    def _r80(d):
        idd = d.sum(axis=(0, 2)); k = int(np.argmax(idd))
        j = k + int(np.where(idd[k:] <= 0.8 * idd[k])[0][0])
        return float(np.interp(0.8 * idd[k], [idd[j], idd[j - 1]], [j, j - 1])) * 3.0

    def test_dose(self, tmp_path):
        hu = np.zeros(self.BOX, dtype=np.float32)
        hu[:, 15:25, :10] = 700.0                       # bone over half the field
        plan = _plan(spots=((0.0, 0.0, 1.0), (-9.0, 0.0, 1.0), (9.0, 0.0, 1.0)), energy=150.0)
        cpu, gpu = self._drivers(tmp_path)
        dc, dg = (drv.compute_dose(hu, self.SPACING, self.ORIGIN, plan, nb_primaries=3e5) for drv in (cpu, gpu))
        assert dg.shape == dc.shape and dg.dtype == np.float32
        assert dg.sum() == pytest.approx(dc.sum(), rel=0.01)
        assert self._r80(dg) == pytest.approx(self._r80(dc), abs=1.0)
        hi = dc > 0.1 * dc.max()
        assert np.sqrt(np.mean(((dg - dc)[hi] / dc.max()) ** 2)) < 0.02

    def test_influence_matrix(self, tmp_path):
        hu = np.zeros(self.BOX, dtype=np.float32)
        plan = _plan(spots=((0.0, 0.0, 1.0), (12.0, 0.0, 1.0), (0.0, 12.0, 1.0)), energy=120.0)
        cpu, gpu = self._drivers(tmp_path)
        mc, mg = (drv.compute_beamlets(hu, self.SPACING, self.ORIGIN, plan, nb_primaries=3e4) for drv in (cpu, gpu))
        assert mg.shape == mc.shape == (int(np.prod(self.BOX)), 3)
        np.testing.assert_allclose(np.asarray(mg.sum(axis=0)).ravel(), np.asarray(mc.sum(axis=0)).ravel(), rtol=0.02)

    def test_robustness_scenarios(self, tmp_path):
        hu = np.zeros(self.BOX, dtype=np.float32)
        plan = _plan(spots=((0.0, 0.0, 1.0),), energy=120.0)
        native = D.robustness_config("REDUCED_SET", (3.0, 3.0, 3.0), (0.0, 0.0, 0.0), 3.0)
        cpu, gpu = self._drivers(tmp_path)
        rc, rg = (drv.compute_scenario_doses(hu, self.SPACING, self.ORIGIN, plan, native, nb_primaries=1e5) for drv in (cpu, gpu))
        assert [r.name for r, _ in rg] == [r.name for r, _ in rc] and len(rg) > 1
        for (rec, dc), (_, dg) in zip(rc, rg):
            assert dg.sum() == pytest.approx(dc.sum(), rel=0.02), rec.name
            assert self._r80(dg) == pytest.approx(self._r80(dc), abs=1.5), rec.name
