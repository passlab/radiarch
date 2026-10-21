"""MCsquare proton dose engine (roadmap R14).

The :class:`DoseEnginePlugin` for proton pencil-beam scanning, backed by
radiarch's own file-protocol driver (:mod:`.mcsquare_driver`): the engine
binary is run as a subprocess on files radiarch writes, and nothing from
OpenTPS is imported. Beam models built before R15 still carry an OpenTPS
``ProtonPlan`` object; :meth:`ProtonPlan.from_opentps` adapts it (duck-typed).

Design notes
------------
* **Frames.** Everything the engine returns is in radiarch's ``(z, y, x)``
  C-order on the geometry grid: the dose array has the geometry's shape and
  the influence matrix's rows are its C-order voxels, so ``Dij @ w`` reshaped
  in C-order is the dose. (The previous OpenTPS-backed engine returned the
  dose in OpenTPS's ``(x, y, z)`` order; on the cubic test phantom that went
  unnoticed.)
* **Scenarios perturb the inputs, never the cached bundle.** A setup shift
  moves every isocenter; a density or range scale rewrites the HU→density
  table the engine reads. Robustness through MCsquare's own scenario mode
  arrives with R3.
* **Determinism.** With ``nb_threads=1`` and a non-zero ``seed`` a run is
  reproducible bit for bit; the defaults (all cores, clock seed) are not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger

from ...models.dose import ScenarioSpec
from ...models.proton_plan import ProtonPlan
from .mcsquare_driver import CalibrationTables, MCsquareAssets, MCsquareDriver, default_assets_dir
from .protocol import (
    BeamModelBundle,
    DoseEnginePlugin,
    EngineParamError,
    EngineRuntimeError,
    EngineUnavailableError,
    GeometryBundle,
    InfluenceData,
    NominalDose,
)
from .registry import register_engine


@dataclass
class MCsquareEngine:
    """Proton dose engine backed by radiarch's MCsquare driver."""

    name: str = "mcsquare"
    version: str = "0.3.0"  # R14: own driver, (z, y, x) frames
    modalities: List[str] = field(default_factory=lambda: ["PROTON_PBS"])

    # ----- driver and settings -----------------------------------------

    @staticmethod
    def _settings():
        from ...config import get_settings
        return get_settings()

    def driver(self, params: Optional[dict] = None) -> MCsquareDriver:
        params = params or {}
        s = self._settings()
        assets = MCsquareAssets(Path(params["mcsquare_dir"])) if params.get("mcsquare_dir") else MCsquareAssets(default_assets_dir())
        return MCsquareDriver(
            assets=assets,
            work_root=Path(s.artifact_dir) / "mcsquare",
            n_threads=int(params.get("nb_threads", s.mcsquare_n_threads)),
            seed=int(params.get("seed", s.mcsquare_seed)),
            keep_workdir=bool(params.get("keep_workdir", s.mcsquare_keep_workdir)),
            scanner=str(params.get("scanner", s.mcsquare_scanner)),
            bdl=str(params.get("bdl", s.mcsquare_bdl)),
        )

    # ----- diagnostics --------------------------------------------------

    def health(self) -> dict:
        drv = self.driver()
        ok, reason = drv.availability()
        diag: Dict[str, Any] = {
            "assets_dir": str(drv.assets.root),
            "binaries": [b.name for b in drv.assets.binaries()],
            "launcher": str(drv.assets.launcher),
            "scanner": drv.scanner,
            "bdl": drv.bdl_name,
            "reason": reason,
        }
        if ok:
            diag["engine_fingerprint"] = drv.fingerprint()
        return {
            "name": self.name,
            "version": self.version,
            "modalities": list(self.modalities),
            "available": ok,
            "test_only": False,
            "supports": {"compute_dose": True, "build_influence": True, "compute_grad": False},
            "diagnostics": diag,
        }

    # ----- validation ---------------------------------------------------

    def validate(self, geometry: GeometryBundle, beam_model: BeamModelBundle, params: dict) -> List[str]:
        issues: List[str] = []
        if beam_model.result.modality.value != "PROTON_PBS":
            issues.append(f"mcsquare engine requires PROTON_PBS, got {beam_model.result.modality.value}")
        if geometry.density.ndim != 3:
            issues.append("geometry density must be 3D")
        if beam_model.result.fluence_elements.total_count < 1:
            issues.append("beam model has no fluence elements")
        if getattr(geometry, "ct_hu", None) is None:
            issues.append("mcsquare engine requires the CT (ct_hu) on the geometry bundle; rebuild the geometry to populate ct_grid_uri")
        ok, reason = self.driver(params).availability()
        if not ok:
            issues.append(f"MCsquare engine not available: {reason}")
        return issues

    # ----- inputs -------------------------------------------------------

    @staticmethod
    def _plan(beam_model: BeamModelBundle) -> ProtonPlan:
        plan = beam_model.plan
        if isinstance(plan, ProtonPlan):
            return plan
        try:
            return ProtonPlan.from_opentps(plan)
        except Exception as exc:
            raise EngineParamError(f"beam model plan is not a proton plan radiarch can read: {exc}") from exc

    @staticmethod
    def _grid(geometry: GeometryBundle):
        ct_hu = getattr(geometry, "ct_hu", None)
        if ct_hu is None:
            raise EngineUnavailableError("MCsquare requires the CT (ct_hu) on the geometry bundle; rebuild the geometry to populate ct_grid_uri.")
        ct_hu = np.asarray(ct_hu)
        if ct_hu.shape != tuple(np.asarray(geometry.density).shape):
            raise EngineParamError(f"ct_hu shape {ct_hu.shape} differs from the density grid {np.asarray(geometry.density).shape}")
        spacing = tuple(float(s) for s in geometry.spacing_mm)
        origin = getattr(geometry, "origin_mm", None)
        if origin is None:
            origin = getattr(geometry.result.grid_spec, "origin_mm", None) or (0.0, 0.0, 0.0)
        return ct_hu, spacing, tuple(float(o) for o in origin)

    @staticmethod
    def _scenario(plan: ProtonPlan, calibration: CalibrationTables, scenario: Optional[ScenarioSpec]):
        """Apply a robustness perturbation: isocenter shift on the plan, density scale on the tables."""
        if scenario is None:
            return plan, calibration
        if scenario.setup_shift_mm is not None:
            shift = np.asarray(scenario.setup_shift_mm, dtype=np.float64)
            if shift.shape != (3,):
                raise EngineParamError(f"setup_shift_mm must be a 3-vector, got shape {shift.shape}")
            plan = plan.shifted(shift)
        scale = 1.0
        if scenario.density_scale is not None:
            scale *= float(scenario.density_scale)
        if scenario.range_scale is not None:
            scale *= 1.0 / float(scenario.range_scale)   # longer range ⇔ lower density
        if scale != 1.0:
            calibration = calibration.scaled(scale)
        return plan, calibration

    # ----- compute_dose ------------------------------------------------

    def compute_dose(
        self,
        geometry: GeometryBundle,
        beam_model: BeamModelBundle,
        weights: np.ndarray,
        scenario: Optional[ScenarioSpec] = None,
        params: Optional[dict] = None,
    ) -> NominalDose:
        params = params or {}
        drv = self.driver(params)
        ok, reason = drv.availability()
        if not ok:
            raise EngineUnavailableError(f"MCsquare is not available: {reason}")
        expected = beam_model.result.fluence_elements.total_count
        weights = np.asarray(weights, dtype=np.float32)
        if weights.shape != (expected,):
            raise EngineParamError(f"weights shape {weights.shape} != ({expected},)")
        plan = self._plan(beam_model)
        if plan.n_spots != expected:
            raise EngineParamError(f"plan has {plan.n_spots} spots; beam model has {expected} fluence elements")
        ct_hu, spacing, origin = self._grid(geometry)
        plan, calibration = self._scenario(plan.with_spot_mus(weights), drv.calibration(), scenario)
        try:
            dose = drv.compute_dose(
                ct_hu, spacing, origin, plan,
                nb_primaries=float(params.get("nb_primaries", 1e4)),
                stat_uncertainty=float(params.get("stat_uncertainty", 0.0)),
                calibration=calibration,
            )
        except (EngineParamError, EngineUnavailableError):
            raise
        except Exception as exc:
            logger.exception("MCsquare dose computation failed")
            raise EngineRuntimeError(f"MCsquare failed: {exc}") from exc
        return NominalDose(dose=np.asarray(dose, dtype=np.float32))

    # ----- build_influence ---------------------------------------------

    def build_influence(
        self,
        geometry: GeometryBundle,
        beam_model: BeamModelBundle,
        scenario: Optional[ScenarioSpec] = None,
        params: Optional[dict] = None,
    ) -> InfluenceData:
        params = params or {}
        drv = self.driver(params)
        ok, reason = drv.availability()
        if not ok:
            raise EngineUnavailableError(f"MCsquare is not available: {reason}")
        plan = self._plan(beam_model)
        expected = beam_model.result.fluence_elements.total_count
        if plan.n_spots != expected:
            raise EngineParamError(f"plan has {plan.n_spots} spots; beam model has {expected} fluence elements")
        ct_hu, spacing, origin = self._grid(geometry)
        plan, calibration = self._scenario(plan, drv.calibration(), scenario)
        try:
            csr = drv.compute_beamlets(
                ct_hu, spacing, origin, plan,
                nb_primaries=float(params.get("nb_primaries", 1e4)),
                calibration=calibration,
            )
        except (EngineParamError, EngineUnavailableError):
            raise
        except Exception as exc:
            logger.exception("MCsquare beamlet computation failed")
            raise EngineRuntimeError(f"MCsquare beamlet failed: {exc}") from exc
        if csr.shape[1] != expected:
            raise EngineRuntimeError(f"MCsquare returned Dij with {csr.shape[1]} columns; beam model has {expected} fluence elements.")
        return InfluenceData(
            indptr=csr.indptr.astype(np.int64),
            indices=csr.indices.astype(np.int32),
            data=csr.data.astype(np.float32),
            n_voxels=int(csr.shape[0]),
            n_elements=int(csr.shape[1]),
        )

    # ----- apply_influence / compute_grad -------------------------------

    def apply_influence(self, influence: InfluenceData, weights: np.ndarray, grid_shape: tuple) -> NominalDose:
        """Standard CSR matvec: dose = Dij @ w, reshaped in C-order to the geometry grid."""
        from scipy.sparse import csr_matrix
        weights = np.asarray(weights, dtype=np.float32)
        if weights.shape != (influence.n_elements,):
            raise EngineParamError(f"weights shape {weights.shape} != ({influence.n_elements},)")
        if int(np.prod(grid_shape)) != influence.n_voxels:
            raise EngineParamError(f"grid_shape {grid_shape} does not match influence.n_voxels {influence.n_voxels}")
        csr = csr_matrix((influence.data, influence.indices, influence.indptr),
                         shape=(influence.n_voxels, influence.n_elements))
        return NominalDose(dose=np.asarray(csr @ weights).reshape(grid_shape).astype(np.float32))

    def compute_grad(self, geometry, beam_model, weights, dL_dDose, scenario=None, params=None):
        raise EngineUnavailableError(
            "mcsquare doesn't implement adjoint gradients. Build a Dij via build_influence() "
            "and compute the gradient as Dij.T @ dL_dDose in the optimizer."
        )


# Register on import — even when the engine binaries are missing, so the registry
# exposes the engine's existence and the health endpoint says why it is down.
register_engine(MCsquareEngine())

__all__ = ["MCsquareEngine"]
