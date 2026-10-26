"""What every RT object radiarch writes shares (roadmap R6).

:class:`CaseContext` carries the patient, study and frame-of-reference
identity the objects of one case must agree on, plus the CT series they
reference. :func:`new_dataset` builds the Patient, General Study, RT Series,
General Equipment and SOP Common modules of a new object on top of it, and
:func:`label_research` stamps the intended-use statement into every object
(public text attributes and a private block, as the legacy exporter did), so
nothing radiarch writes can be mistaken for clinical output.

UIDs come from pydicom's root. A case whose CT has no Frame of Reference UID
(the OpenTPS phantom, for one) gets a stable one derived from the CT series
UID, so the objects written for it still agree with each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence as DSeq
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ...models.common import NOT_FOR_CLINICAL_USE
from ..uids import SOP

MANUFACTURER = "Radiarch"
MODEL_NAME = "radiarch research TPS"
PRIVATE_CREATOR = "RADIARCH"
PRIVATE_GROUP = 0x7779

# Retired Detached Study Management SOP class, still what RT Referenced Study
# Sequence items point at (the standard's own example).
DETACHED_STUDY_SOP_CLASS = "1.2.840.10008.3.1.2.3.1"


def software_version() -> str:
    try:
        from importlib.metadata import version
        return version("radiarch")
    except Exception:  # pragma: no cover
        return "0.1.0"


def stable_uid(*parts: str) -> str:
    """A UID that is the same every time for the same ``parts``."""
    return generate_uid(entropy_srcs=[str(p) for p in parts])


@dataclass
class CaseContext:
    """Identity shared by all objects of one case."""

    patient_name: str = "ANONYMOUS"
    patient_id: str = "ANONYMOUS"
    patient_birth_date: str = ""
    patient_sex: str = ""
    study_instance_uid: str = ""
    study_date: str = ""
    study_time: str = ""
    study_id: str = ""
    accession_number: str = ""
    study_description: str = ""
    referring_physician: str = ""
    frame_of_reference_uid: str = ""
    ct_series_instance_uid: str = ""
    ct_sop_instance_uids: List[str] = field(default_factory=list)
    patient_position: str = "HFS"
    institution_name: str = "Radiarch research"
    station_name: str = "radiarch"
    operator: str = "radiarch"
    engine: str = ""                   # the dose engine and its version, for the private block
    machine: str = ""                  # the machine model id
    now: Optional[datetime] = None      # fixed for reproducible files; None = the clock

    def __post_init__(self) -> None:
        if not self.study_instance_uid:
            self.study_instance_uid = stable_uid(self.ct_series_instance_uid, "study") if self.ct_series_instance_uid else generate_uid()
        if not self.frame_of_reference_uid:
            self.frame_of_reference_uid = (stable_uid(self.ct_series_instance_uid, "for")
                                           if self.ct_series_instance_uid else generate_uid())
        if not self.patient_position:
            self.patient_position = "HFS"
        if self.patient_sex not in ("", "M", "F", "O"):
            self.patient_sex = "O"

    @property
    def clock(self) -> datetime:
        return self.now or datetime.now()

    @property
    def date(self) -> str:
        return self.clock.strftime("%Y%m%d")

    @property
    def time(self) -> str:
        return self.clock.strftime("%H%M%S")

    # ----- builders ----------------------------------------------------

    @classmethod
    def from_ct(cls, ct, **overrides) -> "CaseContext":
        """From a :class:`radiarch.dicom.ct.CTVolume` (or anything with its attributes)."""
        patient = getattr(ct, "patient", None)
        kw = dict(
            patient_name=str(getattr(patient, "name", "") or "ANONYMOUS"),
            patient_id=str(getattr(patient, "id", "") or "ANONYMOUS"),
            patient_birth_date=str(getattr(patient, "birth_date", "") or ""),
            patient_sex=str(getattr(patient, "sex", "") or ""),
            study_instance_uid=str(getattr(ct, "studyInstanceUID", "") or ""),
            study_date=str(getattr(ct, "studyDate", "") or ""),
            study_time=str(getattr(ct, "studyTime", "") or ""),
            study_id=str(getattr(ct, "studyID", "") or ""),
            accession_number=str(getattr(ct, "accessionNumber", "") or ""),
            study_description=str(getattr(ct, "studyDescription", "") or ""),
            frame_of_reference_uid=str(getattr(ct, "frameOfReferenceUID", "") or ""),
            ct_series_instance_uid=str(getattr(ct, "seriesInstanceUID", "") or ""),
            ct_sop_instance_uids=list(getattr(ct, "sopInstanceUIDs", []) or []),
            patient_position=str(getattr(ct, "patientPosition", "") or "HFS"),
        )
        kw.update(overrides)
        return cls(**kw)

    @classmethod
    def from_geometry(cls, geometry, **overrides) -> "CaseContext":
        """From a persisted :class:`radiarch.models.geometry.GeometryResult`."""
        meta = getattr(geometry, "ct_metadata", None)
        g = lambda name, default="": str(getattr(meta, name, None) or default)  # noqa: E731
        kw = dict(
            patient_name=g("patient_name", "ANONYMOUS"),
            patient_id=g("patient_id", "ANONYMOUS"),
            patient_birth_date=g("patient_birth_date"),
            patient_sex=g("patient_sex"),
            study_instance_uid=g("study_instance_uid"),
            study_date=g("study_date"),
            study_time=g("study_time"),
            study_id=g("study_id"),
            accession_number=g("accession_number"),
            study_description=g("study_description"),
            frame_of_reference_uid=str(getattr(geometry, "frame_of_reference_uid", "") or ""),
            ct_series_instance_uid=g("series_instance_uid"),
            ct_sop_instance_uids=list(getattr(meta, "sop_instance_uids", None) or []),
            patient_position=g("patient_position", "HFS"),
        )
        kw.update(overrides)
        return cls(**kw)


# ---------------------------------------------------------------------------
# Dataset skeleton
# ---------------------------------------------------------------------------

def seq(items: Iterable[Dataset]) -> DSeq:
    return DSeq(list(items))


def ref(sop_class: str, sop_instance: str) -> Dataset:
    d = Dataset()
    d.ReferencedSOPClassUID = sop_class
    d.ReferencedSOPInstanceUID = sop_instance
    return d


def new_dataset(ctx: CaseContext, sop_class: str, modality: str, *, series_number: int,
                series_instance_uid: Optional[str] = None,
                sop_instance_uid: Optional[str] = None, instance_number: int = 1) -> FileDataset:
    """A file dataset with the common modules filled from ``ctx``."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = sop_instance_uid or generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
    meta.ImplementationVersionName = "RADIARCH"
    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)

    # SOP Common
    ds.SpecificCharacterSet = "ISO_IR 100"
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.InstanceCreationDate = ctx.date
    ds.InstanceCreationTime = ctx.time

    # Patient
    ds.PatientName = ctx.patient_name
    ds.PatientID = ctx.patient_id
    ds.PatientBirthDate = ctx.patient_birth_date
    ds.PatientSex = ctx.patient_sex

    # General Study
    ds.StudyInstanceUID = ctx.study_instance_uid
    ds.StudyDate = ctx.study_date
    ds.StudyTime = ctx.study_time
    ds.ReferringPhysicianName = ctx.referring_physician
    ds.StudyID = ctx.study_id
    ds.AccessionNumber = ctx.accession_number
    if ctx.study_description:
        ds.StudyDescription = ctx.study_description

    # RT Series
    ds.Modality = modality
    ds.SeriesInstanceUID = series_instance_uid or generate_uid()
    ds.SeriesNumber = int(series_number)
    ds.SeriesDescription = "RESEARCH - " + NOT_FOR_CLINICAL_USE      # the R0 contract, as the legacy exporter wrote it
    ds.SeriesDate = ctx.date
    ds.SeriesTime = ctx.time
    ds.OperatorsName = ctx.operator
    ds.InstanceNumber = int(instance_number)

    # General Equipment
    ds.Manufacturer = MANUFACTURER
    ds.ManufacturerModelName = MODEL_NAME
    ds.InstitutionName = ctx.institution_name
    ds.StationName = ctx.station_name
    ds.SoftwareVersions = software_version()

    label_research(ds, engine=ctx.engine, machine=ctx.machine)
    return ds


def with_frame_of_reference(ds: Dataset, ctx: CaseContext) -> Dataset:
    ds.FrameOfReferenceUID = ctx.frame_of_reference_uid
    ds.PositionReferenceIndicator = ""
    return ds


def label_research(ds: Dataset, engine: str = "", machine: str = "") -> Dataset:
    """The intended-use statement, where every reader of the file will see it, and the attribution
    (radiarch version, engine, machine model) in the same private block."""
    block = ds.private_block(PRIVATE_GROUP, PRIVATE_CREATOR, create=True)
    block.add_new(0x01, "LO", NOT_FOR_CLINICAL_USE)
    block.add_new(0x02, "LO", f"radiarch {software_version()}"[:64])
    if engine:
        block.add_new(0x03, "LO", f"engine {engine}"[:64])
    if machine:
        block.add_new(0x04, "LO", f"machine {machine}"[:64])
    return ds


def research_text(text: str = "") -> str:
    """``text`` prefixed with the short intended-use statement, within an LO."""
    s = f"{NOT_FOR_CLINICAL_USE}; {text}" if text else NOT_FOR_CLINICAL_USE
    return s[:64]


def ct_image_refs(ctx: CaseContext) -> List[Dataset]:
    return [ref(SOP.CT, uid) for uid in ctx.ct_sop_instance_uids]


def save(ds: Dataset, path: Union[str, Path]) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(str(path), enforce_file_format=True)
    return str(path)


def ds_list(values: Sequence[float]) -> List[float]:
    """Floats rounded so they fit DICOM DS (16 characters)."""
    return [float(f"{float(v):.6g}") for v in values]


__all__ = [
    "CaseContext", "MANUFACTURER", "DETACHED_STUDY_SOP_CLASS", "stable_uid", "software_version",
    "seq", "ref", "new_dataset", "with_frame_of_reference", "label_research", "research_text",
    "ct_image_refs", "save", "ds_list",
]


def per_fraction(plan, n_fractions: int):
    """The plan with one fraction's metersets, as DICOM's fraction group and treatment records state them.

    A photon plan's metersets are the whole course's (radiarch optimizes against the course dose), so one fraction's
    are a ``1 / n_fractions`` share. A proton plan carries its own fraction count (its spot metersets times it make
    the course), so one fraction's are ``plan.n_fractions / n_fractions`` of its own."""
    from ...models.photon_plan import PhotonPlan

    n = max(1, int(n_fractions))
    if isinstance(plan, PhotonPlan):
        return plan.scaled(1.0 / n) if n > 1 else plan
    own = max(1, int(getattr(plan, "n_fractions", 1) or 1))
    if own == n:
        return plan
    return plan.with_spot_mus(plan.spot_mus * (own / n)).model_copy(update={"n_fractions": n})
