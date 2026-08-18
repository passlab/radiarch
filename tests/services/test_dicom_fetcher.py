"""Unit tests for radiarch.services.dicom_fetcher.

We build a fake ``OrthancAdapterBase`` that yields synthesized pydicom
Datasets — enough structure to serialize to disk and be re-read, but no
pixel data. That keeps the tests fast and self-contained.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pydicom
import pytest
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from radiarch.adapters.orthanc import OrthancAdapterBase
from radiarch.models.geometry import PatientRef
from radiarch.services.dicom_fetcher import (
    DicomFetcher,
    DicomFetcherError,
    StagedDicom,
)


# ---------------------------------------------------------------------------
# Minimal synthetic DICOM instance
# ---------------------------------------------------------------------------

def _make_instance(
    study_uid: str,
    series_uid: str,
    modality: str,
    sop_uid: Optional[str] = None,
) -> Dataset:
    """Build a minimally-valid pydicom Dataset that can be written to disk."""
    sop_uid = sop_uid or generate_uid()
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset("", {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.Modality = modality
    ds.PatientName = "TEST^PATIENT"
    ds.PatientID = "PID_001"
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    return ds


# ---------------------------------------------------------------------------
# Fake adapter
# ---------------------------------------------------------------------------

class FakePacsAdapter(OrthancAdapterBase):
    """Serves in-memory synthetic DICOM datasets keyed by study/series."""

    def __init__(
        self,
        series_metadata: List[Dict[str, Any]],
        series_instances: Dict[str, List[Dataset]],
        *,
        can_retrieve: bool = True,
    ) -> None:
        self._series_metadata = series_metadata
        self._series_instances = series_instances
        self._can_retrieve = can_retrieve
        self.retrieve_calls: List[str] = []

    def can_retrieve_instances(self) -> bool:
        return self._can_retrieve

    def search_for_series(
        self, study_instance_uid: str, modality: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        out = [s for s in self._series_metadata if s["_study"] == study_instance_uid]
        if modality:
            out = [s for s in out if s["Modality"] == modality]
        return out

    def retrieve_series(
        self, study_instance_uid: str, series_instance_uid: str
    ) -> Iterable[Dataset]:
        self.retrieve_calls.append(series_instance_uid)
        return iter(self._series_instances.get(series_instance_uid, []))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STUDY_UID = "1.2.840.radiarch.test.study.1"
CT_A_UID = "1.2.840.radiarch.test.series.ct_a"  # 10 instances
CT_B_UID = "1.2.840.radiarch.test.series.ct_b"  # 3 instances (smaller)
RT_UID = "1.2.840.radiarch.test.series.rt"

@pytest.fixture
def fake_adapter() -> FakePacsAdapter:
    # Two CT series (to exercise "largest wins") + one RTSTRUCT.
    metadata = [
        {
            "_study": STUDY_UID,
            "SeriesInstanceUID": CT_A_UID,
            "Modality": "CT",
            "NumberOfSeriesRelatedInstances": 10,
        },
        {
            "_study": STUDY_UID,
            "SeriesInstanceUID": CT_B_UID,
            "Modality": "CT",
            "NumberOfSeriesRelatedInstances": 3,
        },
        {
            "_study": STUDY_UID,
            "SeriesInstanceUID": RT_UID,
            "Modality": "RTSTRUCT",
            "NumberOfSeriesRelatedInstances": 1,
        },
    ]
    instances = {
        CT_A_UID: [_make_instance(STUDY_UID, CT_A_UID, "CT") for _ in range(10)],
        CT_B_UID: [_make_instance(STUDY_UID, CT_B_UID, "CT") for _ in range(3)],
        RT_UID: [_make_instance(STUDY_UID, RT_UID, "RTSTRUCT")],
    }
    return FakePacsAdapter(metadata, instances)


# ---------------------------------------------------------------------------
# Capability probe
# ---------------------------------------------------------------------------

class TestCapability:
    def test_can_fetch_passes_through_from_adapter(self) -> None:
        adapter = FakePacsAdapter([], {}, can_retrieve=True)
        assert DicomFetcher(adapter).can_fetch is True

    def test_cannot_fetch_when_adapter_is_metadata_only(self) -> None:
        adapter = FakePacsAdapter([], {}, can_retrieve=False)
        assert DicomFetcher(adapter).can_fetch is False

    def test_fetch_raises_when_adapter_cannot_serve_bytes(self) -> None:
        adapter = FakePacsAdapter([], {}, can_retrieve=False)
        fetcher = DicomFetcher(adapter)
        with pytest.raises(DicomFetcherError, match="does not support"):
            fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID))


# ---------------------------------------------------------------------------
# Series selection
# ---------------------------------------------------------------------------

class TestSeriesSelection:
    def test_picks_largest_ct_series_when_uid_not_given(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        with fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID)) as staged:
            # CT_A has 10 instances → beats CT_B's 3.
            assert staged.ct_series_uid == CT_A_UID
            # And the fetcher actually downloaded from CT_A, not CT_B.
            assert CT_A_UID in fake_adapter.retrieve_calls
            assert CT_B_UID not in fake_adapter.retrieve_calls

    def test_honors_explicit_ct_series_uid(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        # Force the smaller series even though the largest-wins heuristic
        # would have picked CT_A.
        with fetcher.fetch(
            PatientRef(dicom_study_uid=STUDY_UID, ct_series_uid=CT_B_UID)
        ) as staged:
            assert staged.ct_series_uid == CT_B_UID
            assert CT_B_UID in fake_adapter.retrieve_calls

    def test_honors_explicit_rtstruct_uid(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        with fetcher.fetch(
            PatientRef(dicom_study_uid=STUDY_UID, rtstruct_uid=RT_UID)
        ) as staged:
            assert staged.rtstruct_series_uid == RT_UID

    def test_auto_detects_rtstruct_when_uid_not_given(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        with fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID)) as staged:
            assert staged.rtstruct_series_uid == RT_UID

    def test_rtstruct_is_none_when_study_has_no_rtstruct(self) -> None:
        # Only a CT series, no RTSTRUCT.
        metadata = [
            {"_study": STUDY_UID, "SeriesInstanceUID": CT_A_UID, "Modality": "CT",
             "NumberOfSeriesRelatedInstances": 2},
        ]
        instances = {CT_A_UID: [_make_instance(STUDY_UID, CT_A_UID, "CT") for _ in range(2)]}
        adapter = FakePacsAdapter(metadata, instances)
        with DicomFetcher(adapter).fetch(PatientRef(dicom_study_uid=STUDY_UID)) as staged:
            assert staged.rtstruct_series_uid is None

    def test_deterministic_tiebreak_on_equal_size(self) -> None:
        # Two CT series with the same instance count — sort must pick
        # the same one deterministically across runs.
        metadata = [
            {"_study": STUDY_UID, "SeriesInstanceUID": "uid.zzz", "Modality": "CT",
             "NumberOfSeriesRelatedInstances": 5},
            {"_study": STUDY_UID, "SeriesInstanceUID": "uid.aaa", "Modality": "CT",
             "NumberOfSeriesRelatedInstances": 5},
        ]
        instances = {
            "uid.zzz": [_make_instance(STUDY_UID, "uid.zzz", "CT") for _ in range(5)],
            "uid.aaa": [_make_instance(STUDY_UID, "uid.aaa", "CT") for _ in range(5)],
        }
        adapter = FakePacsAdapter(metadata, instances)
        fetcher = DicomFetcher(adapter)
        # Run twice; both runs must pick the same UID (lexicographically
        # smaller as tiebreak).
        with fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID)) as s1:
            first = s1.ct_series_uid
        with fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID)) as s2:
            assert s2.ct_series_uid == first == "uid.aaa"


# ---------------------------------------------------------------------------
# Staging + cleanup
# ---------------------------------------------------------------------------

class TestStaging:
    def test_writes_all_instances_to_temp_dir(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        with fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID)) as staged:
            files = sorted(staged.directory.iterdir())
            # 10 CTs + 1 RTSTRUCT
            assert len(files) == 11
            assert staged.files_written == 11
            # Files are readable as DICOM.
            for f in files:
                ds = pydicom.dcmread(str(f))
                assert ds.StudyInstanceUID == STUDY_UID

    def test_context_manager_cleans_up_on_success(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        with fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID)) as staged:
            directory = staged.directory
            assert directory.exists()
        assert not directory.exists(), "temp dir must be wiped on __exit__"

    def test_context_manager_cleans_up_on_exception(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        captured: Optional[Path] = None
        with pytest.raises(RuntimeError, match="boom"):
            with fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID)) as staged:
                captured = staged.directory
                raise RuntimeError("boom")
        assert captured is not None
        assert not captured.exists()

    def test_explicit_cleanup_is_idempotent(
        self, fake_adapter: FakePacsAdapter
    ) -> None:
        fetcher = DicomFetcher(fake_adapter)
        staged = fetcher.fetch(PatientRef(dicom_study_uid=STUDY_UID))
        staged.cleanup()
        staged.cleanup()  # second call must not raise
        assert not staged.directory.exists()


# ---------------------------------------------------------------------------
# Error surfaces
# ---------------------------------------------------------------------------

class TestErrors:
    def test_raises_when_study_has_no_ct_series(self) -> None:
        # RTSTRUCT only, no CT → clear error, not silent fallback.
        metadata = [
            {"_study": STUDY_UID, "SeriesInstanceUID": RT_UID, "Modality": "RTSTRUCT",
             "NumberOfSeriesRelatedInstances": 1},
        ]
        adapter = FakePacsAdapter(metadata, {})
        with pytest.raises(DicomFetcherError, match="No CT series"):
            DicomFetcher(adapter).fetch(PatientRef(dicom_study_uid=STUDY_UID))

    def test_raises_when_series_produces_zero_instances(self) -> None:
        # Metadata says there's a CT series, but retrieve_series yields nothing.
        metadata = [
            {"_study": STUDY_UID, "SeriesInstanceUID": CT_A_UID, "Modality": "CT",
             "NumberOfSeriesRelatedInstances": 5},
        ]
        adapter = FakePacsAdapter(metadata, {CT_A_UID: []})
        with pytest.raises(DicomFetcherError, match="zero instances"):
            DicomFetcher(adapter).fetch(PatientRef(dicom_study_uid=STUDY_UID))

    def test_tempdir_removed_after_failed_download(self) -> None:
        # Adapter that claims metadata exists but raises during download —
        # tempdir must still be wiped.
        class BrokenAdapter(FakePacsAdapter):
            def retrieve_series(self, study_uid, series_uid):
                raise RuntimeError("network blew up")

        metadata = [
            {"_study": STUDY_UID, "SeriesInstanceUID": CT_A_UID, "Modality": "CT",
             "NumberOfSeriesRelatedInstances": 5},
        ]
        adapter = BrokenAdapter(metadata, {})
        with pytest.raises(RuntimeError, match="network blew up"):
            DicomFetcher(adapter).fetch(PatientRef(dicom_study_uid=STUDY_UID))

        # The prefix is namespaced, so it's easy to assert no leftovers.
        import tempfile
        tmp_root = Path(tempfile.gettempdir())
        leftovers = list(tmp_root.glob("radiarch_dicom_*"))
        assert not leftovers, f"Temp dir leak: {leftovers}"
