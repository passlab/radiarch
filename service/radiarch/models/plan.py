from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PlanWorkflow(str, Enum):
    proton_impt_basic = "proton-impt-basic"
    photon_ccc = "photon-ccc"


class PlanRequest(BaseModel):
    study_instance_uid: str = Field(..., description="DICOM Study Instance UID")
    segmentation_uid: Optional[str] = Field(None, description="RTSTRUCT/SEG UID with target contours")
    workflow_id: PlanWorkflow = Field(default=PlanWorkflow.proton_impt_basic)
    prescription_gy: float = Field(..., gt=0)
    fraction_count: int = Field(default=1, gt=0)
    notes: Optional[str] = None


class PlanSummary(BaseModel):
    id: str
    workflow_id: PlanWorkflow
    status: str
    created_at: datetime
    updated_at: datetime
    prescription_gy: float
    artifact_ids: List[str] = []


class PlanDetail(PlanSummary):
    study_instance_uid: str
    segmentation_uid: Optional[str]
    fraction_count: int
    notes: Optional[str] = None
    job_id: Optional[str] = None
    qa_summary: Optional[dict] = None
