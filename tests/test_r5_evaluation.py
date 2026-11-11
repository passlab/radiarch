"""R5: clinical goals with pass/fail, EQD2 and NTCP/TCP, interpolated gamma, dose-impact comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import pytest

from radiarch.models.evaluation import ClinicalGoal, EvaluationRequest, GoalSetSpec, NTCPSpec, TCPSpec
from radiarch.models.geometry import GeometryBuildRequest, PatientRef
from radiarch.services import radiobiology as rb
from radiarch.services.clinical_goals import builtin_templates, evaluate_goal, evaluate_metric, load_template, parse_metric, resolve_structure


# ---------------------------------------------------------------------------
# Metrics and goals
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_parser(self):
        assert parse_metric("D95%[Gy]").text() == "D95%[Gy]"
        assert parse_metric("d0.03cc[gy]").text() == "D0.03cc[Gy]"
        assert parse_metric("V20Gy[%]").text() == "V20Gy[%]" and parse_metric("V95%[%]").needs_prescription
        assert parse_metric("Dmean[Gy]").stat == "mean" and parse_metric("Dmax[%]").needs_prescription
        for bad in ("D95[Gy]", "V20[%]", "Dmean[cc]", "D5cc[cc]", "Vmax[%]", "X1[Gy]"):
            with pytest.raises(ValueError):
                parse_metric(bad)

    def test_values_on_a_known_distribution(self):
        d = np.linspace(0.0, 100.0, 1001)              # 1001 voxels of 0.1 cc: 0, 0.1, ..., 100 Gy
        vox = 0.1
        assert evaluate_metric(parse_metric("Dmean[Gy]"), d, vox, None) == pytest.approx(50.0)
        assert evaluate_metric(parse_metric("Dmax[Gy]"), d, vox, None) == 100.0
        assert evaluate_metric(parse_metric("D50%[Gy]"), d, vox, None) == pytest.approx(50.0, abs=0.2)
        assert evaluate_metric(parse_metric("D95%[Gy]"), d, vox, None) == pytest.approx(5.0, abs=0.2)
        assert evaluate_metric(parse_metric("V20Gy[%]"), d, vox, None) == pytest.approx(80.0, abs=0.2)
        assert evaluate_metric(parse_metric("V20Gy[cc]"), d, vox, None) == pytest.approx(80.1, abs=0.2)
        # D<cc>: the dose received by at least 10 cc (100 voxels) = the 90th percentile
        assert evaluate_metric(parse_metric("D10cc[Gy]"), d, vox, None) == pytest.approx(90.0, abs=0.2)
        assert evaluate_metric(parse_metric("D200cc[Gy]"), d, vox, None) == 0.0      # larger than the structure: its minimum
        assert evaluate_metric(parse_metric("D95%[%]"), d, vox, 50.0) == pytest.approx(10.0, abs=0.5)
        assert evaluate_metric(parse_metric("V50%[%]"), d, vox, 40.0) == pytest.approx(80.0, abs=0.2)
        with pytest.raises(ValueError, match="prescription"):
            evaluate_metric(parse_metric("D95%[%]"), d, vox, None)

    def test_goal_pass_fail_margin_and_scenarios(self):
        d = np.full(100, 18.0)
        goal = ClinicalGoal(structure="Lungs", metric="Dmean[Gy]", op="<=", value=20.0, priority=1)
        r = evaluate_goal(goal, d, 1.0, None)
        assert r.passed and r.margin == pytest.approx(2.0) and r.achieved == 18.0 and r.worst_case == 18.0
        r2 = evaluate_goal(goal, d, 1.0, None, scenario_doses={"s1": np.full(100, 19.0), "s2": np.full(100, 21.0)})
        assert r2.passed and r2.worst_case == 21.0 and r2.passed_all_scenarios is False and r2.per_scenario == {"s1": 19.0, "s2": 21.0}
        cov = ClinicalGoal(structure="PTV", metric="V95%[%]", op=">=", value=95.0)
        r3 = evaluate_goal(cov, np.concatenate([np.full(96, 60.0), np.full(4, 50.0)]), 1.0, 60.0)
        assert r3.passed and r3.achieved == pytest.approx(96.0) and r3.margin == pytest.approx(1.0)
        with pytest.raises(ValueError):
            ClinicalGoal(structure="X", metric="D95%[Gy]", op="=", value=1.0)

    def test_templates_and_resolution(self):
        ids = sorted(builtin_templates())
        assert ids == ["nccn-head-neck", "pentec-pediatric", "quantec", "rtog-0617", "sbrt-lung-50gy-5fx", "sbrt-lung-54gy-3fx",
                       "tg101-sbrt-3fx", "tg101-sbrt-5fx"]
        t = load_template("rtog-0617")
        assert t.prescription_gy == 60.0 and t.fractions == 30 and any(g.structure == "Lungs-GTV" for g in t.goals)
        assert load_template("pentec-pediatric").provisional and load_template("quantec").dose_basis == "EQD2"
        assert all(len(load_template(i).source) > 20 for i in ids)
        avail = ["PTV_60", "Lung_Total-GTV", "spinal cord", "Heart", "Esophagus"]
        assert resolve_structure("Lungs-GTV", avail, t.aliases) == "Lung_Total-GTV"
        assert resolve_structure("SpinalCord", avail, t.aliases) == "spinal cord"
        assert resolve_structure("PTV", avail, t.aliases, {"PTV": "PTV_60"}) == "PTV_60"
        assert resolve_structure("PTV", avail, t.aliases) is None
        with pytest.raises(ValueError, match="unknown goal template"):
            load_template("rtog-9999")


# ---------------------------------------------------------------------------
# Radiobiology
# ---------------------------------------------------------------------------

class TestRadiobiology:
    def test_eqd2_and_bed(self):
        assert rb.eqd2(np.array([60.0]), 30, 3.0)[0] == pytest.approx(60.0)          # 2 Gy fractions are their own EQD2
        assert rb.eqd2(np.array([54.0]), 3, 3.0)[0] == pytest.approx(54.0 * (18 + 3) / 5)   # 3 x 18 Gy
        assert rb.bed(np.array([60.0]), 30, 10.0)[0] == pytest.approx(72.0)
        with pytest.raises(ValueError):
            rb.eqd2(np.array([1.0]), 0, 3.0)

    def test_geud_and_lkb(self):
        d = np.array([10.0, 20.0, 30.0, 40.0])
        assert rb.geud(d, 1.0) == pytest.approx(25.0)
        assert rb.geud(d, 1e9 if False else 50.0) == pytest.approx(40.0, rel=0.05)      # large a → max
        r = rb.lkb_ntcp(np.full(50, 30.8), 30.8, 0.37, 0.99)
        assert r["ntcp"] == pytest.approx(0.5, abs=1e-9)
        lo = rb.lkb_ntcp(np.full(50, 10.0), 30.8, 0.37, 0.99)["ntcp"]
        hi = rb.lkb_ntcp(np.full(50, 45.0), 30.8, 0.37, 0.99)["ntcp"]
        assert lo < 0.05 < 0.5 < hi
        params = rb.NTCP_MODELS["lung-pneumonitis-quantec"]
        assert params.td50_gy == 30.8 and "Marks" in params.source
        assert len(rb.NTCP_MODELS) >= 10 and all(m.source for m in rb.NTCP_MODELS.values())

    def test_lql_eqd2(self):
        """LQ-L: the LQ curve's tangent above the transition dose per fraction (Astrahan 2008)."""
        lq = rb.eqd2(np.array([54.0]), 3, 3.0)[0]
        lql = rb.eqd2(np.array([54.0]), 3, 3.0, transition_gy=6.0)[0]
        # 3 x 18 Gy, α/β 3, d_T 6: BED per fraction 6 (1 + 6/3) + 12 (1 + 12/3) = 78, EQD2 = 3 x 78 / (1 + 2/3)
        assert lql == pytest.approx(3 * 78.0 / (1 + 2 / 3.0)) and lql < lq
        # at or below the transition it is the LQ model, and the two meet with the same slope at d_T
        assert rb.eqd2(np.array([54.0]), 3, 3.0, transition_gy=18.0)[0] == pytest.approx(lq)
        assert rb.eqd2(np.array([60.0]), 30, 3.0, transition_gy=6.0)[0] == pytest.approx(60.0)
        eps = 1e-4
        below = rb.bed(np.array([6.0 - eps, 6.0]), 1, 3.0)
        above = rb.bed(np.array([6.0, 6.0 + eps]), 1, 3.0, transition_gy=6.0)
        assert (above[1] - above[0]) / eps == pytest.approx((below[1] - below[0]) / eps, rel=1e-3)
        with pytest.raises(ValueError):
            rb.eqd2(np.array([54.0]), 3, 3.0, transition_gy=0.0)

    def test_relative_seriality(self):
        """Källman's model: 0.5 at D50 over the reference volume for any seriality; a small serial organ follows its
        hottest voxels, a parallel one its mean."""
        for s in (0.01, 0.2, 1.0, 30.0):
            r = rb.relative_seriality_ntcp(np.full(50, 52.3), 52.3, 1.28, s)
            assert r["ntcp"] == pytest.approx(0.5) and r["effective_dose_gy"] == pytest.approx(52.3)
        # the explicit product of the paper's equation, voxel by voxel
        d, d50, g, s = np.array([10.0, 30.0, 50.0, 70.0]), 50.0, 2.0, 0.5
        p = np.exp(-np.exp(np.e * g - (d / d50) * (np.e * g - np.log(np.log(2.0)))))
        expected = (1 - np.prod((1 - p ** s) ** 0.25)) ** (1 / s)
        assert rb.relative_seriality_ntcp(d, d50, g, s)["ntcp"] == pytest.approx(expected, rel=1e-12)
        hot = np.r_[np.full(48, 10.0), [80.0, 80.0]]
        serial = rb.relative_seriality_ntcp(hot, 50.0, 2.0, 30.0)["ntcp"]
        parallel = rb.relative_seriality_ntcp(hot, 50.0, 2.0, 0.01)["ntcp"]
        assert serial > 0.5 > 0.01 > parallel
        # a larger reference volume gives each voxel a smaller share and a lower NTCP
        whole = rb.relative_seriality_ntcp(hot, 50.0, 2.0, 1.0)["ntcp"]
        assert rb.relative_seriality_ntcp(hot, 50.0, 2.0, 1.0, np.full(50, 1 / 100))["ntcp"] < whole
        # a steep dose response at low dose: P underflows, P^s does not, and nothing is lost or negative
        r = rb.relative_seriality_ntcp(np.linspace(0, 60, 200), 30.0, 3.0, 0.001)
        assert r["ntcp"] == pytest.approx(0.530882484, abs=1e-8)              # a 60-digit decimal reference
        cold = rb.relative_seriality_ntcp(np.full(10, 1.0), 30.0, 3.0, 1.0)
        assert cold["ntcp"] == 0.0 and str(cold["ntcp"]) == "0.0" and cold["effective_dose_gy"] is None
        heart = rb.RS_MODELS["heart-cardiac-mortality-gagliardi-rs"]
        assert (heart.d50_gy, heart.gamma, heart.s) == (52.3, 1.28, 1.0) and "Gagliardi" in heart.source
        assert all(m.source for m in rb.RS_MODELS.values())

    def test_poisson_tcp(self):
        r = rb.poisson_tcp(np.full(20, 84.5), 84.5, 1.5)
        assert r["tcp"] == pytest.approx(0.5) and r["eud_gy"] == pytest.approx(84.5)
        assert rb.poisson_tcp(np.full(20, 100.0), 84.5, 1.5)["tcp"] > 0.7           # 0.73: 0.5 ** exp(2γ(1 − 100/84.5)/ln 2)
        assert rb.poisson_tcp(np.full(20, 40.0), 84.5, 1.5)["tcp"] < 0.02
        cold = rb.poisson_tcp(np.concatenate([np.full(19, 90.0), [40.0]]), 84.5, 1.5)
        assert cold["tcp"] < rb.poisson_tcp(np.full(20, 90.0), 84.5, 1.5)["tcp"]
        assert rb.default_alpha_beta("SpinalCord") == 2.0 and rb.default_alpha_beta("PTV_60") == 10.0 and rb.default_alpha_beta("Parotid_L") == 3.0


