"""Vendor-neutral DICOMweb STOW-RS client for artifact push.

Uses the standard DICOMweb STOW-RS protocol via dicomweb-client,
so any PACS supporting DICOMweb (Orthanc, DCM4CHEE, Google Healthcare API, etc.)
works as a backend.  Configured via RADIARCH_DICOMWEB_URL; disabled when empty.

Authentication: HTTP basic (``RADIARCH_DICOMWEB_USERNAME`` / ``_PASSWORD``) for a plain
PACS, or an OAuth2 client-credentials bearer token (``RADIARCH_DICOMWEB_TOKEN_URL``,
``_CLIENT_ID``, ``_CLIENT_SECRET``) for an endpoint that wants one, such as a research
write gateway. Tokens are fetched when needed and refreshed before they expire; the
secret and the token are never logged. Both go only to ``RADIARCH_DICOMWEB_URL``: a push
to another URL carries only the credential its caller gives.

An upload token (ADR 0020) is a caller's credential for one push: its value becomes the
``Authorization`` header as given, and radiarch's own credential is not used. It is never
logged, and an error that would quote it says ``[upload token]`` instead.

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
        upload_token: Optional[str] = None,
    ):
        settings = get_settings()
        self._url = url or settings.dicomweb_url
        self._upload_token = upload_token or None
        if self._upload_token and (username or password or token is not None):
            raise ValueError("an upload token or a username and password, not both")
        if self._upload_token and not header_safe(self._upload_token):
            raise ValueError("the upload token holds characters an HTTP header cannot carry")
        # radiarch's own credential only for its configured URL: a request may name another one; never with an upload token
        own = not self._upload_token and bool(settings.dicomweb_url) and _same_url(self._url, settings.dicomweb_url)
        self._username = username or (settings.dicomweb_username if own else None)
        self._password = password or (settings.dicomweb_password if own else None)
        self._token = token
        if self._token is None and not username and own and settings.dicomweb_token_url and settings.dicomweb_client_id:
            secret = settings.dicomweb_client_secret.get_secret_value() if settings.dicomweb_client_secret else ""
            self._token = _shared_token(settings.dicomweb_token_url, settings.dicomweb_client_id, secret, settings.dicomweb_token_scope)
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    @property
    def auth(self) -> str:
        """``upload token``, ``bearer``, ``basic`` or ``none``."""
        if self._upload_token:
            return "upload token"
        return "bearer" if self._token is not None else ("basic" if self._username else "none")

    def _get_client(self):
        try:
            from dicomweb_client.api import DICOMwebClient
        except ImportError:
            logger.warning("dicomweb-client not installed; DICOMweb push disabled")
            return None

        if self._upload_token:
            return DICOMwebClient(url=self._url, headers={"Authorization": self._upload_token})
        if self._token is not None:
            # a client per push: the token in its headers may have been refreshed since the last one
            return DICOMwebClient(url=self._url, headers={"Authorization": f"Bearer {self._token.get()}"})
        if self._client is not None:
            return self._client
        # HTTP basic through a requests session: dicomweb-client takes no username or password itself (passing them
        # failed every authenticated push until 2026-10-27)
        import requests

        session = requests.Session()
        if self._username:
            session.auth = (self._username, self._password or "")
        self._client = DICOMwebClient(url=self._url, session=session)
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
            if self._upload_token and self._upload_token in str(err):
                err = _without(err, self._upload_token, self._url)
                if raise_errors:
                    raise err from None              # the original names the token
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


def header_safe(value: str) -> bool:
    """Whether a value goes into an HTTP header as it is: no line break or NUL, no leading space. The HTTP library
    refuses any other value with an error that quotes it."""
    return value == value.lstrip() and not any(c in value for c in "\r\n\0")


def _without(err: Exception, secret: str, url: str) -> Exception:
    """The error with ``secret`` replaced by ``[upload token]``, as the same kind of error where it can be."""
    if isinstance(err, DICOMwebPushError):
        return DICOMwebPushError(err.status, err.body.replace(secret, "[upload token]"), url)
    return RuntimeError(str(err).replace(secret, "[upload token]"))


def _same_url(a: str, b: str) -> bool:
    """Whether two URLs name the same endpoint: scheme and host compared without case, the path without a final slash."""
    from urllib.parse import urlsplit

    pa, pb = urlsplit(a.strip()), urlsplit(b.strip())
    return ((pa.scheme.lower(), pa.netloc.lower(), pa.path.rstrip("/"), pa.query)
            == (pb.scheme.lower(), pb.netloc.lower(), pb.path.rstrip("/"), pb.query))


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
