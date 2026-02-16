from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

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
    def get_study(self, study_instance_uid: str) -> Optional[StudyMetadata]:
        raise NotImplementedError

    def get_segmentation(self, sop_instance_uid: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def store_artifact(self, dataset_bytes: bytes, content_type: str = "application/dicom") -> str:
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


class OrthancAdapter(OrthancAdapterBase):
    def __init__(self, settings: Settings):
        if DICOMwebClient is None:
            raise OrthancAdapterError("dicomweb-client is not available; install dependencies")

        self.client = DICOMwebClient(
            url=settings.orthanc_base_url,
            username=settings.orthanc_username,
            password=settings.orthanc_password,
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


def build_orthanc_adapter(settings: Settings | None = None) -> OrthancAdapterBase:
    settings = settings or get_settings()
    if settings.orthanc_use_mock:
        logger.info("Using fake Orthanc adapter (mock data mode)")
        return FakeOrthancAdapter()

    logger.info("Using real Orthanc adapter at %s", settings.orthanc_base_url)
    return OrthancAdapter(settings)
