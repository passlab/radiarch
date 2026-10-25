"""Roadmap R9: 4D planning on a synthetic thorax breathing in three phases — average CT, ITV, phase doses,
deformable accumulation, the routes and the lineage."""

from __future__ import annotations

import uuid

import numpy as np
import pytest
import SimpleITK as sitk

from radiarch.models.four_d import AccumulateRequest, AverageCTRequest, ITVRequest, PhaseDose, PhaseDoseRequest, PhaseStructure
from radiarch.models.registration import DeformableMethod, RegistrationRequest
from radiarch.services.four_d import FourDError, FourDService, read_geometry_volumes
from radiarch.services.geometry import GeometryService
from radiarch.services.geometry_bundle import load_ct_hu, load_geometry_arrays
from radiarch.services.registration import RegistrationService

from test_r9_registration import ORIGIN, S, SHAPE, _moved, _phantom, _save

TUMOUR = (-38.0, -5.0, 6.0)


def _breathing(amplitude_mm: float):
    """The inverse of a breathing motion of the right lung region along z (Gaussian fall-off, 35 mm)."""
    z, y, x = np.meshgrid(*[ORIGIN[2 - a] + np.arange(SHAPE[a]) * S for a in range(3)], indexing="ij")
    field = np.zeros(SHAPE + (3,), np.float64)
    field[..., 2] = -amplitude_mm * np.exp(-(((x + 38) ** 2 + y ** 2 + z ** 2) / (2 * 35.0 ** 2)))
    img = sitk.GetImageFromArray(field, isVector=True)
    img.SetOrigin(ORIGIN); img.SetSpacing((S, S, S))
    return sitk.DisplacementFieldTransform(img)


def _phases(store):
    ct, st = _phantom()
    out = []
    for amp in (0.0, 4.0, 8.0):
        pct, pst = (ct, st) if amp == 0.0 else _moved(ct, st, _breathing(amp))
        out.append((_save(store, pct, pst, "1.2.3.4dct"), pct, pst))
    return out


def _plan_on(geometry_id):
    """Four 6 x 6 cm open fields at the tumour, 100 MU each, as a beam model with metersets."""
    from radiarch.models.beam_model import BeamModelResult, FluenceElementSet, Modality, PerBeamElements
    from radiarch.models.photon_plan import PhotonBeam, PhotonPlan, open_field_segment
    from radiarch.services.beam_model import BeamModelService
    from radiarch.services.beam_persistence import BeamModelPaths

    beams = [PhotonBeam(beam_id=f"B{g}", gantry_deg=float(g), isocenter_mm=TUMOUR, energy_mv=6.0,
                        segments=[open_field_segment((-30.0, 30.0), (-30.0, 30.0), 5.0, 100.0)]) for g in (0, 90, 180, 270)]
    plan = PhotonPlan(name="4d-test", beams=beams)
    svc = BeamModelService()
    bm_id = str(uuid.uuid4())
    per_beam = [PerBeamElements(beam_id=b.beam_id, element_count=b.n_beamlets, active_beamlets=b.n_beamlets) for b in beams]
    res = BeamModelResult(beam_model_id=bm_id, geometry_id=geometry_id, modality=Modality.photon_imrt,
                          fluence_elements=FluenceElementSet(total_count=plan.n_beamlets, per_beam=per_beam),
                          beam_model_ref_uri=str(BeamModelPaths.for_id(svc.store.base_dir, bm_id).plan), machine_model_id="synthetic-120",
                          cache_key=f"test-plan-{bm_id}")
    svc.store.save(beam_model_id=bm_id, cache_key=res.cache_key, plan=plan, result=res)
    return res


