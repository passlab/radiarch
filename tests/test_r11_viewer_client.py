"""R11.7: the viewer's API client (viewer/radiarch-client) on a Pareto set, against a running radiarch.

A Pareto set is computed on the stub patient (four static fields, the analytic engine), its balance plan made
deliverable and exported, as an MCO protocol's plan would be. radiarch's app is served with the API key required, and
the client's Node tests (test/mco.test.js) then:
- find the Pareto set behind the exported dose;
- move a slider, lock a trade-off, navigate automatically;
- make the new state deliverable through the job, then from the cache, and export it.
The deliverable plan the client got is checked against radiarch's own store.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from test_r6_rt_export_service import env  # noqa: F401
from test_r13_viewer_client import CLIENT, KEY, NODE, api  # noqa: F401


def mco_export():
    """A Pareto set on the stub patient, its balance plan made deliverable, and that plan exported (2 Gy in 2)."""
    from radiarch.models.beam_model import BeamModelBuildRequest, BeamSetSpec, BeamSpec, DeliveryParams, Modality
    from radiarch.models.dose import EngineSpec
    from radiarch.models.geometry import GeometryBuildRequest, PatientRef
    from radiarch.models.mco import DeliverableRequest, MCORunRequest
    from radiarch.models.optimization import HardConstraint, ObjectiveSpec, SolverConfig
    from radiarch.models.rt_export import PrescriptionSpec, RTExportRequest
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.geometry import GeometryService
    from radiarch.services.mco import MCOService
    from radiarch.services.mco_deliverable import DeliverableService
    from radiarch.services.rt_export import RTExportService

    geo = GeometryService().build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="1.2.3"), hu_to_density_model="LINEAR"))
    bm = BeamModelService().build(BeamModelBuildRequest(
        geometry_id=geo.geometry_id, modality=Modality.photon_imrt, machine_model_id="test-120",
        beam_set=BeamSetSpec(beams=[BeamSpec(beam_id=f"G{g}", gantry_deg=float(g)) for g in (0, 90, 180, 270)]),
        delivery_params=DeliveryParams(jaw_opening_mm=(60.0, 60.0), beamlet_size_mm=(10.0, 10.0))))
    mco = MCOService()
    res = mco.run(MCORunRequest(
        geometry_id=geo.geometry_id, beam_model_id=bm.beam_model_id, dose_engine=EngineSpec(name="analytic"),
        tradeoffs=[ObjectiveSpec(type="UniformRMS", structure_name="PTV", dose_gy=2.0, weight=1.0),
                   ObjectiveSpec(type="MeanDose", structure_name="OAR", dose_gy=0.0, weight=1.0)],
        hard_constraints=[HardConstraint(structure_name="PTV", metric="Dmin", op=">=", value_gy=1.0)],
        solver=SolverConfig(method="L-BFGS-B", max_iterations=100), plan_budget=6))
    plan = DeliverableService(mco_service=mco).run(res.mco_id, DeliverableRequest(levels=5, max_iterations=40))
    svc = RTExportService()
    exp = svc.export(RTExportRequest(beam_model_id=plan.beam_model_id, dose_id=plan.dose_id, label="MCO",
                                     prescription=PrescriptionSpec(dose_gy=2.0, fractions=2)))
    return svc, exp, res, plan


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_viewer_client_on_a_pareto_set(api, tmp_path):  # noqa: F811
    from radiarch.services.mco_deliverable import DeliverableService

    _svc, exp, res, plan = mco_export()
    case = {"mco_id": res.mco_id, "deliverable_id": plan.deliverable_id, "dose_id": plan.dose_id,
            "plan_sop_instance_uid": exp.plan_sop_instance_uid}
    (tmp_path / "case.json").write_text(json.dumps(case))
    out = tmp_path / "out.json"
    proc = subprocess.run([NODE, "--test", "--test-reporter=tap", str(CLIENT / "test" / "mco.test.js")], cwd=CLIENT,
                          capture_output=True, text=True, timeout=600,
                          env={**os.environ, "RADIARCH_TEST_API": api, "RADIARCH_TEST_API_KEY": KEY,
                               "RADIARCH_TEST_MCO_CASE": str(tmp_path / "case.json"), "RADIARCH_TEST_OUT": str(out)})
    report = proc.stdout + proc.stderr
    assert proc.returncode == 0, report
    assert "# skipped 0" in report and "# fail 0" in report, report

    got = json.loads(out.read_text())
    mine = DeliverableService().store.get_by_id(got["deliverable"]["deliverable_id"])
    assert mine is not None and mine.mco_id == res.mco_id and mine.dose_id == got["deliverable"]["dose_id"]
    assert got["export_id"]
