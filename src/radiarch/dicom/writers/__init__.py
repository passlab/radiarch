"""DICOM RT objects out (roadmap R6).

One writer per object, all on a :class:`CaseContext` so the objects of a case
agree on patient, study and frame of reference, and all labelled research
use only:

* :func:`write_rtstruct` — RT Structure Set from masks or polygons;
* :func:`write_rtplan` — RT Plan (photon step-and-shoot) or RT Ion Plan (PBS);
* :func:`write_rtdose` — RT Dose, PLAN or BEAM summation;
* :func:`write_rtimage` — RT Image holding a DRR (:mod:`radiarch.dicom.drr`);
* :func:`write_treatment_record`, :func:`write_summary_record` — RT (Ion)
  Beams Treatment Record per session and the RT Treatment Summary Record.

``services/rt_export.py`` assembles a case from the stores and pushes it
with STOW-RS; ADR 0012 has the decisions.
"""

from .common import CaseContext, stable_uid
from .records import CourseSummary, RecordResult, Session, write_summary_record, write_treatment_record
from .rtdose import RTDoseResult, write_rtdose
from .rtimage import RTImageResult, write_rtimage
from .rtplan import PlanWriteOptions, Prescription, RTPlanResult, write_rtplan
from .rtstruct import RTStructResult, Structure, mask_to_polygons, write_rtstruct

__all__ = [
    "CaseContext", "stable_uid",
    "Structure", "RTStructResult", "mask_to_polygons", "write_rtstruct",
    "Prescription", "PlanWriteOptions", "RTPlanResult", "write_rtplan",
    "RTDoseResult", "write_rtdose",
    "RTImageResult", "write_rtimage",
    "Session", "CourseSummary", "RecordResult", "write_treatment_record", "write_summary_record",
]
