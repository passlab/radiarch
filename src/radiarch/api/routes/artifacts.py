import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...core.store import store

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    record = store.get_artifact(artifact_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {artifact_id}")
    if not os.path.isfile(record.file_path):
        raise HTTPException(status_code=410, detail="Artifact file no longer exists on disk")
    return FileResponse(
        path=record.file_path,
        media_type=record.content_type,
        filename=record.file_name,
    )

