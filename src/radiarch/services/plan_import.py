"""Import a DICOM RT Plan as a beam model (roadmap R2).

A beam model built by the Beam Model Service comes from a geometry and a beam
set radiarch chose; an imported one comes from a plan somebody else made. Both
end up in the same store, with the same :class:`BeamModelResult` shape, so the
Dose, Optimization and Evaluation services treat them alike. The imported
model additionally carries the plan's own metersets per fluence element
(``plan_weights_uri``): those are the weights a dose *recalculation* uses, and
``POST /dose/recalculate`` reads them.

The plan's frame of reference must be the geometry's: a plan computed on
another CT (or on a CT registered to this one) is refused unless the caller
says ``strict_frame_of_reference=False``, which is the registration work of
roadmap R9.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
from loguru import logger

from ..dicom.rtplan import read_rtplan
from ..models.beam_model import BeamModelResult, FluenceElementSet, Modality, PerBeamElements
from ..models.geometry import GeometryResult
from ..models.photon_plan import PhotonPlan
from ..models.proton_plan import ProtonPlan
from .beam_persistence import BeamModelStore

PLAN_WEIGHTS_FILENAME = "plan_weights.npy"


class PlanImportError(ValueError):
    pass


@dataclass
class ImportedPlan:
    beam_model: BeamModelResult
    plan: Union[PhotonPlan, ProtonPlan]
    weights: np.ndarray
    reused: bool = False


def fluence_elements_of(plan: Union[PhotonPlan, ProtonPlan]) -> FluenceElementSet:
    """The fluence-element bookkeeping the services expect, from a plan model."""
    per_beam: List[PerBeamElements] = []
    if isinstance(plan, PhotonPlan):
        for beam in plan.beams:
            per_beam.append(PerBeamElements(beam_id=beam.beam_id, element_count=beam.n_beamlets,
                                            active_beamlets=beam.n_beamlets))
        return FluenceElementSet(total_count=plan.n_beamlets, per_beam=per_beam)
    for beam in plan.beams:
        per_beam.append(PerBeamElements(
            beam_id=beam.beam_id or beam.name or "beam", element_count=beam.n_spots,
            energy_layers=[layer.energy_mev for layer in beam.layers],
            spots_per_layer=[layer.n_spots for layer in beam.layers],
        ))
    return FluenceElementSet(total_count=plan.n_spots, per_beam=per_beam)


def plan_weights(plan: Union[PhotonPlan, ProtonPlan]) -> np.ndarray:
    """The plan's own metersets per fluence element, in Dij column order."""
    if isinstance(plan, PhotonPlan):
        return np.asarray(plan.beamlet_mu(), dtype=np.float32)
    return np.asarray(plan.spot_mus, dtype=np.float32)


def check_frame_of_reference(plan: Union[PhotonPlan, ProtonPlan], geometry: GeometryResult, strict: bool = True) -> Optional[str]:
    """Return a warning (or raise when strict) if the plan and the geometry live in different frames."""
    plan_for = plan.dicom.frame_of_reference_uid if plan.dicom else ""
    geom_for = str(getattr(geometry, "frame_of_reference_uid", "") or "")
    if plan_for and geom_for and plan_for != geom_for:
        msg = (f"plan frame of reference {plan_for} differs from the geometry's {geom_for}; "
               "a plan computed on another CT needs a registration (roadmap R9)")
        if strict:
            raise PlanImportError(msg)
        return msg
    return None


def isocenter_inside(plan: Union[PhotonPlan, ProtonPlan], geometry: GeometryResult) -> bool:
    grid = geometry.grid_spec
    if grid.origin_mm is None or grid.size is None:
        return True
    lo = np.asarray(grid.origin_mm, dtype=float) - np.asarray(grid.spacing_mm) / 2.0
    hi = lo + np.asarray(grid.size, dtype=float) * np.asarray(grid.spacing_mm)
    isos = [b.isocenter_mm for b in plan.beams]
    return all(np.all((np.asarray(i) >= lo) & (np.asarray(i) <= hi)) for i in isos)


