"""Photon dose workflow on the collapsed-cone engine.

Legacy ``/plans`` workflow: loads the CT from the configured data root,
builds a plan of equally spaced open fields on radiarch's own plan model
and computes its dose with :class:`CCCEngine` (the WiscPlan binary run as a
subprocess). Writes an RTDOSE and a target DVH. The service-based path
(geometry → beam model → dose) is the one new work targets; this workflow
stays until the legacy workflows are retired (roadmap R15).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Dict

import numpy as np
from loguru import logger

from ._helpers import (
    compute_dvh,
    export_rtdose,
    find_target_roi,
    load_ct_and_patient,
    setup_sim_dir,
)
from ...models.common import RESEARCH_USE_ONLY
from ...models.geometry import HUDensityModel
from ...models.plan import PlanDetail


def _target_centroid_mm(ct, target_roi) -> tuple:
    """Isocenter for the open fields: the target's centre of mass, else the CT centre."""
    origin = np.asarray(ct.origin, dtype=float)
    spacing = np.asarray(ct.spacing, dtype=float)
    if target_roi is not None:
        try:
            mask = target_roi.getBinaryMask(ct.origin, ct.gridSize, ct.spacing).imageArray.astype(bool)
            idx = np.argwhere(mask)
            if idx.size:
                return tuple(float(v) for v in origin + idx.mean(axis=0) * spacing)
        except Exception as exc:  # pragma: no cover — fall back to the CT centre
            logger.warning("Could not rasterize target for the isocenter: {}", exc)
    size = np.asarray(ct.gridSize, dtype=float)
    return tuple(float(v) for v in origin + (size - 1) / 2.0 * spacing)


def run(plan: PlanDetail) -> Dict[str, Any]:
    from ...services.dose_engines.ccc import CCCEngine
    from ...services.hu_density import get_model
    from ...services.photon_beamlets import build_photon_plan

    logger.info("Starting photon CCC workflow for plan %s", plan.id)
    sim_dir = setup_sim_dir(plan.id)

    # 1. CT as a (z, y, x) density grid
    ct, patient, _ = load_ct_and_patient()
    hu_zyx = np.ascontiguousarray(np.transpose(np.asarray(ct.imageArray), (2, 1, 0))).astype(np.int16)
    density = get_model(HUDensityModel.schneider).convert(hu_zyx).astype(np.float32)
    spacing = tuple(float(v) for v in ct.spacing)
    origin = tuple(float(v) for v in ct.origin)

    # 2. Plan: equally spaced gantry angles, one open field each, isocenter on the target
    target_roi = find_target_roi(patient)
    isocenter = _target_centroid_mm(ct, target_roi)
    beam_count = plan.beam_count
    jaw = (float(plan.jaw_opening_mm[0]), float(plan.jaw_opening_mm[1]))
    photon_plan = build_photon_plan(
        beams=[(i * (360.0 / beam_count), 0.0) for i in range(beam_count)],
        jaw_x_mm=jaw,
        jaw_y_mm=jaw,
        leaf_width_mm=plan.mlc_leaf_width_mm,
        mu_per_beam=plan.mu_per_beam,
        isocenter_mm=isocenter,
        name=f"photon-ccc-{plan.id}",
    )

    # 3. Dose
    engine = CCCEngine()
    dose_zyx = engine.compute_plan_dose(density, spacing, origin, photon_plan)

    # 4. Export: the RTDOSE writer takes (z, y, x); the legacy DVH helper takes OpenTPS (x, y, z)
    rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
    export_rtdose(SimpleNamespace(imageArray=dose_zyx, spacing=np.asarray(spacing), origin=np.asarray(origin)),
                  ct, rtdose_path)
    dose_xyz = SimpleNamespace(imageArray=np.ascontiguousarray(np.transpose(dose_zyx, (2, 1, 0))))

    return {
        "engine": "ccc",
        "engineVersion": engine.version,
        "intended_use": RESEARCH_USE_ONLY,
        "beamCount": beam_count,
        "beamlets": photon_plan.n_beamlets,
        "isocenterMm": list(isocenter),
        "maxDose": float(dose_zyx.max()),
        "meanDose": float(dose_zyx.mean()),
        "rtdosePath": rtdose_path,
        "simDir": sim_dir,
        "dvh": compute_dvh(dose_xyz, target_roi, ct) if target_roi else {},
    }
