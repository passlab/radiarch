from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobStatus(BaseModel):
    id: str
    plan_id: str
    state: JobState
    progress: float = 0.0
    message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
