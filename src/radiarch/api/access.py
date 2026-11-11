"""The access check on every protected route (ADR 0021).

With ``RADIARCH_ACCESS_URL`` set, a request to any route that is not open must name a user (the trusted proxy's
header), and every result or study it names, in its path or its JSON body, must be one the host lets that user see. A
refused or unknown id answers ``404 not found`` alike, so a caller learns nothing about what exists. Listing routes
drop what the user may not see (:func:`keep_visible`). Without the setting nothing changes.

Open routes hold nothing of a patient: machines, protocols, goal templates, NTCP/TCP models, engines, workflow
templates, the capability statement and job status (a state and a result's id, whose read is checked). Every route
that writes needs a user.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, Request, status
from loguru import logger
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..services.access import AccessService, AccessUnavailable, NotVisible, ServerPathRefused, enabled
from .security import requester

JOB_ROUTES = ("/jobs/{job_id}", "/geometry/jobs/{job_id}", "/beam-model/jobs/{job_id}", "/dose/jobs/{job_id}",
              "/optimize/jobs/{job_id}", "/bao/jobs/{job_id}", "/evaluate/jobs/{job_id}", "/mco/jobs/{job_id}",
              "/mco/deliverables/jobs/{job_id}", "/protocols/jobs/{job_id}")
OPEN_ROUTES = frozenset({
    ("GET", "/beam-model/machines"), ("GET", "/beam-model/machines/photon/{machine_id}"),
    ("GET", "/beam-model/machines/proton/{machine_id}"), ("GET", "/dose/engines"), ("GET", "/dose/engines/{name}"),
    ("GET", "/protocols"), ("GET", "/protocols/{protocol_id}"), ("GET", "/evaluate/goal-templates"),
    ("GET", "/evaluate/goal-templates/{template_id}"), ("GET", "/evaluate/models"), ("GET", "/lineage/capability"),
    ("GET", "/workflows"), ("GET", "/workflows/{workflow_id}"),
    *(("GET", p) for p in JOB_ROUTES),
})
MAX_USER = 256

_routes: Dict[Tuple[int, str], Tuple[Optional[str], bool]] = {}


def _route(request: Request) -> Tuple[Optional[str], bool]:
    """The matched route's path template without the API prefix (``/geometry/{geometry_id}``), and whether it takes a
    JSON body (a body that is not a form)."""
    endpoint = request.scope.get("endpoint")
    key = (id(endpoint), request.method)
    if key not in _routes:
        from fastapi import params

        prefix = get_settings().api_prefix
        found = next((r for r in request.app.routes
                      if getattr(r, "endpoint", None) is endpoint and request.method in (getattr(r, "methods", None) or ())), None)
        path = getattr(found, "path", None)
        body = getattr(found, "body_field", None)
        _routes[key] = (path[len(prefix):] if path and path.startswith(prefix) else path,
                        body is not None and not isinstance(body.field_info, params.Form))
    return _routes[key]


def route_template(request: Request) -> Optional[str]:
    return _route(request)[0]


async def access_user(request: Request) -> Optional[str]:
    """The user the host is asked about: the trusted proxy's header exactly as sent (``requester`` checks the proxy's
    secret; the name it records is cleaned for DICOM, which would let two names share one user's access)."""
    if await requester(request) is None:
        return None
    raw = request.headers.get(get_settings().trusted_user_header) or ""
    if len(raw) > MAX_USER:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="the user header is too long")
    return raw if raw.strip() else None


async def access_guard(request: Request) -> None:
    """FastAPI dependency: the access check of ADR 0021 (a no-op without ``RADIARCH_ACCESS_URL``)."""
    if not enabled():
        return
    template, takes_body = _route(request)
    if (request.method, template) in OPEN_ROUTES:
        return
    user = await access_user(request)
    if user is None:
        logger.warning(f"access: a request without a user refused: path={request.url.path} method={request.method}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="this deployment checks every read against the host: the request names no user")
    request.state.access_user = user
    body: Any = None
    if takes_body:
        # whatever the content type says: FastAPI parses a body without one, or with any case of it, as JSON
        raw = await request.body()                                # read and kept by FastAPI before the dependencies
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = None                                           # not JSON: the route refuses it (422)
        except Exception:                                         # JSON this check cannot walk is not passed on
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="the body could not be read") from None
    try:
        await run_in_threadpool(AccessService().check, user, dict(request.path_params), body)
    except NotVisible as exc:
        logger.info(f"access: {user} refused {exc} on {request.method} {template}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from None
    except ServerPathRefused as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"{exc} names a file on the server, not a study: refused while access is checked by user") from None
    except AccessUnavailable as exc:
        logger.warning(f"access: {exc}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="the access check is unavailable") from None


async def require_visible(request: Request, kind: str, version_id: str) -> None:
    """A stored result a route returns without the request naming it (a geometry build's cache hit, whose study comes
    from the CT it read, not from the request): ``404 not found`` unless the user may see it."""
    if enabled() and not await keep_visible(request, [version_id], kind, lambda v: v):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


async def keep_visible(request: Request, items: Iterable[Any], kind, id_of) -> List[Any]:
    """The listed ``items`` the request's user may see (all of them without ``RADIARCH_ACCESS_URL``). ``kind`` and
    ``id_of`` give an item's kind and id: a kind and an attribute name, or functions of the item."""
    items = list(items)
    if not enabled():
        return items
    user = getattr(request.state, "access_user", None)
    svc = AccessService()
    get = (lambda it: getattr(it, id_of)) if isinstance(id_of, str) else id_of
    kind_of = kind if callable(kind) else (lambda it: kind)

    def keep() -> List[Any]:
        return [it for it in items if svc.visible(user, kind_of(it), str(get(it)))]

    try:
        return await run_in_threadpool(keep)
    except AccessUnavailable as exc:
        logger.warning(f"access: {exc}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="the access check is unavailable") from None


__all__ = ["OPEN_ROUTES", "access_guard", "access_user", "keep_visible", "require_visible", "route_template"]
