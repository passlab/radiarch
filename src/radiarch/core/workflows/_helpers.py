"""Shared helpers for the legacy ``/plans`` workflows.

The workflows are thin scripts over the services (geometry → beam model →
dose / optimization → evaluation) that keep the original ``/plans`` API and
its QA summary shape. Nothing here talks to an engine directly; the services
do, through radiarch's own drivers.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import SimpleITK as sitk
from loguru import logger

from ...config import get_settings
from ...models.beam_model import BeamModelBuildRequest, BeamModelResult, BeamSetSpec, BeamSpec, DeliveryParams, Modality
from ...models.common import NOT_FOR_CLINICAL_USE
from ...models.dose import EngineSpec, ScenarioSpec
from ...models.geometry import GeometryBuildRequest, GeometryResult, GridSpec, HUDensityModel, PatientRef
from ...models.optimization import ObjectiveSpec
from ...models.plan import PlanDetail, RobustnessConfig


class PlannerError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

def setup_sim_dir(plan_id: str) -> str:
    """Create and return the output directory for a plan."""
    settings = get_settings()
    sim_dir = os.path.abspath(os.path.join(settings.artifact_dir, "simulations", plan_id))
    os.makedirs(sim_dir, exist_ok=True)
    return sim_dir


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def build_geometry(plan: PlanDetail, hu_model: HUDensityModel = HUDensityModel.stoichiometric) -> GeometryResult:
    """The geometry of the plan's study (PACS when configured, else the data root),
    on the plan's scoring grid (``scoring_spacing_mm``; empty = the CT grid)."""
    from ...services.geometry import GeometryService

    spacing = [float(v) for v in (plan.scoring_spacing_mm or [])]
    grid = GridSpec(spacing_mm=(spacing[0], spacing[1], spacing[2])) if len(spacing) == 3 and min(spacing) > 0 else None
    request = GeometryBuildRequest(
        patient_ref=PatientRef(dicom_study_uid=plan.study_instance_uid, rtstruct_uid=plan.segmentation_uid or None),
        hu_to_density_model=hu_model, grid_spec=grid,
    )
    return GeometryService().build(request)


def build_gantry_angles(beam_count: int) -> list:
    """Evenly spaced gantry angles for ``beam_count`` beams."""
    if beam_count > 1:
        return [i * (360.0 / beam_count) for i in range(beam_count)]
    return [0.0]


def build_beam_model(plan: PlanDetail, geometry: GeometryResult, modality: Modality,
                     gantry_angles: Optional[Sequence[float]] = None,
                     delivery: Optional[DeliveryParams] = None) -> BeamModelResult:
    from ...services.beam_model import BeamModelService

    angles = list(gantry_angles) if gantry_angles is not None else build_gantry_angles(plan.beam_count)
    beam_set = BeamSetSpec(       # no isocenter: the builder places it on the target's centre of mass
        beams=[BeamSpec(beam_id=f"B{i + 1}", gantry_deg=float(g) % 360.0) for i, g in enumerate(angles)],
    )
    if delivery is None:
        delivery = DeliveryParams(spot_spacing_mm=plan.spot_spacing_mm, layer_spacing_mm=plan.layer_spacing_mm)
    return BeamModelService().build(BeamModelBuildRequest(
        plan_id=plan.id, geometry_id=geometry.geometry_id, modality=modality, beam_set=beam_set, delivery_params=delivery,
    ))


def target_of(geometry: GeometryResult) -> Tuple[str, int]:
    from ...services.geometry_bundle import target_structure

    chosen = target_structure(geometry.structure_index)
    if chosen is None:
        raise PlannerError(
            f"no target structure (PTV/GTV/CTV or a structure named Target) in the geometry: {sorted(geometry.structure_index)}"
        )
    return chosen


def mcsquare_engine(nb_primaries: float) -> EngineSpec:
    return EngineSpec(name="mcsquare", params={"nb_primaries": float(nb_primaries)})


