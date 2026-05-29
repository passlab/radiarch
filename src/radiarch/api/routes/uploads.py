"""DICOM upload endpoints — feeder for Service 1.

Lets a client POST a single ZIP containing one patient study (CT series +
RTSTRUCT) and get back an ``upload_id`` that can be passed to
``POST /geometry/build`` via ``patient_ref.upload_id``. The ZIP is
extracted under ``{settings.upload_dir}/{upload_id}/`` and the contents
walked once to give the caller a quick sanity check (how many CT
slices, how many RTSTRUCTs, total bytes).

Endpoints
---------
``POST   /api/v1/uploads/dicom``        — accept a multipart ZIP.
``GET    /api/v1/uploads/{upload_id}``  — inspect what was uploaded.
``DELETE /api/v1/uploads/{upload_id}``  — remove the extracted bundle.
"""

from __future__ import annotations

import os
import shutil
import uuid
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from loguru import logger
from pydantic import BaseModel, Field

from ...config import get_settings

router = APIRouter(prefix="/uploads", tags=["uploads"])


# ---------------------------------------------------------------------------
# Settings helper
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _upload_root() -> Path:
    """Resolve the configured upload directory, creating it if needed.

    When ``settings.upload_dir`` is empty (the default), falls back to
    ``{settings.artifact_dir}/uploads``.
    """
    settings = get_settings()
    base = settings.upload_dir or str(Path(settings.artifact_dir) / "uploads")
    path = Path(base).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _upload_path(upload_id: str) -> Path:
    return _upload_root() / upload_id


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    upload_id: str = Field(..., description="Pass this as patient_ref.upload_id.")
    file_count: int = Field(..., description="Total number of files extracted.")
    dicom_count: int = Field(..., description="Files with a .dcm extension.")
    ct_slice_count: int = Field(..., description="Best-effort count of CT instances.")
    rtstruct_count: int = Field(..., description="Best-effort count of RTSTRUCT instances.")
    total_bytes: int = Field(..., description="Sum of all extracted file sizes.")
    storage_path: str = Field(..., description="Server-side directory holding the extracted bundle.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# DICOM modality is at tag (0008,0060). Reading it requires pydicom; we
# only need it to give the upload response useful counts. Best-effort:
# if pydicom isn't available at request time, we still accept the upload
# and report zeros for the modality-specific fields.

def _scan_directory(root: Path) -> UploadResponse:
    file_count = 0
    dicom_count = 0
    ct_slice_count = 0
    rtstruct_count = 0
    total_bytes = 0

    try:
        import pydicom  # type: ignore
        has_pydicom = True
    except Exception:  # pragma: no cover — pydicom is a hard dep but be safe
        has_pydicom = False

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        file_count += 1
        total_bytes += path.stat().st_size
        is_dcm = path.suffix.lower() == ".dcm"
        if not is_dcm:
            # Some clinical exports drop the .dcm extension. Sniff for it.
            try:
                with path.open("rb") as fh:
                    fh.seek(128)
                    if fh.read(4) == b"DICM":
                        is_dcm = True
            except OSError:
                pass
        if not is_dcm:
            continue
        dicom_count += 1
        if not has_pydicom:
            continue
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
            modality = (getattr(ds, "Modality", "") or "").upper()
            if modality == "CT":
                ct_slice_count += 1
            elif modality == "RTSTRUCT":
                rtstruct_count += 1
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("Could not parse DICOM modality for %s: %s", path, exc)

    return UploadResponse(
        upload_id="",  # filled in by caller
        file_count=file_count,
        dicom_count=dicom_count,
        ct_slice_count=ct_slice_count,
        rtstruct_count=rtstruct_count,
        total_bytes=total_bytes,
        storage_path=str(root),
    )


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """Extract ``zip_path`` into ``dest``, refusing zip-slip traversal."""
    with zipfile.ZipFile(zip_path) as zf:
        dest_resolved = dest.resolve()
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if dest_resolved not in target.parents and target != dest_resolved:
                raise HTTPException(
                    status_code=400,
                    detail=f"Refusing unsafe ZIP entry: {member.filename!r}",
                )
        zf.extractall(dest)


# ---------------------------------------------------------------------------
# POST /uploads/dicom
# ---------------------------------------------------------------------------

@router.post(
    "/dicom",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a ZIP of one patient's DICOM study (CT + RTSTRUCT).",
    responses={
        201: {"description": "Upload accepted; extracted bundle is ready."},
        400: {"description": "File missing, not a ZIP, or unsafe entries."},
        413: {"description": "Upload exceeds configured size limit."},
    },
)
async def upload_dicom(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload must include a filename.")
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail=f"Expected a .zip file, got {file.filename!r}.",
        )

    upload_id = str(uuid.uuid4())
    dest = _upload_path(upload_id)
    dest.mkdir(parents=True, exist_ok=False)

    # Stream the upload to a temporary path inside the upload dir, then
    # extract — keeps everything on one filesystem so we don't pay a
    # cross-FS copy.
    tmp_zip = dest / "_incoming.zip"
    try:
        with tmp_zip.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            _safe_extract_zip(tmp_zip, dest)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(dest, ignore_errors=True)
            raise HTTPException(
                status_code=400, detail=f"Not a valid ZIP archive: {exc}"
            ) from exc
    finally:
        try:
            tmp_zip.unlink()
        except FileNotFoundError:
            pass

    summary = _scan_directory(dest)
    if summary.dicom_count == 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="ZIP contained no DICOM files (.dcm). Upload rejected.",
        )

    summary = summary.model_copy(update={"upload_id": upload_id})
    logger.info(
        "Upload %s accepted: %d files (%d DICOM, %d CT, %d RTSTRUCT, %.1f MB)",
        upload_id,
        summary.file_count,
        summary.dicom_count,
        summary.ct_slice_count,
        summary.rtstruct_count,
        summary.total_bytes / (1024 * 1024),
    )
    return summary


# ---------------------------------------------------------------------------
# GET /uploads/{upload_id}
# ---------------------------------------------------------------------------

@router.get(
    "/{upload_id}",
    response_model=UploadResponse,
    summary="Inspect a previously-uploaded DICOM bundle.",
)
async def get_upload(upload_id: str) -> UploadResponse:
    path = _upload_path(upload_id)
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"Upload not found: {upload_id}")
    summary = _scan_directory(path)
    return summary.model_copy(update={"upload_id": upload_id})


# ---------------------------------------------------------------------------
# DELETE /uploads/{upload_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/{upload_id}",
    status_code=204,
    response_class=Response,
    summary="Delete an extracted DICOM bundle.",
)
async def delete_upload(upload_id: str):
    path = _upload_path(upload_id)
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"Upload not found: {upload_id}")
    shutil.rmtree(path)
    return Response(status_code=204)
