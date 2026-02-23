from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ...core.store import store
from ...models.plan import PlanDetail, PlanRequest, PlanSummary
from ...models.job import JobState
from ...tasks.plan_tasks import run_plan_job

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", response_model=list[PlanSummary])
async def list_plans():
    return store.list_plans()


@router.post("", response_model=PlanDetail, status_code=201)
async def create_plan(request: PlanRequest):
    plan, job = store.create_plan(request)
    run_plan_job.delay(job.id, plan.id)
    return plan


@router.get("/{plan_id}", response_model=PlanDetail)
async def get_plan(plan_id: str):
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.delete("/{plan_id}", status_code=204, response_class=Response)
async def delete_plan(plan_id: str):
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.job_id:
        store.update_job(plan.job_id, state=JobState.cancelled, message="Cancelled by user")
    store.delete_plan(plan_id)
    return Response(status_code=204)

