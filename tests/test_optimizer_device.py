"""The optimizer on the CPU or a GPU (``optimizer_device``, docs/reports/engine-performance.md).

The CPU is the default and its path is unchanged; the setting moves the products with the influence matrix and the
objective terms to a GPU through CuPy, and the solver stays on the host. Without a GPU the device comparisons are
skipped; the setting, the cache keys and the fallbacks are tested everywhere.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest
import scipy.sparse as sp

from radiarch.models.optimization import HardConstraint, ObjectiveSpec
from radiarch.services import array_backend as AB
from radiarch.services import objectives as O
from radiarch.services.hard_constraints import HardConstraintTerm

from test_optimization_service import _req, svc  # noqa: F401


def _gpu_ok() -> bool:
    try:
        return AB.optimizer_device("gpu").gpu
    except Exception:
        return False


needs_gpu = pytest.mark.skipif(not _gpu_ok(), reason="CuPy or a CUDA device not available")


@pytest.fixture
def on_device(monkeypatch):
    """Set the setting ``optimizer_device`` for one test."""
    from radiarch.config import get_settings

    def use(device: str) -> None:
        monkeypatch.setattr(get_settings(), "optimizer_device", device)
    return use


# ---------------------------------------------------------------------------
# The setting, without a GPU
# ---------------------------------------------------------------------------

class TestSetting:
    def test_the_cpu_is_the_default(self):
        from radiarch.config import Settings
        assert Settings().optimizer_device == "cpu"
        assert AB.optimizer_device("cpu") is AB.CPU and not AB.CPU.gpu

    def test_an_unknown_device_is_refused(self):
        with pytest.raises(ValueError, match="optimizer device"):
            AB.optimizer_device("tpu")

    def test_the_cache_key_follows_the_setting(self):
        # the CPU's keys are the ones earlier results were stored under; gpu and auto have their own
        assert AB.device_cache_key("k", "cpu") == "k"
        assert len({AB.device_cache_key("k", "gpu"), AB.device_cache_key("k", "auto"), "k"}) == 3
        assert AB.device_cache_key("k", "GPU") == AB.device_cache_key("k", "gpu")

    def test_gpu_without_cupy_is_an_error_and_auto_falls_back(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "cupy", None)          # importing cupy now fails
        with pytest.raises(AB.DeviceUnavailableError):
            AB.optimizer_device("gpu")
        assert AB.optimizer_device("auto") is AB.CPU

    def test_the_cpu_matrix_is_the_scipy_product(self):
        A = sp.random(60, 7, density=0.3, format="csr", random_state=0, dtype=np.float32)
        dm = AB.CPU.matrix(A, (3, 4, 5))
        w, g = np.arange(7.0), np.random.default_rng(0).random((3, 4, 5))
        assert np.array_equal(dm.forward(w), np.asarray(A @ w).reshape(3, 4, 5))
        assert np.array_equal(dm.backward(g), np.asarray(A.T @ g.ravel(), dtype=np.float64))

    def test_a_cpu_run_is_unchanged(self, svc, on_device):  # noqa: F811
        on_device("cpu")
        res = svc.run(_req())
        assert res.cache_key == _req().compute_cache_key()
        assert not any("GPU" in n for n in res.convergence.notes)


# ---------------------------------------------------------------------------
# On a GPU
# ---------------------------------------------------------------------------

@needs_gpu
class TestOnTheGPU:
    def test_the_products_match_the_cpu(self):
        A = sp.random(5000, 300, density=0.05, format="csr", random_state=1, dtype=np.float32)
        gpu = AB.optimizer_device("gpu")
        dm, cpu = gpu.matrix(A, (50, 10, 10)), AB.CPU.matrix(A, (50, 10, 10))
        rng = np.random.default_rng(2)
        w, g = rng.random(300), rng.random((50, 10, 10))
        d = dm.forward(w)
        assert type(d).__module__.startswith("cupy") and d.dtype == np.float64
        assert np.allclose(AB.to_host(d), cpu.forward(w), rtol=1e-12, atol=0)
        assert np.allclose(dm.backward(g), cpu.backward(g), rtol=1e-12, atol=0)
        assert isinstance(dm.backward(gpu.asarray(g)), np.ndarray)

    @pytest.mark.parametrize("obj", [
        O.DMin("s", 60, 2.0), O.DMax("s", 40, 1.5), O.DUniform("s", 50), O.DVHMin("s", 55, 0.05), O.DVHMax("s", 30, 0.2),
        O.EUD("s", 30, 4.0), O.MeanDose("s", 10), O.EUDMax("s", 5, 8.0), O.EUDMin("s", 65, -10.0), O.RMSOver("s", 40),
        O.RMSUnder("s", 60), O.UniformRMS("s", 50), O.ConstraintPenalty("s", "<=", 45), O.ConstraintPenalty("s", ">=", 20),
    ], ids=lambda o: o.name)
    def test_every_objective_matches_the_cpu(self, obj):
        rng = np.random.default_rng(3)
        dose = rng.random((20, 30, 25)) * 70
        mask = (rng.random(dose.shape) > 0.6).astype(np.float64)
        gpu = AB.optimizer_device("gpu")
        l_cpu, g_cpu = obj(dose, mask)
        for d, m in ((gpu.asarray(dose), gpu.asarray(mask)), (dose, gpu.asarray(mask))):     # a host dose too
            l_gpu, g_gpu = obj(d, m)
            assert l_gpu == pytest.approx(l_cpu, rel=1e-12, abs=1e-300)
            assert np.allclose(AB.to_host(g_gpu), g_cpu, rtol=1e-12, atol=1e-300)

    def test_the_reference_dose_matches_the_cpu(self):
        rng = np.random.default_rng(4)
        dose, ref = rng.random((10, 12, 14)) * 70, rng.random((10, 12, 14)) * 70
        mask = (rng.random(dose.shape) > 0.5).astype(np.float64)
        gpu = AB.optimizer_device("gpu")
        for role in ("organ", "target"):
            obj = O.ReferenceDose("s", ref, role)
            (l1, g1), (l2, g2) = obj(dose, mask), obj(gpu.asarray(dose), gpu.asarray(mask))
            assert l2 == pytest.approx(l1, rel=1e-12) and np.allclose(AB.to_host(g2), g1, rtol=1e-12)

    @pytest.mark.parametrize("hc", [
        HardConstraint(structure_name="s", metric="Dmax", op="<=", value_gy=50.0),
        HardConstraint(structure_name="s", metric="Dmin", op=">=", value_gy=30.0),
        HardConstraint(structure_name="s", metric="Dmean", op="<=", value_gy=20.0),
        HardConstraint(structure_name="s", metric="gEUD", op="<=", value_gy=40.0, eud_a=8.0),
    ], ids=lambda c: c.metric)
    def test_a_hard_constraint_term_matches_the_cpu(self, hc):
        rng = np.random.default_rng(5)
        dose = rng.random((12, 10, 8)) * 70
        mask = (rng.random(dose.shape) > 0.5).astype(np.float64)
        gpu = AB.optimizer_device("gpu")
        t_cpu, t_gpu = HardConstraintTerm(hc, mask), HardConstraintTerm(hc, gpu.asarray(mask))
        for rho in (1.0, 10.0):
            (l1, g1), (l2, g2) = t_cpu.term(dose, rho), t_gpu.term(gpu.asarray(dose), rho)
            assert l2 == pytest.approx(l1, rel=1e-12) and np.allclose(AB.to_host(g2), g1, rtol=1e-12)
            t_cpu.update(dose, rho)
            t_gpu.update(gpu.asarray(dose), rho)
        assert t_gpu.violation(gpu.asarray(dose)) == pytest.approx(t_cpu.violation(dose), rel=1e-12)
        assert t_gpu.outcome(gpu.asarray(dose)) == t_cpu.outcome(dose)

    def test_a_run_on_the_gpu_reaches_the_cpu_cost(self, svc, on_device):  # noqa: F811
        req = _req(objectives=[ObjectiveSpec(type="DUniform", structure_name="PTV", dose_gy=10.0, weight=1.0),
                               ObjectiveSpec(type="DMax", structure_name="OAR", dose_gy=2.0, weight=1.0)])
        on_device("cpu")
        cpu = svc.run(req)
        on_device("gpu")
        gpu = svc.run(req)
        assert gpu.optimization_id != cpu.optimization_id and gpu.cache_key == AB.device_cache_key(req.compute_cache_key(), "gpu")
        assert "solved on the GPU (optimizer_device)" in gpu.convergence.notes
        # the CPU path doses in float32 (apply_influence), the GPU's in float64: the same optimum, not the same digits
        assert gpu.convergence.final_cost == pytest.approx(cpu.convergence.final_cost, rel=1e-4, abs=1e-9)

    def test_too_little_gpu_memory_falls_back_to_the_cpu(self, svc, on_device, monkeypatch):  # noqa: F811
        on_device("gpu")
        monkeypatch.setattr(AB.OptimizerDevice, "free_bytes", lambda self: 10)
        prob = svc._assemble_problem(_req())
        assert not prob.device.gpu and prob.dev_mats == {}
