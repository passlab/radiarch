"""A planning case on disk: one CT series and its structure sets (roadmap R15).

Replaces the OpenTPS ``dataLoader`` path the geometry service used. The CT
series is the one a structure set references when it says so, else the
series with the most slices; every structure set in the directory is read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from loguru import logger

from .ct import CTVolume, inventory, read_ct_series
from .rtstruct import Contour, StructureSet, read_rtstruct


@dataclass
class LoadedCase:
    ct: CTVolume
    structure_sets: List[StructureSet] = field(default_factory=list)

    @property
    def contours(self) -> List[Contour]:
        return [c for s in self.structure_sets for c in s.contours]

    @property
    def patient(self):
        return self.ct.patient


def load_case(directory: Union[str, Path], ct_series_uid: Optional[str] = None,
              rtstruct_uid: Optional[str] = None) -> LoadedCase:
    inv = inventory(directory)
    if not inv.ct_series:
        raise ValueError(f"no CT series found under {directory}")
    structure_sets = [read_rtstruct(p) for p in inv.rtstructs]
    if rtstruct_uid:
        # the SOP Instance UID names one structure set; a series UID may name several (TG-119 ships four in one series)
        by_sop = [s for s in structure_sets if s.sop_instance_uid == rtstruct_uid]
        chosen = by_sop or [s for s in structure_sets if s.series_instance_uid == rtstruct_uid]
        if not chosen:
            raise ValueError(f"structure set {rtstruct_uid} not found under {directory} "
                             f"({len(structure_sets)} structure set(s) there)")
        structure_sets = chosen
    series_uid = ct_series_uid
    if series_uid is None:
        referenced = [s.referenced_ct_series_uid for s in structure_sets if s.referenced_ct_series_uid in inv.ct_series]
        if referenced:
            series_uid = referenced[0]
        else:
            series_uid = max(inv.ct_series, key=lambda k: len(inv.ct_series[k]))
    if series_uid not in inv.ct_series:
        raise ValueError(f"CT series {series_uid} not found under {directory}")
    if len(inv.ct_series) > 1:
        logger.info("{} CT series under {}; using {} ({} slices)", len(inv.ct_series), directory, series_uid, len(inv.ct_series[series_uid]))
    ct = read_ct_series(inv.ct_series[series_uid])
    return LoadedCase(ct=ct, structure_sets=structure_sets)


__all__ = ["LoadedCase", "load_case"]
