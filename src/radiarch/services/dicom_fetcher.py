"""Download a DICOM study from a PACS and stage it to a temp directory.

The Geometry Service talks to PACS through the ``OrthancAdapterBase``
abstraction. This module sits between that adapter and OpenTPS's
``dataLoader.readData`` (which only knows how to read from a directory
on disk). Flow:

1. Ask the adapter which series live in the study.
2. Pick the target CT series — explicit UID wins; otherwise "largest"
   (the series with the most instances, which in practice is the
   planning CT). Deterministic.
3. Pick the RTSTRUCT series — explicit UID wins; otherwise the first
   RTSTRUCT series the adapter returns.
4. Stream every instance of both series through the adapter and write
   ``.dcm`` files into an mkdtemp'd directory.
5. Yield a :class:`StagedDicom` whose ``__exit__`` wipes the directory.

Only axis-aligned CT is supported in v1 (see the resampling module);
we don't enforce that here — invalid affines are caught downstream
with a clear error.

Adapters that can't serve bytes (``FakeOrthancAdapter``, etc.) raise
via ``retrieve_series``; callers should check
``adapter.can_retrieve_instances()`` first and fall back to local disk
loading if it returns False.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from ..adapters.orthanc import OrthancAdapterBase
from ..models.geometry import PatientRef


class DicomFetcherError(RuntimeError):
    """The adapter couldn't produce a usable study for this request."""


@dataclass
class StagedDicom(AbstractContextManager):
    """A temp directory populated with one CT + (optional) RTSTRUCT series.

    Use as a context manager so the directory is cleaned up reliably even
    on exceptions — OpenTPS's ``dataLoader`` reads everything eagerly, so
    we can delete the files as soon as the caller hands us back the
    loaded ``CTImage`` / ``RTStruct`` objects.
    """

    directory: Path
    ct_series_uid: str
    rtstruct_series_uid: Optional[str] = None
    files_written: int = 0
    _cleaned: bool = field(default=False, repr=False)

    def __enter__(self) -> "StagedDicom":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self._cleaned:
            return
        shutil.rmtree(self.directory, ignore_errors=True)
        self._cleaned = True


# ---------------------------------------------------------------------------
# DicomFetcher
# ---------------------------------------------------------------------------

class DicomFetcher:
    """Adapter-driven DICOM study download."""

    def __init__(self, adapter: OrthancAdapterBase) -> None:
        self.adapter = adapter

    # ---- Capability probe --------------------------------------------

    @property
    def can_fetch(self) -> bool:
        """True iff the adapter is wired to deliver DICOM bytes."""
        return bool(self.adapter.can_retrieve_instances())

    # ---- Main entry point --------------------------------------------

    def fetch(self, patient_ref: PatientRef) -> StagedDicom:
        """Download the study and return a populated :class:`StagedDicom`.

        On any failure we clean up the temp dir before raising — callers
        should *not* have to worry about partial state.
        """
        if not self.can_fetch:
            raise DicomFetcherError(
                "Adapter does not support retrieving DICOM instances; "
                "caller should fall back to data_root loading."
            )

        ct_series_uid = self._pick_ct_series(
            patient_ref.dicom_study_uid, patient_ref.ct_series_uid
        )
        rtstruct_series_uid = self._pick_rtstruct_series(
            patient_ref.dicom_study_uid, patient_ref.rtstruct_uid
        )

        tmpdir = Path(tempfile.mkdtemp(prefix="radiarch_dicom_"))
        try:
            ct_count = self._stage_series(
                tmpdir, patient_ref.dicom_study_uid, ct_series_uid, "CT"
            )
            rt_count = 0
            if rtstruct_series_uid:
                rt_count = self._stage_series(
                    tmpdir, patient_ref.dicom_study_uid, rtstruct_series_uid, "RT"
                )
            logger.info(
                "Staged study %s → %s (CT=%d instances, RT=%d instances)",
                patient_ref.dicom_study_uid,
                tmpdir,
                ct_count,
                rt_count,
            )
            return StagedDicom(
                directory=tmpdir,
                ct_series_uid=ct_series_uid,
                rtstruct_series_uid=rtstruct_series_uid,
                files_written=ct_count + rt_count,
            )
        except Exception:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise

    # ---- Series selection --------------------------------------------

    def _pick_ct_series(self, study_uid: str, explicit_uid: Optional[str]) -> str:
        """Resolve the target CT series UID.

        Explicit UIDs short-circuit any search — if the caller said
        ``ct_series_uid="1.2.3"``, that's what we use, and we only hit
        ``search_for_series`` to confirm it exists. When the caller
        leaves it null, we list all CT series in the study and pick the
        one with the most instances (the planning CT, in practice).
        """
        if explicit_uid:
            return explicit_uid

        series = self.adapter.search_for_series(study_uid, modality="CT")
        if not series:
            raise DicomFetcherError(
                f"No CT series found in study {study_uid}"
            )

        # "Largest" = most instances. Deterministic tiebreak on UID so
        # two equally-large series always resolve the same way across
        # machines.
        def _sort_key(s: Dict[str, Any]):
            count = s.get("NumberOfSeriesRelatedInstances") or 0
            return (-int(count), str(s.get("SeriesInstanceUID") or ""))

        winner = sorted(series, key=_sort_key)[0]
        uid = winner.get("SeriesInstanceUID")
        if not uid:
            raise DicomFetcherError(
                f"Study {study_uid} has a CT series missing SeriesInstanceUID"
            )
        return uid

    def _pick_rtstruct_series(
        self, study_uid: str, explicit_uid: Optional[str]
    ) -> Optional[str]:
        """Resolve the RTSTRUCT series UID. ``None`` means "no RTSTRUCT"."""
        if explicit_uid:
            return explicit_uid

        try:
            series = self.adapter.search_for_series(study_uid, modality="RTSTRUCT")
        except Exception as exc:
            logger.warning(
                "RTSTRUCT series lookup failed for %s: %s — continuing without it",
                study_uid,
                exc,
            )
            return None

        if not series:
            logger.info("No RTSTRUCT series found in study %s", study_uid)
            return None

        # For now: take the first one. When we encounter studies with
        # multiple RTSTRUCT series this'll need policy (pick by Label,
        # by most recent, etc.) — revisit when the real data forces it.
        return series[0].get("SeriesInstanceUID")

    # ---- Download ----------------------------------------------------

    def _stage_series(
        self,
        tmpdir: Path,
        study_uid: str,
        series_uid: str,
        kind: str,
    ) -> int:
        """Pull every instance of ``series_uid`` into ``tmpdir``. Returns count."""
        written = 0
        for dataset in self.adapter.retrieve_series(study_uid, series_uid):
            sop_uid = getattr(dataset, "SOPInstanceUID", None) or f"{kind}_{written:04d}"
            # Filename prefix keeps CTs and RT structs visually grouped in
            # the temp dir — helps when debugging a failed build by hand.
            dest = tmpdir / f"{kind}_{sop_uid}.dcm"
            dataset.save_as(str(dest))
            written += 1
        if written == 0:
            raise DicomFetcherError(
                f"Series {series_uid} produced zero instances"
            )
        return written


__all__ = ["DicomFetcher", "DicomFetcherError", "StagedDicom"]
