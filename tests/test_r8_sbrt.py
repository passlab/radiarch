"""Roadmap R8: SBRT plan-quality indices and the lung SBRT planning templates."""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.services.clinical_goals import load_template
from radiarch.services.sbrt import RTOG_CONFORMALITY, grade, rtog_limits, sbrt_indices


class TestTable:
    def test_rows_and_interpolation(self):
        assert rtog_limits(1.8)["R50"] == (5.9, 7.5) and rtog_limits(1.8)["D2cm"] == (50.0, 57.0)
        assert rtog_limits(163.0)["R50"] == (2.9, 3.7)
        mid = rtog_limits(60.0)                       # halfway between 50 and 70 cc
        assert mid["R50"] == pytest.approx((3.75, 4.9)) and mid["D2cm"] == pytest.approx((64.0, 81.5))
        assert rtog_limits(0.5) == rtog_limits(1.8) and rtog_limits(500.0) == rtog_limits(163.0)

    def test_limits_tighten_with_volume(self):
        t = RTOG_CONFORMALITY
        assert np.all(np.diff(t[:, 0]) > 0) and np.all(np.diff(t[:, 1]) < 0) and np.all(np.diff(t[:, 2]) < 0)
        assert np.all(t[:, 2] > t[:, 1]) and np.all(t[:, 4] >= t[:, 3])

    def test_grade(self):
        assert grade(1.1, (1.2, 1.5)) == "none" and grade(1.3, (1.2, 1.5)) == "minor" and grade(1.6, (1.2, 1.5)) == "major"


def test_indices_of_a_spherical_dose():
    s = 2.0
    n = 81
    z, y, x = np.meshgrid(*(np.arange(n) * s - (n - 1) / 2 * s for _ in range(3)), indexing="ij")
    r = np.sqrt(x ** 2 + y ** 2 + z ** 2)
    ptv = r <= 15.0
    body = r <= 75.0
    rx = 54.0
    dose = np.where(r <= 16.0, rx * 1.1, rx * 1.1 * np.exp(-(r - 16.0) / 12.0)).astype(np.float32)
    lungs = (r > 20.0) & (np.abs(x) < 70)
    ind = sbrt_indices(dose, ptv, body, rx, (s, s, s), lungs_zyx=lungs)
    assert ind.ptv_cc == pytest.approx(4 / 3 * np.pi * 15.0 ** 3 / 1000.0, rel=0.05)
    # the prescription isodose is the sphere r <= 16 + 12 ln 1.1, the 50 % one r <= 16 + 12 ln 2.2
    r100, r50 = 16.0 + 12 * np.log(1.1), 16.0 + 12 * np.log(2.2)
    assert ind.r100 == pytest.approx((r100 / 15.0) ** 3, rel=0.08)
    assert ind.r50 == pytest.approx((r50 / 15.0) ** 3, rel=0.08)
    # 2 cm from the voxelized PTV: distances run from voxel centres, so the shell may sit up to a voxel inside 35 mm
    assert 110.0 * np.exp(-(35.0 - 16.0) / 12.0) <= ind.d2cm_pct <= 110.0 * np.exp(-(35.0 - s - 16.0) / 12.0)
    assert ind.gradient_index == pytest.approx(ind.r50 / ind.r100, rel=1e-9)
    assert set(ind.deviations) == {"R100", "R50", "D2cm", "LungV20"}
    assert ind.to_dict()["acceptable"] == ind.acceptable


@pytest.mark.parametrize("tid,rx,fx,tg", [("sbrt-lung-54gy-3fx", 54.0, 3, "tg101-sbrt-3fx"), ("sbrt-lung-50gy-5fx", 50.0, 5, "tg101-sbrt-5fx")])
def test_planning_templates(tid, rx, fx, tg):
    t = load_template(tid)
    assert t.prescription_gy == rx and t.fractions == fx and t.site == "lung"
    ptv = [g for g in t.goals if g.structure == "PTV"]
    assert {g.metric for g in ptv} >= {"V100%[%]", "V90%[%]"}
    tg101 = load_template(tg)
    keys = {(g.structure, g.metric, g.op, g.value) for g in t.goals}
    assert all((g.structure, g.metric, g.op, g.value) in keys for g in tg101.goals)
