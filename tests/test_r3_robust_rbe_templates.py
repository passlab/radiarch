"""R3: engine-native scenario sets, RBE-weighted dose, DVH bands and the craniospinal template."""

from __future__ import annotations

import types
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pytest

from radiarch.models.beam_model import BeamSetSpec, BeamSpec, DeliveryParams, Modality
from radiarch.models.dose import (
    DoseComputeRequest, EngineScenarioSet, EngineSpec, InfluenceBuildRequest, ScenarioSetSpec, ScenarioSpec,
    WeightVector, default_rbe, dose_units_for,
)
from radiarch.services.geometry_bundle import GeometryArrays


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestModels:
    def test_default_rbe_by_modality(self):
        assert default_rbe(Modality.proton_pbs) == 1.1 and default_rbe(Modality.photon_imrt) == 1.0
        assert dose_units_for(1.1) == "Gy(RBE)" and dose_units_for(1.0) == "Gy"

    def test_native_set_counts_and_hash(self):
        assert EngineScenarioSet().n_scenarios == 21
        assert EngineScenarioSet(selection="all").n_scenarios == 81 and EngineScenarioSet(selection="all").selection == "ALL"
        assert EngineScenarioSet(selection="RANDOM", count=7).n_scenarios == 7
        with pytest.raises(ValueError):
            EngineScenarioSet(selection="SOME")
        a, b = EngineScenarioSet(), EngineScenarioSet(range_error_pct=3.5)
        assert a.hash() != b.hash() and a.hash() == EngineScenarioSet().hash()

    def test_scenario_set_native_mode(self):
        spec = ScenarioSetSpec(engine_native=EngineScenarioSet())
        assert spec.scenarios is None and spec.hash() != ScenarioSetSpec(engine_native=EngineScenarioSet(selection="ALL")).hash()
        with pytest.raises(ValueError):
            ScenarioSetSpec()

    def test_random_setup_sigma_is_part_of_the_scenario(self):
        a = ScenarioSpec(name="s", setup_shift_mm=(1, 0, 0))
        b = ScenarioSpec(name="s", setup_shift_mm=(1, 0, 0), setup_random_sigma_mm=(1, 1, 1))
        assert a.hash() != b.hash() and not b.is_nominal()
        assert ScenarioSpec(setup_random_sigma_mm=(1, 1, 1)).is_nominal() is False

    def test_rbe_in_the_cache_keys(self):
        base = dict(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="analytic"),
                    weights=WeightVector(length=2, values=[1.0, 1.0]))
        assert DoseComputeRequest(**base).compute_cache_key() != DoseComputeRequest(rbe=1.0, **base).compute_cache_key()
        inf = dict(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="analytic"))
        assert InfluenceBuildRequest(**inf).compute_cache_key() != InfluenceBuildRequest(rbe=1.2, **inf).compute_cache_key()

    def test_beam_spec_fields(self):
        b = BeamSpec(beam_id="S1", gantry_deg=180.0, isocenter_mm=(0, 0, -100), target_z_range_mm=(-200.0, -20.0))
        assert b.target_z_range_mm == (-200.0, -20.0)
        with pytest.raises(ValueError):
            BeamSpec(beam_id="S1", gantry_deg=180.0, target_z_range_mm=(10.0, 10.0))
        assert BeamSetSpec(beams=[b]).isocenter_mm is None


# ---------------------------------------------------------------------------
# RBE through the dose service (analytic engine, dev mode)
# ---------------------------------------------------------------------------

