"""FastAPI routes for the Beam Model Service (Service 2).

Status-code contract for ``POST /beam-model/build``:

* ``200 OK`` + full :class:`BeamModelResult` — cache hit, no job created.
* ``202 Accepted`` + :class:`BeamModelBuildResponse` carrying ``job_id``
  — cache miss, build dispatched to Celery. Client polls
  ``GET /beam-model/jobs/{job_id}`` until ``state == succeeded``, then
  fetches ``GET /beam-model/{beam_model_id}``.
* ``422 Unprocessable Entity`` — request validation failed (unknown
  ``geometry_id``, modality/params mismatch, unknown machine model id).

Endpoints
---------
``POST   /api/v1/beam-model/build``                — build / reuse cached.
``GET    /api/v1/beam-model/{id}``                 — retrieve result.
``GET    /api/v1/beam-model/{id}/artifact``        — stream pickled plan.
``DELETE /api/v1/beam-model/{id}``                 — remove from cache.
``GET    /api/v1/beam-model/jobs/{job_id}``        — async job status.
``POST   /api/v1/beam-model/import``               — a DICOM RT Plan as a beam model (R2).
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional, Tuple

from ...core.store import store
from ...models.beam_model import (
    BeamModelBuildRequest,
    BeamModelJobStatus,
    BeamModelResult,
)
from ...services.beam_model import BeamModelService
from ...services.beam_persistence import PLAN_FILENAME

router = APIRouter(prefix="/beam-model", tags=["beam-model"])


@lru_cache(maxsize=1)
def _service() -> BeamModelService:
    """Singleton service instance, reused across requests."""
    return BeamModelService()


# ---------------------------------------------------------------------------
# Async-dispatch response shape
# ---------------------------------------------------------------------------

class BeamModelBuildResponse(BaseModel):
    """Returned by ``POST /build`` when a Celery job is dispatched."""

    job_id: str
    cache_key: str
    state: str = "queued"
    message: str = (
        "Build dispatched; poll /beam-model/jobs/{job_id} for progress."
    )


# ---------------------------------------------------------------------------
# POST /build
# ---------------------------------------------------------------------------

@router.post(
    "/build",
    summary="Build (or reuse cached) beam model from a geometry + beam set.",
    responses={
        200: {"description": "Cache hit — returned the existing beam model inline."},
        202: {"description": "Cache miss — Celery job dispatched."},
        422: {"description": "Request validation error."},
    },
)
async def build_beam_model(request: BeamModelBuildRequest, response: Response):
    try:
        cache_key = request.compute_cache_key()
        service = _service()
        cached = service.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            response.status_code = status.HTTP_200_OK
            return cached

        job = store.create_beam_model_job(cache_key)
        # Lazy task import: this module imports cleanly even if Celery
        # isn't configured (tests without a broker).
        from ...tasks.beam_model_tasks import build_beam_model_job

        build_beam_model_job.delay(job.id, request.model_dump(mode="json"))
        response.status_code = status.HTTP_202_ACCEPTED
        return BeamModelBuildResponse(job_id=job.id, cache_key=cache_key)

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /import — a DICOM RT Plan / RT Ion Plan as a beam model (roadmap R2)
# ---------------------------------------------------------------------------

class BeamModelImportRequest(BaseModel):
    """Where the plan is and which geometry it belongs to.

    Exactly one of ``upload_id`` (a bundle from ``POST /uploads/dicom``, which
    must hold one plan unless ``file_name`` picks it) or ``path`` (a file on the
    server) names the plan.
    """

    geometry_id: str = Field(..., min_length=1, max_length=36)
    upload_id: Optional[str] = Field(default=None, max_length=64)
    file_name: Optional[str] = Field(default=None, description="File within the upload when it holds several plans.")
    path: Optional[str] = Field(default=None, description="Server-side path of the RT Plan file.")
    machine_model_id: str = Field(default="default", max_length=64)
    beamlet_spacing_mm: Tuple[float, float] = Field(default=(5.0, 5.0), description="Beamlet pixel size for photon apertures.")
    strict_frame_of_reference: bool = Field(default=True, description="Refuse a plan whose frame of reference is not the geometry's.")


def _locate_plan_file(request: BeamModelImportRequest) -> Path:
    from ...services.plan_import import find_rtplan_files
    from .uploads import _upload_path

    if bool(request.upload_id) == bool(request.path):
        raise ValueError("give exactly one of upload_id or path")
    if request.path:
        p = Path(request.path).expanduser()
        if not p.is_file():
            raise ValueError(f"plan file not found: {p}")
        return p
    root = _upload_path(request.upload_id)
    if not root.is_dir():
        raise ValueError(f"upload not found: {request.upload_id}")
    plans = find_rtplan_files(root)
    if request.file_name:
        plans = [q for q in plans if q.name == request.file_name or str(q.relative_to(root)) == request.file_name]
    if not plans:
        raise ValueError(f"no RT Plan / RT Ion Plan in upload {request.upload_id}")
    if len(plans) > 1:
        raise ValueError(f"upload {request.upload_id} holds {len(plans)} plans; name one with file_name: "
                         + ", ".join(str(q.relative_to(root)) for q in plans))
    return plans[0]


@router.post(
    "/import",
    response_model=BeamModelResult,
    summary="Import a DICOM RT Plan or RT Ion Plan as a beam model of a geometry.",
    responses={
        200: {"description": "Plan imported (or an identical earlier import reused)."},
        404: {"description": "Unknown geometry."},
        422: {"description": "The plan could not be read or does not fit the geometry."},
    },
)
async def import_plan(request: BeamModelImportRequest) -> BeamModelResult:
    from ...services.geometry import GeometryService
    from ...services.plan_import import PlanImportError, import_rtplan
    from ...dicom.rtplan import RTPlanError

    geometry = GeometryService().store.get_by_id(request.geometry_id)
    if geometry is None:
        raise HTTPException(status_code=404, detail=f"Geometry not found: {request.geometry_id}")
    try:
        path = _locate_plan_file(request)
        imported = import_rtplan(
            path, geometry, _service().store,
            machine_model_id=request.machine_model_id,
            beamlet_spacing_mm=request.beamlet_spacing_mm,
            strict_frame_of_reference=request.strict_frame_of_reference,
        )
    except (ValueError, PlanImportError, RTPlanError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return imported.beam_model


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------

@router.get(
    "/jobs/{job_id}",
    response_model=BeamModelJobStatus,
    summary="Poll an async beam-model build job.",
)
async def get_beam_model_job(job_id: str) -> BeamModelJobStatus:
    job = store.get_beam_model_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail=f"Beam model job not found: {job_id}"
        )
    return job


# ---------------------------------------------------------------------------
# Result retrieval + artifact stream + delete
# ---------------------------------------------------------------------------

@router.get(
    "/{beam_model_id}",
    response_model=BeamModelResult,
    summary="Retrieve completed beam-model metadata.",
)
async def get_beam_model(beam_model_id: str) -> BeamModelResult:
    result = _service().store.get_by_id(beam_model_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Beam model not found: {beam_model_id}"
        )
    return result


@router.delete(
    "/{beam_model_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a cached beam model.",
)
async def delete_beam_model(beam_model_id: str):
    svc = _service()
    if svc.store.get_by_id(beam_model_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Beam model not found: {beam_model_id}"
        )
    svc.store.delete_by_id(beam_model_id)
    return Response(status_code=204)


@router.get(
    "/{beam_model_id}/artifact",
    summary="Stream the serialized OpenTPS plan (pickled).",
    response_class=FileResponse,
)
async def get_beam_model_artifact(beam_model_id: str):
    svc = _service()
    if svc.store.get_by_id(beam_model_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Beam model not found: {beam_model_id}"
        )
    plan_path = svc.store.base_dir / beam_model_id / PLAN_FILENAME
    if not os.path.isfile(plan_path):
        raise HTTPException(
            status_code=410, detail=f"{PLAN_FILENAME} no longer on disk"
        )
    return FileResponse(
        path=str(plan_path),
        media_type="application/octet-stream",
        filename=PLAN_FILENAME,
    )
