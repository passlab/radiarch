"""FastAPI routes for the Evaluation Service (Service 6).

Mirrors ``api/routes/optimization.py``: router-level auth, the
200/202/422/401 contract, audit emission.

Endpoints
---------
``POST   /api/v1/evaluate/run``                — run / reuse cached evaluation.
``GET    /api/v1/evaluate/jobs/{job_id}``      — poll an async run.
``GET    /api/v1/evaluate/{evaluation_id}``    — retrieve the report.
``DELETE /api/v1/evaluate/{evaluation_id}``    — drop from cache.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from ...core.store import store
from ...models.evaluation import (
    EvaluationJobStatus,
    EvaluationRequest,
    EvaluationResult,
)
from ...services.audit import emit, make_event
from ...services.evaluation import EvaluationService
from ..security import api_key_auth

router = APIRouter(
    prefix="/evaluate",
    tags=["evaluation"],
)


@lru_cache(maxsize=1)
def _service() -> EvaluationService:
    return EvaluationService()


# ---------------------------------------------------------------------------
# Clinical goals, radiobiology models and comparisons (R5)
# ---------------------------------------------------------------------------

@router.get("/goal-templates", summary="The clinical-goal templates that ship with radiarch.")
async def list_goal_templates() -> list:
    from ...services.clinical_goals import builtin_templates, load_template

    out = []
    for tid in builtin_templates():
        t = load_template(tid)
        out.append({"template_id": tid, "name": t.name, "site": t.site, "dose_basis": t.dose_basis, "n_goals": len(t.goals),
                    "provisional": t.provisional, "source": t.source})
    return out


@router.get("/goal-templates/{template_id}", summary="A clinical-goal template in full.")
async def get_goal_template(template_id: str) -> dict:
    from ...services.clinical_goals import load_template

    try:
        return load_template(template_id).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/models", summary="The NTCP and TCP parameter sets that ship with radiarch, with their sources.")
async def list_radiobiology_models() -> dict:
    from ...services.radiobiology import DEFAULT_ALPHA_BETA, NTCP_MODELS, TCP_MODELS

    return {"ntcp": [m.model_dump() for m in NTCP_MODELS.values()], "tcp": [m.model_dump() for m in TCP_MODELS.values()],
            "default_alpha_beta_gy": DEFAULT_ALPHA_BETA}


class CompareRequest(BaseModel):
    """Two evaluations side by side: ``a`` and ``b`` are evaluation requests (run or reused) or evaluation ids."""

    a: Optional[EvaluationRequest] = None
    b: Optional[EvaluationRequest] = None
    evaluation_id_a: Optional[str] = None
    evaluation_id_b: Optional[str] = None
    structures: Optional[list] = None


@router.post("/compare", summary="dvh_impact: the DVH metrics, indices and goal states of two evaluations and their differences (b − a).")
async def compare(request: CompareRequest, api_key_prefix: Optional[str] = Depends(api_key_auth)) -> dict:
    from ...services.dose_compare import compare_evaluations

    service = _service()

    def resolve(req, eid, label):
        if eid:
            r = service.store.get_by_id(eid)
            if r is None:
                raise HTTPException(status_code=404, detail=f"evaluation {eid!r} not found")
            return r
        if req is None:
            raise HTTPException(status_code=422, detail=f"compare needs {label} or evaluation_id_{label}")
        try:
            return service.run(req)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{label}: {exc}") from exc

    a = resolve(request.a, request.evaluation_id_a, "a")
    b = resolve(request.b, request.evaluation_id_b, "b")
    return compare_evaluations(a, b, request.structures)


class EvaluationRunResponse(BaseModel):
    job_id: str
    cache_key: str
    state: str = "queued"
    message: str = "Run dispatched; poll /evaluate/jobs/{job_id} for progress."


@router.post(
    "/run",
    summary="Run (or reuse cached) plan evaluation (DVH + indices + gamma).",
    responses={
        200: {"description": "Cache hit — returned the existing report inline."},
        202: {"description": "Cache miss — Celery job dispatched."},
        401: {"description": "Missing / invalid API key."},
        422: {"description": "Request validation error."},
    },
)
async def run_evaluation(
    request: EvaluationRequest,
    response: Response,
    api_key_prefix: Optional[str] = Depends(api_key_auth),
):
    try:
        cache_key = request.compute_cache_key()
        service = _service()
        cached = service.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            response.status_code = status.HTTP_200_OK
            emit(make_event(
                "evaluate.run", state="cache_hit", cache_key=cache_key,
                geometry_id=request.geometry_id, dose_id=request.dose_id,
                api_key_prefix=api_key_prefix,
                extra={"evaluation_id": cached.evaluation_id},
            ))
            return cached

        job = store.create_evaluation_job(cache_key)
        from ...tasks.evaluation_tasks import run_evaluation_job
        run_evaluation_job.delay(job.id, request.model_dump(mode="json"))
        response.status_code = status.HTTP_202_ACCEPTED
        emit(make_event(
            "evaluate.run", state="dispatched", cache_key=cache_key,
            geometry_id=request.geometry_id, dose_id=request.dose_id,
            api_key_prefix=api_key_prefix, extra={"job_id": job.id},
        ))
        return EvaluationRunResponse(job_id=job.id, cache_key=cache_key)

    except ValueError as exc:
        emit(make_event(
            "evaluate.run", state="failed",
            geometry_id=request.geometry_id, dose_id=request.dose_id,
            error_type=type(exc).__name__, error_message=str(exc)[:200],
            api_key_prefix=api_key_prefix,
        ))
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/jobs/{job_id}",
    response_model=EvaluationJobStatus,
    summary="Poll an async evaluation run.",
)
async def get_evaluation_job(job_id: str) -> EvaluationJobStatus:
    job = store.get_evaluation_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Evaluation job not found: {job_id}")
    return job


@router.get(
    "/{evaluation_id}",
    response_model=EvaluationResult,
    summary="Retrieve a completed evaluation report.",
)
async def get_evaluation(evaluation_id: str) -> EvaluationResult:
    result = _service().store.get_by_id(evaluation_id)
    if result is None:
        raise HTTPException(status_code=404,
                            detail=f"Evaluation not found: {evaluation_id}")
    return result


@router.delete(
    "/{evaluation_id}",
    status_code=204,
    response_class=Response,
    summary="Delete a cached evaluation report.",
)
async def delete_evaluation(evaluation_id: str):
    svc = _service()
    if svc.store.get_by_id(evaluation_id) is None:
        raise HTTPException(status_code=404,
                            detail=f"Evaluation not found: {evaluation_id}")
    svc.store.delete_by_id(evaluation_id)
    return Response(status_code=204)
