"""FastAPI routes for the Dose Service (Service 3).

Status-code contract for ``POST /dose/compute`` and ``POST /dose/influence``:

* ``200 OK`` + full :class:`DoseResult` / :class:`InfluenceResult` — cache hit.
* ``202 Accepted`` + :class:`DoseBuildResponse` carrying ``job_id`` —
  cache miss, build dispatched to Celery. Poll the matching job endpoint.
* ``422 Unprocessable Entity`` — request validation failed (unknown
  geometry/beam model, modality mismatch, missing engine).
* ``501 Not Implemented`` — engine raised
  :class:`EngineUnavailableError` (e.g. MCsquare/CCC backend missing).

Endpoints
---------
``POST   /api/v1/dose/compute``                   — build / reuse nominal dose.
``POST   /api/v1/dose/influence``                 — build / reuse Dij matrix.
``GET    /api/v1/dose/{dose_id}``                 — retrieve dose result.
``GET    /api/v1/dose/{dose_id}/artifact``        — stream the dose NIfTI.
``DELETE /api/v1/dose/{dose_id}``                 — drop from cache.
``GET    /api/v1/dose/influence/{influence_id}``  — retrieve influence result.
``DELETE /api/v1/dose/influence/{influence_id}``  — drop from cache.
``GET    /api/v1/dose/jobs/{job_id}``             — poll an async dose/influence job.

The compute and influence endpoints share a single job table (kind='dose'
or 'influence') so there's only one polling endpoint.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from ._lineage_guard import assert_deletable
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ...core.store import store
from ...models.dose import (
    DoseComputeRequest,
    DoseJobStatus,
    DoseResult,
    EngineSpec,
    InfluenceBuildRequest,
    InfluenceResult,
    ScenarioSetSpec,
    WeightVector,
)
from ...services.audit import audit_span, emit, make_event
from ...services.dose import DoseService
from ...services.dose_engines import (
    EngineRegistryError,
    engine_health,
    list_engines,
)
from ...services.dose_engines.protocol import EngineUnavailableError
from ...services.dose_persistence import DOSE_FILENAME, INFLUENCE_FILENAME
from ..security import api_key_auth

# All routes in this router require a valid API key when one is
# configured (D8.2). The dependency is a no-op when api_key is empty.
router = APIRouter(
    prefix="/dose",
    tags=["dose"],
)


@lru_cache(maxsize=1)
def _service() -> DoseService:
    """Singleton service instance, reused across requests."""
    return DoseService()


# ---------------------------------------------------------------------------
# Async-dispatch response shape
# ---------------------------------------------------------------------------

class DoseBuildResponse(BaseModel):
    """Returned by ``POST /compute`` / ``POST /influence`` on cache miss."""

    job_id: str
    cache_key: str
    kind: str
    state: str = "queued"
    message: str = (
        "Build dispatched; poll /dose/jobs/{job_id} for progress."
    )


# ---------------------------------------------------------------------------
# D6.7 — Engine health-check endpoints
# ---------------------------------------------------------------------------

class EngineSummary(BaseModel):
    """One entry in the engine listing."""

    name: str
    version: str = ""
    modalities: List[str] = []
    available: bool = False
    registered: bool = True
    test_only: bool = False


@router.get(
    "/engines",
    summary="List registered dose engines and availability.",
    response_model=List[EngineSummary],
)
async def get_engines() -> List[EngineSummary]:
    """Lightweight snapshot — one line per engine, no diagnostics."""
    out: List[EngineSummary] = []
    for name in list_engines():
        h = engine_health(name)
        out.append(EngineSummary(
            name=h.get("name", name),
            version=h.get("version", ""),
            modalities=h.get("modalities", []),
            available=bool(h.get("available", False)),
            registered=bool(h.get("registered", True)),
            test_only=bool(h.get("test_only", False)),
        ))
    return out


@router.get(
    "/engines/{name}",
    summary="Full health-check payload for one engine.",
)
async def get_engine_health(name: str) -> dict:
    """Returns the engine's ``health()`` dict including diagnostics.

    Returns 404 if the engine isn't registered; returns 200 with
    ``available: false`` if registered but the backend isn't loadable
    (e.g. MCsquare binary missing). Distinguishing "doesn't exist"
    from "exists but broken" is the whole point of this endpoint.
    """
    if name not in list_engines():
        raise HTTPException(
            status_code=404,
            detail=f"Engine not registered: {name}",
        )
    return engine_health(name)


# ---------------------------------------------------------------------------
# POST /compute
# ---------------------------------------------------------------------------

@router.post(
    "/compute",
    summary="Compute (or reuse cached) dose from geometry + beam model + weights.",
    responses={
        200: {"description": "Cache hit — returned the existing dose inline."},
        202: {"description": "Cache miss — Celery job dispatched."},
        401: {"description": "Missing / invalid API key."},
        422: {"description": "Request validation error."},
    },
)
async def compute_dose(
    request: DoseComputeRequest,
    response: Response,
    api_key_prefix: Optional[str] = Depends(api_key_auth),
):
    try:
        cache_key = request.compute_cache_key()
        service = _service()
        cached = service.dose_store.lookup_by_cache_key(cache_key)
        if cached is not None:
            response.status_code = status.HTTP_200_OK
            emit(make_event(
                "dose.compute",
                state="cache_hit",
                cache_key=cache_key,
                dose_id=cached.dose_id,
                geometry_id=request.geometry_id,
                beam_model_id=request.beam_model_id,
                engine_name=request.engine.name,
                engine_version=request.engine.version,
                api_key_prefix=api_key_prefix,
            ))
            return cached

        job = store.create_dose_job(cache_key, kind="dose")
        from ...tasks.dose_tasks import build_dose_job
        build_dose_job.delay(job.id, request.model_dump(mode="json"))
        response.status_code = status.HTTP_202_ACCEPTED
        emit(make_event(
            "dose.compute",
            state="dispatched",
            cache_key=cache_key,
            geometry_id=request.geometry_id,
            beam_model_id=request.beam_model_id,
            engine_name=request.engine.name,
            engine_version=request.engine.version,
            api_key_prefix=api_key_prefix,
            extra={"job_id": job.id},
        ))
        return DoseBuildResponse(job_id=job.id, cache_key=cache_key, kind="dose")

    except (ValueError, EngineRegistryError) as exc:
        emit(make_event(
            "dose.compute",
            state="failed",
            geometry_id=request.geometry_id,
            beam_model_id=request.beam_model_id,
            engine_name=request.engine.name,
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
            api_key_prefix=api_key_prefix,
        ))
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# POST /recalculate — dose from an imported DICOM RT Plan (roadmap R2)
# ---------------------------------------------------------------------------

class DoseRecalculateRequest(BaseModel):
    """Recompute the dose of a plan imported with ``POST /beam-model/import``:
    the same pipeline as ``/compute`` with the plan's own metersets as weights."""

    plan_id: Optional[str] = Field(default=None, max_length=36)
    geometry_id: str = Field(..., min_length=1, max_length=36)
    beam_model_id: str = Field(..., min_length=1, max_length=36, description="An imported plan's beam model.")
    engine: EngineSpec
    scenarios: Optional[ScenarioSetSpec] = None
    rbe: Optional[float] = Field(default=None, gt=0.0, le=2.0, description="Null = 1.1 for protons, 1.0 for photons.")


