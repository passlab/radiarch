"""DICOM RT objects in and, from R6 on, out (roadmap R2, R6).

Readers turn RT Plan and RT Ion Plan objects into radiarch's plan models,
RT Dose objects into volumes on radiarch's ``(z, y, x)`` grid convention,
and Spatial / Deformable Spatial Registration objects into transforms.
Everything is pydicom; nothing from OpenTPS.
"""

from .reg import DeformableRegistration, SpatialRegistration, read_registration
from .rtdose import RTDoseVolume, read_rtdose, resample_dose_to_grid
from .rtplan import read_ion_plan, read_photon_plan, read_rtplan
from .uids import SOP

__all__ = [
    "SOP",
    "read_rtplan", "read_photon_plan", "read_ion_plan",
    "RTDoseVolume", "read_rtdose", "resample_dose_to_grid",
    "SpatialRegistration", "DeformableRegistration", "read_registration",
]
