"""Photon dose workflow on the collapsed-cone engine.

Legacy ``/plans`` workflow: builds the geometry of the plan's study, a plan
of equally spaced open fields on radiarch's photon plan model and computes
its dose with :class:`CCCEngine` (the WiscPlan binary run as a subprocess).
Writes an RTDOSE and a target DVH.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import numpy as np
from loguru import logger

from ._helpers import (
    build_geometry, compute_dvh, ct_provenance, dose_image, dose_summary, export_rtdose, read_structure,
    setup_sim_dir, target_of,
)
from ...models.common import RESEARCH_USE_ONLY
from ...models.geometry import HUDensityModel
from ...models.plan import PlanDetail


def _target_centroid_mm(mask_zyx: np.ndarray, origin, spacing) -> tuple:
    """Isocenter for the open fields: the target's centre of mass, else the grid centre."""
    origin = np.asarray(origin, dtype=float)
    spacing = np.asarray(spacing, dtype=float)
    idx = np.argwhere(mask_zyx)
    if idx.size:
        com_zyx = idx.mean(axis=0)
        return tuple(float(v) for v in origin + com_zyx[::-1] * spacing)
    size = np.asarray(mask_zyx.shape[::-1], dtype=float)
    return tuple(float(v) for v in origin + (size - 1) / 2.0 * spacing)


def run(plan: PlanDetail) -> Dict[str, Any]:
    import SimpleITK as sitk
    from ...services.dose_engines.ccc import CCCEngine
    from ...services.photon_beamlets import build_photon_plan

    logger.info("Starting photon CCC workflow for plan %s", plan.id)
    sim_dir = setup_sim_dir(plan.id)

    # 1. Geometry: density on the CT grid (Schneider), the target mask
    geometry = build_geometry(plan, HUDensityModel.schneider)
    density = sitk.GetArrayFromImage(sitk.ReadImage(geometry.density_grid_uri)).astype(np.float32)
    spacing = tuple(float(v) for v in geometry.grid_spec.spacing_mm)
    origin = tuple(float(v) for v in (geometry.grid_spec.origin_mm or (0.0, 0.0, 0.0)))
    target_name, target_label = target_of(geometry)
    target = read_structure(geometry, target_label)

    # 2. Plan: equally spaced gantry angles, one open field each, isocenter on the target
    isocenter = _target_centroid_mm(target, origin, spacing)
    beam_count = plan.beam_count
    jaw = (float(plan.jaw_opening_mm[0]), float(plan.jaw_opening_mm[1]))
    photon_plan = build_photon_plan(
        beams=[(i * (360.0 / beam_count), 0.0) for i in range(beam_count)],
        jaw_x_mm=jaw, jaw_y_mm=jaw, leaf_width_mm=plan.mlc_leaf_width_mm, mu_per_beam=plan.mu_per_beam,
        isocenter_mm=isocenter, name=f"photon-ccc-{plan.id}",
    )

    # 3. Dose
    engine = CCCEngine()
    dose_zyx = engine.compute_plan_dose(density, spacing, origin, photon_plan)

    # 4. Export
    rtdose_path = os.path.join(sim_dir, "RTDOSE.dcm")
    export_rtdose(dose_image(dose_zyx, geometry), ct_provenance(geometry), rtdose_path)

    return {
        "engine": "ccc",
        "engineVersion": engine.version,
        "doseUnits": "Gy",
        "intended_use": RESEARCH_USE_ONLY,
        "beamCount": beam_count,
        "beamlets": photon_plan.n_beamlets,
        "isocenterMm": list(isocenter),
        "geometryId": geometry.geometry_id,
        **dose_summary(dose_zyx),
        "rtdosePath": rtdose_path,
        "simDir": sim_dir,
        "dvh": compute_dvh(dose_zyx, target, target_name),
    }
