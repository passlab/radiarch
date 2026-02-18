"""Session endpoint — temporary DICOM upload for plan preview.

Mirrors MONAILabel's /session pattern: clients upload temp data, preview results,
then commit or discard.  Sessions live on the filesystem with auto-expiry.
"""

from __future__ import annotations

import os
import shutil
import time
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ...config import get_settings

router = APIRouter(tags=["sessions"])

settings = get_settings()

# Default TTL = 1 hour
SESSION_TTL_SECONDS = int(os.environ.get("RADIARCH_SESSION_TTL", "3600"))


class SessionInfo(BaseModel):
    id: str
    created_at: float
    expires_at: float
    file_count: int


# In-memory registry (lightweight; sessions are filesystem-backed)
_sessions: dict[str, SessionInfo] = {}


def _session_dir(session_id: str) -> str:
    return os.path.join(settings.artifact_dir, "sessions", session_id)


def _cleanup_expired():
    """Remove expired sessions."""
    now = time.time()
    expired = [sid for sid, info in _sessions.items() if info.expires_at < now]
    for sid in expired:
        sdir = _session_dir(sid)
        if os.path.exists(sdir):
            shutil.rmtree(sdir, ignore_errors=True)
        _sessions.pop(sid, None)


@router.post("/sessions", response_model=SessionInfo)
async def create_session(file: UploadFile = File(...)):
    """Upload a temporary DICOM file and create a new session."""
    _cleanup_expired()

    session_id = str(uuid.uuid4())
    sdir = _session_dir(session_id)
    os.makedirs(sdir, exist_ok=True)

    filename = file.filename or "upload.dcm"
    dest = os.path.join(sdir, filename)
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    now = time.time()
    info = SessionInfo(
        id=session_id,
        created_at=now,
        expires_at=now + SESSION_TTL_SECONDS,
        file_count=1,
    )
    _sessions[session_id] = info
    return info


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """Retrieve session info."""
    _cleanup_expired()
    info = _sessions.get(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return info


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Expire a session early and remove its files."""
    info = _sessions.pop(session_id, None)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    sdir = _session_dir(session_id)
    if os.path.exists(sdir):
        shutil.rmtree(sdir, ignore_errors=True)
    return {"detail": "session deleted", "id": session_id}
