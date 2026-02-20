"""Pydantic models for dose delivery simulation (Phase 8D)."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SimulationStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class SimulationRequest(BaseModel):
    """Request body for POST /simulations."""

    plan_id: str = Field(..., description="ID of the completed plan to simulate delivery for")
    motion_amplitude_mm: List[float] = Field(
        default=[0.0, 0.0, 0.0],
        min_length=3,
        max_length=3,
        description="Breathing motion amplitude [x, y, z] in mm",
    )
    motion_period_s: float = Field(
        default=4.0, gt=0,
        description="Breathing cycle period in seconds",
    )
    delivery_time_per_spot_ms: float = Field(
        default=5.0, gt=0,
        description="Time to deliver each spot in ms",
    )
    num_fractions: int = Field(
        default=1, ge=1,
        description="Number of fractions to simulate",
    )
    notes: Optional[str] = None


class SimulationSummary(BaseModel):
    """Returned by GET /simulations and POST /simulations."""

    id: str
    plan_id: str
    status: SimulationStatus = SimulationStatus.queued
    created_at: datetime
    updated_at: datetime
    progress: float = 0.0
    message: str = ""


class SimulationResult(BaseModel):
    """Detailed result of a completed simulation."""

    id: str
    plan_id: str
    status: SimulationStatus
    created_at: datetime
    updated_at: datetime

    # Results
    delivered_dose_max_gy: Optional[float] = None
    delivered_dose_mean_gy: Optional[float] = None
    gamma_pass_rate: Optional[float] = None
    dose_difference_pct: Optional[float] = None
    motion_amplitude_mm: List[float] = [0.0, 0.0, 0.0]
    artifact_path: Optional[str] = None
    qa_metrics: Optional[Dict] = None
    notes: Optional[str] = None
