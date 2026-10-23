"""SBRT plan-quality indices (roadmap R8): dose fall-off and conformity graded as the RTOG lung SBRT
protocols do.

* **R100** — volume (anywhere in the body) receiving the prescription, over the PTV volume.
* **R50** — volume receiving half the prescription, over the PTV volume.
* **D2cm** — the highest dose 2 cm or more from the PTV in any direction, in % of the prescription.
* **GI** — Paddick's gradient index, V50 % / V100 % (reported, not graded).
* **Lung V20** — % of the lungs (minus the GTV) receiving 20 Gy or more.

Grading follows the conformality table of RTOG 0813 and RTOG 0915 (the same table; NRG LU002 and the NRG
Oncology protocol template reproduce it): below the first limit no deviation, up to the second a minor
deviation, beyond it a major one; between tabulated PTV volumes the limits are interpolated linearly and
outside them clamped. Provenance of the numbers: the minor-deviation limits of R50 and D2cm were checked
against Table 6 of the NRG Oncology radiation-therapy protocol template (v2025.01.31); the no-deviation
limits are the RTOG 0813/0915 values as reproduced in the lung SBRT literature (the 1.8 cc row checked
against several sources); confirm them against the protocol before relying on them. R100 below 1.2 (minor
up to 1.5) and lung V20 below 10 % (minor up to 15 %) are the protocols' too.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Optional, Sequence

import numpy as np

# PTV volume (cc) | R50 none | R50 minor | D2cm none (% Rx) | D2cm minor (% Rx)
RTOG_CONFORMALITY = np.array([
    [1.8, 5.9, 7.5, 50.0, 57.0],
    [3.8, 5.5, 6.5, 50.0, 57.0],
    [7.4, 5.1, 6.0, 50.0, 58.0],
    [13.2, 4.7, 5.8, 50.0, 58.0],
    [22.0, 4.5, 5.5, 54.0, 63.0],
    [34.0, 4.3, 5.3, 58.0, 68.0],
    [50.0, 4.0, 5.0, 62.0, 77.0],
    [70.0, 3.5, 4.8, 66.0, 86.0],
    [95.0, 3.3, 4.4, 70.0, 89.0],
    [126.0, 3.1, 4.0, 73.0, 91.0],
    [163.0, 2.9, 3.7, 77.0, 94.0],
])
R100_LIMITS = (1.2, 1.5)
LUNG_V20_LIMITS = (10.0, 15.0)


def rtog_limits(ptv_cc: float) -> Dict[str, tuple]:
    """``{"R50": (none, minor), "D2cm": (none, minor)}`` at a PTV volume, interpolated (clamped at the ends)."""
    t = RTOG_CONFORMALITY
    v = float(np.clip(ptv_cc, t[0, 0], t[-1, 0]))
    f = lambda col: float(np.interp(v, t[:, 0], t[:, col]))   # noqa: E731
    return {"R50": (f(1), f(2)), "D2cm": (f(3), f(4)), "R100": R100_LIMITS, "LungV20": LUNG_V20_LIMITS}


def grade(value: float, limits: tuple) -> str:
    """``none`` below the first limit, ``minor`` up to the second, ``major`` beyond (RTOG deviation language)."""
    if value < limits[0]:
        return "none"
    if value <= limits[1]:
        return "minor"
    return "major"


@dataclass
class SBRTIndices:
    prescription_gy: float
    ptv_cc: float
    r100: float
    r50: float
    d2cm_pct: float
    gradient_index: float
    lung_v20_pct: Optional[float]
    limits: Dict[str, tuple] = field(default_factory=dict)
    deviations: Dict[str, str] = field(default_factory=dict)

    @property
    def acceptable(self) -> bool:
        """No major deviation."""
        return all(v != "major" for v in self.deviations.values())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["acceptable"] = self.acceptable
        return d


def sbrt_indices(dose_zyx: np.ndarray, ptv_zyx: np.ndarray, body_zyx: np.ndarray, prescription_gy: float,
                 spacing_mm: Sequence[float], lungs_zyx: Optional[np.ndarray] = None, d2cm_mm: float = 20.0) -> SBRTIndices:
    """The indices of a plan on its grid. ``spacing_mm`` is ``(sx, sy, sz)``; masks are ``(z, y, x)`` like the
    dose; ``lungs_zyx`` should already exclude the GTV."""
    from scipy.ndimage import distance_transform_edt

    dose = np.asarray(dose_zyx, dtype=np.float64)
    ptv = np.asarray(ptv_zyx, bool)
    body = np.asarray(body_zyx, bool) | ptv
    sx, sy, sz = (float(v) for v in spacing_mm)
    voxel_cc = sx * sy * sz / 1000.0
    ptv_cc = float(ptv.sum() * voxel_cc)
    if ptv_cc <= 0:
        raise ValueError("the PTV is empty")
    rx = float(prescription_gy)
    v100 = float(((dose >= rx) & body).sum() * voxel_cc)
    v50 = float(((dose >= 0.5 * rx) & body).sum() * voxel_cc)
    dist = distance_transform_edt(~ptv, sampling=(sz, sy, sx))
    far = body & (dist >= d2cm_mm)
    d2cm = float(dose[far].max() / rx * 100.0) if far.any() else 0.0
    v20 = None
    if lungs_zyx is not None and np.asarray(lungs_zyx, bool).any():
        lungs = np.asarray(lungs_zyx, bool)
        v20 = float((dose[lungs] >= 20.0).mean() * 100.0)
    limits = rtog_limits(ptv_cc)
    out = SBRTIndices(prescription_gy=rx, ptv_cc=ptv_cc, r100=v100 / ptv_cc, r50=v50 / ptv_cc, d2cm_pct=d2cm,
                      gradient_index=(v50 / v100) if v100 > 0 else float("inf"), lung_v20_pct=v20, limits=limits)
    out.deviations = {"R100": grade(out.r100, limits["R100"]), "R50": grade(out.r50, limits["R50"]),
                      "D2cm": grade(out.d2cm_pct, limits["D2cm"])}
    if v20 is not None:
        out.deviations["LungV20"] = grade(v20, limits["LungV20"])
    return out


__all__ = ["RTOG_CONFORMALITY", "rtog_limits", "grade", "SBRTIndices", "sbrt_indices"]
