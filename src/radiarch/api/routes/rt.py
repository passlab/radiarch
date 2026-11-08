"""FastAPI routes of the RT object export (roadmap R6).

``POST /api/v1/rt/export``                          — write the RT objects of a plan.
``GET  /api/v1/rt/exports``                         — exports by DICOM UID (study, series, instance), newest first.
``GET  /api/v1/rt/exports/{export_id}``             — the manifest.
``GET  /api/v1/rt/exports/{export_id}/files/{name}``— one object (application/dicom).
``POST /api/v1/rt/exports/{export_id}/records``     — treatment records for sessions, and the summary.
``POST /api/v1/rt/exports/{export_id}/push``        — STOW-RS push of the export's objects.

A push (an export or records with ``push``, or the push route) may carry an upload token in the
``upload_token_header`` header (ADR 0020): the archive gets it as the push's Authorization, and radiarch keeps
no trace of it.
"""

from __future__ import annotations

from functools import lru_cache

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ...models.rt_export import RTExportRequest, RTExportResult, RTPushRequest, RTPushResult, RTRecordRequest, RTRecordResult
from ...config import get_settings
from ...services.rt_export import RTExportError, RTExportService, RTPushRefused, UploadTokenError
from ..security import requester

router = APIRouter(prefix="/rt", tags=["rt-objects"])


@lru_cache(maxsize=1)
def _service() -> RTExportService:
    return RTExportService()


async def upload_token(request: Request) -> Optional[str]:
    """The request's upload token (``upload_token_header``), or None. Read from the headers, never from the body, so a
    validation error cannot echo it."""
    value = request.headers.get(get_settings().upload_token_header, "").strip()
    return value or None


@router.post("/export", response_model=RTExportResult, summary="Write the DICOM RT objects of a plan.",
             responses={200: {"description": "Objects written; the manifest lists them."},
                        404: {"description": "The plan, geometry or dose was not found."},
                        422: {"description": "The plan cannot be exported as asked, or a push needs an upload token."},
                        502: {"description": "The archive refused the push and RADIARCH_DICOMWEB_PUSH_REQUIRED is set: nothing kept."}})
async def export_rt_objects(request: RTExportRequest, user: Optional[str] = Depends(requester),
                            token: Optional[str] = Depends(upload_token)) -> RTExportResult:
    request = request.model_copy(update={"requested_by": user})
    try:
        return _service().export(request, upload_token=token)
    except RTPushRefused as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RTExportError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/exports", response_model=List[RTExportResult], summary="Exports by DICOM UID, newest first.",
            description="A viewer that shows a study, series or instance finds the export radiarch wrote it in; every filter given must match.")
async def find_exports(study_instance_uid: Optional[str] = Query(default=None, max_length=64),
                       series_instance_uid: Optional[str] = Query(default=None, max_length=64),
                       sop_instance_uid: Optional[str] = Query(default=None, max_length=64),
                       limit: int = Query(default=50, ge=1, le=500)) -> List[RTExportResult]:
    return _service().find(study_instance_uid=study_instance_uid, series_instance_uid=series_instance_uid,
                           sop_instance_uid=sop_instance_uid, limit=limit)


@router.get("/exports/{export_id}", response_model=RTExportResult, summary="The manifest of an export.")
async def get_export(export_id: str) -> RTExportResult:
    result = _service().get(export_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"export not found: {export_id}")
    return result


@router.get("/exports/{export_id}/files/{file_name}", response_class=FileResponse, summary="One object of an export.")
async def get_export_file(export_id: str, file_name: str):
    path = _service().file_path(export_id, file_name)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail=f"no file {file_name} in export {export_id}")
    return FileResponse(str(path), media_type="application/dicom", filename=file_name)


@router.post("/exports/{export_id}/records", response_model=RTRecordResult,
             summary="Write RT (Ion) Beams Treatment Records for sessions of the plan, and the course summary.")
async def write_records(export_id: str, request: RTRecordRequest, token: Optional[str] = Depends(upload_token)) -> RTRecordResult:
    try:
        return _service().records(export_id, request, upload_token=token)
    except RTExportError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/exports/{export_id}/push", response_model=RTPushResult, summary="Push the export's objects with STOW-RS.",
             responses={422: {"description": "An upload token with a username, or none where one is required."}})
async def push_export(export_id: str, request: RTPushRequest, token: Optional[str] = Depends(upload_token)) -> RTPushResult:
    try:
        out = _service().push(export_id, url=request.url, username=request.username, password=request.password, kinds=request.kinds,
                              upload_token=token)
    except UploadTokenError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RTExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if out.error and get_settings().dicomweb_push_required:
        raise HTTPException(status_code=502, detail=f"the DICOMweb push of export {export_id} was refused: {out.error}")
    return out
