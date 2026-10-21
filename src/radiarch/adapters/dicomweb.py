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

    def store_instances(self, instances, raise_errors: bool = False) -> bool:
        """Push DICOM instances via STOW-RS: pydicom datasets, file paths or bytes.

        Returns True on success. Failures are logged and return False unless
        ``raise_errors`` is set — a plan job should not fail because the PACS is
        unreachable, but an explicit push request wants the error.
        """
        if not self.enabled:
            if raise_errors:
                raise RuntimeError("DICOMweb push is disabled: RADIARCH_DICOMWEB_URL is empty")
            return False

        client = self._get_client()
        if client is None:
            if raise_errors:
                raise RuntimeError("dicomweb-client is not installed")
            return False

        try:
            datasets = [_as_dataset(x) for x in (instances if isinstance(instances, (list, tuple)) else [instances])]
            logger.info("STOW-RS push of {} instance(s) to {}", len(datasets), self._url)
            client.store_instances(datasets=datasets)
            logger.info("STOW-RS push succeeded")
            return True
        except Exception as exc:
            if raise_errors:
                raise
            logger.error("STOW-RS push failed (non-fatal): {}", exc)
            return False


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
