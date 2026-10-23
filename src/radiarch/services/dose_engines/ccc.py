"""Collapsed-cone photon dose engine: the WiscPlan ``CCC_DoseEngine`` binary
driven through :mod:`.ccc_driver` (roadmap R1).

The engine computes, per beamlet, the dose per unit beamlet weight. Beamlet
weights are metersets (each beamlet carries its segment's MU; fluence per
beamlet scales with its area, so a uniform field gives the same dose at any
beamlet size). An **output factor** turns the engine's arbitrary units into
Gy: it is chosen so that a 10 cm × 10 cm open field at 100 cm SSD delivers
1 cGy per MU at d_max on the central axis in water, the usual reference
calibration. The factor is computed once per kernel set by running the
engine on a water phantom (:class:`CCCCalibration`) and cached under the
artifact directory; ``params["output_factor_gy_per_unit"]`` overrides it.

Limits (see ADR 0001, ADR 0005 and docs/reports/tps-evaluation-and-roadmap.md): generic
6 MV kernels only, no linac head model (no output factors, head scatter,
MLC transmission or tongue-and-groove), no published validation. Research
use only.

Scenarios: ``setup_shift_mm`` moves the isocenter by the shift (the same
convention as the MCsquare engine), ``density_scale`` scales the density
grid, ``range_scale`` has no meaning for photons and is ignored with a
warning.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import scipy.sparse as sp
from loguru import logger

from ...models.dose import ScenarioSpec
from ...models.photon_plan import PhotonPlan
from .ccc_driver import CCCDriver, beamlet_geometry_from_plan, delivered_beamlet_geometry
from .protocol import (
    BeamModelBundle,
    EngineParamError,
    EngineRuntimeError,
    EngineUnavailableError,
    GeometryBundle,
    InfluenceData,
    NominalDose,
)
from .registry import register_engine


def _settings():
    from ...config import get_settings  # lazy: the registry imports without settings
    return get_settings()


# ---------------------------------------------------------------------------
# Output calibration
# ---------------------------------------------------------------------------

@dataclass
class CalibrationRecord:
    factor_gy_per_unit: float
    dmax_mm: float
    spacing_mm: float
    kernel_fingerprint: str
    engine_version: str
    created_at: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "CalibrationRecord":
        return cls(**json.loads(text))


class CCCCalibration:
    """Reference-field calibration of the engine's output.

    Water phantom 30 cm wide and 25 cm deep, surface at the isocenter plane
    (SSD = SAD = 100 cm), one 10 cm × 10 cm open field from gantry 0 (5 mm
    beamlets, 10 mm leaves, unit weight). The output factor maps the
    central-axis maximum to 1 cGy per MU.
    """

    REFERENCE_FIELD_MM = 100.0
    DOSE_AT_DMAX_GY_PER_MU = 0.01
    PHANTOM_HALF_WIDTH_MM = 150.0
    PHANTOM_DEPTH_MM = 250.0
    BEAMLET_MM = 5.0
    LEAF_MM = 10.0
    DMAX_PLAUSIBLE_MM = (5.0, 40.0)

    _memory: Dict[str, CalibrationRecord] = {}

    def __init__(self, driver: CCCDriver, cache_dir: Optional[Path], spacing_mm: float, engine_version: str) -> None:
        self.driver = driver
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.spacing_mm = float(spacing_mm)
        self.engine_version = engine_version

    @property
    def key(self) -> str:
        scatter = "" if self.driver.scatter_key == "shipped" else f"-{self.driver.scatter_key}"
        return f"{self.driver.kernel_fingerprint()}-{self.spacing_mm:g}mm-v{self.engine_version}{scatter}"

    def _cache_path(self) -> Optional[Path]:
        return (self.cache_dir / f"calibration-{self.key}.json") if self.cache_dir else None

    def record(self) -> CalibrationRecord:
        key = self.key
        if key in self._memory:
            return self._memory[key]
        path = self._cache_path()
        if path is not None and path.is_file():
            try:
                rec = CalibrationRecord.from_json(path.read_text())
                self._memory[key] = rec
                return rec
            except Exception as exc:  # pragma: no cover — corrupt cache
                logger.warning("Ignoring unreadable CCC calibration {}: {}", path, exc)
        rec = self.compute()
        self._memory[key] = rec
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rec.to_json())
        return rec

    def phantom(self) -> Tuple[np.ndarray, Tuple[float, float, float], Tuple[float, float, float]]:
        """Water box as ``(density_zyx, spacing_mm, origin_mm)``: lateral voxel
        centres span ±half width with one centred on the axis; depth voxels
        start half a voxel below the surface at y = 0."""
        s = self.spacing_mm
        n_lat = 2 * int(round(self.PHANTOM_HALF_WIDTH_MM / s)) + 1
        n_depth = int(round(self.PHANTOM_DEPTH_MM / s))
        half = (n_lat - 1) / 2.0 * s
        density = np.ones((n_lat, n_depth, n_lat), dtype=np.float32)
        return density, (s, s, s), (-half, s / 2.0, -half)

    def compute(self) -> CalibrationRecord:
        from ..photon_beamlets import build_photon_plan

        density, spacing, origin = self.phantom()
        h = self.REFERENCE_FIELD_MM / 2.0
        plan = build_photon_plan(
            beams=[(0.0, 0.0)], jaw_x_mm=(-h, h), jaw_y_mm=(-h, h),
            leaf_width_mm=self.LEAF_MM, mu_per_beam=1.0,
            beamlet_spacing_mm=(self.BEAMLET_MM, self.BEAMLET_MM), name="ccc-reference-field",
        )
        logger.info("CCC calibration: reference 10×10 field on a water phantom at {} mm", self.spacing_mm)
        dij = self.driver.run(density, spacing, origin, (0.0, 0.0, 0.0), beamlet_geometry_from_plan(plan))
        dose = np.asarray(dij @ np.ones(dij.shape[1], dtype=np.float32)).reshape(density.shape)
        centre = (density.shape[0] - 1) // 2
        cax = dose[centre, :, centre]
        k = int(np.argmax(cax))
        dmax_mm = origin[1] + k * self.spacing_mm
        peak = float(cax[k])
        if peak <= 0 or not (self.DMAX_PLAUSIBLE_MM[0] <= dmax_mm <= self.DMAX_PLAUSIBLE_MM[1]):
            raise EngineRuntimeError(
                f"CCC calibration failed: central-axis maximum {peak} at {dmax_mm} mm depth "
                "is not a 6 MV build-up curve; check the engine binary and kernels."
            )
        rec = CalibrationRecord(
            factor_gy_per_unit=self.DOSE_AT_DMAX_GY_PER_MU / peak,
            dmax_mm=float(dmax_mm),
            spacing_mm=self.spacing_mm,
            kernel_fingerprint=self.driver.kernel_fingerprint(),
            engine_version=self.engine_version,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info("CCC calibration: d_max {:.1f} mm, output factor {:.4e} Gy per engine unit", rec.dmax_mm, rec.factor_gy_per_unit)
        return rec


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class CCCEngine:
    """Photon dose engine on the WiscPlan collapsed-cone binary."""

    name: str = "ccc"
    version: str = "1.1.0"   # 1.1.0: IEC gantry, couch and collimator rotation (R8); 1.0.0 mirrored lateral beams
    modalities: List[str] = field(default_factory=lambda: ["PHOTON_IMRT"])
    test_only: bool = False

    # ----- configuration ------------------------------------------------

    def driver(self, params: Optional[dict] = None) -> CCCDriver:
        """The driver for a run. ``params["scatter"]`` is ``"shipped"`` (the binary's constants:
        scatter truncated at ~2 cm, fast; the default for Dij) or ``"full"`` (0.01 % cutoff, 10 cm
        mask; for studies of the truncation: R7 found it no closer to Monte Carlo with these kernels); ``params["dose_cutoff"]`` and ``params["rsafe_cm"]``
        set the two constants directly. ``RADIARCH_CCC_SCATTER`` is the default."""
        s = _settings()
        p = params or {}
        n_jobs = int(p.get("n_jobs", s.ccc_n_jobs))
        scatter = str(p.get("scatter", getattr(s, "ccc_scatter", "shipped") or "shipped")).lower()
        if scatter not in ("shipped", "full"):
            raise EngineParamError(f"ccc scatter must be 'shipped' or 'full', not {scatter!r}")
        cutoff = p.get("dose_cutoff", CCCDriver.FULL_SCATTER_DOSE_CUTOFF if scatter == "full" else None)
        rsafe = p.get("rsafe_cm", CCCDriver.FULL_SCATTER_RSAFE_CM if scatter == "full" else None)
        return CCCDriver(engine_dir=Path(s.ccc_engine_dir) if s.ccc_engine_dir else None, n_jobs=n_jobs,
                         dose_cutoff=cutoff, rsafe_cm=rsafe)

    def calibration(self, params: Optional[dict] = None) -> CCCCalibration:
        s = _settings()
        spacing = float((params or {}).get("calibration_spacing_mm", s.ccc_calibration_spacing_mm))
        return CCCCalibration(self.driver(params), Path(s.artifact_dir) / "ccc", spacing, self.version)

    def output_factor(self, params: Optional[dict] = None) -> float:
        """Gy per engine unit per unit weight (MU)."""
        override = (params or {}).get("output_factor_gy_per_unit")
        if override is not None:
            return float(override)
        return self.calibration(params).record().factor_gy_per_unit

    # ----- health / validation ------------------------------------------

    def health(self) -> dict:
        drv = self.driver()
        ok, reason = drv.availability()
        diag: Dict[str, Any] = {"binary": str(drv.binary), "kernel_dir": str(drv.kernel_dir), "reason": reason}
        if ok:
            try:
                cal = self.calibration()
                p = cal._cache_path()
                diag["calibration_cached"] = bool(p and p.is_file())
                diag["kernel_fingerprint"] = drv.kernel_fingerprint()
            except Exception as exc:  # pragma: no cover
                diag["calibration_error"] = str(exc)
        return {
            "name": self.name, "version": self.version, "modalities": list(self.modalities),
            "available": ok, "test_only": False, "diagnostics": diag,
        }

    def validate(self, geometry: GeometryBundle, beam_model: BeamModelBundle, params: dict) -> List[str]:
        issues: List[str] = []
        if beam_model.result.modality.value != "PHOTON_IMRT":
            issues.append(f"ccc engine requires PHOTON_IMRT, got {beam_model.result.modality.value}")
        if geometry.density is None or np.asarray(geometry.density).ndim != 3:
            issues.append("geometry density must be 3D")
        if beam_model.result.fluence_elements.total_count < 1:
            issues.append("beam model has no fluence elements")
        if not isinstance(beam_model.plan, PhotonPlan):
            issues.append(
                "beam model plan is not a radiarch PhotonPlan (built before R1); rebuild the beam model"
            )
        if self._origin(geometry) is None:
            issues.append("geometry has no grid origin; the engine cannot place the isocenter")
        ok, reason = self.driver(params).availability()
        if not ok:
            issues.append(reason)
        return issues

    # ----- the shared core ----------------------------------------------

    def influence_matrix(
        self,
        density_zyx: np.ndarray,
        spacing_mm: Sequence[float],
        origin_mm: Sequence[float],
        plan: PhotonPlan,
        scenario: Optional[ScenarioSpec] = None,
        params: Optional[dict] = None,
    ) -> sp.csr_matrix:
        """``(n_voxels, n_beamlets)`` CSR in Gy per unit weight, rows in
        ``(z, y, x)`` C-order, columns in the plan's beamlet order."""
        density = np.asarray(density_zyx, dtype=np.float32)
        iso = np.asarray(plan.isocenter_mm, dtype=np.float64)
        if scenario is not None:
            if scenario.setup_shift_mm is not None:
                iso = iso + np.asarray(scenario.setup_shift_mm, dtype=np.float64)
            if scenario.density_scale is not None:
                density = density * np.float32(scenario.density_scale)
            if scenario.range_scale is not None:
                logger.warning("ccc: range_scale {} ignored (no meaning for photons)", scenario.range_scale)
        beamlets = beamlet_geometry_from_plan(plan)
        if len(beamlets) == 0:
            raise EngineParamError("photon plan has no beamlets")
        dij = self.driver(params).run(density, spacing_mm, origin_mm, tuple(iso), beamlets)
        dij = dij.tocsr().astype(np.float32)
        dij.data *= np.float32(self.output_factor(params))
        return dij

    def compute_plan_dose(
        self,
        density_zyx: np.ndarray,
        spacing_mm: Sequence[float],
        origin_mm: Sequence[float],
        plan: PhotonPlan,
        weights: Optional[np.ndarray] = None,
        scenario: Optional[ScenarioSpec] = None,
        params: Optional[dict] = None,
    ) -> np.ndarray:
        """Dose in Gy on the density grid; ``weights`` default to the plan's metersets."""
        dij = self.influence_matrix(density_zyx, spacing_mm, origin_mm, plan, scenario, params)
        w = plan.beamlet_mu() if weights is None else np.asarray(weights, dtype=np.float32)
        if w.shape != (dij.shape[1],):
            raise EngineParamError(f"weights shape {w.shape} != ({dij.shape[1]},)")
        return np.asarray(dij @ w.astype(np.float32)).reshape(np.asarray(density_zyx).shape).astype(np.float32)

    def compute_delivered_dose(
        self,
        density_zyx: np.ndarray,
        spacing_mm: Sequence[float],
        origin_mm: Sequence[float],
        plan: PhotonPlan,
        params: Optional[dict] = None,
    ) -> np.ndarray:
        """Dose in Gy of the plan as delivered: every aperture through its coverage beamlets, weighted by
        segment MU and open fraction, so that apertures no wider than one beamlet (sliding-window arcs)
        are dosed. Use it to recompute a sequenced plan; :meth:`compute_plan_dose` keeps the optimizer's columns."""
        beamlets, mu = delivered_beamlet_geometry(plan)
        if len(beamlets) == 0:
            raise EngineParamError("photon plan has no open apertures")
        dij = self.driver(params).run(np.asarray(density_zyx, dtype=np.float32), spacing_mm, origin_mm,
                                      tuple(np.asarray(plan.isocenter_mm, dtype=np.float64)), beamlets)
        dose = dij.tocsr().astype(np.float32) @ mu.astype(np.float32)
        return (np.asarray(dose) * np.float32(self.output_factor(params))).reshape(np.asarray(density_zyx).shape).astype(np.float32)

    # ----- DoseEnginePlugin -------------------------------------------------

    @staticmethod
    def _origin(geometry: GeometryBundle) -> Optional[Tuple[float, float, float]]:
        origin = getattr(geometry, "origin_mm", None)
        if origin is None:
            try:
                origin = geometry.result.grid_spec.origin_mm
            except Exception:
                origin = None
        return None if origin is None else tuple(float(v) for v in origin)

    def _plan(self, beam_model: BeamModelBundle) -> PhotonPlan:
        plan = beam_model.plan
        if not isinstance(plan, PhotonPlan):
            raise EngineParamError(
                "beam model plan is not a radiarch PhotonPlan (built before R1); rebuild the beam model"
            )
        return plan

    def build_influence(self, geometry, beam_model, scenario=None, params=None) -> InfluenceData:
        plan = self._plan(beam_model)
        origin = self._origin(geometry)
        if origin is None:
            raise EngineParamError("geometry has no grid origin; the engine cannot place the isocenter")
        expected = beam_model.result.fluence_elements.total_count
        if plan.n_beamlets != expected:
            raise EngineParamError(
                f"plan has {plan.n_beamlets} beamlets but the beam model records {expected} fluence elements"
            )
        csr = self.influence_matrix(geometry.density, geometry.spacing_mm, origin, plan, scenario, params)
        return InfluenceData(
            indptr=csr.indptr.astype(np.int64),
            indices=csr.indices.astype(np.int32),
            data=csr.data.astype(np.float32),
            n_voxels=int(csr.shape[0]),
            n_elements=int(csr.shape[1]),
        )

    def compute_dose(self, geometry, beam_model, weights, scenario=None, params=None) -> NominalDose:
        expected = beam_model.result.fluence_elements.total_count
        weights = np.asarray(weights, dtype=np.float32)
        if weights.shape != (expected,):
            raise EngineParamError(f"weights shape {weights.shape} != ({expected},)")
        influence = self.build_influence(geometry, beam_model, scenario, params)
        return self.apply_influence(influence, weights, tuple(np.asarray(geometry.density).shape))

    def apply_influence(self, influence: InfluenceData, weights: np.ndarray, grid_shape: tuple) -> NominalDose:
        weights = np.asarray(weights, dtype=np.float32)
        if weights.shape != (influence.n_elements,):
            raise EngineParamError(f"weights shape {weights.shape} != ({influence.n_elements},)")
        if int(np.prod(grid_shape)) != influence.n_voxels:
            raise EngineParamError(f"grid_shape {grid_shape} does not match influence.n_voxels {influence.n_voxels}")
        csr = sp.csr_matrix(
            (influence.data, influence.indices, influence.indptr),
            shape=(influence.n_voxels, influence.n_elements),
        )
        dose = np.asarray(csr @ weights).reshape(grid_shape).astype(np.float32)
        return NominalDose(dose=dose)

    def compute_grad(self, geometry, beam_model, weights, dL_dDose, scenario=None, params=None):
        raise EngineUnavailableError(
            "ccc doesn't implement adjoint gradients. Build a Dij via build_influence() "
            "and compute the gradient as Dij.T @ dL_dDose in the optimizer."
        )


register_engine(CCCEngine())


__all__ = ["CCCEngine", "CCCCalibration", "CalibrationRecord"]
