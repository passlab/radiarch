"""FastAPI routes for the Registration Service (R9).

A registration maps a fixed geometry onto a moving one (rigid, then Demons or B-spline) and keeps
the result as one displacement field on the fixed grid, with its quality figures (AAPM TG-132).
It runs in the request: a CT pair at 3 mm takes seconds to a minute.

Endpoints
---------
``POST   /api/v1/registrations``                    — register (or reuse the cached result).
``GET    /api/v1/registrations/{id}``               — the result and its quality.
``GET    /api/v1/registrations/{id}/field``         — stream the displacement field NIfTI.
``POST   /api/v1/registrations/{id}/propagate``     — the moving structures on the fixed geometry, as a derived geometry.
``POST   /api/v1/registrations/{id}/map-dose``      — a dose on the moving geometry, mapped onto the fixed one.
``POST   /api/v1/registrations/{id}/dicom``         — the registration as DICOM Spatial and Deformable Spatial Registration objects.
``DELETE /api/v1/registrations/{id}``               — remove a registration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from ._lineage_guard import assert_deletable
from ...models.dose import DoseResult
from ...models.geometry import GeometryResult
from ...models.registration import MapDoseRequest, PropagateRequest, RegistrationRequest, RegistrationResult
from ...services.audit import emit, make_event
from ...services.registration import RegistrationError, RegistrationService
from ..security import api_key_auth

router = APIRouter(prefix="/registrations", tags=["registration"])


@lru_cache(maxsize=1)
def _service() -> RegistrationService:
    return RegistrationService()


def _get(registration_id: str) -> RegistrationResult:
    result = _service().store.get_by_id(registration_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Registration not found: {registration_id}")
    return result


# Plain ``def`` routes: the registration blocks for seconds, so FastAPI runs it in its thread pool.

@router.post(
    "",
    response_model=RegistrationResult,
    summary="Register a moving geometry's CT to a fixed one: rigid, then deformable; the field and its quality (R9).",
    responses={404: {"description": "A geometry not found."}, 422: {"description": "A geometry without a CT, or an invalid request."}},
)
def register(request: RegistrationRequest, api_key_prefix: Optional[str] = Depends(api_key_auth)) -> RegistrationResult:
    svc = _service()
    for gid in (request.fixed_geometry_id, request.moving_geometry_id):
        if svc.geometry_service.store.get_by_id(gid) is None:
            raise HTTPException(status_code=404, detail=f"Geometry not found: {gid}")
    try:
        result = svc.register(request)
    except (RegistrationError, ValueError) as exc:
        emit(make_event("registration.run", state="failed", geometry_id=request.fixed_geometry_id, error_type=type(exc).__name__,
                        error_message=str(exc)[:200], api_key_prefix=api_key_prefix))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    emit(make_event("registration.run", state="succeeded", cache_key=result.cache_key, geometry_id=request.fixed_geometry_id,
                    api_key_prefix=api_key_prefix,
                    extra={"registration_id": result.registration_id, "moving_geometry_id": request.moving_geometry_id,
                           "deformable": result.deformable.value}))
    return result


@router.get("/{registration_id}", response_model=RegistrationResult, summary="A registration and its quality.")
async def get_registration(registration_id: str) -> RegistrationResult:
    return _get(registration_id)


@router.get("/{registration_id}/field", response_class=FileResponse,
            summary="Stream the displacement field u (NIfTI, three components, mm) on the fixed grid: T(x) = x + u(x).")
async def get_field(registration_id: str):
    _get(registration_id)
    path = _service().store.field_path(registration_id)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="field.nii.gz no longer on disk")
    return FileResponse(path=str(path), media_type="application/gzip", filename="field.nii.gz")


@router.post(
    "/{registration_id}/propagate",
    response_model=GeometryResult,
    summary="A derived geometry of the fixed one with the moving geometry's structures warped onto it (R9).",
    responses={404: {"description": "Registration not found."},
               422: {"description": "An unknown structure, a name clash without a suffix, or too many structures."}},
)
def propagate(registration_id: str, request: PropagateRequest) -> GeometryResult:
    _get(registration_id)
    try:
        return _service().propagate(registration_id, request)
    except (RegistrationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{registration_id}/map-dose",
    response_model=DoseResult,
    summary="A dose on the moving geometry, pulled back through the registration onto the fixed geometry, as a new dose (R9).",
    responses={404: {"description": "Registration not found."}, 422: {"description": "The dose is not found or not on the moving geometry."}},
)
def map_dose(registration_id: str, request: MapDoseRequest) -> DoseResult:
    _get(registration_id)
    try:
        return _service().map_dose(registration_id, request.dose_id)
    except (RegistrationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{registration_id}/dicom", summary="Write the registration as DICOM Spatial / Deformable Spatial Registration objects (R9).")
def export_dicom(registration_id: str) -> list:
    _get(registration_id)
    try:
        return _service().export_dicom(registration_id)
    except (RegistrationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{registration_id}", status_code=204, response_class=Response, summary="Delete a registration.")
async def delete_registration(registration_id: str):
    _get(registration_id)
    assert_deletable("registration", registration_id)
    _service().store.delete_by_id(registration_id)
    return Response(status_code=204)
