"""Unit tests for the HU → density module.

We deliberately avoid importing OpenTPS here — the Stoichiometric model is
exercised in the OpenTPS integration suite, not this fast-tier test file.
Schneider and Linear have no heavy deps and must stay fast.
"""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.models.geometry import HUDensityModel
from radiarch.services.hu_density import (
    LinearModel,
    SchneiderModel,
    get_model,
)


# ---------------------------------------------------------------------------
# Schneider
# ---------------------------------------------------------------------------

class TestSchneider:
    def setup_method(self) -> None:
        self.model = SchneiderModel()

    def test_air_is_near_zero(self) -> None:
        rho = self.model.convert(np.array([-1000.0]))
        assert rho.dtype == np.float32
        assert float(rho[0]) == pytest.approx(0.00121, abs=1e-4)

    def test_water_is_unity(self) -> None:
        # HU=0 lies between -98 (fat, ρ=0.93) and 14 (soft tissue, ρ=1.03);
        # at HU=0 the interpolation gives ρ ≈ 0.93 + (0 - -98)/(14 - -98) * (1.03 - 0.93)
        #                                     = 0.93 + 98/112 * 0.10 ≈ 1.0175.
        rho = self.model.convert(np.array([0.0]))
        assert 0.99 < float(rho[0]) < 1.03

    def test_soft_tissue_is_close_to_unity(self) -> None:
        rho = self.model.convert(np.array([14.0, 23.0]))
        assert np.allclose(rho, 1.03, atol=1e-3)

    def test_bone_is_denser_than_water(self) -> None:
        rho = self.model.convert(np.array([1000.0]))
        assert float(rho[0]) > 1.4

    def test_clamps_below_floor(self) -> None:
        rho = self.model.convert(np.array([-5000.0]))
        # np.interp clamps at left endpoint; must not go negative.
        assert float(rho[0]) == pytest.approx(0.00121, abs=1e-4)

    def test_clamps_above_cap(self) -> None:
        rho = self.model.convert(np.array([10_000.0]))
        assert float(rho[0]) == pytest.approx(2.88, abs=1e-3)

    def test_monotone_non_decreasing_on_dense_range(self) -> None:
        hu = np.linspace(-1000, 2000, 200)
        rho = self.model.convert(hu)
        # Allow equality (the HU=14..23 plateau is intentional).
        assert np.all(np.diff(rho) >= -1e-5), "Schneider curve must be non-decreasing"

    def test_preserves_shape(self) -> None:
        hu = np.arange(24, dtype=np.int16).reshape(2, 3, 4)
        rho = self.model.convert(hu.astype(np.float32))
        assert rho.shape == hu.shape
        assert rho.dtype == np.float32


# ---------------------------------------------------------------------------
# Linear
# ---------------------------------------------------------------------------

class TestLinear:
    def setup_method(self) -> None:
        self.model = LinearModel()

    def test_water_is_exactly_one(self) -> None:
        rho = self.model.convert(np.array([0.0]))
        assert float(rho[0]) == pytest.approx(1.0, abs=1e-7)

    def test_air_is_zero_not_negative(self) -> None:
        rho = self.model.convert(np.array([-1000.0]))
        assert float(rho[0]) == pytest.approx(0.0, abs=1e-7)

    def test_extreme_negative_clamped_to_zero(self) -> None:
        rho = self.model.convert(np.array([-5000.0]))
        # 1 + (-5000)/1000 = -4 → clamped to 0
        assert float(rho[0]) == 0.0

    def test_bone_density(self) -> None:
        rho = self.model.convert(np.array([1000.0]))
        assert float(rho[0]) == pytest.approx(2.0, abs=1e-6)

    def test_vectorized_shape(self) -> None:
        hu = np.random.RandomState(0).uniform(-1000, 2000, size=(5, 5, 5))
        rho = self.model.convert(hu)
        assert rho.shape == (5, 5, 5)
        assert rho.dtype == np.float32


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_enum_dispatch(self) -> None:
        assert isinstance(get_model(HUDensityModel.schneider), SchneiderModel)
        assert isinstance(get_model(HUDensityModel.linear), LinearModel)

    def test_string_dispatch(self) -> None:
        assert isinstance(get_model("SCHNEIDER"), SchneiderModel)
        assert isinstance(get_model("LINEAR"), LinearModel)

    def test_rejects_unknown_string(self) -> None:
        with pytest.raises(ValueError, match="Unknown HU density model"):
            get_model("PLASTICINE")

    def test_callable_interface(self) -> None:
        # get_model(...) should return an object you can call like a function.
        model = get_model(HUDensityModel.linear)
        rho_call = model(np.array([0.0]))
        rho_convert = model.convert(np.array([0.0]))
        np.testing.assert_array_equal(rho_call, rho_convert)