# ---------------------------------------------------------------------------
# Objectives, solvers, robustness
# ---------------------------------------------------------------------------

_SOLVER_ALIASES = {
    "scipy_l-bfgs-b": "L-BFGS-B", "scipy-lbfgs": "L-BFGS-B", "lbfgs": "L-BFGS-B", "l-bfgs-b": "L-BFGS-B",
    "adam": "Adam", "projectedgradient": "ProjectedGradient", "gradient": "ProjectedGradient", "fista": "ProjectedGradient",
}


def solver_method(name: str) -> str:
    """Map the legacy optimizer names (OpenTPS spellings included) onto radiarch's solvers."""
    from ...services.optimization_solvers import get_solver

    method = _SOLVER_ALIASES.get(str(name).strip().lower(), str(name))
    try:
        get_solver(method)
    except Exception as exc:
        raise PlannerError(f"unknown optimization_method {name!r}: {exc}") from exc
    return method


def build_objectives(plan: PlanDetail, geometry: GeometryResult, target_name: str) -> List[ObjectiveSpec]:
    """The plan's objectives on structures the geometry has; a uniform target dose when it has none."""
    objectives: List[ObjectiveSpec] = []
    names = {n.strip().lower(): n for n in geometry.structure_index}
    for obj in plan.objectives or []:
        name = names.get(obj.structure_name.strip().lower())
        if name is None:
            logger.warning("Objective ROI %s not found in the geometry; skipped", obj.structure_name)
            continue
        kind = obj.objective_type.value if hasattr(obj.objective_type, "value") else str(obj.objective_type)
        objectives.append(ObjectiveSpec(
            type=kind, structure_name=name, dose_gy=float(obj.dose_gy), weight=float(obj.weight),
            volume_fraction=obj.volume_fraction,
        ))
    if not objectives:
        objectives.append(ObjectiveSpec(type="DUniform", structure_name=target_name, dose_gy=float(plan.prescription_gy), weight=100.0))
    return objectives


_STRATEGIES = ("REDUCED_SET", "ALL", "RANDOM")


def robust_scenarios(cfg: Optional[RobustnessConfig]) -> List[ScenarioSpec]:
    """Setup and range scenarios from a :class:`RobustnessConfig`.

    * ``REDUCED_SET``: the six axis-aligned setup shifts by the systematic
      error, plus the two range scalings (±range error) — 8 scenarios.
    * ``ALL``: every axis shift combined with each range state (nominal,
      under, over), plus the range-only pair — 20 scenarios.
    * ``RANDOM``: ``num_scenarios`` draws with Gaussian setup shifts (σ =
      systematic error per axis) and range scaling (σ = range error),
      from a fixed seed.

    The nominal scenario is added by the optimizer itself. The random
    per-fraction setup error of the configuration has no scenario
    representation and is ignored (reported in the summary).
    """
    if cfg is None:
        cfg = RobustnessConfig()
    strategy = str(cfg.selection_strategy).strip().upper()
    if strategy not in _STRATEGIES:
        raise PlannerError(f"Unknown robustness selection_strategy {cfg.selection_strategy!r}; expected one of {list(_STRATEGIES)}")
    sys_err = [float(v) for v in cfg.setup_systematic_error_mm][:3] + [0.0] * (3 - len(cfg.setup_systematic_error_mm))
    r = float(cfg.range_systematic_error_pct) / 100.0
    axes = "xyz"

    def shift(axis: int, sign: int) -> Tuple[float, float, float]:
        v = [0.0, 0.0, 0.0]
        v[axis] = sign * sys_err[axis]
        return (v[0], v[1], v[2])

    scenarios: List[ScenarioSpec] = []
    if strategy == "RANDOM":
        rng = np.random.default_rng(20261021)
        for i in range(int(cfg.num_scenarios)):
            s = tuple(float(rng.normal(0.0, e)) if e > 0 else 0.0 for e in sys_err)
            scale = float(1.0 + rng.normal(0.0, r)) if r > 0 else None
            scenarios.append(ScenarioSpec(name=f"random{i + 1}", setup_shift_mm=s if any(s) else None, range_scale=scale))
        return scenarios

    range_states: List[Optional[float]] = [None] if strategy == "REDUCED_SET" else [None, 1.0 - r, 1.0 + r]
    for axis in range(3):
        if sys_err[axis] <= 0:
            continue
        for sign in (+1, -1):
            for scale in range_states:
                if scale is not None and r <= 0:
                    continue
                tag = f"{axes[axis]}{'+' if sign > 0 else '-'}"
                if scale is not None:
                    tag += "_range" + ("+" if scale > 1 else "-")
                scenarios.append(ScenarioSpec(name=tag, setup_shift_mm=shift(axis, sign), range_scale=scale))
    if r > 0:
        scenarios.append(ScenarioSpec(name="range-", range_scale=1.0 - r))
        scenarios.append(ScenarioSpec(name="range+", range_scale=1.0 + r))
    return scenarios