def import_rtplan(source: Union[str, Path], geometry: GeometryResult, store: BeamModelStore, *,
                  machine_model_id: str = "default", beamlet_spacing_mm: Tuple[float, float] = (5.0, 5.0),
                  strict_frame_of_reference: bool = True) -> ImportedPlan:
    """Read ``source`` (an RT Plan or RT Ion Plan file) and store it as a beam model of ``geometry``."""
    plan = read_rtplan(source, beamlet_spacing_mm)
    warning = check_frame_of_reference(plan, geometry, strict_frame_of_reference)
    if warning:
        logger.warning(warning)
    if not isocenter_inside(plan, geometry):
        logger.warning("imported plan {}: an isocenter lies outside the geometry grid", plan.name)

    modality = Modality.photon_imrt if isinstance(plan, PhotonPlan) else Modality.proton_pbs
    weights = plan_weights(plan)
    fluence = fluence_elements_of(plan)
    if weights.shape != (fluence.total_count,):
        raise PlanImportError(f"plan has {weights.shape[0]} metersets for {fluence.total_count} fluence elements")

    digest = hashlib.sha256()
    digest.update(b"rtplan-import|")
    digest.update(geometry.geometry_id.encode())
    digest.update(b"|" + machine_model_id.encode() + b"|")
    digest.update(plan.model_dump_json(exclude={"dicom": {"source_path"}}).encode())
    cache_key = digest.hexdigest()
    cached = store.lookup_by_cache_key(cache_key)
    if cached is not None and cached.plan_weights_uri and Path(cached.plan_weights_uri).is_file():
        return ImportedPlan(beam_model=cached, plan=plan, weights=np.load(cached.plan_weights_uri), reused=True)

    beam_model_id = str(uuid.uuid4())
    root = store.base_dir / beam_model_id
    result = BeamModelResult(
        beam_model_id=beam_model_id,
        geometry_id=geometry.geometry_id,
        modality=modality,
        fluence_elements=fluence,
        beam_model_ref_uri=str(root / "plan.pkl"),
        machine_model_id=machine_model_id,
        cache_key=cache_key,
        plan_weights_uri=str(root / PLAN_WEIGHTS_FILENAME),
        imported_plan=plan.dicom,
    )
    paths = store.save(beam_model_id=beam_model_id, cache_key=cache_key, plan=plan, result=result)
    np.save(paths.root / PLAN_WEIGHTS_FILENAME, weights)
    logger.info("Imported {} {} as beam model {}: {} beams, {} fluence elements, {:.1f} MU",
                plan.dicom.sop_class if plan.dicom else "plan", plan.name, beam_model_id,
                len(plan.beams), fluence.total_count, float(weights.sum()))
    return ImportedPlan(beam_model=result, plan=plan, weights=weights)


def find_rtplan_files(directory: Union[str, Path]) -> List[Path]:
    """Every RT Plan / RT Ion Plan file under ``directory`` (DICOM headers only)."""
    import pydicom
    from ..dicom.uids import PLAN_SOP_CLASSES

    found: List[Path] = []
    for p in sorted(Path(directory).rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            ds = pydicom.dcmread(str(p), stop_before_pixels=True, specific_tags=["SOPClassUID", "Modality"])
        except Exception:
            continue
        if str(getattr(ds, "SOPClassUID", "")) in PLAN_SOP_CLASSES or str(getattr(ds, "Modality", "")) in ("RTPLAN", "RTIONPLAN"):
            found.append(p)
    return found


__all__ = ["PlanImportError", "ImportedPlan", "import_rtplan", "find_rtplan_files",
           "fluence_elements_of", "plan_weights", "check_frame_of_reference", "PLAN_WEIGHTS_FILENAME"]
