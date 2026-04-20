"""FastAPI routes for the Geometry Service (Service 1).

v1 is synchronous — ``POST /geometry/build`` runs the build in-process
and returns the :class:`GeometryResult` directly. The ``/jobs`` variant
listed in the spec comes with the async-mode PR (Celery + DB); in the
meantime, we expose a placeholder so existing clients can evolve.

Endpoints
---------
``POST   /api/v1/geometry/build``       — build (or reuse cached) geometry.
``GET    /api/v1/geometry/{id}``        — retrieve cached geometry metadata.
``GET    /api/v1/geometry/{id}/density``— stream density NIfTI.
``GET    /api/v1/geometry/{id}/masks``  — stream multi-label mask NIfTI.
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...models.geometry import GeometryBuildRequest, GeometryResult
from ...services.geometry import GeometryService
from ...services.persistence import DENSITY_FILENAME, MASKS_FILENAME

router = APIRouter(prefix="/geometry", tags=["geometry"])


@lru_cache(maxsize=1)
def _service() -> GeometryService:
    """Singleton service instance. Cached for the process lifetime so
    every request reuses the same on-disk store + cache index."""
    return GeometryService()


@router.post(
    "/build",
    response_model=GeometryResult,
    summary="Build (or reuse cached) geometry from a DICOM study.",
)
async def build_geometry(request: GeometryBuildRequest) -> GeometryResult:
    try:
        return _service().build(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Request-level validation problems — e.g., rotated affine,
        # underspecified grid. Bubble up as 422 so clients can act.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
