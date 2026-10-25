"""4D planning on a respiratory-correlated CT (roadmap R9): the average-intensity CT, the ITV over the phases, a
plan's dose on every phase and its deformable accumulation on a reference phase.

* **Average CT**: the voxelwise mean HU of the phases (all on one grid and frame of reference), converted to density
  with the reference phase's HU model; the reference phase's structures are kept. A derived geometry of the
  reference phase.
* **ITV**: the union of a target over the phases, on one geometry. A phase on the same grid and frame of reference
  contributes its contour as drawn; a phase given with a registration (the ITV's geometry fixed, the phase moving)
  contributes its contour propagated. A derived geometry with the ITV added.
* **Phase doses**: the plan's metersets (photon apertures and MU, or proton spot MU) recomputed on each phase's CT
  with the plan's isocenter in the shared patient coordinates. A photon plan with apertures goes through the
  engine's aperture path, the one its own delivered dose used (VMAT, R8).
* **Accumulation**: each phase dose pulled back through its registration onto the reference phase and summed with
  the phases' shares of the delivery (equal by default, as for a regular breathing pattern). Pull-back does not
  conserve energy where tissue compresses; the registrations report how far their Jacobians are from 1.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from loguru import logger

from ..models.dose import DoseResult
from ..models.four_d import AccumulateRequest, AverageCTRequest, ITVRequest, PhaseDoseRequest
from ..models.geometry import GeometryResult


class FourDError(ValueError):
    pass


FOUR_D_VERSION = "1"


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(["four-d", FOUR_D_VERSION, *parts]).encode("utf-8")).hexdigest()


def _same_grid(a: GeometryResult, b: GeometryResult) -> bool:
    ga, gb = a.grid_spec, b.grid_spec
    return (tuple(ga.size or ()) == tuple(gb.size or ()) and np.allclose(ga.spacing_mm, gb.spacing_mm)
            and np.allclose(ga.origin_mm or (0, 0, 0), gb.origin_mm or (0, 0, 0)))


def save_derived_geometry(store, parent: GeometryResult, key: str, density: np.ndarray, masks: np.ndarray, ct: Optional[np.ndarray],
                          index: dict, op: dict) -> GeometryResult:
    """A geometry derived from ``parent`` with new volumes ((z, y, x), as read) and one more operation on record."""
    from .masks import BITMASK
    from .persistence import GeometryPaths

    gid = str(uuid.uuid4())
    paths = GeometryPaths.for_id(store.base_dir, gid)
    result = parent.model_copy(update={
        "geometry_id": gid, "density_grid_uri": str(paths.density), "structure_masks_uri": str(paths.masks),
        "ct_grid_uri": str(paths.ct) if ct is not None else None, "structure_index": index, "mask_encoding": BITMASK,
        "cache_key": key, "parent_geometry_id": parent.geometry_id, "derived_operations": list(parent.derived_operations) + [op]})
    # (z, y, x) here; the store takes (x, y, z)
    store.save(geometry_id=gid, cache_key=key, density=density.transpose(2, 1, 0), masks=masks.transpose(2, 1, 0),
               ct=ct.transpose(2, 1, 0) if ct is not None else None, result=result)
    return result


def read_geometry_volumes(geom: GeometryResult):
    """Density, bitmask structures, CT (or None) as (z, y, x), and the structure index."""
    import SimpleITK as sitk
    from .masks import to_bitmask

    read = lambda p: sitk.GetArrayFromImage(sitk.ReadImage(str(p)))       # noqa: E731
    index = {str(k): int(v) for k, v in geom.structure_index.items()}
    masks = to_bitmask(read(geom.structure_masks_uri), index.values(), getattr(geom, "mask_encoding", "labels") or "labels")
    density = read(geom.density_grid_uri).astype(np.float32)
    ct = read(geom.ct_grid_uri).astype(np.int16) if geom.ct_grid_uri else None
    return density, masks, ct, index


class FourDService:
    def __init__(self, geometry_service=None, dose_service=None, registration_service=None) -> None:
        from .dose import DoseService
        from .geometry import GeometryService
        from .registration import RegistrationService

        self.geometry_service = geometry_service or GeometryService()
        self.dose_service = dose_service or DoseService()
        self.registration_service = registration_service or RegistrationService(geometry_service=self.geometry_service)

    def _geometry(self, geometry_id: str) -> GeometryResult:
        g = self.geometry_service.store.get_by_id(geometry_id)
        if g is None:
            raise FourDError(f"geometry {geometry_id!r} not found")
        return g

    def _same_frame(self, ref: GeometryResult, other: GeometryResult, what: str) -> None:
        if ref.frame_of_reference_uid and other.frame_of_reference_uid and ref.frame_of_reference_uid != other.frame_of_reference_uid:
            raise FourDError(f"{what} {other.geometry_id} is in another frame of reference than {ref.geometry_id}; register it instead")

    # ----- average CT ---------------------------------------------------------

    def average(self, request: AverageCTRequest) -> GeometryResult:
        from .geometry_bundle import load_ct_hu
        from .hu_density import get_model
        from ..models.geometry import HUDensityModel

        ref = self._geometry(request.reference_geometry_id)
        phases = [self._geometry(g) for g in request.phase_geometry_ids]
        for p in phases:
            self._same_frame(ref, p, "phase")
            if not _same_grid(ref, p):
                raise FourDError(f"phase {p.geometry_id} is on another grid than {ref.geometry_id}; build the phases on one grid")
        key = _key("average", ref.cache_key, *[p.cache_key for p in phases])
        cached = self.geometry_service.store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        total = None
        for p in phases:
            hu = load_ct_hu(p)
            if hu is None:
                raise FourDError(f"phase {p.geometry_id} has no CT on disk; rebuild it")
            total = hu.astype(np.float64) if total is None else total + hu
        mean_hu = (total / len(phases)).astype(np.float32)
        hu_model = get_model(ref.hu_to_density_model or HUDensityModel.stoichiometric.value)
        _, masks, _, index = read_geometry_volumes(ref)
        density = hu_model.convert(mean_hu).astype(np.float32)
        result = save_derived_geometry(self.geometry_service.store, ref, key, density, masks, np.rint(mean_hu).astype(np.int16), index,
                                    {"op": "average_ct", "geometry_ids": [p.geometry_id for p in phases]})
        logger.info("Average CT of {} phases → geometry {}", len(phases), result.geometry_id)
        return result

    # ----- ITV ----------------------------------------------------------------

    def itv(self, request: ITVRequest) -> GeometryResult:
        from .geometry_bundle import load_geometry_arrays
        from .masks import BITMASK, MAX_BITMASK_STRUCTURES, set_structure
        from .registration import _grid

        target = self._geometry(request.geometry_id)
        density, masks, ct, index = read_geometry_volumes(target)
        if request.name.lower() in {k.lower() for k in index}:
            raise FourDError(f"the geometry already has {request.name!r}; choose another name")
        if len(index) >= MAX_BITMASK_STRUCTURES:
            raise FourDError(f"a geometry holds at most {MAX_BITMASK_STRUCTURES} structures")
        keys = [target.cache_key, request.name, str(request.threshold)]
        union = np.zeros(density.shape, bool)
        used = []
        for src in request.sources:
            g = self._geometry(src.geometry_id)
            arr = load_geometry_arrays(g)
            lower = {k.lower(): k for k in arr.structure_index}
            if src.structure.lower() not in lower:
                raise FourDError(f"structure {src.structure!r} not in geometry {g.geometry_id} ({sorted(arr.structure_index)})")
            m = arr.mask_zyx(arr.structure_index[lower[src.structure.lower()]])
            if src.registration_id:
                reg = self.registration_service.get(src.registration_id)
                if reg.fixed_geometry_id != target.geometry_id or reg.moving_geometry_id != g.geometry_id:
                    raise FourDError(f"registration {src.registration_id} does not map {target.geometry_id} (fixed) to {g.geometry_id} (moving)")
                origin, spacing = _grid(g)
                m = self.registration_service.map_volume(src.registration_id, m.astype(np.float32), origin, spacing) >= request.threshold
                keys.append(f"{g.cache_key}:{src.structure}:{reg.cache_key}")
            else:
                self._same_frame(target, g, "phase")
                if not _same_grid(target, g):
                    raise FourDError(f"phase {g.geometry_id} is on another grid than {target.geometry_id}: give a registration")
                keys.append(f"{g.cache_key}:{src.structure}")
            union |= m
            used.append(src.model_dump(exclude_none=True))
        key = _key("itv", *keys)
        cached = self.geometry_service.store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        label = max(index.values(), default=0) + 1
        index[request.name] = label
        masks = set_structure(masks, label, union, BITMASK)
        result = save_derived_geometry(self.geometry_service.store, target, key, density, masks, ct, index, {"op": "itv", "name": request.name, "sources": used})
        logger.info("ITV {} over {} phase(s) → geometry {}", request.name, len(used), result.geometry_id)
        return result

    # ----- phase doses ----------------------------------------------------------

    def phase_doses(self, request: PhaseDoseRequest) -> List[DoseResult]:
        from .dose import _summary_stats
        from .dose_engines.registry import ensure_engine_allowed, get_engine
        from .dose_persistence import DOSE_FILENAME
        from ..models.photon_plan import PhotonPlan

        ds = self.dose_service
        bm = ds._load_beam_model(request.beam_model_id)
        plan_geom = self._geometry(bm.result.geometry_id)
        engine = get_engine(request.engine.name)
        ensure_engine_allowed(engine)
        out = []
        for gid in request.geometry_ids:
            geom = self._geometry(gid)
            self._same_frame(plan_geom, geom, "phase")
            key = _key("phase-dose", bm.result.cache_key, geom.cache_key, request.engine.name, request.engine.key_version(),
                       json.dumps(request.engine.params, sort_keys=True))
            cached = ds.dose_store.lookup_by_cache_key(key)
            if cached is not None:
                out.append(cached)
                continue
            bundle = ds._load_geometry(gid)
            plan = bm.plan
            if isinstance(plan, PhotonPlan) and hasattr(engine, "compute_plan_dose"):
                params = {"fluence": "apertures", **request.engine.params}
                dose = engine.compute_plan_dose(bundle.density, bundle.spacing_mm, bundle.origin_mm, plan, params=params)
            else:
                weights = np.asarray(plan.beamlet_mu() if isinstance(plan, PhotonPlan) else plan.spot_mus, np.float32)
                dose = engine.compute_dose(bundle, bm, weights, params=request.engine.params).dose
            dose = np.asarray(dose, np.float32)
            did = str(uuid.uuid4())
            result = DoseResult(dose_id=did, geometry_id=gid, beam_model_id=bm.result.beam_model_id, modality=bm.result.modality,
                                engine_name=engine.name, engine_version=engine.version, dose_grid_uri=str(ds.dose_store.base_dir / did / DOSE_FILENAME),
                                statistics=_summary_stats(dose), cache_key=key, created_at=datetime.now(timezone.utc))
            ds.dose_store.save(dose_id=did, cache_key=key, nominal_dose=dose, spacing_mm=bundle.spacing_mm, scenario_doses=None, result=result)
            out.append(result)
        logger.info("Plan {} recomputed on {} phase(s)", request.beam_model_id, len(out))
        return out

    # ----- accumulation ---------------------------------------------------------

    def accumulate(self, request: AccumulateRequest) -> DoseResult:
        from .dose import _summary_stats
        from .dose_persistence import DOSE_FILENAME, read_dose_volume
        from .registration import _grid

        ds = self.dose_service
        ref = self._geometry(request.reference_geometry_id)
        weights = request.weights()
        sources, keys = [], [ref.cache_key]
        for p, w in zip(request.phases, weights):
            d = ds.dose_store.get_by_id(p.dose_id)
            if d is None:
                raise FourDError(f"dose {p.dose_id!r} not found")
            sources.append(d)
            reg_key = ""
            if p.registration_id:
                reg = self.registration_service.get(p.registration_id)
                if reg.fixed_geometry_id != ref.geometry_id or reg.moving_geometry_id != d.geometry_id:
                    raise FourDError(f"registration {p.registration_id} does not map {ref.geometry_id} (fixed) to the dose's geometry "
                                     f"{d.geometry_id} (moving)")
                reg_key = reg.cache_key
            elif d.geometry_id != ref.geometry_id and not _same_grid(ref, self._geometry(d.geometry_id)):
                raise FourDError(f"dose {p.dose_id} is on geometry {d.geometry_id}, not on the reference grid: give a registration")
            keys.append(f"{d.cache_key}:{reg_key}:{w:.6f}")
        units = {d.dose_units for d in sources}
        if len(units) > 1:
            raise FourDError(f"the phase doses are in different units {sorted(units)}")
        key = _key("accumulate", "absolute" if request.absolute else "shares", f"scenarios={request.phases_as_scenarios}",
                   json.dumps(request.names), *keys)
        cached = ds.dose_store.lookup_by_cache_key(key)
        if cached is not None:
            return cached
        from ..models.dose import ScenarioDoseEntry

        total = None
        did = str(uuid.uuid4())
        names = request.names or [f"phase {i}" for i in range(1, len(request.phases) + 1)]
        scenario_arrays: Dict[str, np.ndarray] = {}
        entries: List[ScenarioDoseEntry] = []
        for name, p, w, d in zip(names, request.phases, weights, sources):
            arr = read_dose_volume(Path(d.dose_grid_uri))
            if p.registration_id:
                origin, spacing = _grid(self._geometry(d.geometry_id))
                arr = np.clip(self.registration_service.map_volume(p.registration_id, arr, origin, spacing), 0.0, None)
            total = w * arr if total is None else total + w * arr
            if request.phases_as_scenarios:
                # each phase as if the whole course were delivered in it: the dose of the phase, on the reference anatomy
                h = hashlib.sha256(f"{d.cache_key}|{p.registration_id}".encode("utf-8")).hexdigest()[:16]
                scenario_arrays[h] = arr.astype(np.float32)
                entries.append(ScenarioDoseEntry(scenario_name=name, scenario_hash=h, statistics=_summary_stats(arr),
                                                 dose_grid_uri=str(ds.dose_store.base_dir / did / f"scenario_{h}.nii.gz")))
        first = sources[0]
        result = first.model_copy(update={
            "dose_id": did, "geometry_id": ref.geometry_id, "dose_grid_uri": str(ds.dose_store.base_dir / did / DOSE_FILENAME),
            "statistics": _summary_stats(total), "scenario_doses": entries or None, "mapped_from": None, "cache_key": key,
            "created_at": datetime.now(timezone.utc),
            "accumulated_from": [{"dose_id": p.dose_id, "registration_id": p.registration_id, "weight": w}
                                 for p, w in zip(request.phases, weights)]})
        ds.dose_store.save(dose_id=did, cache_key=key, nominal_dose=total.astype(np.float32), spacing_mm=tuple(ref.grid_spec.spacing_mm),
                           scenario_doses=scenario_arrays or None, result=result)
        logger.info("Accumulated {} phase dose(s) on geometry {} → dose {}", len(sources), ref.geometry_id, did)
        return result


__all__ = ["FourDError", "FourDService", "read_geometry_volumes", "save_derived_geometry"]