# ---------------------------------------------------------------------------
# Results: dose volumes, DVH, RTDOSE
# ---------------------------------------------------------------------------

def read_dose(uri: str) -> np.ndarray:
    """A persisted dose volume as (z, y, x) float32 Gy."""
    path = uri[len("file://"):] if uri.startswith("file://") else uri
    return sitk.GetArrayFromImage(sitk.ReadImage(path)).astype(np.float32)


def read_masks(geometry: GeometryResult) -> np.ndarray:
    return sitk.GetArrayFromImage(sitk.ReadImage(geometry.structure_masks_uri)).astype(np.uint16)


def compute_dvh(dose_zyx: np.ndarray, mask_zyx: np.ndarray, roi_name: str) -> Dict[str, Any]:
    """The cumulative DVH of one structure in the legacy summary shape."""
    from ...services.dvh import cumulative_dvh

    dose = np.asarray(dose_zyx, dtype=np.float32)
    mask = np.asarray(mask_zyx, dtype=bool)
    if mask.shape != dose.shape:
        logger.warning("DVH mask shape %s != dose shape %s — skipping", mask.shape, dose.shape)
        return {}
    target_doses = dose[mask]
    if target_doses.size == 0:
        return {}
    bins, vol = cumulative_dvh(dose, mask, 100)
    return {
        "roiName": roi_name,
        "doseGy": [round(float(d), 4) for d in bins],
        "volumePct": [round(float(v), 2) for v in vol],
        "minDoseGy": round(float(target_doses.min()), 4),
        "maxDoseGy": round(float(target_doses.max()), 4),
        "meanDoseGy": round(float(target_doses.mean()), 4),
    }


def dose_image(dose_zyx: np.ndarray, geometry: GeometryResult) -> SimpleNamespace:
    """The ``(z, y, x)`` dose with its grid, as :func:`export_rtdose` takes it."""
    spacing = np.asarray(geometry.grid_spec.spacing_mm, dtype=float)
    origin = np.asarray(geometry.grid_spec.origin_mm or (0.0, 0.0, 0.0), dtype=float)
    return SimpleNamespace(imageArray=np.asarray(dose_zyx, dtype=np.float32), spacing=spacing, origin=origin)


def ct_provenance(geometry: GeometryResult) -> SimpleNamespace:
    meta = geometry.ct_metadata
    return SimpleNamespace(
        frameOfReferenceUID=geometry.frame_of_reference_uid or "",
        patientName=getattr(meta, "patient_name", "ANONYMOUS") or "ANONYMOUS",
        patientID="UNKNOWN",
        studyInstanceUID=getattr(meta, "study_instance_uid", None),
    )