@pytest.fixture
def dev_env(monkeypatch, tmp_path):
    for k, v in {"RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
                 "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://",
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path), "RADIARCH_ALLOW_TEST_ENGINES": "1"}.items():
        monkeypatch.setenv(k, v)
    from radiarch.config import get_settings
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _bundles(modality: Modality, n_elements: int = 4):
    from radiarch.models.beam_model import BeamModelResult, FluenceElementSet, PerBeamElements
    from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot
    from radiarch.services.dose_engines.protocol import BeamModelBundle, GeometryBundle

    n = 12
    density = np.ones((n, n, n), dtype=np.float32)
    masks = np.zeros((n, n, n), dtype=np.uint16); masks[4:8, 4:8, 4:8] = 1
    geom = GeometryBundle(
        result=types.SimpleNamespace(geometry_id="g", structure_index={"PTV": 1},
                                     grid_spec=types.SimpleNamespace(origin_mm=(0, 0, 0), spacing_mm=(2, 2, 2))),
        density=density, masks=masks, spacing_mm=(2.0, 2.0, 2.0), ct_hu=np.zeros((n, n, n), np.int16), origin_mm=(0.0, 0.0, 0.0),
    )
    plan = ProtonPlan(beams=[ProtonBeam(isocenter_mm=(0, 0, 0), layers=[ProtonLayer(
        energy_mev=100.0, spots=[ProtonSpot(x_mm=float(i), y_mm=0.0, mu=1.0) for i in range(n_elements)])])])
    bm = BeamModelBundle(
        result=BeamModelResult(beam_model_id="b", geometry_id="g", modality=modality,
                               fluence_elements=FluenceElementSet(total_count=n_elements, per_beam=[PerBeamElements(beam_id="B1", element_count=n_elements)]),
                               beam_model_ref_uri="x", machine_model_id="default", cache_key="k"),
        plan=plan,
    )
    return geom, bm


class TestRBE:
    def test_proton_dose_is_rbe_weighted_by_default(self, dev_env, monkeypatch):
        from radiarch.services.dose import DoseService

        svc = DoseService(dose_dir=dev_env / "dose", influence_dir=dev_env / "inf")
        geom, bm = _bundles(Modality.proton_pbs)
        monkeypatch.setattr(svc, "_load_geometry", lambda gid: geom)
        monkeypatch.setattr(svc, "_load_beam_model", lambda bid: bm)
        # the analytic engine is photon-only in its modality list; register a proton-capable stand-in
        from radiarch.services.dose_engines import registry
        from radiarch.services.dose_engines.analytic import AnalyticEngine
        eng = AnalyticEngine()
        monkeypatch.setattr(eng, "modalities", ["PROTON_PBS", "PHOTON_IMRT"], raising=False)
        monkeypatch.setattr(registry, "get_engine", lambda name: eng)
        monkeypatch.setattr("radiarch.services.dose.get_engine", lambda name: eng)

        base = dict(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="analytic"),
                    weights=WeightVector(length=4, values=[1.0] * 4))
        physical = svc.compute_dose(DoseComputeRequest(rbe=1.0, **base))
        weighted = svc.compute_dose(DoseComputeRequest(**base))
        assert physical.dose_units == "Gy" and physical.rbe_factor == 1.0
        assert weighted.dose_units == "Gy(RBE)" and weighted.rbe_factor == 1.1
        assert weighted.statistics.max_gy == pytest.approx(1.1 * physical.statistics.max_gy, rel=1e-5)
        from radiarch.services.dose_persistence import read_dose_volume
        a = read_dose_volume(Path(physical.dose_grid_uri)); b = read_dose_volume(Path(weighted.dose_grid_uri))
        np.testing.assert_allclose(b, 1.1 * a, rtol=1e-5)

        inf_phys = svc.build_influence(InfluenceBuildRequest(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="analytic"), rbe=1.0))
        inf_rbe = svc.build_influence(InfluenceBuildRequest(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="analytic")))
        assert inf_rbe.dose_units == "Gy(RBE)" and inf_rbe.rbe_factor == 1.1
        d0 = svc.influence_store.load_influence(inf_phys.influence_id); d1 = svc.influence_store.load_influence(inf_rbe.influence_id)
        np.testing.assert_allclose(d1.data, 1.1 * d0.data, rtol=1e-5)

    def test_photon_dose_stays_physical(self, dev_env, monkeypatch):
        from radiarch.services.dose import DoseService

        svc = DoseService(dose_dir=dev_env / "dose", influence_dir=dev_env / "inf")
        geom, bm = _bundles(Modality.photon_imrt)
        monkeypatch.setattr(svc, "_load_geometry", lambda gid: geom)
        monkeypatch.setattr(svc, "_load_beam_model", lambda bid: bm)
        res = svc.compute_dose(DoseComputeRequest(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="analytic"),
                                                  weights=WeightVector(length=4, values=[1.0] * 4)))
        assert res.dose_units == "Gy" and res.rbe_factor == 1.0


# ---------------------------------------------------------------------------
# Native scenario sets through the dose service (a fake engine) and the evaluation bands
# ---------------------------------------------------------------------------