@router.post(
    "/recalculate",
    summary="Compute the dose of an imported RT Plan with the plan's own metersets.",
    responses={
        200: {"description": "Cache hit — returned the existing dose inline."},
        202: {"description": "Cache miss — Celery job dispatched."},
        422: {"description": "Not an imported plan, or the request is invalid."},
    },
)
async def recalculate_dose(
    request: DoseRecalculateRequest,
    response: Response,
    api_key_prefix: Optional[str] = Depends(api_key_auth),
):
    from pathlib import Path as _Path
    from ...services.beam_persistence import BeamModelStore
    from ...config import get_settings

    bm = BeamModelStore(_Path(get_settings().artifact_dir) / "beam_models").get_by_id(request.beam_model_id)
    if bm is None:
        raise HTTPException(status_code=422, detail=f"beam_model_id {request.beam_model_id!r} not found")
    if not bm.plan_weights_uri or not _Path(bm.plan_weights_uri).is_file():
        raise HTTPException(status_code=422, detail="beam model was not imported from an RT Plan (no plan metersets); use /dose/compute with explicit weights")
    if bm.geometry_id != request.geometry_id:
        raise HTTPException(status_code=422, detail=f"beam model {request.beam_model_id} belongs to geometry {bm.geometry_id}, not {request.geometry_id}")
    compute_request = DoseComputeRequest(
        plan_id=request.plan_id,
        geometry_id=request.geometry_id,
        beam_model_id=request.beam_model_id,
        engine=request.engine,
        weights=WeightVector(length=bm.fluence_elements.total_count, weights_uri=bm.plan_weights_uri),
        scenarios=request.scenarios,
        rbe=request.rbe,
    )
    return await compute_dose(compute_request, response, api_key_prefix)


# ---------------------------------------------------------------------------
# POST /influence
# ---------------------------------------------------------------------------

