"""FastAPI routes for multi-criteria optimization (R11).

Endpoints
---------
``POST /api/v1/mco/run``            — the Pareto set of a beam model: the cached set (200) or a job (202).
``GET  /api/v1/mco/jobs/{job_id}``  — a run's progress.
``GET  /api/v1/mco/{mco_id}``       — a Pareto set: its plans, objective values and error bound.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from ...core.store import store
from ...models.mco import MCOJobStatus, MCORunRequest, MCOResult
from ...services.audit import emit, make_event
from ...services.mco import MCOService
from ..security import api_key_auth

router = APIRouter(prefix="/mco", tags=["mco"])


@lru_cache(maxsize=1)
def _service() -> MCOService:
    return MCOService()


class MCORunResponse(BaseModel):
    job_id: str
    cache_key: str
    state: str = "queued"
    message: str = "Run dispatched; poll /mco/jobs/{job_id} for progress."


@router.post("/run", summary="The Pareto set of a beam model (R11).",
             responses={200: {"description": "The same set was computed before."}, 202: {"description": "A job: poll /mco/jobs/{job_id}."},
                        422: {"description": "Not trade-off objectives, or invalid constraints."}})
async def run_mco(request: MCORunRequest, response: Response, api_key_prefix: Optional[str] = Depends(api_key_auth)):
    key = request.compute_cache_key()
    cached = _service().store.lookup_by_cache_key(key)
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        emit(make_event("mco.run", state="cache_hit", cache_key=key, geometry_id=request.geometry_id, beam_model_id=request.beam_model_id,
                        api_key_prefix=api_key_prefix, extra={"mco_id": cached.mco_id}))
        return cached
    job = store.create_mco_job(key)
    from ...tasks.mco_tasks import run_mco_job

    run_mco_job.delay(job.id, request.model_dump(mode="json"))
    response.status_code = status.HTTP_202_ACCEPTED
    emit(make_event("mco.run", state="dispatched", cache_key=key, geometry_id=request.geometry_id, beam_model_id=request.beam_model_id,
                    api_key_prefix=api_key_prefix, extra={"job_id": job.id}))
    return MCORunResponse(job_id=job.id, cache_key=key)


@router.get("/jobs/{job_id}", response_model=MCOJobStatus, summary="An MCO run's progress.")
async def get_job(job_id: str) -> MCOJobStatus:
    job = store.get_mco_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"MCO job not found: {job_id}")
    return job


@router.get("/{mco_id}", response_model=MCOResult, summary="A Pareto set.")
async def get_mco(mco_id: str) -> MCOResult:
    result = _service().store.get_by_id(mco_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Pareto set not found: {mco_id}")
    return result