class _NativeEngine:
    """A stand-in engine with a native robustness mode: shifts the dose along z per scenario."""

    name = "fake-native"
    version = "1"
    modalities = ["PROTON_PBS"]
    test_only = False

    def validate(self, geometry, beam_model, params):
        return []

    def _dose(self, geometry, weights, shift_z: float = 0.0):
        n = geometry.density.shape[0]
        z = np.arange(n, dtype=np.float32)[:, None, None]
        centre = 5.5 + shift_z / 2.0
        return (float(np.sum(weights)) * np.exp(-((z - centre) ** 2) / 4.0) * np.ones(geometry.density.shape, np.float32)).astype(np.float32)

    def compute_dose(self, geometry, beam_model, weights, scenario=None, params=None):
        from radiarch.services.dose_engines.protocol import NominalDose
        dz = scenario.setup_shift_mm[2] if scenario is not None and scenario.setup_shift_mm else 0.0
        return NominalDose(dose=self._dose(geometry, weights, dz))

    def compute_scenario_doses(self, geometry, beam_model, weights, scenario_set, params=None):
        out = [(ScenarioSpec(name="nominal"), self._dose(geometry, weights))]
        for i, dz in enumerate((-2.0, 2.0, 0.0)[: scenario_set.n_scenarios]):
            sc = ScenarioSpec(name=f"scenario_{i + 1}", setup_shift_mm=(0.0, 0.0, dz) if dz else None,
                              setup_random_sigma_mm=tuple(scenario_set.setup_random_mm), range_scale=1.0 + scenario_set.range_error_pct / 100)
            out.append((sc, self._dose(geometry, weights, dz)))
        return out

    def build_influence(self, geometry, beam_model, scenario=None, params=None):
        raise NotImplementedError

    def apply_influence(self, influence, weights, grid_shape):
        raise NotImplementedError

    def compute_grad(self, *a, **k):
        raise NotImplementedError


class TestNativeScenarioSets:
    def test_dose_service_runs_the_engine_once_and_labels_the_scenarios(self, dev_env, monkeypatch):
        from radiarch.services.dose import DoseService

        svc = DoseService(dose_dir=dev_env / "dose", influence_dir=dev_env / "inf")
        geom, bm = _bundles(Modality.proton_pbs)
        monkeypatch.setattr(svc, "_load_geometry", lambda gid: geom)
        monkeypatch.setattr(svc, "_load_beam_model", lambda bid: bm)
        eng = _NativeEngine()
        monkeypatch.setattr("radiarch.services.dose.get_engine", lambda name: eng)
        monkeypatch.setattr("radiarch.services.dose.ensure_engine_allowed", lambda e: None)
        req = DoseComputeRequest(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="fake-native"),
                                 weights=WeightVector(length=4, values=[1.0] * 4),
                                 scenarios=ScenarioSetSpec(engine_native=EngineScenarioSet(selection="RANDOM", count=3, range_error_pct=2.0)))
        res = svc.compute_dose(req)
        assert res.dose_units == "Gy(RBE)" and len(res.scenario_doses) == 3
        names = [e.scenario_name for e in res.scenario_doses]
        assert names == ["scenario_1", "scenario_2", "scenario_3"]
        assert res.scenario_doses[0].scenario.setup_shift_mm == (0.0, 0.0, -2.0)
        assert res.scenario_doses[0].scenario.setup_random_sigma_mm == (1.0, 1.0, 1.0)
        assert res.scenario_doses[0].scenario.range_scale == pytest.approx(1.02)
        assert all(Path(e.dose_grid_uri).is_file() for e in res.scenario_doses)
        # cache hit on the same request
        assert svc.compute_dose(req).dose_id == res.dose_id

        # the evaluation reports bands and worst-case goals over those scenarios
        from radiarch.models.evaluation import EvaluationRequest
        from radiarch.services.evaluation import EvaluationService
        ev = EvaluationService(base_dir=dev_env / "eval", dose_service=svc)
        out = ev.run(EvaluationRequest(dose_id=res.dose_id, geometry_id="g", prescription_gy=2.0, target_structure="PTV", dvh_bins=50))
        assert out.n_scenarios == 3 and out.dose_units == "Gy(RBE)"
        band = out.dvh_bands[0]
        assert band.structure_name == "PTV" and band.n_scenarios == 3 and len(band.dose_bins_gy) == 50
        assert all(lo <= nom <= hi for lo, nom, hi in zip(band.min_pct, band.nominal_pct, band.max_pct))
        assert band.nominal_pct[0] == 100.0 and band.min_pct[-1] <= band.max_pct[-1]
        rm = out.robust_metrics[0]
        assert rm.lowest.d95_gy <= rm.nominal.d95_gy <= rm.highest.d95_gy
        assert set(rm.per_scenario) == set(names)
        ri = out.robust_indices
        assert ri is not None and ri.n_scenarios == 3 and ri.worst_coverage_pct <= out.indices.coverage_pct
        assert ri.worst_hotspot_gy >= out.indices.hotspot_gy and ri.worst_scenario in names
        # without scenarios nothing robust is reported
        plain = ev.run(EvaluationRequest(dose_id=res.dose_id, geometry_id="g", prescription_gy=2.0, include_scenarios=False))
        assert plain.n_scenarios == 0 and not plain.dvh_bands and plain.robust_indices is None

    def test_engines_without_native_mode_are_refused(self, dev_env, monkeypatch):
        from radiarch.services.dose import DoseService

        svc = DoseService(dose_dir=dev_env / "dose", influence_dir=dev_env / "inf")
        geom, bm = _bundles(Modality.photon_imrt)
        monkeypatch.setattr(svc, "_load_geometry", lambda gid: geom)
        monkeypatch.setattr(svc, "_load_beam_model", lambda bid: bm)
        with pytest.raises(ValueError, match="native scenario mode"):
            svc.compute_dose(DoseComputeRequest(geometry_id="g", beam_model_id="b", engine=EngineSpec(name="analytic"),
                                                weights=WeightVector(length=4, values=[1.0] * 4),
                                                scenarios=ScenarioSetSpec(engine_native=EngineScenarioSet())))