@router.post(
    "/influence",
    summary="Build (or reuse cached) influence Dij matrix.",
    responses={
        200: {"description": "Cache hit."},
        202: {"description": "Cache miss — Celery job dispatched."},
        401: {"description": "Missing / invalid API key."},
        422: {"description": "Request validation error."},
    },
)
async def build_influence(
    request: InfluenceBuildRequest,
    response: Response,
    api_key_prefix: Optional[str] = Depends(api_key_auth),
):
    try:
        cache_key = request.compute_cache_key()
        service = _service()
        cached = service.influence_store.lookup_by_cache_key(cache_key)
        if cached is not None:
            response.status_code = status.HTTP_200_OK
            emit(make_event(
                "dose.influence",
                state="cache_hit",
                cache_key=cache_key,
                influence_id=cached.influence_id,
                geometry_id=request.geometry_id,
                beam_model_id=request.beam_model_id,
                engine_name=request.engine.name,
                api_key_prefix=api_key_prefix,
            ))
            return cached

        job = store.create_dose_job(cache_key, kind="influence")
        from ...tasks.dose_tasks import build_influence_job
        build_influence_job.delay(job.id, request.model_dump(mode="json"))
        response.status_code = status.HTTP_202_ACCEPTED
        emit(make_event(
            "dose.influence",
            state="dispatched",
            cache_key=cache_key,
            geometry_id=request.geometry_id,
            beam_model_id=request.beam_model_id,
            engine_name=request.engine.name,
            api_key_prefix=api_key_prefix,
            extra={"job_id": job.id},
        ))
        return DoseBuildResponse(job_id=job.id, cache_key=cache_key, kind="influence")

    except (ValueError, EngineRegistryError) as exc:
        emit(make_event(
            "dose.influence",
            state="failed",
            geometry_id=request.geometry_id,
            beam_model_id=request.beam_model_id,
            engine_name=request.engine.name,
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
            api_key_prefix=api_key_prefix,
        ))
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------

@router.get(
    "/jobs/{job_id}",
    response_model=DoseJobStatus,
    summary="Poll an async dose/influence build job.",
)
async def get_dose_job(job_id: str) -> DoseJobStatus:
    job = store.get_dose_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail=f"Dose job not found: {job_id}"
        )
    return job


# ---------------------------------------------------------------------------
# Dose result + artifact + delete
# ---------------------------------------------------------------------------

@router.get(
    "/{dose_id}",
    response_model=DoseResult,
    summary="Retrieve completed dose metadata.",
)
async def get_dose(dose_id: str) -> DoseResult:
    result = _service().dose_store.get_by_id(dose_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Dose not found: {dose_id}"
        )
    return result


@router.delete(
    "/{dose_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a cached dose.",
)
async def delete_dose(dose_id: str):
    svc = _service()
    if svc.dose_store.get_by_id(dose_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Dose not found: {dose_id}"
        )
    assert_deletable("dose", dose_id)
    svc.dose_store.delete_by_id(dose_id)
    return Response(status_code=204)


@router.get(
    "/{dose_id}/artifact",
    summary="Stream the dose NIfTI volume.",
    response_class=FileResponse,
)
async def get_dose_artifact(dose_id: str):
    svc = _service()
    if svc.dose_store.get_by_id(dose_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Dose not found: {dose_id}"
        )
    dose_path = svc.dose_store.base_dir / dose_id / DOSE_FILENAME
    if not os.path.isfile(dose_path):
        raise HTTPException(
            status_code=410, detail=f"{DOSE_FILENAME} no longer on disk"
        )
    return FileResponse(
        path=str(dose_path),
        media_type="application/octet-stream",
        filename=DOSE_FILENAME,
    )


# ---------------------------------------------------------------------------
# Influence result + delete
# ---------------------------------------------------------------------------

@router.get(
    "/influence/{influence_id}",
    response_model=InfluenceResult,
    summary="Retrieve influence-matrix metadata.",
)
async def get_influence(influence_id: str) -> InfluenceResult:
    result = _service().influence_store.get_by_id(influence_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Influence not found: {influence_id}"
        )
    return result


@router.delete(
    "/influence/{influence_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a cached influence matrix.",
)
async def delete_influence(influence_id: str):
    svc = _service()
    if svc.influence_store.get_by_id(influence_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Influence not found: {influence_id}"
        )
    assert_deletable("influence", influence_id)
    svc.influence_store.delete_by_id(influence_id)
    return Response(status_code=204)


@router.get(
    "/influence/{influence_id}/artifact",
    summary="Stream the sparse Dij matrix (.npz).",
    response_class=FileResponse,
)
async def get_influence_artifact(influence_id: str):
    svc = _service()
    if svc.influence_store.get_by_id(influence_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Influence not found: {influence_id}"
        )
    dij_path = svc.influence_store.base_dir / influence_id / INFLUENCE_FILENAME
    if not os.path.isfile(dij_path):
        raise HTTPException(
            status_code=410, detail=f"{INFLUENCE_FILENAME} no longer on disk"
        )
    return FileResponse(
        path=str(dij_path),
        media_type="application/octet-stream",
        filename=INFLUENCE_FILENAME,
    )