# ---------------------------------------------------------------------------
# Gamma
# ---------------------------------------------------------------------------

class TestGamma:
    @staticmethod
    def _gaussian(shape=(20, 30, 30), s=2.0):
        z, y, x = (np.arange(n) * s for n in shape)
        zz, yy, xx = np.meshgrid(z - z.mean(), y - y.mean(), x - x.mean(), indexing="ij")
        return (60.0 * np.exp(-(xx ** 2 + yy ** 2) / (2 * 12.0 ** 2) - zz ** 2 / (2 * 15.0 ** 2))).astype(np.float32), s

    def test_identical_and_sub_voxel_shift_pass(self):
        from radiarch.services.gamma import gamma_index, gamma_map

        ref, s = self._gaussian()
        assert gamma_index(ref, ref, (s, s, s), 3.0, 2.0, 10.0).pass_rate_pct == 100.0
        # a 1 mm shift is inside a 2 mm DTA: the interpolated search passes everywhere
        assert gamma_index(np.roll(ref, 1, axis=2) * 1.0, ref, (s, s, s), 3.0, 2.0, 10.0).pass_rate_pct == 100.0
        g = gamma_map(ref * 1.02, ref, (s, s, s), 3.0, 2.0, 10.0)
        assert np.nanmax(g) <= 1.0 and np.isnan(g[0, 0, 0])

    def test_large_shift_and_scale_fail(self):
        from radiarch.services.gamma import gamma_index

        ref, s = self._gaussian()
        far = gamma_index(np.roll(ref, 3, axis=1) * 1.04, ref, (s, s, s), 3.0, 2.0, 10.0)
        assert 2.0 < far.pass_rate_pct < 90.0 and far.mean_gamma > 0.5
        # a 10 % scaling with a 2 mm DTA is absorbed by the gradient (a scaled gaussian matches the
        # reference a little farther out); with a 0.5 mm DTA only the low-dose shell (< 30 % of the
        # maximum, where 10 % of the local dose is under 3 % of the maximum) passes
        assert gamma_index(ref * 1.10, ref, (s, s, s), 3.0, 2.0, 10.0).pass_rate_pct > 80.0
        scaled = gamma_index(ref * 1.10, ref, (s, s, s), 3.0, 0.5, 10.0)
        assert 20.0 < scaled.pass_rate_pct < 80.0
        # a local 3 % criterion on a 5 % scaling: with a 2 mm DTA the gradient absorbs it; with 0.5 mm it mostly does not
        tight = gamma_index(ref * 1.05, ref, (s, s, s), 3.0, 0.5, 10.0, local=True)
        loose = gamma_index(ref * 1.05, ref, (s, s, s), 3.0, 2.0, 10.0, local=True)
        assert tight.pass_rate_pct < 95.0 and tight.mean_gamma > 0.5 and loose.pass_rate_pct == 100.0
        assert tight.mean_gamma > loose.mean_gamma


