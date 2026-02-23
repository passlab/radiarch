"""Vendor-neutral DICOMweb STOW-RS client for artifact push.

Uses the standard DICOMweb STOW-RS protocol via dicomweb-client,
so any PACS supporting DICOMweb (Orthanc, DCM4CHEE, Google Healthcare API, etc.)
works as a backend.  Configured via RADIARCH_DICOMWEB_URL; disabled when empty.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from ..config import get_settings


class DICOMwebNotifier:
    """Push DICOM artifacts to a remote PACS via STOW-RS."""

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        settings = get_settings()
        self._url = url or settings.dicomweb_url
        self._username = username or settings.dicomweb_username
        self._password = password or settings.dicomweb_password
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from dicomweb_client.api import DICOMwebClient
        except ImportError:
            logger.warning("dicomweb-client not installed; DICOMweb push disabled")
            return None

        kwargs = {"url": self._url}
        if self._username:
            kwargs["username"] = self._username
            kwargs["password"] = self._password

        self._client = DICOMwebClient(**kwargs)
        return self._client

    def store_instances(self, dicom_bytes: bytes) -> bool:
        """Push DICOM data via STOW-RS.  Returns True on success, False on error.

        Failures are logged but never raise — the job should not fail because
        the remote PACS is temporarily unreachable.
        """
        if not self.enabled:
            return False

        client = self._get_client()
        if client is None:
            return False

        try:
            logger.info("STOW-RS push to %s (%d bytes)", self._url, len(dicom_bytes))
            client.store_instances(datasets=[dicom_bytes])
            logger.info("STOW-RS push succeeded")
            return True
        except Exception as exc:
            logger.error("STOW-RS push failed (non-fatal): %s", exc)
            return False


# Module-level singleton (lazy)
_notifier: Optional[DICOMwebNotifier] = None


def get_dicomweb_notifier() -> DICOMwebNotifier:
    global _notifier
    if _notifier is None:
        _notifier = DICOMwebNotifier()
    return _notifier