@pytest.fixture()
def env(monkeypatch, tmp_path):
    from radiarch.config import get_settings

    for k, v in {"RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
                 "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://", "RADIARCH_PB_DEVICE": "cpu",
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path), "RADIARCH_API_KEY": "", "RADIARCH_DICOMWEB_URL": ""}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_average_ct_and_itv(env):
    svc = FourDService()
    (g0, ct0, st0), (g1, ct1, st1), (g2, ct2, st2) = _phases(svc.geometry_service.store)
    aip = svc.average(AverageCTRequest(reference_geometry_id=g0.geometry_id, phase_geometry_ids=[g0.geometry_id, g1.geometry_id, g2.geometry_id]))
    mean = (ct0.astype(np.int16).astype(float) + ct1.astype(np.int16) + ct2.astype(np.int16)) / 3
    assert np.abs(load_ct_hu(aip).astype(float) - mean).max() <= 0.51
    assert aip.parent_geometry_id == g0.geometry_id and set(aip.structure_index) == set(g0.structure_index)
    density = read_geometry_volumes(aip)[0]
    assert density.shape == SHAPE and np.isfinite(density).all() and density.max() > 1.0          # the spine's density survives

    # the ITV of the drawn contours holds every phase's tumour and is larger than any of them
    itv = svc.itv(ITVRequest(geometry_id=aip.geometry_id, sources=[PhaseStructure(geometry_id=g.geometry_id, structure="Tumour") for g in (g0, g1, g2)]))
    arr = load_geometry_arrays(itv)
    itv_mask = arr.mask_zyx(arr.structure_index["ITV"])
    for st in (st0, st1, st2):
        assert itv_mask[st["Tumour"]].all()
    assert itv_mask.sum() > 1.2 * st0["Tumour"].sum()
    with pytest.raises(FourDError, match="already has"):
        svc.itv(ITVRequest(geometry_id=itv.geometry_id, sources=[PhaseStructure(geometry_id=g0.geometry_id, structure="Tumour")]))

    # a phase in another frame of reference needs a registration
    other = _save(svc.geometry_service.store, ct2, st2, "9.9.9")
    with pytest.raises(FourDError, match="frame of reference"):
        svc.average(AverageCTRequest(reference_geometry_id=g0.geometry_id, phase_geometry_ids=[g0.geometry_id, other.geometry_id]))
    reg = svc.registration_service.register(RegistrationRequest(fixed_geometry_id=g0.geometry_id, moving_geometry_id=other.geometry_id,
                                                                deformable=DeformableMethod.demons, demons_iterations=40))
    via = svc.itv(ITVRequest(geometry_id=g0.geometry_id, name="Tumour_from_other",
                             sources=[PhaseStructure(geometry_id=other.geometry_id, structure="Tumour", registration_id=reg.registration_id)]))
    va = load_geometry_arrays(via)
    warped, ref = va.mask_zyx(va.structure_index["Tumour_from_other"]), st0["Tumour"]
    assert 2 * (warped & ref).sum() / (warped.sum() + ref.sum()) > 0.85                 # pulled back onto the reference tumour


def test_phase_doses_and_accumulation(env):
    from radiarch.models.lineage import VersionRef
    from radiarch.services.dose_persistence import read_dose_volume
    from radiarch.services.lineage import LineageService
    from pathlib import Path

    svc = FourDService()
    phases = _phases(svc.geometry_service.store)
    g0, _, st0 = phases[0]
    bm = _plan_on(g0.geometry_id)
    doses = svc.phase_doses(PhaseDoseRequest(beam_model_id=bm.beam_model_id, geometry_ids=[g.geometry_id for g, _, _ in phases]))
    assert [d.geometry_id for d in doses] == [g.geometry_id for g, _, _ in phases]
    arrays = [read_dose_volume(Path(d.dose_grid_uri)) for d in doses]
    tumour_means = [arr[st["Tumour"]].mean() for arr, (_, _, st) in zip(arrays, phases)]
    assert min(tumour_means) > 0.95 * max(tumour_means)                                  # the 6 cm fields cover the tumour in every phase
    assert svc.phase_doses(PhaseDoseRequest(beam_model_id=bm.beam_model_id, geometry_ids=[g0.geometry_id]))[0].dose_id == doses[0].dose_id

    regs = [None] + [svc.registration_service.register(RegistrationRequest(fixed_geometry_id=g0.geometry_id, moving_geometry_id=g.geometry_id,
                                                                           deformable=DeformableMethod.demons, demons_iterations=40)).registration_id
                     for g, _, _ in phases[1:]]
    acc = svc.accumulate(AccumulateRequest(reference_geometry_id=g0.geometry_id,
                                           phases=[PhaseDose(dose_id=d.dose_id, registration_id=r) for d, r in zip(doses, regs)]))
    total = read_dose_volume(Path(acc.dose_grid_uri))
    assert acc.geometry_id == g0.geometry_id and len(acc.accumulated_from) == 3
    assert abs(sum(p["weight"] for p in acc.accumulated_from) - 1.0) < 1e-9
    # the tumour's accumulated dose is the mean of what it received in each phase
    assert total[st0["Tumour"]].mean() == pytest.approx(np.mean(tumour_means), rel=0.03)
    node = LineageService().node(VersionRef(kind="dose", id=acc.dose_id))
    keys = {p.key for p in node.parents}
    assert {f"dose:{d.dose_id}" for d in doses} <= keys and {f"registration:{r}" for r in regs if r} <= keys
    with pytest.raises(FourDError, match="give a registration|does not map"):
        svc.accumulate(AccumulateRequest(reference_geometry_id=g0.geometry_id,
                                         phases=[PhaseDose(dose_id=doses[1].dose_id, registration_id=regs[2])]))
    with pytest.raises(ValueError, match="every phase or for none"):
        AccumulateRequest(reference_geometry_id=g0.geometry_id, phases=[PhaseDose(dose_id="a", weight=1.0), PhaseDose(dose_id="b")])


