"""FastAPI routes of versions, lineage, attribution and states (roadmap R12).

``GET  /api/v1/lineage/capability``                       — what radiarch declares to a capability registry.
``GET  /api/v1/lineage/{kind}/{id}``                      — the version and everything it derives from.
``GET  /api/v1/lineage/{kind}/{id}/descendants``          — what derives from it.
``GET  /api/v1/lineage/{kind}/{id}/attribution``          — who produced it, with what, from what.
``GET  /api/v1/lineage/{kind}/{id}/derivation``           — the SMIS transformation record (dataset_id, version of the input).
``GET  /api/v1/lineage/{kind}/{id}/state``                — state, immutability and history.
``POST /api/v1/lineage/{kind}/{id}/state``                — record a transition decided elsewhere.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ...models.lineage import KINDS, Attribution, DerivationRecord, LineageGraph, LineageNode, StateRecord, VersionRef, VersionStatus
from ...services.lineage import LineageError, LineageService

router = APIRouter(prefix="/lineage", tags=["lineage"])


@lru_cache(maxsize=1)
def _service() -> LineageService:
    return LineageService()


def _ref(kind: str, version_id: str) -> VersionRef:
    if kind not in KINDS:
        raise HTTPException(status_code=422, detail=f"unknown kind {kind!r}; one of {list(KINDS)}")
    return VersionRef(kind=kind, id=version_id)


@router.get("/capability", summary="What radiarch declares about itself to a capability registry.")
async def capability() -> dict:
    return _service().capability()


@router.get("/{kind}/{version_id}", response_model=LineageGraph, summary="A version and everything it derives from.")
async def get_lineage(kind: str, version_id: str, max_depth: int = Query(default=32, ge=1, le=256)) -> LineageGraph:
    try:
        return _service().lineage(_ref(kind, version_id), max_depth=max_depth)
    except LineageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{kind}/{version_id}/descendants", response_model=List[LineageNode], summary="Every version derived from this one.")
async def get_descendants(kind: str, version_id: str) -> List[LineageNode]:
    try:
        return _service().descendants(_ref(kind, version_id))
    except LineageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{kind}/{version_id}/attribution", response_model=Attribution, summary="Who produced the version, with what, from what.")
async def get_attribution(kind: str, version_id: str) -> Attribution:
    try:
        return _service().attribution(_ref(kind, version_id))
    except LineageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{kind}/{version_id}/derivation", response_model=DerivationRecord,
            summary="The version as a SMIS transformation record (manifest member `derivation`).")
async def get_derivation(kind: str, version_id: str, dataset_id: str = Query(..., min_length=1),
                         version: int = Query(..., ge=0), identifiability: str = Query(default="pseudonymized"),
                         description: Optional[str] = None) -> DerivationRecord:
    try:
        return _service().derivation_record(_ref(kind, version_id), inputs=[{"dataset_id": dataset_id, "version": version}],
                                            identifiability=identifiability, description=description)
    except LineageError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{kind}/{version_id}/state", response_model=VersionStatus, summary="State, immutability and history of a version.")
async def get_state(kind: str, version_id: str) -> VersionStatus:
    svc = _service()
    ref = _ref(kind, version_id)
    if svc.get(ref) is None:
        raise HTTPException(status_code=404, detail=f"{kind} {version_id!r} not found")
    return svc.status(ref)


@router.post("/{kind}/{version_id}/state", response_model=VersionStatus, summary="Record a state transition decided elsewhere.",
             responses={409: {"description": "The transition is not allowed from the current state."}})
async def set_state(kind: str, version_id: str, record: StateRecord) -> VersionStatus:
    svc = _service()
    ref = _ref(kind, version_id)
    try:
        return svc.transition(ref, record)
    except LineageError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 409, detail=str(exc)) from exc
