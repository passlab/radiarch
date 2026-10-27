"""``RTExportService`` — radiarch's results as DICOM RT objects (roadmap R6).

An export resolves its plan from the stores (an aperture sequence, a proton
optimization with its weights, or a beam model with its own metersets),
builds the case context from the geometry's CT provenance, and writes into
``{artifact_dir}/rt_exports/{export_id}/``:

* ``RS.dcm``   the structure set of the geometry (every structure, or the
  ones asked for; derived structures included);
* ``RP.dcm``   the RT Plan (photons, step-and-shoot) or RT Ion Plan;
* ``RD.dcm``   the plan dose, ``RD_B{n}.dcm`` one dose per beam when asked
  (an engine run per beam with the other beams' elements zeroed; cached by
  the dose service like any dose);
* ``RI_B{n}.dcm`` one DRR per beam, referenced from the plan's beam;
* ``manifest.json`` the :class:`RTExportResult`.

Treatment records are written against an export: ``RT_F{n}.dcm`` per
session and ``RTS.dcm`` for the summary. ``push`` sends the files with
STOW-RS through the DICOMweb notifier.

Geometries built before R6 carry no CT slice UIDs; the structure set then
needs the CT directory (``RADIARCH_DATA_ROOT``), from which the slices are
re-inventoried; without it the export fails with a clear message.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import SimpleITK as sitk
from loguru import logger

from ..config import get_settings
from ..dicom.drr import compute_drr
from ..dicom.uids import SOP
from ..dicom.writers import (
    CaseContext, CourseSummary, PlanWriteOptions, Prescription, Session, Structure, write_rtdose, write_rtimage,
    write_rtplan, write_rtstruct, write_summary_record, write_treatment_record,
)
from ..models.beam_model import BeamModelResult
from ..models.dose import DoseComputeRequest, EngineSpec, WeightVector
from ..models.geometry import GeometryResult
from ..models.photon_plan import PhotonPlan
from ..models.proton_plan import ProtonPlan
from ..models.rt_export import (
    RTExportRequest, RTExportResult, RTObjectRef, RTPushResult, RTRecordRequest, RTRecordResult,
)
from .geometry_bundle import GeometryArrays, load_geometry_arrays, target_structure

MANIFEST = "manifest.json"


class RTExportError(ValueError):
    """The export cannot be made from what the stores hold."""


class _Source:
    def __init__(self, geometry: GeometryResult, beam_model: BeamModelResult, plan, dose_zyx: Optional[np.ndarray],
                 dose_id: Optional[str], rbe: float, dose_units: str, engine_name: Optional[str], weights: np.ndarray) -> None:
        self.geometry = geometry
        self.beam_model = beam_model
        self.plan = plan
        self.dose_zyx = dose_zyx
        self.dose_id = dose_id
        self.rbe = rbe
        self.dose_units = dose_units
        self.engine_name = engine_name
        self.weights = weights


class RTExportService:
    def __init__(self, base_dir: Optional[Union[str, Path]] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else Path(get_settings().artifact_dir) / "rt_exports"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def directory(self, export_id: str) -> Path:
        return self.base_dir / export_id

    def get(self, export_id: str) -> Optional[RTExportResult]:
        p = self.directory(export_id) / MANIFEST
        if not p.is_file():
            return None
        return RTExportResult.model_validate_json(p.read_text())

    def file_path(self, export_id: str, file_name: str) -> Optional[Path]:
        result = self.get(export_id)
        if result is None:
            return None
        for obj in result.objects:
            if obj.file_name == file_name:
                return Path(obj.path)
        return None

    def _save(self, result: RTExportResult) -> None:
        d = self.directory(result.export_id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / (MANIFEST + ".tmp")
        tmp.write_text(result.model_dump_json(indent=2))
        tmp.replace(d / MANIFEST)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, request: RTExportRequest) -> RTExportResult:
        src = self._resolve(request)
        arrays = load_geometry_arrays(src.geometry)
        ctx = self._context(src.geometry, src)
        export_id = str(uuid.uuid4())
        out = self.directory(export_id)
        out.mkdir(parents=True, exist_ok=True)
        objects: List[RTObjectRef] = []
        origin, spacing = arrays.origin_mm, arrays.spacing_mm

        # 1. structures
        rtstruct_uid = request.rtstruct_uid
        roi_numbers: Dict[str, int] = {}
        if "rtstruct" in request.objects:
            names = request.structures or sorted(arrays.structure_index, key=lambda n: arrays.structure_index[n])
            missing = [n for n in names if n not in arrays.structure_index]
            if missing:
                raise RTExportError(f"structures not in the geometry: {missing}")
            structures = [Structure(name=n, mask_zyx=arrays.mask_zyx(arrays.structure_index[n])) for n in names]
            rs = write_rtstruct(ctx, structures, out / "RS.dcm", origin_mm=origin, spacing_mm=spacing, label=request.label,
                                description=request.description)
            rtstruct_uid = rs.sop_instance_uid
            roi_numbers = rs.roi_numbers
            objects.append(self._ref("RTSTRUCT", rs.path, SOP.RTSTRUCT, rs.sop_instance_uid, rs.series_instance_uid))

        # 2. DRRs need the plan's SOP instance UID before the plan is written
        plan_sop_class = SOP.RTPLAN if isinstance(src.plan, PhotonPlan) else SOP.RTIONPLAN
        plan_uid = _new_uid()
        options = self._plan_options(request, src, roi_numbers, arrays)
        options.sop_instance_uid = plan_uid
        beams = list(src.plan.beams)
        if "rtimage" in request.objects:
            for n, beam in enumerate(beams, start=1):
                sad = float(getattr(beam, "sad_mm", options.virtual_sad_mm[0]))
                drr = compute_drr(arrays.ct_hu, origin, spacing, beam.isocenter_mm, beam.gantry_deg, beam.couch_deg, sad_mm=sad,
                                  size_mm=request.drr_size_mm, pixel_mm=request.drr_pixel_mm)
                name = _beam_name(beam, n)
                im = write_rtimage(ctx, drr, out / f"RI_B{n}.dcm", beam_number=n, beam_name=name, plan_sop_class=plan_sop_class,
                                   plan_sop_instance=plan_uid, machine_name=request.machine_name, instance_number=n,
                                   series_instance_uid=_series_uid(export_id, "rtimage"))
                options.drr_refs[_beam_key(beam)] = (SOP.RTIMAGE, im.sop_instance_uid)
                objects.append(self._ref("RTIMAGE", im.path, SOP.RTIMAGE, im.sop_instance_uid, im.series_instance_uid, beam=name))

        # 3. plan
        beam_numbers: Dict[str, int] = {}
        metersets: Dict[str, float] = {}
        n_fractions = options.prescription.fractions if options.prescription else getattr(src.plan, "n_fractions", 1)
        if "rtplan" in request.objects:
            if not rtstruct_uid:
                raise RTExportError("an RT Plan references a structure set: write rtstruct too or give rtstruct_uid")
            rp = write_rtplan(ctx, src.plan, out / "RP.dcm", rtstruct_uid=rtstruct_uid, options=options)
            beam_numbers, metersets, n_fractions = rp.beam_numbers, rp.beam_metersets, rp.n_fractions
            objects.append(self._ref(plan_sop_class == SOP.RTPLAN and "RTPLAN" or "RTIONPLAN", rp.path, rp.sop_class_uid,
                                     rp.sop_instance_uid, rp.series_instance_uid))

        # 4. doses
        if "rtdose" in request.objects:
            if src.dose_zyx is None:
                raise RTExportError("no dose to write: give dose_id with the beam model, or export a sequence or optimization")
            if tuple(src.dose_zyx.shape) != tuple(arrays.shape_zyx):
                raise RTExportError(f"dose shape {src.dose_zyx.shape} differs from the geometry grid {arrays.shape_zyx}")
            rd = write_rtdose(ctx, src.dose_zyx, origin, spacing, out / "RD.dcm", plan_sop_class=plan_sop_class, plan_sop_instance=plan_uid,
                              rbe=src.rbe, dose_units=src.dose_units, comment=f"engine {src.engine_name}" if src.engine_name else "",
                              series_instance_uid=_series_uid(export_id, "rtdose"), summation=request.dose_summation,
                              other_plans=[(plan_sop_class, u) for u in request.summed_plan_uids])
            objects.append(self._ref("RTDOSE", rd.path, SOP.RTDOSE, rd.sop_instance_uid, rd.series_instance_uid, summation=request.dose_summation))
            if request.per_beam_dose:
                for n, (beam, dose) in enumerate(zip(beams, self._beam_doses(request, src)), start=1):
                    rdb = write_rtdose(ctx, dose, origin, spacing, out / f"RD_B{n}.dcm", plan_sop_class=plan_sop_class,
                                       plan_sop_instance=plan_uid, summation="BEAM", beam_number=n, rbe=src.rbe, dose_units=src.dose_units,
                                       series_instance_uid=_series_uid(export_id, "rtdose-beams"), instance_number=n)
                    objects.append(self._ref("RTDOSE", rdb.path, SOP.RTDOSE, rdb.sop_instance_uid, rdb.series_instance_uid,
                                             beam=_beam_name(beam, n), summation="BEAM"))

        result = RTExportResult(
            export_id=export_id, geometry_id=src.geometry.geometry_id, beam_model_id=src.beam_model.beam_model_id,
            dose_id=src.dose_id, plan_id=request.plan_id, modality=src.beam_model.modality, directory=str(out),
            study_instance_uid=ctx.study_instance_uid, frame_of_reference_uid=ctx.frame_of_reference_uid,
            rtstruct_uid=rtstruct_uid, plan_sop_class_uid=plan_sop_class if "rtplan" in request.objects else None,
            plan_sop_instance_uid=plan_uid if "rtplan" in request.objects else None,
            beam_numbers=beam_numbers, beam_metersets=metersets, n_fractions=int(n_fractions), prescription=request.prescription,
            machine_name=request.machine_name, attribution=self._attribution(src), objects=objects, created_at=datetime.now(timezone.utc),
        )
        if request.push:
            ok, err = self._push([o.path for o in objects])
            result.pushed, result.push_error = ok, err
            result.viewer_url = viewer_link(result.study_instance_uid) if ok else None
        self._save(result)
        logger.info("RT export {}: {} objects in {}", export_id, len(objects), out)
        return result

    # ------------------------------------------------------------------
    # Treatment records
    # ------------------------------------------------------------------

    def records(self, export_id: str, request: RTRecordRequest) -> RTRecordResult:
        result = self.get(export_id)
        if result is None:
            raise RTExportError(f"export {export_id!r} not found")
        if not result.plan_sop_instance_uid:
            raise RTExportError("the export holds no RT Plan; records reference one")
        src_plan = self._plan_of(result)
        geometry = self._geometry(result.geometry_id)
        ctx = self._context(geometry)
        out = self.directory(export_id)
        options = PlanWriteOptions(machine_name=result.machine_name, prescription=self._prescription(result.prescription, {}),
                                   leaf_boundaries_mm=self._leaf_boundaries(result.beam_model_id, src_plan))
        earlier = [o for o in result.objects if o.kind == "RTRECORD"]
        sessions = [Session(fraction_number=s.fraction_number, treatment_date=s.treatment_date, treatment_time=s.treatment_time,
                            delivered=s.delivered, termination=s.termination, verification=s.verification,
                            machine_name=s.machine_name or result.machine_name, beam_delivered=dict(s.beam_delivered),
                            couch_vertical_mm=s.couch_vertical_mm, couch_longitudinal_mm=s.couch_longitudinal_mm,
                            couch_lateral_mm=s.couch_lateral_mm, referenced_record_uids=[o.sop_instance_uid for o in earlier])
                    for s in request.sessions]
        new_objects: List[RTObjectRef] = []
        for s in sessions:
            path = out / f"RT_F{s.fraction_number}.dcm"
            rec = write_treatment_record(ctx, src_plan, s, path, plan_sop_instance=result.plan_sop_instance_uid, options=options,
                                         series_instance_uid=_series_uid(export_id, "rtrecord"))
            new_objects.append(self._ref("RTRECORD", rec.path, rec.sop_class_uid, rec.sop_instance_uid, rec.series_instance_uid,
                                         fraction_number=s.fraction_number))
            earlier.append(new_objects[-1])
            s.referenced_record_uids = [o.sop_instance_uid for o in earlier[:-1]]
        # the course so far: every session recorded for this export
        result.objects = [o for o in result.objects if o.kind != "RTSUMMARY"] + new_objects
        delivered_fractions = sorted({o.fraction_number for o in result.objects if o.kind == "RTRECORD" and o.fraction_number})
        planned = int(result.n_fractions)
        status = request.status or ("COMPLETED" if len(delivered_fractions) >= planned else "ON_TREATMENT")
        if request.summary:
            all_sessions = self._sessions_so_far(result, sessions)
            course = CourseSummary(sessions=all_sessions, fractions_planned=planned, status=status, comment=request.comment,
                                   prescription_dose_gy=result.prescription.dose_gy if result.prescription else None,
                                   dose_reference_description=(result.prescription.target_structure or "target") if result.prescription else "target")
            sm = write_summary_record(ctx, course, out / "RTS.dcm", plan_sop_class=result.plan_sop_class_uid,
                                      plan_sop_instance=result.plan_sop_instance_uid, machine_name=result.machine_name,
                                      series_instance_uid=_series_uid(export_id, "rtsummary"))
            new_objects.append(self._ref("RTSUMMARY", sm.path, sm.sop_class_uid, sm.sop_instance_uid, sm.series_instance_uid))
            result.objects.append(new_objects[-1])
        pushed, err = False, None
        if request.push:
            pushed, err = self._push([o.path for o in new_objects])
        self._save(result)
        return RTRecordResult(export_id=export_id, objects=new_objects, fractions_delivered=len(delivered_fractions),
                              fractions_planned=planned, status=status, pushed=pushed, push_error=err)

    def _sessions_so_far(self, result: RTExportResult, new: List[Session]) -> List[Session]:
        """Sessions of every record of the export: earlier ones re-read from their files."""
        import pydicom

        by_fraction: Dict[int, Session] = {s.fraction_number: s for s in new}
        for o in result.objects:
            if o.kind != "RTRECORD" or o.fraction_number in by_fraction or not Path(o.path).is_file():
                continue
            ds = pydicom.dcmread(o.path, stop_before_pixels=True)
            beams = getattr(ds, "TreatmentSessionBeamSequence", None) or getattr(ds, "TreatmentSessionIonBeamSequence", [])
            spec = sum(float(b.SpecifiedPrimaryMeterset) for b in beams) or 1.0
            deliv = sum(float(b.DeliveredPrimaryMeterset) for b in beams)
            by_fraction[int(o.fraction_number)] = Session(
                fraction_number=int(o.fraction_number), treatment_date=str(ds.TreatmentDate), treatment_time=str(ds.TreatmentTime),
                delivered=deliv / spec, termination=str(beams[0].TreatmentTerminationStatus) if beams else "NORMAL")
        return [by_fraction[k] for k in sorted(by_fraction)]

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------

    def push(self, export_id: str, *, url: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None,
             kinds: Optional[Sequence[str]] = None) -> RTPushResult:
        result = self.get(export_id)
        if result is None:
            raise RTExportError(f"export {export_id!r} not found")
        from ..adapters.dicomweb import DICOMwebNotifier, DICOMwebPushError

        notifier = DICOMwebNotifier(url=url, username=username, password=password)
        paths = [o.path for o in result.objects if kinds is None or o.kind.lower() in {k.lower() for k in kinds}]
        try:
            notifier.store_instances(paths, raise_errors=True)
        except DICOMwebPushError as exc:
            return RTPushResult(export_id=export_id, pushed=0, url=notifier._url or "", error=str(exc),
                                http_status=exc.status, response=exc.details if exc.details is not None else exc.body)
        except Exception as exc:
            return RTPushResult(export_id=export_id, pushed=0, url=notifier._url or "", error=str(exc))
        result.pushed, result.push_error = True, None
        result.viewer_url = viewer_link(result.study_instance_uid)
        self._save(result)
        return RTPushResult(export_id=export_id, pushed=len(paths), url=notifier._url or "", viewer_url=result.viewer_url)

    def _push(self, paths: Sequence[str]) -> Tuple[bool, Optional[str]]:
        from ..adapters.dicomweb import get_dicomweb_notifier

        try:
            get_dicomweb_notifier().store_instances(list(paths), raise_errors=True)
            return True, None
        except Exception as exc:
            logger.warning("STOW-RS push failed: {}", exc)
            return False, str(exc)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _geometry(self, geometry_id: str) -> GeometryResult:
        from .geometry import GeometryService

        geom = GeometryService().store.get_by_id(geometry_id)
        if geom is None:
            raise RTExportError(f"geometry {geometry_id!r} not found")
        return geom

    def _beam_model(self, beam_model_id: str):
        from .dose import DoseService

        bundle = DoseService()._load_beam_model(beam_model_id)
        if bundle.plan is None:
            raise RTExportError(f"beam model {beam_model_id!r} has no plan artifact on disk")
        return bundle.result, bundle.plan

    def _resolve(self, request: RTExportRequest) -> _Source:
        from .dose import DoseService

        dose_service = DoseService()
        if request.sequence_id:
            from .apertures import ApertureService

            seq_result = ApertureService().store.get_by_id(request.sequence_id)
            if seq_result is None:
                raise RTExportError(f"sequence {request.sequence_id!r} not found")
            bm, plan = self._beam_model(seq_result.beam_model_id)
            if not isinstance(plan, PhotonPlan):
                raise RTExportError("the sequence's beam model holds no photon plan")
            dose_result = dose_service.dose_store.get_by_id(seq_result.dose_id)
            dose = _read_volume(dose_result.dose_grid_uri) if dose_result else None
            rbe = dose_result.rbe_factor if dose_result else 1.0
            return _Source(self._geometry(bm.geometry_id), bm, plan, dose, seq_result.dose_id, rbe,
                           seq_result.dose_units, dose_result.engine_name if dose_result else None, plan.beamlet_mu())

        if request.optimization_id:
            from .optimization import OptimizationService

            opt_service = OptimizationService()
            opt = opt_service.store.get_by_id(request.optimization_id)
            if opt is None:
                raise RTExportError(f"optimization {request.optimization_id!r} not found")
            weights = np.asarray(opt_service.store.load_weights(request.optimization_id), dtype=float)
            bm, plan = self._beam_model(opt.beam_model_id)
            if isinstance(plan, PhotonPlan):
                raise RTExportError("a photon optimization is a fluence, not a deliverable plan: sequence it first "
                                    "(POST /optimize/{id}/sequence) and export the sequence")
            if weights.shape[0] != plan.n_spots:
                raise RTExportError(f"optimization has {weights.shape[0]} weights, the plan {plan.n_spots} spots")
            plan = plan.with_spot_mus(weights)
            dose = _read_volume(opt.dose_ref_uri) if opt.dose_ref_uri else None
            return _Source(self._geometry(opt.geometry_id), bm, plan, dose, None, opt.rbe_factor, opt.dose_units, opt.engine_name, weights)

        bm, plan = self._beam_model(request.beam_model_id)
        weights = None
        if bm.plan_weights_uri and Path(bm.plan_weights_uri).is_file():
            weights = np.load(bm.plan_weights_uri)
            if isinstance(plan, ProtonPlan) and weights.shape[0] == plan.n_spots:
                plan = plan.with_spot_mus(weights)
        if weights is None:
            weights = plan.spot_mus if isinstance(plan, ProtonPlan) else plan.beamlet_mu()
        dose, dose_id, rbe, units, engine = None, None, 1.0, "Gy", None
        if request.dose_id:
            dose_result = dose_service.dose_store.get_by_id(request.dose_id)
            if dose_result is None:
                raise RTExportError(f"dose {request.dose_id!r} not found")
            if dose_result.beam_model_id != bm.beam_model_id:
                raise RTExportError("the dose was computed for another beam model")
            dose, dose_id, rbe, units, engine = (_read_volume(dose_result.dose_grid_uri), request.dose_id, dose_result.rbe_factor,
                                                 dose_result.dose_units, dose_result.engine_name)
        return _Source(self._geometry(bm.geometry_id), bm, plan, dose, dose_id, rbe, units, engine, np.asarray(weights, dtype=float))

    def _plan_of(self, result: RTExportResult):
        """The plan an export wrote, re-read from the plan file so the records match it exactly."""
        from ..dicom.rtplan import read_rtplan

        plan_obj = next((o for o in result.objects if o.kind in ("RTPLAN", "RTIONPLAN")), None)
        if plan_obj is None or not Path(plan_obj.path).is_file():
            raise RTExportError("the export's plan file is missing")
        return read_rtplan(plan_obj.path)

    # ------------------------------------------------------------------
    # Pieces
    # ------------------------------------------------------------------

    def _context(self, geometry: GeometryResult, src: Optional[_Source] = None) -> CaseContext:
        ctx = CaseContext.from_geometry(geometry)
        if not ctx.ct_sop_instance_uids:
            ctx.ct_sop_instance_uids = self._ct_slices_from_disk(ctx.ct_series_instance_uid)
        if src is not None:
            a = self._attribution(src)
            ctx.engine = " ".join(v for v in (a.get("engine_name"), a.get("engine_version")) if v)
            ctx.machine = str(a.get("machine_model_id") or "")
        return ctx

    @staticmethod
    def _attribution(src: _Source) -> Dict[str, Any]:
        """Who made what the export writes (R12): the capability, engine, machine model and HU model."""
        from .lineage import radiarch_version

        engine_name = (src.engine_name or "").split("+")[0] or None
        engine_version = None
        if engine_name:
            try:
                from .dose_engines.registry import get_engine
                engine_version = str(getattr(get_engine(engine_name), "version", "") or "") or None
            except Exception:
                engine_version = None
        return {"capability_id": "radiarch", "capability_version": radiarch_version(), "engine_name": engine_name,
                "engine_version": engine_version, "machine_model_id": src.beam_model.machine_model_id,
                "hu_model": getattr(src.geometry, "hu_to_density_model", None), "modality": str(getattr(src.beam_model.modality, "value", src.beam_model.modality))}

    @staticmethod
    def _ct_slices_from_disk(series_uid: str) -> List[str]:
        """The CT slice UIDs of a geometry built before R6, from the data root when it holds that series."""
        import pydicom
        from ..dicom.ct import inventory

        root = get_settings().data_root
        if not root or not series_uid or not Path(root).is_dir():
            return []
        inv = inventory(root)
        files = inv.ct_series.get(series_uid)
        if not files:
            return []
        z, uids = [], []
        for f in files:
            ds = pydicom.dcmread(str(f), stop_before_pixels=True, specific_tags=["SOPInstanceUID", "ImagePositionPatient"])
            z.append(float(ds.ImagePositionPatient[2])); uids.append(str(ds.SOPInstanceUID))
        return [uids[k] for k in np.argsort(z)]

    def _prescription(self, spec, roi_numbers: Dict[str, int]) -> Optional[Prescription]:
        if spec is None:
            return None
        target = spec.target_structure or ""
        return Prescription(dose_gy=spec.dose_gy, fractions=spec.fractions, target_name=target,
                            target_roi_number=roi_numbers.get(target), description=f"{spec.dose_gy:g} Gy in {spec.fractions} fx to {target or 'target'}")

    def _plan_options(self, request: RTExportRequest, src: _Source, roi_numbers: Dict[str, int], arrays: GeometryArrays) -> PlanWriteOptions:
        prescription = request.prescription
        if prescription is not None and not prescription.target_structure:
            t = target_structure(arrays.structure_index)
            prescription = prescription.model_copy(update={"target_structure": t[0] if t else None})
        opt = PlanWriteOptions(label=request.label, description=request.description, machine_name=request.machine_name,
                               prescription=self._prescription(prescription, roi_numbers))
        if request.predecessor_plan_uid:
            sop = SOP.RTPLAN if isinstance(src.plan, PhotonPlan) else SOP.RTIONPLAN
            opt.referenced_plans.append((sop, request.predecessor_plan_uid, "PREDECESSOR"))
        if isinstance(src.plan, PhotonPlan):
            opt.leaf_boundaries_mm = self._leaf_boundaries(src.beam_model.machine_model_id, src.plan)
        else:
            self._proton_machine(opt, src.beam_model.machine_model_id)
        return opt

    @staticmethod
    def _leaf_boundaries(machine_model_id: Optional[str], plan) -> Optional[List[float]]:
        """The machine's leaf boundaries when every MLC row of the plan is one of its pairs; else None (from the rows)."""
        if not isinstance(plan, PhotonPlan):
            return None
        try:
            from .machine_model import PhotonMachineModel

            bounds = [float(v) for v in PhotonMachineModel.from_id(machine_model_id or "default").spec.mlc.leaf_boundaries_mm]
        except Exception:
            return None
        keys = {round(b, 4) for b in bounds}
        for beam in plan.beams:
            for seg in beam.segments:
                for r in seg.mlc_rows:
                    if round(r.y_min_mm, 4) not in keys or round(r.y_max_mm, 4) not in keys:
                        return None
                    i = bounds.index(round(r.y_min_mm, 4)) if round(r.y_min_mm, 4) in bounds else None
                    if i is None or i + 1 >= len(bounds) or round(bounds[i + 1], 4) != round(r.y_max_mm, 4):
                        return None
        return bounds

    @staticmethod
    def _proton_machine(opt: PlanWriteOptions, machine_model_id: Optional[str]) -> None:
        try:
            from .machine_model import ProtonMachineModel

            spec = ProtonMachineModel.from_id(machine_model_id or "default").spec
        except Exception:
            return
        smx, smy = spec.smx_to_isocenter_mm, spec.smy_to_isocenter_mm
        if smx and smy:
            opt.virtual_sad_mm = (float(smx), float(smy))
        opt.range_shifter_types = {rs.shifter_id: "BINARY" for rs in spec.range_shifters}

    def _beam_doses(self, request: RTExportRequest, src: _Source) -> List[np.ndarray]:
        """One dose per beam: the plan's weights with every other beam's elements zeroed, through the dose service."""
        from .dose import DoseService

        engine = request.engine or (EngineSpec(name=src.engine_name.split("+")[0]) if src.engine_name else None)
        if engine is None:
            raise RTExportError("per-beam doses need an engine: give engine")
        counts = [int(b.element_count) for b in src.beam_model.fluence_elements.per_beam]
        if sum(counts) != src.weights.shape[0]:
            raise RTExportError(f"beam model has {sum(counts)} elements, the plan {src.weights.shape[0]} weights")
        doses, start = [], 0
        for count in counts:
            w = np.zeros_like(src.weights)
            w[start:start + count] = src.weights[start:start + count]
            start += count
            res = DoseService().compute_dose(DoseComputeRequest(
                plan_id=request.plan_id, geometry_id=src.geometry.geometry_id, beam_model_id=src.beam_model.beam_model_id,
                engine=engine, weights=WeightVector(length=int(w.shape[0]), values=[float(v) for v in w]), rbe=src.rbe))
            doses.append(_read_volume(res.dose_grid_uri))
        return doses

    @staticmethod
    def _ref(kind: str, path: str, sop_class: str, sop_instance: str, series: str, **extra) -> RTObjectRef:
        p = Path(path)
        return RTObjectRef(kind=kind, file_name=p.name, path=str(p), sop_class_uid=sop_class, sop_instance_uid=sop_instance,
                           series_instance_uid=series, size_bytes=p.stat().st_size if p.is_file() else 0, **extra)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def viewer_link(study_instance_uid: str) -> Optional[str]:
    """A link that opens the study in the configured DICOMweb viewer (OHIF's study route); None without one."""
    base = get_settings().viewer_url.strip().rstrip("/")
    return f"{base}/viewer?StudyInstanceUIDs={study_instance_uid}" if base else None


def _read_volume(uri: str) -> np.ndarray:
    path = uri[len("file://"):] if uri.startswith("file://") else uri
    return sitk.GetArrayFromImage(sitk.ReadImage(path)).astype(np.float32)


def _new_uid() -> str:
    from pydicom.uid import generate_uid
    return generate_uid()


def _series_uid(export_id: str, kind: str) -> str:
    from ..dicom.writers import stable_uid
    return stable_uid(export_id, kind)


def _beam_key(beam) -> str:
    return beam.beam_id if getattr(beam, "beam_id", "") else getattr(beam, "name", "")


def _beam_name(beam, number: int) -> str:
    if hasattr(beam, "segments"):          # a photon beam: its id is its name
        return beam.beam_id
    return beam.name or beam.beam_id or f"B{number}"


__all__ = ["RTExportService", "RTExportError", "MANIFEST"]
