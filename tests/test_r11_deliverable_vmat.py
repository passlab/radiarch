"""R11.5: a navigation state made deliverable as VMAT arcs (D7), on test_r8_vmat's stub patient with the pencil-beam
engine: the Pareto set of the arc's sector beams, the balance plan, arcs whose metersets mimic its dose; then (R11.11) a
second set over the arc's interval metersets, navigated and made the plan."""

from __future__ import annotations

import numpy as np

from radiarch.models.mco import DeliverableRequest
from radiarch.models.vmat import ArcSpec, sector_beams

from test_r8_vmat import env, needs_kernel  # noqa: F401  (a water cylinder with a PTV and an OAR; the pb kernel)


@needs_kernel
def test_arcs_mimic_the_navigated_dose(env):  # noqa: F811
    from radiarch.models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from radiarch.models.dose import EngineSpec
    from radiarch.models.geometry import GeometryBuildRequest, PatientRef
    from radiarch.models.mco import MCORunRequest
    from radiarch.models.optimization import HardConstraint, ObjectiveSpec, SolverConfig
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.geometry import GeometryService
    from radiarch.services.mco import MCOService
    from radiarch.services.mco_deliverable import DeliverableService

    arc = ArcSpec(arc_id="A1", start_deg=300, stop_deg=60, direction="CW", sectors=4, control_point_spacing_deg=4.0)
    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id="synthetic-120",
        beam_set=BeamSetSpec(isocenter_mm=(10.0, 0.0, 0.0), beams=[BeamSpec(beam_id=b, gantry_deg=g, collimator_deg=col) for b, g, _, col in sector_beams([arc])]),
        delivery_params=DeliveryParams(jaw_opening_mm=(40.0, 40.0), beamlet_size_mm=(5.0, 5.0))))
    mco = MCOService().run(MCORunRequest(
        geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=EngineSpec(name="pb"),
        tradeoffs=[ObjectiveSpec(type="UniformRMS", structure_name="PTV", dose_gy=2.0, weight=1.0),
                   ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=0.0, weight=1.0)],
        hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=1.6)],
        solver=SolverConfig(method="L-BFGS-B", max_iterations=60), plan_budget=4))
    out = DeliverableService().run(mco.mco_id, DeliverableRequest(arcs=[arc], max_iterations=60, project=True))
    assert out.technique == "vmat" and out.vmat_id and out.dose_id and out.projected
    rows = {r.name: r for r in out.deviation}
    assert set(rows) == {"UniformRMS(PTV)", "MeanDose(OAR)"}
    # the arcs reproduce the navigated dose roughly (sector fluence swept by the leaves): within half a gray here
    assert all(abs(r.worse_by) < 0.5 for r in rows.values()), rows

    # R11.11: a second set over the arc's interval metersets; a state on it made the plan keeps the arc's apertures
    from radiarch.models.mco import ApertureSetRequest, NavigateRequest
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.mco_apertures import ApertureSetService, deliverable_elements
    from radiarch.services.navigation import NavigationService

    msvc = MCOService()
    second = ApertureSetService(mco_service=msvc).run(out.deliverable_id, ApertureSetRequest(plan_budget=4))
    assert second.elements == "arc intervals" and second.source_deliverable_id == out.deliverable_id
    el = deliverable_elements(DeliverableService(mco_service=msvc).store.get_by_id(out.deliverable_id))
    W = np.load(second.weights_uri)
    assert W.shape[1] == el.z0.size and np.all(W >= el.lower - 1e-6)                    # every interval at or above its floor
    oar = [p.values_gy[1] for p in second.plans]
    st = NavigationService(msvc.store).navigate(second.mco_id, NavigateRequest(move={"MeanDose(OAR)": 0.5 * (min(oar) + max(oar))}))
    made = DeliverableService(mco_service=msvc).run(second.mco_id, DeliverableRequest(state_id=st.state_id, arcs=[arc]))
    assert made.technique == "vmat" and made.vmat_id == out.vmat_id and made.mco_id == second.mco_id
    store = BeamModelService().store
    old, new = store.load_plan(out.beam_model_id).beams[0].arc, store.load_plan(made.beam_model_id).beams[0].arc
    assert [[(r.x_left_mm, r.x_right_mm) for r in cp.mlc_rows] for cp in new.control_points] == \
        [[(r.x_left_mm, r.x_right_mm) for r in cp.mlc_rows] for cp in old.control_points]
    # the plan's dose is the full kernel's; navigation showed the pencil beam's interval doses: close, not equal
    assert all(abs(r.worse_by) < 0.5 for r in made.deviation), made.deviation