# ---------------------------------------------------------------------------
# MCsquare's robustness mode through the driver (needs the binary)
# ---------------------------------------------------------------------------

def _mcsquare_ok() -> bool:
    try:
        from radiarch.services.dose_engines.mcsquare_driver import MCsquareAssets, default_assets_dir
        return MCsquareAssets(default_assets_dir()).availability()[0]
    except Exception:
        return False


def test_scenarios_file_parser(tmp_path):
    from radiarch.services.dose_engines.mcsquare_driver import read_scenarios_file, robustness_config

    (tmp_path / "Robustness_scenarios.txt").write_text(
        "Robustness Parameters:\n----------------------\nSystematic Setup Error = 0.200 0.200 0.200 cm\n\n"
        "Uncertainty scenarios:\n----------------------\n"
        "Nominal: Systematic_Setup(0.00 0.00 0.00 mm) Random_Setup(0.00 0.00 0.00 mm) Systematic_Range(+0.00 %) \n"
        "Scenario (1/2): Systematic_Setup(-2.000 0.000 0.000 mm) Random_Setup(1.000 1.000 1.000 mm) Systematic_Range(-3.00 %)\n"
        "Scenario (2/2): Systematic_Setup(0.167183 -0.143822 -0.125031 mm) Random_Setup(0.066737 -0.093606 0.041359 mm) Systematic_Range(1.059116 %)\n"
    )
    recs = read_scenarios_file(tmp_path)
    assert [r.index for r in recs] == [0, 1, 2] and recs[0].is_nominal and recs[1].count == 2
    assert recs[1].setup_shift_mm == (-2.0, 0.0, 0.0) and recs[1].range_error_pct == -3.0 and recs[1].range_scale == pytest.approx(0.97)
    assert recs[2].setup_shift_mm == pytest.approx((0.167183, -0.143822, -0.125031))
    assert recs[1].dose_file() == "Dose_Scenario_1-2.mhd" and recs[0].sparse_file() == "Sparse_Dose_Nominal.txt"
    cfg = robustness_config("reduced_set", (2.5, 2.5, 2.5), (1, 1, 1), 3.0)
    assert cfg["Scenario_selection"] == "ReducedSet" and cfg["Systematic_Setup_Error"] == [0.25, 0.25, 0.25] and cfg["Robustness_Mode"] is True


