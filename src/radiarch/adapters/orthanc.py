from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from ..config import Settings, get_settings
from . import sample_data

try:
    from dicomweb_client.api import DICOMwebClient
except ImportError:  # pragma: no cover - dependency mocked in tests
    DICOMwebClient = None


class OrthancAdapterError(RuntimeError):
    pass


@dataclass
class StudyMetadata:
    study_instance_uid: str
    raw: Dict[str, Any]


class OrthancAdapterBase:
    # ---- Metadata / control-plane methods -----------------------------

    def get_study(self, study_instance_uid: str) -> Optional[StudyMetadata]:
        raise NotImplementedError

    def get_segmentation(self, sop_instance_uid: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def store_artifact(self, dataset_bytes: bytes, content_type: str = "application/dicom") -> str:
        raise NotImplementedError

    # ---- Data-plane methods (Geometry Service path) -------------------

    def can_retrieve_instances(self) -> bool:
        """Does this adapter support downloading DICOM instance bytes?

        Returns False for metadata-only fake adapters — callers can use
        this to decide whether to fall back to a local data root.
        """
        return False

    def search_for_series(
        self,
        study_instance_uid: str,
        modality: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return series-level metadata for ``study_instance_uid``.

        Each entry should at minimum expose ``SeriesInstanceUID`` and
        ``Modality``. Implementations may also include
        ``NumberOfSeriesRelatedInstances`` so the Geometry Service can
        pick the largest CT series when no explicit UID is provided.
        """
        raise NotImplementedError

    def retrieve_series(
        self,
        study_instance_uid: str,
        series_instance_uid: str,
    ) -> Iterable[Any]:
        """Yield ``pydicom.Dataset`` objects for every instance in a series."""
        raise NotImplementedError


class FakeOrthancAdapter(OrthancAdapterBase):
    def get_study(self, study_instance_uid: str) -> Optional[StudyMetadata]:
        study = sample_data.SAMPLE_STUDIES.get(study_instance_uid)
        if not study:
            return None
        return StudyMetadata(study_instance_uid=study_instance_uid, raw=study)

    def get_segmentation(self, sop_instance_uid: str) -> Optional[Dict[str, Any]]:
        return sample_data.SAMPLE_SEGMENTATIONS.get(sop_instance_uid)

    def store_artifact(self, dataset_bytes: bytes, content_type: str = "application/dicom") -> str:
        logger.debug("Storing artifact in fake adapter (content type %s, %s bytes)", content_type, len(dataset_bytes))
        return "mock-artifact-uid"

    # The fake adapter has no DICOM bytes — expose metadata only so the
    # Geometry Service can cleanly detect "mock mode" and fall back to
    # the local data root.
    def can_retrieve_instances(self) -> bool:
        return False

    def search_for_series(
        self,
        study_instance_uid: str,
        modality: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        study = sample_data.SAMPLE_STUDIES.get(study_instance_uid)
        if not study:
            return []
        series = study.get("series", [])
        if modality:
            series = [s for s in series if s.get("Modality") == modality]
        return list(series)

    def retrieve_series(self, study_instance_uid, series_instance_uid):
        raise OrthancAdapterError(
            "FakeOrthancAdapter does not serve DICOM bytes; "
            "set RADIARCH_ORTHANC_USE_MOCK=false or use a real adapter."
        )


class OrthancAdapter(OrthancAdapterBase):
    def __init__(self, settings: Settings):
        if DICOMwebClient is None:
            raise OrthancAdapterError("dicomweb-client is not available; install dependencies")

        import requests
        session = requests.Session()
        if settings.orthanc_username and settings.orthanc_password:
            session.auth = (settings.orthanc_username, settings.orthanc_password)

        self.client = DICOMwebClient(
            url=str(settings.orthanc_base_url),
            session=session,
        )

    def get_study(self, study_instance_uid: str) -> Optional[StudyMetadata]:
        logger.debug("Fetching study metadata from Orthanc: %s", study_instance_uid)
        studies = self.client.search_for_studies(search_filters={"StudyInstanceUID": study_instance_uid})
        if not studies:
            return None
        return StudyMetadata(study_instance_uid=study_instance_uid, raw=studies[0])

    def get_segmentation(self, sop_instance_uid: str) -> Optional[Dict[str, Any]]:
        logger.debug("Fetching segmentation %s from Orthanc", sop_instance_uid)
        try:
            dataset = self.client.retrieve_instance(sop_instance_uid)
        except Exception as exc:  # pragma: no cover - network errors
            logger.error("Failed to retrieve segmentation %s: %s", sop_instance_uid, exc)
            return None
        return {"InstanceUID": sop_instance_uid, "Raw": dataset}

    def store_artifact(self, dataset_bytes: bytes, content_type: str = "application/dicom") -> str:
        logger.debug("Storing artifact via STOW-RS (%s bytes)", len(dataset_bytes))
        try:
            result = self.client.store_instances(dataset_bytes, content_type=content_type)
        except Exception as exc:  # pragma: no cover
            raise OrthancAdapterError(f"Failed to store artifact: {exc}") from exc
        return result[0]["ID"] if result else ""

    def can_retrieve_instances(self) -> bool:
        return True

    def search_for_series(
        self,
        study_instance_uid: str,
        modality: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {"StudyInstanceUID": study_instance_uid}
        if modality:
            filters["Modality"] = modality
        try:
            results = self.client.search_for_series(search_filters=filters)
        except Exception as exc:  # pragma: no cover — network paths
            raise OrthancAdapterError(
                f"search_for_series failed for study {study_instance_uid}: {exc}"
            ) from exc
        return self._flatten_series_metadata(results)

    def retrieve_series(
        self,
        study_instance_uid: str,
        series_instance_uid: str,
    ) -> Iterable[Any]:
        try:
            yield from self.client.retrieve_series(
                study_instance_uid=study_instance_uid,
                series_instance_uid=series_instance_uid,
            )
        except Exception as exc:  # pragma: no cover — network paths
            raise OrthancAdapterError(
                f"retrieve_series failed for {series_instance_uid}: {exc}"
            ) from exc

    @staticmethod
    def _flatten_series_metadata(results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize DICOMwebClient search responses.

        dicomweb-client returns tag-addressed dicts (``{"0020000E":
        {"Value": ["..."]}}``) which are miserable downstream. Flatten
        the handful of tags we actually use into plain strings so callers
        can treat the result as a regular dict.
        """
        flat: List[Dict[str, Any]] = []
        for entry in results:
            if not isinstance(entry, dict):
                continue
            series_uid = _tag_value(entry, "0020000E") or entry.get("SeriesInstanceUID")
            modality = _tag_value(entry, "00080060") or entry.get("Modality")
            count = _tag_value(entry, "00201209") or entry.get("NumberOfSeriesRelatedInstances")
            flat.append(
                {
                    "SeriesInstanceUID": series_uid,
                    "Modality": modality,
                    "NumberOfSeriesRelatedInstances": int(count) if count is not None else None,
                    "_raw": entry,
                }
            )
        return flat


def _tag_value(entry: Dict[str, Any], tag: str) -> Any:
    """Pull the first Value out of a DICOMweb tag-addressed dict, if present."""
    node = entry.get(tag)
    if not isinstance(node, dict):
        return None
    values = node.get("Value")
    if not values:
        return None
    return values[0]


def build_orthanc_adapter(settings: Settings | None = None) -> OrthancAdapterBase:
    settings = settings or get_settings()
    if settings.orthanc_use_mock:
        logger.info("Using fake Orthanc adapter (mock data mode)")
        return FakeOrthancAdapter()

    logger.info("Using real Orthanc adapter at %s", settings.orthanc_base_url)
    return OrthancAdapter(settings)