# ---------------------------------------------------------------------------
# Through the evaluation service and the API
# ---------------------------------------------------------------------------

@dataclass
class _Patient:
    name: str = "R5"


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

    n = 20
    ct = np.zeros((n, n, n), np.int16)
    xx, yy, zz = np.mgrid[:n, :n, :n]
    ptv = (np.abs(xx - 9.5) <= 3) & (np.abs(yy - 9.5) <= 3) & (np.abs(zz - 9.5) <= 3)
    lungs = (np.abs(xx - 9.5) <= 8) & (np.abs(zz - 9.5) <= 8) & (yy < 7)
    cord = (np.abs(xx - 9.5) <= 1) & (np.abs(yy - 16) <= 1)
    vol = _CT(imageArray=ct, origin=(-38.0, -38.0, -38.0), spacing=(4.0, 4.0, 4.0), patient=_Patient())
    return _LoadedCT(ct=vol, patient=vol.patient,
                     contours=[_Contour("PTV", ptv), _Contour("Lung_Total-GTV", lungs), _Contour("SpinalCord", cord)])


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


def _geometry_and_dose(tmp_path, hot_cord: bool = False):
    """A 60 Gy box on the PTV, a lung bath, the cord at 30 or 55 Gy; (z, y, x) dose written as a file."""
    from radiarch.services.dose_persistence import _write_dose_volume
    from radiarch.services.geometry import GeometryService
    from radiarch.services.geometry_bundle import load_geometry_arrays

    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    arrays = load_geometry_arrays(geo)
    dose = np.zeros(arrays.ct_hu.shape, np.float32)
    dose[arrays.mask_zyx(arrays.label_of("Lung_Total-GTV"))] = 12.0
    dose[arrays.mask_zyx(arrays.label_of("SpinalCord"))] = 55.0 if hot_cord else 30.0
    dose[arrays.mask_zyx(arrays.label_of("PTV"))] = 60.0
    path = tmp_path / ("dose_hot.nii.gz" if hot_cord else "dose.nii.gz")
    _write_dose_volume(path, dose, (4.0, 4.0, 4.0))
    return geo, str(path)