@pytest.mark.skipif(not _mcsquare_ok(), reason="MCsquare not available")
def test_mcsquare_native_scenarios_doses_and_beamlets(tmp_path, dev_env):
    from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot
    from radiarch.services.dose_engines import mcsquare_driver as D

    drv = D.MCsquareDriver(work_root=tmp_path / "runs", n_threads=0, seed=5)
    hu = np.zeros((21, 40, 25), dtype=np.float32)
    plan = ProtonPlan(beams=[ProtonBeam(beam_id="B", gantry_deg=0.0, isocenter_mm=(0.0, 0.0, 0.0), layers=[
        ProtonLayer(energy_mev=100.0, spots=[ProtonSpot(x_mm=0, y_mm=0, mu=1.0), ProtonSpot(x_mm=12, y_mm=0, mu=1.0)])])])
    cfg = D.robustness_config("RANDOM", (2.0, 2.0, 2.0), (1.0, 1.0, 1.0), 3.0, count=2)
    doses = drv.compute_scenario_doses(hu, (3.0, 3.0, 3.0), (-36.0, 1.5, -30.0), plan, cfg, nb_primaries=3000)
    assert [r.index for r, _ in doses] == [0, 1, 2] and all(d.shape == hu.shape and d.max() > 0 for _, d in doses)
    assert doses[1][0].setup_random_mm != (0.0, 0.0, 0.0)
    beamlets = drv.compute_scenario_beamlets(hu, (3.0, 3.0, 3.0), (-36.0, 1.5, -30.0), plan, cfg, nb_primaries=3000)
    assert [r.index for r, _ in beamlets] == [0, 1, 2]
    for _, dij in beamlets:
        assert dij.shape == (hu.size, 2) and dij.nnz > 0

    # the engine plugin labels the scenarios
    from radiarch.services.dose_engines.mcsquare import MCsquareEngine
    geom, bm = _bundles(Modality.proton_pbs, n_elements=2)
    geom.ct_hu = hu; geom.density = np.ones_like(hu); geom.masks = np.zeros(hu.shape, np.uint16)
    geom.spacing_mm = (3.0, 3.0, 3.0); geom.origin_mm = (-36.0, 1.5, -30.0)
    bm.plan = plan
    eng = MCsquareEngine()
    out = eng.compute_scenario_doses(geom, bm, np.ones(2, np.float32), EngineScenarioSet(selection="RANDOM", count=2),
                                     params={"nb_primaries": 3000, "seed": 5, "nb_threads": 0})
    assert out[0][0].is_nominal() and len(out) == 3 and out[1][0].setup_random_sigma_mm is not None


# ---------------------------------------------------------------------------
# Field-specific targets and the craniospinal template
# ---------------------------------------------------------------------------

def _long_target(nz: int = 120, ny: int = 24, nx: int = 24, spacing: float = 4.0) -> GeometryArrays:
    """A 480 mm long cylinder of 20 mm radius along z (a spinal canal) with a 60 mm ball on top (the brain)."""
    ct = np.zeros((nz, ny, nx), dtype=np.int16)
    zz, yy, xx = np.mgrid[:nz, :ny, :nx]
    cx, cy = (nx - 1) / 2.0, (ny - 1) / 2.0
    canal = ((xx - cx) ** 2 + (yy - cy) ** 2) * spacing ** 2 <= 20.0 ** 2
    canal &= zz < 100
    ball = ((xx - cx) ** 2 + (yy - cy) ** 2 + (zz - 108) ** 2) * spacing ** 2 <= 30.0 ** 2
    masks = np.where(canal | ball, 1, 0).astype(np.uint16)
    origin = (-cx * spacing, -cy * spacing, -200.0)
    return GeometryArrays("g-csi", ct, masks, {"PTV_CSI": 1}, origin, (spacing,) * 3)


