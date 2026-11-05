"""Static API-key authentication (D8.2).

Simple ``X-API-Key`` header check via a FastAPI dependency. The key
is configured per-deployment via ``RADIARCH_API_KEY``. Leaving it
empty disables auth — that's deliberate for dev / docker-compose
loops, but **must** be set in any deployment exposed beyond
localhost.

Why static keys (and not OAuth/JWT) for v1
------------------------------------------
* Radiarch is currently deployed inside hospital networks behind an
  upstream reverse proxy that already handles SSO. The proxy injects
  a trusted header; we just need a shared-secret check to confirm
  the request is from the proxy and not from someone bypassing it.
* OAuth2/JWT adds a dependency on an IdP we don't currently own.
* The plugin contract for the auth layer is intentionally small
  (one FastAPI dependency) so swapping to JWT later is a localized
  change in this file plus the route decorators — no API contract
  change.

When a user is required, prefer ``api_key_auth`` over rolling your
own header check inline in the route. That keeps the failure mode
consistent (401 + opaque "invalid API key" message — never leak whether
the header was present-but-wrong vs missing entirely).
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request, status
from loguru import logger

from ..config import get_settings


def _constant_time_eq(a: str, b: str) -> bool:
    """Length-constant comparison to avoid timing oracle leaks.

    Python's ``hmac.compare_digest`` is the standard idiom; we wrap
    so the import is local to security code.
    """
    import hmac
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


async def api_key_auth(request: Request) -> Optional[str]:
    """FastAPI dependency — validates X-API-Key against settings.

    Returns the matched key (for downstream logging) on success.
    Raises HTTPException(401) on missing / invalid keys.

    Auth is **disabled** when ``settings.api_key`` is empty — useful
    for dev/test. Production deployments must set ``RADIARCH_API_KEY``
    to a high-entropy secret; the audit log will tag every request
    with the key prefix so multiple keys (e.g. per-client) can be
    rotated independently in a future version.
    """
    settings = get_settings()
    expected = settings.api_key

    if not expected:
        # Auth disabled — let the request through. Log at debug so
        # devs can see this is happening without noise in prod logs.
        logger.debug("api_key_auth: no key configured; allowing request")
        return None

    presented = request.headers.get(settings.api_key_header, "")
    if not presented or not _constant_time_eq(presented, expected):
        # Don't differentiate missing vs wrong — same 401, same
        # message. Forces an attacker to bruteforce instead of probe.
        logger.warning(
            "api_key_auth: rejected request "
            f"path={request.url.path} method={request.method} "
            f"presented_len={len(presented)}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": f'ApiKey realm="radiarch"'},
        )

    # Return a short prefix for audit-log correlation (never the whole key).
    return presented[:6]




def _clean_user(value: str) -> str:
    """A user name fit for the records and for a DICOM person name: printable, no DICOM delimiters, at most 64."""
    cleaned = "".join(c for c in value.strip() if c.isprintable() and c not in "\\^=")
    return cleaned[:64]


def user_header_untrusted(request: Request) -> bool:
    """Whether the request carries the trusted user header without the trusted proxy's secret.

    The app refuses such a request on every route (a middleware), not only where the user is read, so a caller that
    reaches radiarch around the proxy gets the same 401 wherever it claims a user."""
    settings = get_settings()
    header = getattr(settings, "trusted_user_header", "")         # settings stubbed without it: off
    if not header or request.headers.get(header) is None:
        return False
    expected = settings.trusted_proxy_secret.get_secret_value() if settings.trusted_proxy_secret else ""
    presented = request.headers.get(settings.trusted_proxy_secret_header, "")
    return not expected or not presented or not _constant_time_eq(presented, expected)


async def requester(request: Request) -> Optional[str]:
    """The requesting user, when a trusted proxy names one (``trusted_user_header`` with ``trusted_proxy_secret``).

    Radiarch does not authenticate the user: it trusts the proxy, and the proxy proves itself with the shared
    secret. A request that carries the user header without the right secret is refused (401), so a caller that
    reaches radiarch around the proxy cannot claim a user. Without the setting, or without the header, None."""
    if user_header_untrusted(request):
        logger.warning("requester: a user header without the trusted proxy's secret; refused")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="untrusted user header")
    header = getattr(get_settings(), "trusted_user_header", "")
    value = request.headers.get(header) if header else None
    if value is None:
        return None
    user = _clean_user(value)
    return user or None


__all__ = ["api_key_auth", "requester", "user_header_untrusted"]
