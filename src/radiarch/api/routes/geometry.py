"""FastAPI routes for the Geometry Service (Service 1).

The service runs either synchronously (cache hits — the answer is
already on disk) or asynchronously (cache misses — a Celery task builds
the geometry in the background and the client polls the jobs endpoint
for progress).

Endpoints
---------
``POST   /api/v1/geometry/build``            — build or reuse cached.
``GET    /api/v1/geometry/{id}``             — retrieve geometry metadata.
``GET    /api/v1/geometry/{id}/density``     — stream density NIfTI.
``GET    /api/v1/geometry/{id}/masks``       — stream multi-label mask NIfTI.
``DELETE /api/v1/geometry/{id}``             — remove a cached geometry.
``GET    /api/v1/geometry/jobs/{job_id}``    — async job status / progress.

Status-code contract for ``POST /build``:

* ``200 OK`` + full :class:`GeometryResult` — cache hit, no job created.
* ``202 Accepted`` + :class:`GeometryBuildResponse` with ``job_id`` —
  cache miss, build dispatched to Celery. Client polls the jobs
  endpoint and then fetches the geometry once ``state=succeeded``.
* ``422 Unprocessable Entity`` — request-level validation error
  (e.g. underspecified grid, rotated affine).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...core.store import store
from ...models.geometry import (
    GeometryBuildRequest,
    GeometryJobStatus,
    GeometryResult,
)
from ...services.geometry import GeometryService
from ...services.persistence import DENSITY_FILENAME, MASKS_FILENAME

router = APIRouter(prefix="/geometry", tags=["geometry"])


@lru_cache(maxsize=1)
def _service() -> GeometryService:
    """Singleton service instance. Cached for the process lifetime so
    every request reuses the same on-disk store + cache index."""
    return GeometryService()


# ---------------------------------------------------------------------------
# Response shape for the async build case
# ---------------------------------------------------------------------------

class GeometryBuildResponse(BaseModel):
    """Returned by ``POST /build`` when a Celery job is dispatched.

    When the cache hits, the endpoint returns a full
    :class:`GeometryResult` instead — ``response_model=Union[...]`` on
    the route union-types the OpenAPI schema accordingly.
    """

    job_id: str
    cache_key: str
    state: str = "queued"
    message: str = "Build dispatched; poll /geometry/jobs/{job_id} for progress."


# ---------------------------------------------------------------------------
# POST /build — cache-hit fast path or async dispatch
# ---------------------------------------------------------------------------

@router.post(
    "/build",
    summary="Build (or reuse cached) geometry from a DICOM study.",
    responses={
        200: {"description": "Cache hit — returned the existing geometry inline."},
        202: {"description": "Cache miss — Celery job dispatched; poll the jobs endpoint."},
        422: {"description": "Request validation error."},
    },
)
async def build_geometry(request: GeometryBuildRequest, response: Response):
    try:
        cache_key = request.compute_cache_key()
        service = _service()
        cached = service.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            # Fast path: no job, no Celery round-trip. Return 200 + full result.
            response.status_code = status.HTTP_200_OK
            return cached

        # Cache miss → create job row and dispatch to Celery.
        job = store.create_geometry_job(cache_key)
        # Lazy import of the task so this module imports cleanly even
        # when Celery isn't configured (e.g., unit tests without broker).
        from ...tasks.geometry_tasks import build_geometry_job

        build_geometry_job.delay(job.id, request.model_dump(mode="json"))
        response.status_code = status.HTTP_202_ACCEPTED
        return GeometryBuildResponse(job_id=job.id, cache_key=cache_key)

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /jobs/{job_id} — poll progress
# ---------------------------------------------------------------------------

@router.get(
    "/jobs/{job_id}",
    response_model=GeometryJobStatus,
    summary="Poll an async geometry build job.",
)
async def get_geometry_job(job_id: str) -> GeometryJobStatus:
    job = store.get_geometry_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Geometry job not found: {job_id}")
    return job


# ---------------------------------------------------------------------------
# Geometry retrieval + streams
# ---------------------------------------------------------------------------

@router.get(
    "/{geometry_id}",
    response_model=GeometryResult,
    summary="Retrieve completed geometry metadata.",
)
async def get_geometry(geometry_id: str) -> GeometryResult:
    result = _service().store.get_by_id(geometry_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Geometry not found: {geometry_id}")
    return result


@router.delete(
    "/{geometry_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a cached geometry (NIfTI files + metadata + cache index entry).",
)
async def delete_geometry(geometry_id: str):
    svc = _service()
    # Load first so we can fail with 404 if it never existed. Also gives
    # us the ``cache_key`` to scrub from the index.
    result = svc.store.get_by_id(geometry_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Geometry not found: {geometry_id}")

    svc.store.delete_by_id(geometry_id)
    return Response(status_code=204)


@router.get(
    "/{geometry_id}/density",
    summary="Stream the density NIfTI volume.",
    response_class=FileResponse,
)
async def get_density(geometry_id: str):
    return _stream_geometry_file(geometry_id, DENSITY_FILENAME, "application/gzip")


@router.get(
    "/{geometry_id}/masks",
    summary="Stream the multi-label mask NIfTI volume.",
    response_class=FileResponse,
)
async def get_masks(geometry_id: str):
    return _stream_geometry_file(geometry_id, MASKS_FILENAME, "application/gzip")


def _stream_geometry_file(geometry_id: str, filename: str, media_type: str):
    result = _service().store.get_by_id(geometry_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Geometry not found: {geometry_id}")

    base = _service().store.base_dir / geometry_id / filename
    if not os.path.isfile(base):
        raise HTTPException(status_code=410, detail=f"{filename} no longer on disk")
    return FileResponse(path=str(base), media_type=media_type, filename=filename)
