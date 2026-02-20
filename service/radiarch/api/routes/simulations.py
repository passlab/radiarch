"""API routes for delivery simulation (Phase 8D).

POST /simulations     — Start a simulation for a completed plan
GET  /simulations     — List all simulations
GET  /simulations/{id} — Get simulation result
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ...core.store import store
from ...models.simulation import (
    SimulationRequest,
    SimulationResult,
    SimulationStatus,
    SimulationSummary,
)
from ...core.simulator import DeliverySimulator

router = APIRouter(prefix="/simulations", tags=["simulations"])

# In-memory simulation store (mirrors plan/job pattern)
_simulations: dict[str, SimulationResult] = {}

simulator = DeliverySimulator()


def _utcnow():
    return datetime.now(timezone.utc)


@router.post("", response_model=SimulationSummary, status_code=201)
async def create_simulation(request: SimulationRequest):
    """Submit a delivery simulation for a completed plan."""
    # Verify plan exists and has a QA summary
    plan = store.get_plan(request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan not found: {request.plan_id}")
    if not plan.qa_summary:
        raise HTTPException(
            status_code=400,
            detail="Plan has no QA summary — must complete planning before simulation",
        )

    sim_id = str(uuid.uuid4())
    now = _utcnow()

    # Create initial record
    result = SimulationResult(
        id=sim_id,
        plan_id=request.plan_id,
        status=SimulationStatus.running,
        created_at=now,
        updated_at=now,
        motion_amplitude_mm=request.motion_amplitude_mm,
        notes=request.notes,
    )
    _simulations[sim_id] = result

    # Run simulation synchronously (in dev/eager mode)
    # For production, this would be a Celery task
    try:
        sim_result = simulator.run(request, plan.qa_summary)
        result.status = SimulationStatus.succeeded
        result.delivered_dose_max_gy = sim_result.get("delivered_dose_max_gy")
        result.delivered_dose_mean_gy = sim_result.get("delivered_dose_mean_gy")
        result.gamma_pass_rate = sim_result.get("gamma_pass_rate")
        result.dose_difference_pct = sim_result.get("dose_difference_pct")
        result.artifact_path = sim_result.get("artifact_path")
        result.qa_metrics = sim_result
        result.updated_at = _utcnow()
    except Exception as exc:
        result.status = SimulationStatus.failed
        result.notes = f"Simulation failed: {exc}"
        result.updated_at = _utcnow()

    return SimulationSummary(
        id=result.id,
        plan_id=result.plan_id,
        status=result.status,
        created_at=result.created_at,
        updated_at=result.updated_at,
        progress=1.0 if result.status in (SimulationStatus.succeeded, SimulationStatus.failed) else 0.0,
        message=result.notes or "",
    )


@router.get("", response_model=list[SimulationSummary])
async def list_simulations():
    """List all simulations."""
    return [
        SimulationSummary(
            id=s.id,
            plan_id=s.plan_id,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            progress=1.0 if s.status in (SimulationStatus.succeeded, SimulationStatus.failed) else 0.0,
            message=s.notes or "",
        )
        for s in _simulations.values()
    ]


@router.get("/{simulation_id}", response_model=SimulationResult)
async def get_simulation(simulation_id: str):
    """Get simulation result."""
    sim = _simulations.get(simulation_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim
