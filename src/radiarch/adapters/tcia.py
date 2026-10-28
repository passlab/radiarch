"""Public cases from The Cancer Imaging Archive (TCIA), for trying radiarch on a real CT with contoured structures.

TCIA's NBIA REST API serves its public collections without an account. A patient's CT and structure set are
downloaded to a local cache (never into the repository) and can then be pushed to a DICOMweb server, as
``radiarch fetch-tcia`` does for the lung demo (docs/demo.md). Each collection has its own licence, which comes with
every series (LICENSE in the cache) and which the caller shows; NSCLC-Radiomics, the demo's, is CC BY-NC 3.0.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

API = "https://services.cancerimagingarchive.net/nbia-api/services/v1"
TIMEOUT = 300


class TCIAError(RuntimeError):
    pass


@dataclass
class FetchedCase:
    collection: str
    patient_id: str
    study_instance_uid: str
    series: Dict[str, List[Path]] = field(default_factory=dict)     # modality -> files
    licence: str = ""

    @property
    def files(self) -> List[Path]:
        return [f for files in self.series.values() for f in files]


def _session(session=None):
    if session is not None:
        return session
    import requests

    return requests.Session()


def list_series(collection: str, patient_id: str, session=None) -> List[dict]:
    """The patient's series in the collection, as NBIA describes them (SeriesInstanceUID, StudyInstanceUID, Modality, ...)."""
    r = _session(session).get(f"{API}/getSeries", params={"Collection": collection, "PatientID": patient_id}, timeout=TIMEOUT)
    r.raise_for_status()
    rows = r.json() if r.content else []
    if not rows:
        raise TCIAError(f"TCIA has no public series of patient {patient_id!r} in collection {collection!r}")
    return rows


def download_series(series_uid: str, dest: Path, session=None) -> List[Path]:
    """One series into ``dest`` (its DICOM files and the collection's LICENSE); a completed download is reused."""
    done = dest / ".complete"
    if not done.exists():
        r = _session(session).get(f"{API}/getImage", params={"SeriesInstanceUID": series_uid}, timeout=TIMEOUT)
        r.raise_for_status()
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                base = Path(name).name
                if base.lower().endswith(".dcm") or base == "LICENSE":
                    (dest / base).write_bytes(z.read(name))
        if not any(dest.glob("*.dcm")):
            raise TCIAError(f"series {series_uid}: the download held no DICOM files")
        done.touch()
    return sorted(dest.glob("*.dcm"))


def fetch_patient(collection: str, patient_id: str, cache: Path, modalities: Iterable[str] = ("CT", "RTSTRUCT"),
                  session=None) -> FetchedCase:
    """The patient's planning study: the study with a structure set (else the first), its series of the modalities
    asked for, downloaded into ``cache/<collection>/<patient>/<modality>_<series uid>``."""
    session = _session(session)
    wanted = {m.upper() for m in modalities}
    rows = [s for s in list_series(collection, patient_id, session) if str(s.get("Modality", "")).upper() in wanted]
    studies = sorted({s["StudyInstanceUID"] for s in rows})
    if not studies:
        raise TCIAError(f"patient {patient_id!r} has no {'/'.join(sorted(wanted))} series in {collection!r}")
    with_struct = [u for u in studies if any(s["StudyInstanceUID"] == u and s["Modality"] == "RTSTRUCT" for s in rows)]
    study = (with_struct or studies)[0]
    case = FetchedCase(collection=collection, patient_id=patient_id, study_instance_uid=study)
    for s in sorted((s for s in rows if s["StudyInstanceUID"] == study), key=lambda s: (s["Modality"], s["SeriesInstanceUID"])):
        d = Path(cache) / collection / patient_id / f"{s['Modality']}_{s['SeriesInstanceUID']}"
        case.series.setdefault(s["Modality"], []).extend(download_series(s["SeriesInstanceUID"], d, session))
        lic = d / "LICENSE"
        if not case.licence and lic.exists():
            case.licence = lic.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0]
    return case


def push(case: FetchedCase, notifier=None, batch: int = 25) -> int:
    """The case's files to the DICOMweb server (default: RADIARCH_DICOMWEB_URL), in batches; returns how many."""
    if notifier is None:
        from .dicomweb import DICOMwebNotifier

        notifier = DICOMwebNotifier()
    files = [str(f) for f in case.files]
    for i in range(0, len(files), batch):
        notifier.store_instances(files[i:i + batch], raise_errors=True)
    return len(files)


def licence_notice(case: FetchedCase) -> Optional[str]:
    return f"{case.collection} {case.patient_id} from The Cancer Imaging Archive. {case.licence}" if case.licence else None
