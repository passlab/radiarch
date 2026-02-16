from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    raise HTTPException(status_code=501, detail=f"Artifact retrieval not implemented: {artifact_id}")