class TestCraniospinal:
    def test_split_extent(self):
        from radiarch.services.plan_templates import split_extent

        assert split_extent(0.0, 250.0, 300.0, 40.0) == [(0.0, 250.0)]
        slabs = split_extent(-200.0, 260.0, 300.0, 40.0)
        assert len(slabs) == 2 and slabs[0][1] == 260.0 and slabs[-1][0] == -200.0
        assert slabs[0][0] < slabs[1][1] and slabs[1][1] - slabs[0][0] == pytest.approx(40.0)
        three = split_extent(0.0, 700.0, 300.0, 40.0)
        assert len(three) == 3 and all(b - a <= 300.0 + 1e-9 for a, b in three)

    def test_template_fields_and_junctions(self):
        from radiarch.services.plan_templates import craniospinal_template

        g = _long_target()
        t = craniospinal_template(g, field_length_mm=300.0, overlap_mm=40.0)
        assert t.target_name == "PTV_CSI" and len(t.fields) == 2 and len(t.junctions_mm) == 1
        assert t.target_z_extent_mm[0] == -200.0
        top, bottom = t.fields
        assert top.z_range_mm[1] > bottom.z_range_mm[1] and top.z_range_mm[0] < top.z_range_mm[1]
        lo, hi = t.junctions_mm[0]
        assert hi - lo == pytest.approx(40.0, abs=1e-6)
        assert all(b.target_z_range_mm is not None and b.isocenter_mm is not None for b in t.beam_set.beams)
        assert top.isocenter_mm[2] > bottom.isocenter_mm[2]
        assert sum(f.n_target_voxels for f in t.fields) > int(g.masks.sum())      # the junction is counted twice

    def test_brain_field_pair(self):
        from radiarch.services.plan_templates import craniospinal_template

        g = _long_target()
        t = craniospinal_template(g, field_length_mm=300.0, overlap_mm=40.0, brain_oblique_deg=20.0)
        ids = [b.beam_id for b in t.beam_set.beams]
        assert ids == ["CSI1L", "CSI1R", "CSI2"]
        pair = t.beam_set.beams[:2]
        assert {b.gantry_deg for b in pair} == {200.0, 160.0}
        assert pair[0].isocenter_mm == pair[1].isocenter_mm and pair[0].target_z_range_mm == pair[1].target_z_range_mm
        assert t.beam_set.beams[2].gantry_deg == 180.0
        with pytest.raises(ValueError):
            craniospinal_template(g, brain_oblique_deg=95.0)
        clinical = craniospinal_template(g, preset="clinical")
        assert {b.gantry_deg for b in clinical.beam_set.beams[:2]} == {195.0, 165.0} and len(clinical.beam_set.beams) == 3
        assert len(craniospinal_template(g).beam_set.beams) == 2          # research default: one posterior brain field
        with pytest.raises(ValueError, match="preset"):
            craniospinal_template(g, preset="vendor")

    def test_spots_follow_the_field_slabs(self):
        from radiarch.services.machine_model import ProtonMachineModel
        from radiarch.services.plan_templates import craniospinal_template
        from radiarch.services.proton_spots import generate_proton_spots, target_slab

        g = _long_target()
        t = craniospinal_template(g, field_length_mm=300.0, overlap_mm=40.0)
        result = generate_proton_spots(g, ProtonMachineModel.from_default(), t.beam_set, DeliveryParams(spot_spacing_mm=8.0, layer_spacing_mm=8.0))
        plan = result.plan
        assert len(plan.beams) == 2 and all(b.n_spots > 0 for b in plan.beams)
        for beam, field in zip(plan.beams, t.fields):
            assert beam.isocenter_mm == pytest.approx(field.isocenter_mm)
            # BEV y is patient z for a posterior field at gantry 180: the spots stay inside the slab (+ margin + spacing)
            ys = np.array([s.y_mm for layer in beam.layers for s in layer.spots])
            lo, hi = field.z_range_mm
            assert ys.min() + beam.isocenter_mm[2] >= lo - 5.0 - 8.0 and ys.max() + beam.isocenter_mm[2] <= hi + 5.0 + 8.0
        slab = target_slab(g.mask_xyz(1), g.origin_mm, g.spacing_mm, t.fields[1].z_range_mm)
        assert 0 < slab.sum() < g.masks.sum()

    def test_explicit_isocenter_is_honoured(self):
        from radiarch.services.machine_model import ProtonMachineModel
        from radiarch.services.proton_spots import generate_proton_spots

        g = _long_target()
        bs = BeamSetSpec(isocenter_mm=(0.0, 0.0, -100.0), beams=[BeamSpec(beam_id="B1", gantry_deg=180.0, target_z_range_mm=(-200.0, 0.0))])
        plan = generate_proton_spots(g, ProtonMachineModel.from_default(), bs, DeliveryParams(spot_spacing_mm=8.0, layer_spacing_mm=8.0)).plan
        assert plan.beams[0].isocenter_mm == (0.0, 0.0, -100.0)
