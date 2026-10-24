"""Vendor-neutral DICOMweb STOW-RS client for artifact push.

Uses the standard DICOMweb STOW-RS protocol via dicomweb-client,
so any PACS supporting DICOMweb (Orthanc, DCM4CHEE, Google Healthcare API, etc.)
works as a backend.  Configured via RADIARCH_DICOMWEB_URL; disabled when empty.

Authentication: HTTP basic (``RADIARCH_DICOMWEB_USERNAME`` / ``_PASSWORD``) for a plain
PACS, or an OAuth2 client-credentials bearer token (``RADIARCH_DICOMWEB_TOKEN_URL``,
``_CLIENT_ID``, ``_CLIENT_SECRET``) for an endpoint that wants one, such as a research
write gateway. Tokens are fetched when needed and refreshed before they expire; the
secret and the token are never logged.

A refused push raises :class:`DICOMwebPushError` with the HTTP status and the response
body, so a caller can say why (a gateway answers with JSON findings).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

from loguru import logger

from ..config import get_settings

TOKEN_MARGIN_S = 30.0          # refresh this long before a token expires (or at a fifth of its life if shorter)
BODY_LIMIT = 8000               # characters of a refusal body kept in the error


class DICOMwebPushError(RuntimeError):
    """A STOW-RS push the server refused: its HTTP status, its body as text and, when JSON, parsed."""

    def __init__(self, status: Optional[int], body: str, url: str):
        self.status = status
        self.body = body[:BODY_LIMIT]
        try:
            self.details: Any = json.loads(body) if body else None
        except ValueError:
            self.details = None
        super().__init__(f"STOW-RS push to {url} refused: HTTP {status}: {self.body}")


class ClientCredentialsToken:
    """An OAuth2 client-credentials token, fetched on first use and refreshed before it expires."""

    def __init__(self, token_url: str, client_id: str, client_secret: str, scope: str = "", timeout_s: float = 10.0):
        self._token_url, self._client_id, self._client_secret, self._scope = token_url, client_id, client_secret, scope
        self._timeout = timeout_s
        self._token: Optional[str] = None
        self._refresh_at = 0.0
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._token is None or time.monotonic() >= self._refresh_at:
                self._fetch()
            return self._token  # type: ignore[return-value]

    def _fetch(self) -> None:
        import requests

        data = {"grant_type": "client_credentials", "client_id": self._client_id, "client_secret": self._client_secret}
        if self._scope:
            data["scope"] = self._scope
        resp = requests.post(self._token_url, data=data, timeout=self._timeout)
        if resp.status_code != 200:
            # the body of a token error names the problem (invalid_client, ...), never the secret
            raise DICOMwebPushError(resp.status_code, resp.text, self._token_url)
        payload = resp.json()
        token = payload.get("access_token")
        if not token:
            raise DICOMwebPushError(resp.status_code, "token response without access_token", self._token_url)
        life = float(payload.get("expires_in", 60))
        self._token = token
        self._refresh_at = time.monotonic() + max(1.0, life - min(TOKEN_MARGIN_S, life / 5.0))
        logger.info("DICOMweb: bearer token for client {} (expires in {:.0f} s)", self._client_id, life)


class DICOMwebNotifier:
    """Push DICOM artifacts to a remote PACS via STOW-RS."""

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[ClientCredentialsToken] = None,
    ):
        settings = get_settings()
        self._url = url or settings.dicomweb_url
        self._username = username or settings.dicomweb_username
        self._password = password or settings.dicomweb_password
        self._token = token
        if self._token is None and not username and settings.dicomweb_token_url and settings.dicomweb_client_id:
            secret = settings.dicomweb_client_secret.get_secret_value() if settings.dicomweb_client_secret else ""
            self._token = _shared_token(settings.dicomweb_token_url, settings.dicomweb_client_id, secret, settings.dicomweb_token_scope)
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    @property
    def auth(self) -> str:
        """``bearer``, ``basic`` or ``none``."""
        return "bearer" if self._token is not None else ("basic" if self._username else "none")

    def _get_client(self):
        try:
            from dicomweb_client.api import DICOMwebClient
        except ImportError:
            logger.warning("dicomweb-client not installed; DICOMweb push disabled")
            return None

        if self._token is not None:
            # a client per push: the token in its headers may have been refreshed since the last one
            return DICOMwebClient(url=self._url, headers={"Authorization": f"Bearer {self._token.get()}"})
        if self._client is not None:
            return self._client
        kwargs = {"url": self._url}
        if self._username:
            kwargs["username"] = self._username
            kwargs["password"] = self._password
        self._client = DICOMwebClient(**kwargs)
        return self._client

    def store_instances(self, instances, raise_errors: bool = False) -> bool:
        """Push DICOM instances via STOW-RS: pydicom datasets, file paths or bytes.

        Returns True on success. Failures are logged and return False unless
        ``raise_errors`` is set — a plan job should not fail because the PACS is
        unreachable, but an explicit push request wants the error. A refusal raises
        :class:`DICOMwebPushError` with the server's status and body.
        """
        if not self.enabled:
            if raise_errors:
                raise RuntimeError("DICOMweb push is disabled: RADIARCH_DICOMWEB_URL is empty")
            return False

        try:
            client = self._get_client()
            if client is None:
                if raise_errors:
                    raise RuntimeError("dicomweb-client is not installed")
                return False
            datasets = [_as_dataset(x) for x in (instances if isinstance(instances, (list, tuple)) else [instances])]
            logger.info("STOW-RS push of {} instance(s) to {} ({} auth)", len(datasets), self._url, self.auth)
            client.store_instances(datasets=datasets)
            logger.info("STOW-RS push succeeded")
            return True
        except Exception as exc:
            err = _refusal(exc, self._url)
            if raise_errors:
                raise err from exc
            logger.error("STOW-RS push failed (non-fatal): {}", err)
            return False


def _refusal(exc: Exception, url: str) -> Exception:
    """An HTTP error from the client as a :class:`DICOMwebPushError` carrying the response body."""
    if isinstance(exc, DICOMwebPushError):
        return exc
    resp = getattr(exc, "response", None)
    if resp is None:
        return exc
    try:
        body = resp.text or ""
    except Exception:  # pragma: no cover
        body = ""
    return DICOMwebPushError(getattr(resp, "status_code", None), body, url)


_tokens: dict = {}
_tokens_lock = threading.Lock()


def _shared_token(token_url: str, client_id: str, secret: str, scope: str) -> ClientCredentialsToken:
    """One token source per (endpoint, client, scope) for the process, so pushes reuse a live token."""
    key = (token_url, client_id, scope)
    with _tokens_lock:
        if key not in _tokens:
            _tokens[key] = ClientCredentialsToken(token_url, client_id, secret, scope)
        return _tokens[key]


def _as_dataset(x):
    import pydicom

    if isinstance(x, pydicom.Dataset):
        return x
    if isinstance(x, (bytes, bytearray)):
        from io import BytesIO
        return pydicom.dcmread(BytesIO(bytes(x)))
    return pydicom.dcmread(str(x))


# Module-level singleton (lazy)
_notifier: Optional[DICOMwebNotifier] = None


def get_dicomweb_notifier() -> DICOMwebNotifier:
    global _notifier
    if _notifier is None:
        _notifier = DICOMwebNotifier()
    return _notifier
