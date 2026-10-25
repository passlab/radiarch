"""Roadmap R9: adaptive replanning — a plan on a later, shifted and recalibrated image of the synthetic thorax; a new
plan written with its predecessor and the course's MULTI_PLAN dose."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest
import SimpleITK as sitk

from radiarch.models.evaluation import ClinicalGoal, GoalSetSpec
from radiarch.models.four_d import AccumulateRequest, PhaseDose, PhaseDoseRequest
from radiarch.models.lineage import VersionRef
from radiarch.models.registration import DeformableMethod
from radiarch.models.replan import DensitySource, ReplanAssessRequest
from radiarch.services.dose_persistence import read_dose_volume
from radiarch.services.geometry_bundle import load_geometry_arrays
from radiarch.services.replan import ReplanService

from test_r9_four_d import _plan_on, env  # noqa: F401
from test_r9_registration import ORIGIN, S, SHAPE, _moved, _phantom, _save

SHIFT = (6.0, -4.0, 9.0)


def _day_image(store, ct, st):
    """The patient on a later day: shifted by SHIFT, imaged on a cone-beam CT (another frame of reference and calibration)."""
    t = sitk.Euler3DTransform((0.0, 0.0, 0.0), 0.0, 0.0, 0.0, SHIFT)
    mct, mst = _moved(ct, st, t.GetInverse())
    cbct = 0.85 * mct + 60.0
    # a cone-beam field of view: a cylinder of 70 mm radius about the axis, padded with -1000 outside, as a cone-beam
    # CT resampled onto a planning grid is (where the planning CT has tissue)
    z, y, x = np.meshgrid(*[ORIGIN[2 - a] + np.arange(SHAPE[a]) * S for a in range(3)], indexing="ij")
    cbct[x ** 2 + y ** 2 > 70.0 ** 2] = -1000.0
    return _save(store, cbct, {"Body": mst["Body"]}, "1.2.3.cbct"), mst


def test_assess_moves_the_isocenter_and_recomputes_on_the_day(env):  # noqa: F811
    from radiarch.services.lineage import LineageService

    svc = ReplanService()
    ct, st = _phantom()
    planning = _save(svc.geometry_service.store, ct, st, "1.2.3.ct")
    day, day_st = _day_image(svc.geometry_service.store, ct, st)
    bm = _plan_on(planning.geometry_id)
    planned = svc.four_d.phase_doses(PhaseDoseRequest(beam_model_id=bm.beam_model_id, geometry_ids=[planning.geometry_id]))[0]
    goals = GoalSetSpec(goals=[ClinicalGoal(structure="Tumour", metric="Dmean[Gy]", op=">=", value=1.0, priority=1),
                               ClinicalGoal(structure="Spine", metric="D0.03cc[Gy]", op="<=", value=100.0, priority=2)])
    a = svc.assess(ReplanAssessRequest(planning_geometry_id=planning.geometry_id, day_geometry_id=day.geometry_id, beam_model_id=bm.beam_model_id,
                                       planned_dose_id=planned.dose_id, density=DensitySource.deformed_planning_ct, deformable=DeformableMethod.bspline,
                                       structures=["Tumour", "Spine", "Lung_R"], prescription_gy=1.0, target_structure="Tumour", goals=goals))
    # the couch shift follows the patient
    assert np.allclose(a.isocenter_shift_mm, SHIFT, atol=1.0)
    assert a.registration_quality.jacobian.fraction_nonpositive == 0.0                      # the padding does not tear the field
    assert max(abs(v) for v in a.residual_rotation_deg) < 1.0
    # the day's geometry: the propagated tumour lies on the moved tumour; its density is the planning CT's, not the cone-beam's
    g = svc.geometry_service.store.get_by_id(a.day_geometry_id)
    arr = load_geometry_arrays(g)
    tum = arr.mask_zyx(arr.structure_index["Tumour"])
    # 0.80, not the 0.85 of an unpadded image: the metric's margin reaches across the field-of-view edge (ADR 0016)
    assert 2 * (tum & day_st["Tumour"]).sum() / (tum.sum() + day_st["Tumour"].sum()) > 0.80
    assert g.derived_operations[-1]["op"] == "density_from_registration"
    assert abs(float(np.median(arr.ct_hu[day_st["Tumour"]])) - 40.0) < 30.0             # planning HU 40, the cone-beam's 94
    # the plan on the day gives the tumour what it got on the planning CT
    planned_arr = read_dose_volume(Path(planned.dose_grid_uri))
    day_arr = read_dose_volume(Path(svc.dose_service.dose_store.get_by_id(a.day_dose_id).dose_grid_uri))
    assert day_arr[tum].mean() == pytest.approx(planned_arr[st["Tumour"]].mean(), rel=0.03)
    # the goals side by side, and the mapped planned dose
    by = {c.structure: c for c in a.goals}
    assert by["Tumour"].planned == pytest.approx(by["Tumour"].day, rel=0.03) and by["Tumour"].day_passed
    assert a.mapped_planned_dose_id is not None
    # cached; lineage of the day's plan reaches the planned one and the registration
    again = svc.assess(a.request)
    assert again.assessment_id == a.assessment_id
    node = LineageService().node(VersionRef(kind="beam_model", id=a.day_beam_model_id))
    assert f"beam_model:{bm.beam_model_id}" in {p.key for p in node.parents}
    gnode = LineageService().node(VersionRef(kind="geometry", id=a.day_geometry_id))
    assert {f"geometry:{planning.geometry_id}", f"registration:{a.registration_id}"} <= {p.key for p in gnode.parents}


def test_course_accumulation_with_absolute_weights(env):  # noqa: F811
    svc = ReplanService()
    ct, st = _phantom()
    planning = _save(svc.geometry_service.store, ct, st, "1.2.3.ct")
    bm = _plan_on(planning.geometry_id)
    d = svc.four_d.phase_doses(PhaseDoseRequest(beam_model_id=bm.beam_model_id, geometry_ids=[planning.geometry_id]))[0]
    # 10 of 30 fractions with this plan, 20 of 30 with a plan of twice the dose: 1/3 + 2 * 2/3 = 5/3 of the first
    double = svc.dose_service.dose_store.get_by_id(d.dose_id)
    arr = read_dose_volume(Path(double.dose_grid_uri))
    from radiarch.services.dose import _summary_stats
    from radiarch.services.dose_persistence import DOSE_FILENAME
    import uuid
    did = str(uuid.uuid4())
    r2 = double.model_copy(update={"dose_id": did, "cache_key": f"double-{did}", "dose_grid_uri": str(svc.dose_service.dose_store.base_dir / did / DOSE_FILENAME),
                                   "statistics": _summary_stats(2 * arr)})
    svc.dose_service.dose_store.save(dose_id=did, cache_key=r2.cache_key, nominal_dose=2 * arr, spacing_mm=(3.0, 3.0, 3.0), scenario_doses=None, result=r2)
    course = svc.four_d.accumulate(AccumulateRequest(reference_geometry_id=planning.geometry_id, absolute=True,
                                                     phases=[PhaseDose(dose_id=d.dose_id, weight=10 / 30), PhaseDose(dose_id=did, weight=20 / 30)]))
    total = read_dose_volume(Path(course.dose_grid_uri))
    assert np.allclose(total, arr * 5 / 3, rtol=1e-4, atol=1e-6)
    with pytest.raises(ValueError, match="absolute weights"):
        AccumulateRequest(reference_geometry_id="g", absolute=True, phases=[PhaseDose(dose_id="a")])


def test_export_request_checks_the_summation():
    from radiarch.models.rt_export import RTExportRequest

    with pytest.raises(ValueError, match="MULTI_PLAN"):
        RTExportRequest(beam_model_id="b", dose_summation="MULTI_PLAN", objects=["rtstruct", "rtplan", "rtdose"])
    with pytest.raises(ValueError, match="MULTI_PLAN"):
        RTExportRequest(beam_model_id="b", summed_plan_uids=["1.2"], objects=["rtstruct", "rtplan", "rtdose"])
    ok = RTExportRequest(beam_model_id="b", dose_summation="MULTI_PLAN", summed_plan_uids=["1.2"], predecessor_plan_uid="1.2",
                         objects=["rtstruct", "rtplan", "rtdose"])
    assert ok.predecessor_plan_uid == "1.2"


def test_writers_reference_the_predecessor_and_the_summed_plans(tmp_path):
    from radiarch.dicom.uids import SOP
    from radiarch.dicom.writers import CaseContext
    from radiarch.dicom.writers.rtdose import build_rtdose
    from radiarch.dicom.writers.rtplan import PlanWriteOptions, write_rtplan
    from radiarch.models.photon_plan import PhotonBeam, PhotonPlan, open_field_segment

    ctx = CaseContext(patient_id="R9", patient_name="R9^REPLAN", study_instance_uid="1.2.826.0.1.3680043.8.498.9", frame_of_reference_uid="1.2.826.0.1.3680043.8.498.10")
    plan = PhotonPlan(name="p", beams=[PhotonBeam(beam_id="B1", gantry_deg=0.0, segments=[open_field_segment((-20, 20), (-20, 20), 5.0, 100.0)])])
    rp = write_rtplan(ctx, plan, tmp_path / "RP.dcm", rtstruct_uid="1.2.826.0.1.3680043.8.498.11",
                      options=PlanWriteOptions(label="RESEARCH", referenced_plans=[(SOP.RTPLAN, "1.2.826.0.1.3680043.8.498.12", "PREDECESSOR")]))
    ds = pydicom.dcmread(rp.path)
    assert ds.ReferencedRTPlanSequence[0].RTPlanRelationship == "PREDECESSOR"
    assert ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID == "1.2.826.0.1.3680043.8.498.12"
    rd = build_rtdose(ctx, np.ones((2, 3, 4), np.float32), (0, 0, 0), (2, 2, 2), plan_sop_class=SOP.RTPLAN, plan_sop_instance=rp.sop_instance_uid,
                      summation="MULTI_PLAN", other_plans=[(SOP.RTPLAN, "1.2.826.0.1.3680043.8.498.12")])
    assert rd.DoseSummationType == "MULTI_PLAN"
    assert [r.ReferencedSOPInstanceUID for r in rd.ReferencedRTPlanSequence] == [rp.sop_instance_uid, "1.2.826.0.1.3680043.8.498.12"]
    with pytest.raises(ValueError, match="MULTI_PLAN"):
        build_rtdose(ctx, np.ones((2, 3, 4), np.float32), (0, 0, 0), (2, 2, 2), plan_sop_class=SOP.RTPLAN, plan_sop_instance=rp.sop_instance_uid,
                     other_plans=[(SOP.RTPLAN, "1.2")])
