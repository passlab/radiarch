"""FastAPI routes for multi-criteria optimization (R11).

Endpoints
---------
``POST /api/v1/mco/run``            — the Pareto set of a beam model: the cached set (200) or a job (202).
``GET  /api/v1/mco/jobs/{job_id}``  — a run's progress.
``GET  /api/v1/mco/{mco_id}``       — a Pareto set: its plans, objective values and error bound.
``POST /api/v1/mco/{mco_id}/navigate``            — a slider move, a reference point or clamps: a navigation state.
``POST /api/v1/mco/{mco_id}/auto-navigate``       — the blend that best meets a goal set, priority by priority.
``GET  /api/v1/mco/{mco_id}/states``              — the stored states, the balance plan first.
``GET  /api/v1/mco/{mco_id}/states/{state_id}``   — one state.
``POST /api/v1/mco/{mco_id}/deliverable``         — a state made deliverable: the cached plan (200) or a job (202).
``GET  /api/v1/mco/deliverables/jobs/{job_id}``   — its progress.
``GET  /api/v1/mco/deliverables/{deliverable_id}`` — the deliverable plan and its deviation table.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from ...core.store import store
from ...models.mco import AutoNavigateRequest, DeliverableJobStatus, DeliverableRequest, MCODeliverable, MCOJobStatus, MCORunRequest, MCOResult, NavigateRequest, NavigationState
from ...services.audit import emit, make_event
from ...services.mco import MCOService
from ...services.mco_deliverable import DeliverableRefused, DeliverableService
from ...services.navigation import NavigationError, NavigationService
from ..security import api_key_auth

router = APIRouter(prefix="/mco", tags=["mco"])


@lru_cache(maxsize=1)
def _service() -> MCOService:
    return MCOService()


@lru_cache(maxsize=1)
def _navigation() -> NavigationService:
    return NavigationService(_service().store)


@lru_cache(maxsize=1)
def _deliverables() -> DeliverableService:
    return DeliverableService(mco_service=_service())


def _known(mco_id: str) -> None:
    if _service().store.get_by_id(mco_id) is None:
        raise HTTPException(status_code=404, detail=f"Pareto set not found: {mco_id}")


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


class DeliverableResponse(BaseModel):
    job_id: str
    cache_key: str
    state: str = "queued"
    message: str = "Dispatched; poll /mco/deliverables/jobs/{job_id} for progress."


@router.get("/deliverables/jobs/{job_id}", response_model=DeliverableJobStatus, summary="A deliverable plan's progress.")
async def get_deliverable_job(job_id: str) -> DeliverableJobStatus:
    job = store.get_deliverable_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Deliverable job not found: {job_id}")
    return job


@router.get("/deliverables", response_model=List[MCODeliverable], summary="Deliverable plans by their dose or beam model (R11.7).")
async def find_deliverables(dose_id: Optional[str] = None, beam_model_id: Optional[str] = None, limit: int = 20) -> List[MCODeliverable]:
    """The deliverable plans that made a dose or a beam model, newest first: how a viewer finds the Pareto set behind the
    dose on screen. With neither filter, the newest plans."""
    found = _deliverables().store.find(dose_id=dose_id, beam_model_id=beam_model_id)
    return found[: max(1, min(int(limit), 200))]


@router.get("/deliverables/{deliverable_id}", response_model=MCODeliverable, summary="A deliverable plan and its deviation table.")
async def get_deliverable(deliverable_id: str) -> MCODeliverable:
    result = _deliverables().store.get_by_id(deliverable_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Deliverable plan not found: {deliverable_id}")
    return result


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


@router.post("/{mco_id}/navigate", response_model=NavigationState, summary="Navigate the Pareto set (R11.3).",
             responses={404: {"description": "Unknown Pareto set or state."},
                        422: {"description": "An unknown objective, or no blend meets the clamps."}})
async def navigate(mco_id: str, request: NavigateRequest) -> NavigationState:
    _known(mco_id)
    try:
        return _navigation().navigate(mco_id, request)
    except NavigationError as exc:
        raise HTTPException(status_code=404 if "no state" in str(exc) else 422, detail=str(exc)) from exc
    except ValueError as exc:                     # a goal template or metric the grader refuses
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{mco_id}/auto-navigate", response_model=NavigationState, summary="Automatic navigation by goal priority (R11.4).",
             responses={404: {"description": "Unknown Pareto set or state."},
                        422: {"description": "An unknown objective or template, a goal needing a prescription, or clamps no blend meets."}})
async def auto_navigate(mco_id: str, request: AutoNavigateRequest) -> NavigationState:
    _known(mco_id)
    try:
        return _navigation().auto_navigate(mco_id, request)
    except NavigationError as exc:
        raise HTTPException(status_code=404 if "no state" in str(exc) else 422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{mco_id}/states", response_model=List[NavigationState], summary="The stored navigation states.")
async def list_states(mco_id: str) -> List[NavigationState]:
    _known(mco_id)
    return _navigation().list_states(mco_id)


@router.get("/{mco_id}/states/{state_id}", response_model=NavigationState, summary="One navigation state.")
async def get_state(mco_id: str, state_id: str) -> NavigationState:
    _known(mco_id)
    state = _navigation().get_state(mco_id, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"no state {state_id!r} in Pareto set {mco_id}")
    return state


@router.post("/{mco_id}/deliverable", summary="A navigation state made deliverable (R11.5).",
             responses={200: {"description": "Made before: the stored plan."}, 202: {"description": "A job: poll /mco/deliverables/jobs/{job_id}."},
                        404: {"description": "Unknown Pareto set or state."},
                        422: {"description": "A robust photon Pareto set (robust deliverables are made for protons)."}})
async def make_deliverable(mco_id: str, request: DeliverableRequest, response: Response,
                           api_key_prefix: Optional[str] = Depends(api_key_auth)):
    _known(mco_id)
    try:
        key = _deliverables().cache_key(mco_id, request)
    except DeliverableRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    cached = _deliverables().store.lookup_by_cache_key(key)
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return cached
    job = store.create_deliverable_job(key)
    from ...tasks.mco_tasks import run_deliverable_job

    run_deliverable_job.delay(job.id, mco_id, request.model_dump(mode="json"))
    response.status_code = status.HTTP_202_ACCEPTED
    emit(make_event("mco.deliverable", state="dispatched", cache_key=key, api_key_prefix=api_key_prefix,
                    extra={"job_id": job.id, "mco_id": mco_id, "state_id": request.state_id}))
    return DeliverableResponse(job_id=job.id, cache_key=key)