def export_rtdose(dose_image, ct, output_path: str, rbe: float = 1.0) -> None:
    """Write a dose volume as a DICOM RTDOSE file.

    ``dose_image`` has ``imageArray`` in ``(z, y, x)`` order, ``spacing`` and
    ``origin`` in ``(x, y, z)``; ``ct`` carries ``frameOfReferenceUID``,
    ``patientName``, ``patientID`` and ``studyInstanceUID``. With ``rbe`` other
    than 1 the dose is an RBE-weighted dose (``DoseType EFFECTIVE``). Every
    file says it is not for clinical use (R0).
    """
    import pydicom
    from pydicom.dataset import FileDataset
    from pydicom.uid import ExplicitVRLittleEndian
    import pydicom.uid

    file_meta = pydicom.Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.2"
    file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    # Explicit VR little endian: the transfer syntax in file_meta decides the
    # encoding (pydicom 3); implicit VR would make private tags read back as UN.
    ds = FileDataset(output_path, {}, file_meta=file_meta, preamble=b"\x00" * 128)

    ds.PatientName = getattr(ct, "patientName", "ANONYMOUS") or "ANONYMOUS"
    ds.PatientID = getattr(ct, "patientID", "UNKNOWN") or "UNKNOWN"
    ds.StudyInstanceUID = getattr(ct, "studyInstanceUID", None) or pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.Modality = "RTDOSE"
    ds.FrameOfReferenceUID = getattr(ct, "frameOfReferenceUID", "") or pydicom.uid.generate_uid()
    # Intended-use statement in the public text attributes and in a private
    # block, so it survives tools that rewrite descriptions.
    ds.SeriesDescription = "RESEARCH - " + NOT_FOR_CLINICAL_USE
    ds.DoseComment = NOT_FOR_CLINICAL_USE
    block = ds.private_block(0x7779, "RADIARCH", create=True)
    block.add_new(0x01, "LO", NOT_FOR_CLINICAL_USE)
    ds.Manufacturer = "Radiarch"
    ds.DoseUnits = "GY"
    ds.DoseType = "EFFECTIVE" if abs(float(rbe) - 1.0) > 1e-9 else "PHYSICAL"
    if abs(float(rbe) - 1.0) > 1e-9:
        ds.DoseComment = f"{NOT_FOR_CLINICAL_USE}; RBE {float(rbe):g}, Gy(RBE)"
    ds.DoseSummationType = "PLAN"

    dose_array = np.asarray(dose_image.imageArray, dtype=np.float32)
    ds.Rows = dose_array.shape[1]
    ds.Columns = dose_array.shape[2]
    ds.NumberOfFrames = dose_array.shape[0]
    ds.PixelSpacing = [float(dose_image.spacing[1]), float(dose_image.spacing[0])]
    ds.ImagePositionPatient = [float(dose_image.origin[0]), float(dose_image.origin[1]), float(dose_image.origin[2])]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.GridFrameOffsetVector = [float(i * dose_image.spacing[2]) for i in range(dose_array.shape[0])]

    dose_max = float(dose_array.max())
    if dose_max > 0:
        dose_grid_scaling = dose_max / (2**31 - 1)
        scaled = (dose_array / dose_grid_scaling).astype(np.uint32)
    else:
        dose_grid_scaling = 1.0
        scaled = np.zeros_like(dose_array, dtype=np.uint32)

    ds.DoseGridScaling = str(dose_grid_scaling)
    ds.BitsAllocated = 32
    ds.BitsStored = 32
    ds.HighBit = 31
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PixelData = scaled.tobytes()
    ds.save_as(output_path, enforce_file_format=True)
    logger.info("RTDOSE saved to %s", output_path)


def dose_summary(dose_zyx: np.ndarray) -> Dict[str, float]:
    d = np.asarray(dose_zyx, dtype=np.float32)
    return {"maxDose": float(d.max()), "meanDose": float(d.mean())}


__all__ = [
    "PlannerError", "setup_sim_dir", "build_geometry", "build_gantry_angles", "build_beam_model", "target_of",
    "mcsquare_engine", "solver_method", "build_objectives", "robust_scenarios", "read_dose", "read_masks",
    "compute_dvh", "dose_image", "ct_provenance", "export_rtdose", "dose_summary",
]
