"""FastAPI routes for adaptive replanning (R9): a plan checked on a later image of the patient.

Endpoints
---------
``POST /api/v1/replan/assess``    — register, propagate, recompute the plan on the day's anatomy, compare the goals.
``GET  /api/v1/replan/{id}``      — an assessment.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from ...models.replan import ReplanAssessment, ReplanAssessRequest
from ...services.replan import ReplanError, ReplanService

router = APIRouter(prefix="/replan", tags=["replan"])


@lru_cache(maxsize=1)
def _service() -> ReplanService:
    return ReplanService()


# A plain ``def`` route: registration and dose recomputation take seconds to minutes (FastAPI's thread pool).

@router.post("/assess", response_model=ReplanAssessment,
             summary="A plan on a later image: registration, propagated structures, the plan recomputed on the day, goals compared (R9).")
def assess(request: ReplanAssessRequest) -> ReplanAssessment:
    from ...services.dose_engines.protocol import EngineParamError, EngineUnavailableError
    from ...services.four_d import FourDError
    from ...services.registration import RegistrationError

    try:
        return _service().assess(request)
    except (ReplanError, FourDError, RegistrationError, EngineParamError, EngineUnavailableError, ValueError) as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc


@router.get("/{assessment_id}", response_model=ReplanAssessment, summary="A replanning assessment.")
async def get_assessment(assessment_id: str) -> ReplanAssessment:
    a = _service().store.get_by_id(assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Assessment not found: {assessment_id}")
    return a
