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
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

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