class TestEvaluationService:
    def test_goals_ntcp_tcp(self, env):
        from radiarch.services.evaluation import EvaluationService

        geo, uri = _geometry_and_dose(env)
        req = EvaluationRequest(
            dose_ref_uri=uri, geometry_id=geo.geometry_id, prescription_gy=60.0, target_structure="PTV", fractions=30,
            goals=GoalSetSpec(template_id="rtog-0617", goals=[ClinicalGoal(structure="PTV", metric="D98%[%]", op=">=", value=95.0, priority=1)]),
            ntcp=[NTCPSpec(model_id="lung-pneumonitis-quantec", structure="Lung_Total-GTV"), NTCPSpec(model_id="spinal-cord-myelopathy-burman")],
            tcp=[TCPSpec(model_id="nsclc-martel")],
        )
        out = EvaluationService().run(req)
        g = out.goals
        assert g is not None and g.template_id == "rtog-0617" and g.dose_basis == "physical" and g.fractions == 30
        by = {(r.structure, r.metric): r for r in g.results}
        assert by[("Lungs-GTV", "V20Gy[%]")].resolved_structure == "Lung_Total-GTV" and by[("Lungs-GTV", "V20Gy[%]")].passed
        assert by[("Lungs-GTV", "Dmean[Gy]")].achieved == pytest.approx(12.0) and by[("Lungs-GTV", "Dmean[Gy]")].passed
        assert by[("SpinalCord", "D0.03cc[Gy]")].achieved == pytest.approx(30.0) and by[("SpinalCord", "D0.03cc[Gy]")].passed
        assert by[("PTV", "V60Gy[%]")].passed and by[("PTV", "D98%[%]")].achieved == pytest.approx(100.0)
        assert by[("Esophagus", "Dmean[Gy]")].missing and by[("Esophagus", "Dmean[Gy]")].passed is None
        assert g.n_missing >= 3 and g.all_priority1_passed and g.n_failed == 0 and g.robust_all_passed is None
        assert all(r.source for r in g.results)
        lung = next(r for r in out.ntcp if r.model_id == "lung-pneumonitis-quantec")
        assert lung.structure == "Lung_Total-GTV" and lung.eqd2_applied and 0.0 < lung.ntcp < 0.1
        cord = next(r for r in out.ntcp if r.model_id == "spinal-cord-myelopathy-burman")
        assert cord.structure == "SpinalCord" and cord.ntcp < 1e-3
        assert out.tcp[0].structure == "PTV" and 0.0 < out.tcp[0].tcp < 0.5         # 60 Gy against D50 84.5
        # cached; a hot cord fails the priority-1 goal
        assert EvaluationService().run(req).evaluation_id == out.evaluation_id
        geo2, uri2 = _geometry_and_dose(env, hot_cord=True)
        hot = EvaluationService().run(req.model_copy(update={"dose_ref_uri": uri2}))
        assert not hot.goals.all_priority1_passed and hot.goals.failed_by_priority[1] == 1
        cordres = next(r for r in hot.goals.results if r.structure == "SpinalCord")
        assert cordres.achieved == pytest.approx(55.0) and cordres.margin == pytest.approx(-4.5)

    def test_eqd2_goals_need_fractions(self, env):
        from radiarch.services.evaluation import EvaluationService

        geo, uri = _geometry_and_dose(env)
        with pytest.raises(ValueError, match="fractions"):
            EvaluationService().run(EvaluationRequest(dose_ref_uri=uri, geometry_id=geo.geometry_id, prescription_gy=60.0,
                                                      goals=GoalSetSpec(template_id="quantec")))
        out = EvaluationService().run(EvaluationRequest(dose_ref_uri=uri, geometry_id=geo.geometry_id, prescription_gy=60.0, fractions=30,
                                                        goals=GoalSetSpec(template_id="quantec", structure_aliases={"Lungs": "Lung_Total-GTV"})))
        lungs = {(r.structure, r.metric): r for r in out.goals.results}[("Lungs", "Dmean[Gy]")]
        assert lungs.resolved_structure == "Lung_Total-GTV" and lungs.achieved == pytest.approx(rb.eqd2(np.array([12.0]), 30, 3.0)[0])

    def test_unknown_model_and_structure(self, env):
        from radiarch.services.evaluation import EvaluationService

        geo, uri = _geometry_and_dose(env)
        with pytest.raises(ValueError, match="unknown NTCP model"):
            EvaluationService().run(EvaluationRequest(dose_ref_uri=uri, geometry_id=geo.geometry_id, prescription_gy=60.0, ntcp=[NTCPSpec(model_id="nope")]))
        with pytest.raises(ValueError, match="not in the geometry"):
            EvaluationService().run(EvaluationRequest(dose_ref_uri=uri, geometry_id=geo.geometry_id, prescription_gy=60.0, ntcp=[NTCPSpec(model_id="liver-rild-dawson")]))
        with pytest.raises(ValueError, match="not both"):
            NTCPSpec(parameters=rb.NTCP_MODELS["kidney-burman"], relative_seriality=rb.RS_MODELS["heart-cardiac-mortality-gagliardi-rs"])

    def test_relative_seriality_and_lql_in_an_evaluation(self, env):
        from radiarch.services.evaluation import EvaluationService

        geo, uri = _geometry_and_dose(env)
        base = EvaluationRequest(dose_ref_uri=uri, geometry_id=geo.geometry_id, prescription_gy=60.0, fractions=30,
                                 ntcp=[NTCPSpec(model_id="lung-pneumonitis-quantec", structure="Lung_Total-GTV")])
        cord_eqd2 = float(rb.eqd2(np.array([30.0]), 30, 2.0)[0])              # the cord's 30 Gy in 30 fractions: 22.5 Gy
        cord = rb.RelativeSerialityParameters(model_id="cord-test", structure="SpinalCord", endpoint="test", d50_gy=cord_eqd2,
                                              gamma=2.0, s=1.0, alpha_beta_gy=2.0)
        out = EvaluationService().run(base.model_copy(update={"ntcp": base.ntcp + [
            NTCPSpec(relative_seriality=cord),
            NTCPSpec(relative_seriality=cord.model_copy(update={"model_id": "cord-ref", "reference_volume_cc": 1000.0}))]}))
        lkb, rs, ref = out.ntcp
        assert lkb.model == "lkb" and lkb.geud_gy is not None and lkb.effective_dose_gy is None
        # the cord's EQD2 is uniform at its D50: 0.5 over its own volume, less over a larger reference volume
        assert rs.model == "relative_seriality" and rs.ntcp == pytest.approx(0.5) and rs.effective_dose_gy == pytest.approx(cord_eqd2)
        assert rs.geud_gy is None and ref.ntcp < rs.ntcp
        # LQ-L changes nothing at fractions below the transition, and keys a new evaluation only when set
        lql = EvaluationService().run(base.model_copy(update={"lql_transition_gy": 6.0}))
        plain = EvaluationService().run(base)
        assert lql.ntcp[0].ntcp == pytest.approx(plain.ntcp[0].ntcp) and lql.evaluation_id != plain.evaluation_id
        assert base.compute_cache_key() != base.model_copy(update={"lql_transition_gy": 6.0}).compute_cache_key()
        with pytest.raises(ValueError, match="needs the plan's fractions"):
            EvaluationRequest(dose_ref_uri=uri, geometry_id=geo.geometry_id, prescription_gy=60.0, lql_transition_gy=6.0)


