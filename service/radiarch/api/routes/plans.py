from fastapi import APIRouter, HTTPException

from ...core.store import store
from ...models.plan import PlanDetail, PlanRequest, PlanSummary

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=list[PlanSummary])
async def list_plans():
    return store.list_plans()


@router.post("", response_model=PlanDetail, status_code=201)
async def create_plan(request: PlanRequest):
    plan, _ = store.create_plan(request)
    return plan


@router.get("/{plan_id}", response_model=PlanDetail)
async def get_plan(plan_id: str):
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan
