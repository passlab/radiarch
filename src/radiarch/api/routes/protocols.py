"""FastAPI routes for planning protocols and auto-planning (R10).

Endpoints
---------
``GET  /api/v1/protocols``                 — the shipped protocols.
``GET  /api/v1/protocols/{protocol_id}``   — one protocol in full.
``POST /api/v1/protocols/run``             — run a protocol on a geometry: the cached run (200) or a job (202).
``GET  /api/v1/protocols/jobs/{job_id}``   — a run's progress.
``GET  /api/v1/protocols/runs/{run_id}``   — a run: the deliverable plan, its dose, its goals.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from ...core.store import store
from ...models.protocol import AutoplanJobStatus, PlanningProtocol, ProtocolRunRequest, ProtocolRunResult
from ...services.audit import emit, make_event
from ...services.autoplan import AutoplanError, AutoplanService, builtin_protocols, load_protocol
from ..security import api_key_auth

router = APIRouter(prefix="/protocols", tags=["protocols"])


@lru_cache(maxsize=1)
def _service() -> AutoplanService:
    return AutoplanService()


class ProtocolRunResponse(BaseModel):
    job_id: str
    cache_key: str
    state: str = "queued"
    message: str = "Run dispatched; poll /protocols/jobs/{job_id} for progress."


@router.get("", summary="The planning protocols that ship with radiarch.")
async def list_protocols() -> list:
    out = []
    for pid in builtin_protocols():
        p = load_protocol(pid)
        out.append({"protocol_id": pid, "name": p.name, "site": p.site, "version": p.version, "technique": p.beams.technique,
                    "prescription": p.prescription.model_dump(), "source": p.source})
    return out


@router.get("/jobs/{job_id}", response_model=AutoplanJobStatus, summary="A protocol run's progress.")
async def get_job(job_id: str) -> AutoplanJobStatus:
    job = store.get_autoplan_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Protocol job not found: {job_id}")
    return job


@router.get("/runs/{run_id}", response_model=ProtocolRunResult, summary="A protocol run.")
async def get_run(run_id: str) -> ProtocolRunResult:
    run = _service().store.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Protocol run not found: {run_id}")
    return run


@router.get("/{protocol_id}", response_model=PlanningProtocol, summary="A shipped protocol in full.")
async def get_protocol(protocol_id: str) -> PlanningProtocol:
    try:
        return load_protocol(protocol_id)
    except AutoplanError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/run", summary="Run a planning protocol on a geometry (R10).",
             responses={200: {"description": "The same protocol ran on this geometry before: its run."},
                        202: {"description": "A job: poll /protocols/jobs/{job_id}."},
                        404: {"description": "Unknown geometry or protocol."}, 422: {"description": "An invalid protocol."}})
async def run_protocol(request: ProtocolRunRequest, response: Response, api_key_prefix: Optional[str] = Depends(api_key_auth)):
    try:
        key = _service().cache_key(request)
    except AutoplanError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    cached = _service().store.lookup_by_cache_key(key)
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        emit(make_event("autoplan.run", state="cache_hit", cache_key=key, geometry_id=request.geometry_id,
                        api_key_prefix=api_key_prefix, extra={"run_id": cached.run_id}))
        return cached
    job = store.create_autoplan_job(key)
    from ...tasks.autoplan_tasks import run_autoplan_job

    run_autoplan_job.delay(job.id, request.model_dump(mode="json"))
    response.status_code = status.HTTP_202_ACCEPTED
    emit(make_event("autoplan.run", state="dispatched", cache_key=key, geometry_id=request.geometry_id, api_key_prefix=api_key_prefix,
                    extra={"job_id": job.id}))
    return ProtocolRunResponse(job_id=job.id, cache_key=key)