def test_api_templates_models_and_compare(env, monkeypatch):
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.app import create_app
    from radiarch.core import store as store_module

    geo, uri = _geometry_and_dose(env)
    geo2, uri_hot = _geometry_and_dose(env, hot_cord=True)
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    app = create_app()
    with TestClient(app) as client:
        t = client.get("/api/v1/evaluate/goal-templates").json()
        assert [x["template_id"] for x in t] == sorted(builtin_templates()) and all(x["source"] for x in t)
        full = client.get("/api/v1/evaluate/goal-templates/tg101-sbrt-5fx").json()
        assert full["fractions"] == 5 and len(full["goals"]) > 10
        assert client.get("/api/v1/evaluate/goal-templates/nope").status_code == 404
        m = client.get("/api/v1/evaluate/models").json()
        assert len(m["ntcp"]) >= 10 and len(m["tcp"]) >= 3 and m["default_alpha_beta_gy"]["lungs"] == 3.0
        assert [x["model_id"] for x in m["ntcp_relative_seriality"]] == ["heart-cardiac-mortality-gagliardi-rs"]
        base = {"geometry_id": geo.geometry_id, "prescription_gy": 60.0, "target_structure": "PTV", "fractions": 30,
                "goals": {"template_id": "rtog-0617"}}
        r = client.post("/api/v1/evaluate/compare", json={"a": {**base, "dose_ref_uri": uri}, "b": {**base, "dose_ref_uri": uri_hot}})
        assert r.status_code == 200, r.text
        body = r.json()
        cord = next(s for s in body["structures"] if s["structure"] == "SpinalCord")
        assert cord["delta"]["max_gy"] == pytest.approx(25.0) and body["largest_metric_delta"] == pytest.approx(25.0)
        assert body["goal_changes"] and body["goal_changes"][0]["structure"] == "SpinalCord" and body["goal_changes"][0]["b_passed"] is False
        assert body["indices_delta"]["coverage_pct"] == pytest.approx(0.0)
        r2 = client.post("/api/v1/evaluate/compare", json={"evaluation_id_a": body["evaluation_a"], "evaluation_id_b": body["evaluation_b"], "structures": ["PTV"]})
        assert r2.status_code == 200 and [s["structure"] for s in r2.json()["structures"]] == ["PTV"]
        assert client.post("/api/v1/evaluate/compare", json={"evaluation_id_a": "x"}).status_code == 404
    store_module.reset_store()
