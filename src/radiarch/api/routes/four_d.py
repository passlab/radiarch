"""FastAPI routes for 4D planning (R9): the average-intensity CT, the ITV, phase doses and their accumulation.

Endpoints
---------
``POST /api/v1/four-d/average``       — the average-intensity CT of a 4DCT's phases, as a derived geometry.
``POST /api/v1/four-d/itv``           — a target's union over the phases, added to a geometry.
``POST /api/v1/four-d/phase-doses``   — a plan with metersets recomputed on each phase.
``POST /api/v1/four-d/accumulate``    — phase doses mapped onto a reference phase and summed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from fastapi import APIRouter, HTTPException

from ...models.dose import DoseResult
from ...models.four_d import AccumulateRequest, AverageCTRequest, ITVRequest, PhaseDoseRequest
from ...models.geometry import GeometryResult
from ...services.four_d import FourDError, FourDService

router = APIRouter(prefix="/four-d", tags=["4d"])


@lru_cache(maxsize=1)
def _service() -> FourDService:
    return FourDService()


def _run(fn, request):
    from ...services.dose_engines.protocol import EngineParamError, EngineUnavailableError
    from ...services.registration import RegistrationError

    try:
        return fn(request)
    except (FourDError, RegistrationError, EngineParamError, EngineUnavailableError, ValueError) as exc:
        status = 404 if "not found" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc


# Plain ``def`` routes: the work blocks for seconds to minutes, so FastAPI runs it in its thread pool.

@router.post("/average", response_model=GeometryResult, summary="The average-intensity CT of a 4DCT's phases, as a derived geometry (R9).")
def average(request: AverageCTRequest) -> GeometryResult:
    return _run(_service().average, request)


@router.post("/itv", response_model=GeometryResult, summary="A target's union over the breathing phases, added to a geometry (R9).")
def itv(request: ITVRequest) -> GeometryResult:
    return _run(_service().itv, request)


@router.post("/phase-doses", response_model=List[DoseResult], summary="A plan with metersets recomputed on each phase's CT (R9).")
def phase_doses(request: PhaseDoseRequest) -> List[DoseResult]:
    return _run(_service().phase_doses, request)


@router.post("/accumulate", response_model=DoseResult, summary="Phase doses mapped onto a reference phase and summed by their shares (R9).")
def accumulate(request: AccumulateRequest) -> DoseResult:
    return _run(_service().accumulate, request)
