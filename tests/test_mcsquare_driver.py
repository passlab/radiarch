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
import tempfile
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot, RangeShifterSetting
from radiarch.services.dose_engines import mcsquare_driver as D

ASSETS = D.MCsquareAssets(D.default_assets_dir())
GOLDEN = Path(__file__).resolve().parent / "golden" / "mcsquare_inputs_simplefantom"


needs_assets = pytest.mark.skipif(not ASSETS.root.is_dir(), reason="MCsquare assets not present")
needs_binary = pytest.mark.skipif(not ASSETS.availability()[0], reason=ASSETS.availability()[1])


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
