from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArtifactRecord(BaseModel):
    id: str
    plan_id: str
    file_path: str
    content_type: str = "application/dicom"
    file_name: str = ""
    created_at: Optional[datetime] = None
