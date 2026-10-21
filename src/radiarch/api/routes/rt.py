"""FastAPI routes of the RT object export (roadmap R6).

``POST /api/v1/rt/export``                          — write the RT objects of a plan.
``GET  /api/v1/rt/exports/{export_id}``             — the manifest.
``GET  /api/v1/rt/exports/{export_id}/files/{name}``— one object (application/dicom).
``POST /api/v1/rt/exports/{export_id}/records``     — treatment records for sessions, and the summary.
``POST /api/v1/rt/exports/{export_id}/push``        — STOW-RS push of the export's objects.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...models.rt_export import RTExportRequest, RTExportResult, RTPushRequest, RTPushResult, RTRecordRequest, RTRecordResult
from ...services.rt_export import RTExportError, RTExportService

router = APIRouter(prefix="/rt", tags=["rt-objects"])


@lru_cache(maxsize=1)
def _service() -> RTExportService:
    return RTExportService()


@router.post("/export", response_model=RTExportResult, summary="Write the DICOM RT objects of a plan.",
             responses={200: {"description": "Objects written; the manifest lists them."},
                        404: {"description": "The plan, geometry or dose was not found."},
                        422: {"description": "The plan cannot be exported as asked."}})
async def export_rt_objects(request: RTExportRequest) -> RTExportResult:
    try:
        return _service().export(request)
    except RTExportError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
async def write_records(export_id: str, request: RTRecordRequest) -> RTRecordResult:
    try:
        return _service().records(export_id, request)
    except RTExportError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/exports/{export_id}/push", response_model=RTPushResult, summary="Push the export's objects with STOW-RS.")
async def push_export(export_id: str, request: RTPushRequest) -> RTPushResult:
    try:
        return _service().push(export_id, url=request.url, username=request.username, password=request.password, kinds=request.kinds)
    except RTExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
