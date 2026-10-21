"""The immutability rule of R12 at the delete routes: an approved version, and every version it
derives from, cannot be deleted (409)."""

from __future__ import annotations

from fastapi import HTTPException


def assert_deletable(kind: str, version_id: str) -> None:
    from ...models.lineage import VersionRef
    from ...services.lineage import LineageService, VersionLocked

    try:
        LineageService().assert_deletable(VersionRef(kind=kind, id=version_id))
    except VersionLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