def test_four_d_routes(env, monkeypatch):
    from fastapi.testclient import TestClient
    import radiarch.app as radiarch_app
    from radiarch.api.routes import four_d as routes
    from radiarch.app import create_app

    routes._service.cache_clear()
    store = GeometryService().store
    (g0, _, _), (g1, _, _), _ = _phases(store)
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with TestClient(create_app()) as client:
        r = client.post("/api/v1/four-d/average", json={"reference_geometry_id": g0.geometry_id, "phase_geometry_ids": [g0.geometry_id, g1.geometry_id]})
        assert r.status_code == 200, r.text
        aip = r.json()["geometry_id"]
        r = client.post("/api/v1/four-d/itv", json={"geometry_id": aip, "sources": [{"geometry_id": g0.geometry_id, "structure": "Tumour"},
                                                                                     {"geometry_id": g1.geometry_id, "structure": "Tumour"}]})
        assert r.status_code == 200 and "ITV" in r.json()["structure_index"]
        assert client.post("/api/v1/four-d/itv", json={"geometry_id": aip, "sources": [{"geometry_id": g0.geometry_id, "structure": "Nope"}]}).status_code == 422
        assert client.post("/api/v1/four-d/itv", json={"geometry_id": "nope", "sources": [{"geometry_id": g0.geometry_id, "structure": "Tumour"}]}).status_code == 404
        assert client.post("/api/v1/four-d/average", json={"reference_geometry_id": g0.geometry_id, "phase_geometry_ids": [g0.geometry_id]}).status_code == 422
    routes._service.cache_clear()


def test_phases_as_scenarios_give_the_worst_phase(env):
    """4D robustness: the mapped phase doses kept as scenarios of the accumulated dose; an evaluation grades the
    worst phase against a goal the nominal passes."""
    from pathlib import Path
    from radiarch.models.evaluation import ClinicalGoal, EvaluationRequest, GoalSetSpec
    from radiarch.services.dose_persistence import read_dose_volume
    from radiarch.services.evaluation import EvaluationService

    svc = FourDService()
    phases = _phases(svc.geometry_service.store)
    g0, _, st0 = phases[0]
    bm = _plan_on(g0.geometry_id)
    doses = svc.phase_doses(PhaseDoseRequest(beam_model_id=bm.beam_model_id, geometry_ids=[g.geometry_id for g, _, _ in phases]))
    regs = [None] + [svc.registration_service.register(RegistrationRequest(fixed_geometry_id=g0.geometry_id, moving_geometry_id=g.geometry_id,
                                                                           deformable=DeformableMethod.demons, demons_iterations=40)).registration_id
                     for g, _, _ in phases[1:]]
    acc = svc.accumulate(AccumulateRequest(reference_geometry_id=g0.geometry_id, phases_as_scenarios=True, names=["0 %", "50 %", "100 %"],
                                           phases=[PhaseDose(dose_id=d.dose_id, registration_id=r) for d, r in zip(doses, regs)]))
    assert [e.scenario_name for e in acc.scenario_doses] == ["0 %", "50 %", "100 %"]
    per_phase = [read_dose_volume(Path(e.dose_grid_uri))[st0["Tumour"]].mean() for e in acc.scenario_doses]
    nominal = read_dose_volume(Path(acc.dose_grid_uri))[st0["Tumour"]].mean()
    assert min(per_phase) <= nominal <= max(per_phase)
    limit = float(nominal) * 0.999
    ev = EvaluationService(dose_service=svc.dose_service).run(EvaluationRequest(
        dose_id=acc.dose_id, geometry_id=g0.geometry_id, prescription_gy=float(nominal), include_scenarios=True,
        goals=GoalSetSpec(goals=[ClinicalGoal(structure="Tumour", metric="Dmean[Gy]", op=">=", value=limit, priority=1)])))
    (g,) = ev.goals.results
    assert g.passed and g.worst_case == pytest.approx(min(per_phase), rel=1e-3)
    assert set(g.per_scenario) == {"0 %", "50 %", "100 %"} and g.passed_all_scenarios == bool(min(per_phase) >= limit)
