"""R7: the pieces of the validation report that run without engines or data — the CCC
scatter parameters, the Monte Carlo reference bookkeeping, the report generator, the
goal arithmetic of the planning cases."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from radiarch.validation import cases_r7, mc_reference, report
from radiarch.validation.run import KINDS


def test_ccc_driver_scatter_parameters(monkeypatch):
    from radiarch.services.dose_engines.ccc import CCCEngine
    from radiarch.services.dose_engines.ccc_driver import CCCDriver

    d = CCCDriver()
    assert d.scatter_key == "shipped" and "CCC_DOSE_CUTOFF" not in d.environment() and "CCC_RSAFE_CM" not in d.environment()
    monkeypatch.setenv("CCC_DOSE_CUTOFF", "0.1")           # a stray value in the parent environment never leaks into a shipped run
    assert "CCC_DOSE_CUTOFF" not in d.environment()
    full = CCCDriver(dose_cutoff=1e-4, rsafe_cm=10.0)
    assert full.scatter_key == "cutoff0.0001-rsafe10" and full.environment()["CCC_DOSE_CUTOFF"] == "0.0001" and full.environment()["CCC_RSAFE_CM"] == "10"
    eng = CCCEngine()
    assert eng.driver({"scatter": "full"}).scatter_key == "cutoff0.0001-rsafe10"
    assert eng.driver({"scatter": "shipped"}).scatter_key == "shipped"
    assert eng.driver({"dose_cutoff": 0.001}).scatter_key == "cutoff0.001-rsafe2"
    with pytest.raises(Exception, match="scatter"):
        eng.driver({"scatter": "lots"})
    # the calibration is keyed by the scatter setting: a full-scatter output factor never applies to a shipped run
    assert eng.calibration({"scatter": "full"}).key != eng.calibration().key
    assert eng.calibration({"scatter": "full"}).key.endswith("cutoff0.0001-rsafe10")


def test_ccc_source_carries_the_runtime_parameters():
    src = Path(__file__).resolve().parents[1] / "engines" / "ccc" / "CCC_DoseEngine"
    defs = (src / "defs.h").read_text()
    conv = (src / "convolution.cpp").read_text()
    assert "extern float ccc_dose_cutoff_threshold" in defs and "#define RSAFE ccc_rsafe_cm" in defs
    assert 'getenv("CCC_DOSE_CUTOFF")' in conv and 'getenv("CCC_RSAFE_CM")' in conv
    assert "ccc_dose_cutoff_threshold = 0.005f" in conv and "ccc_rsafe_cm = 2.0f" in conv


def test_mohan_spectrum_reads_as_a_normalised_histogram():
    edges, weights = mc_reference.read_egsnrc_spectrum(mc_reference.SPECTRUM)
    assert edges[0] == 0.0 and len(weights) == len(edges) - 1 == 24 and abs(sum(weights) - 1.0) < 1e-9
    assert 5.5 < edges[-1] <= 6.5 and max(weights) == weights[np.argmax(weights)]
    mean = float(np.sum(((edges[1:] + edges[:-1]) / 2) * np.asarray(weights)))
    assert 1.5 < mean < 2.2            # a 6 MV spectrum averages below 2 MeV


def test_mc_array_maps_onto_radiarch_axes():
    mc = np.zeros((4, 3, 2), np.float32)          # (z_mc, y_mc, x_mc); beam along -z, surface at the top (last z index)
    mc[3, 1, 0] = 1.0                            # surface voxel, y_mc = 1, x_mc = 0
    r = mc_reference.to_radiarch(mc)
    assert r.shape == (3, 4, 2) and r[1, 0, 0] == 1.0     # radiarch (z=1, y=0 surface, x=0)
    assert mc_reference.SLABS["lung_slab"] == [(30.0, 110.0, 0.26)] and mc_reference.FIELDS["water_4x4"] == 40.0


def test_report_renders_every_engine_from_a_run(tmp_path):
    run_dir = tmp_path / "20261021-120000-abc1234"
    run_dir.mkdir()
    results = {"intended_use": "RESEARCH USE ONLY", "radiarch_commit": "abc1234", "timestamp": "20261021-120000", "fast": True, "host": "h", "python": "3.14",
               "results": [
                   {"name": "photon_pdd_10x10", "kind": "photon_pdd", "status": "pass", "seconds": 1.0, "notes": [], "error": None, "metrics": {},
                    "checks": [{"name": "PDD10 (%)", "value": 67.0, "target": "66.1 ± 1.5", "passed": True, "note": "Beyer 2013"}]},
                   {"name": "proton_range_water", "kind": "proton_range", "status": "fail", "seconds": 2.0, "notes": ["n"], "error": None, "metrics": {},
                    "checks": [{"name": "R80", "value": 1.0, "target": "2", "passed": False, "note": ""}]},
                   {"name": "gamma_crosscheck_synthetic", "kind": "gamma_crosscheck", "status": "pass", "seconds": 1.0, "notes": [], "error": None, "metrics": {}, "checks": []},
               ]}
    (run_dir / "results.json").write_text(json.dumps(results))
    out = tmp_path / "reports"
    paths = report.write_reports(run_dir, out)
    names = {p.name for p in paths}
    assert len(paths) == 3 and (out / "LATEST.md").is_file() and any("-ccc-" in n for n in names) and any("-mcsquare-" in n for n in names)
    ccc = next(p for p in paths if "-ccc-" in p.name).read_text()
    assert "RESEARCH USE ONLY" in ccc and "every graded check passed" in ccc and "PDD10 (%)" in ccc and "| Medical physicist" in ccc
    assert "binary_sha256" in ccc and "scatter_settings" in ccc
    mcs = next(p for p in paths if "-mcsquare-" in p.name).read_text()
    assert "graded checks failed" in mcs and "**FAIL**" in mcs
    assert report.latest_run(tmp_path) == run_dir


def test_r7_kinds_are_registered():
    for kind in ("photon_vs_mc", "dij_consistency", "proton_bragg_peak", "tg119_planning", "lung_e2e"):
        assert kind in KINDS


def test_goal_arithmetic_and_sphere_polygons():
    doses = np.linspace(0.0, 100.0, 1001)
    assert cases_r7._goal_value(doses, "Dmax") == 100.0 and abs(cases_r7._goal_value(doses, "D95") - 5.0) < 0.2
    assert abs(cases_r7._goal_value(doses, "D10") - 90.0) < 0.2 and abs(cases_r7._goal_value(doses, "Dmean") - 50.0) < 1e-6
    polys = cases_r7._sphere_polygons((0.0, 0.0, 0.0), 10.0, np.arange(-20.0, 21.0, 2.0))
    assert len(polys) == 9 and all(p.shape[0] % 3 == 0 for p in polys)
    eq = polys[4].reshape(-1, 3)
    assert np.allclose(np.hypot(eq[:, 0], eq[:, 1]), 10.0) and np.allclose(eq[:, 2], 0.0)
    a = np.random.default_rng(1).uniform(0, 1, (8, 8, 8)).astype(np.float32)
    rep = cases_r7._agreement(a, a * 1.01)
    assert abs(rep["integral_ratio"] - 1.01) < 1e-6 and rep["correlation"] > 0.9999 and abs(rep["highdose_p95"] - 0.01) < 1e-5


def test_bdl_row_reads_spot_sizes():
    bdl = Path(__file__).resolve().parents[1] / "engines" / "mcsquare" / "BDL" / "BDL_default_DN_RangeShifter.txt"
    if not bdl.is_file():
        pytest.skip("engine assets not fetched")
    row = cases_r7._bdl_row(bdl, 150.0)
    assert row is not None and row["NominalEnergy"] == 150.0 and 1.0 < row["SpotSize1x"] < 10.0 and 0.0 < row["EnergySpread"] < 5.0
    assert cases_r7._bdl_row(bdl, 151.0) is None
    assert cases_r7._bdl_nozzle_to_isocenter_mm(bdl) == 410.0
    r100 = cases_r7._bdl_row(bdl, 100.0)
    # the 100 MeV primary Gaussian grows from 3.99 mm at the nozzle exit to about 4.92 mm at the isocenter
    assert abs(cases_r7._propagated_sigma_mm(r100, "x", 410.0) - 4.92) < 0.03 and cases_r7._propagated_sigma_mm(r100, "x", 0.0) == pytest.approx(r100["SpotSize1x"])


def test_plan_normalisation_scales_to_the_coverage_goal(tmp_path):
    from types import SimpleNamespace

    from radiarch.validation.common import Context

    dose = np.random.default_rng(3).uniform(40.0, 70.0, (6, 6, 6)).astype(np.float32)
    target = dose[1:4, 1:4, 1:4].ravel()
    scaled, k = cases_r7._normalise_to_goal(dose, target, "D95", 50.0)
    assert abs(cases_r7._goal_value(scaled[1:4, 1:4, 1:4].ravel(), "D95") - 50.0) < 1e-3 and np.allclose(scaled, dose * k)
    ctx = Context(workdir=tmp_path)
    arrays = SimpleNamespace(spacing_mm=(2.0, 2.0, 3.0), origin_mm=(-5.0, -5.0, -7.5))
    uri = cases_r7._write_volume(ctx, "d", scaled, arrays)
    import SimpleITK as sitk
    img = sitk.ReadImage(uri)
    assert tuple(img.GetSpacing()) == (2.0, 2.0, 3.0) and np.allclose(sitk.GetArrayFromImage(img), scaled)


def test_geometry_reads_only_the_named_structure_set(tmp_path, monkeypatch):
    """Two structure sets in one directory, both with a ROI named PTV: the named one wins (R7 defect)."""
    from datetime import datetime

    from radiarch.config import get_settings
    from radiarch.dicom.writers import CaseContext, Structure, write_rtstruct
    from radiarch.models.geometry import GeometryBuildRequest, GridSpec, PatientRef
    from radiarch.services.geometry import GeometryService
    from radiarch.services.geometry_bundle import load_geometry_arrays
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    case = tmp_path / "case"; case.mkdir()
    series, study, frame = generate_uid(), generate_uid(), generate_uid()
    uids = []
    for k in range(12):
        meta = FileMetaDataset(); meta.MediaStorageSOPClassUID = CTImageStorage; meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = CTImageStorage; ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID; ds.Modality = "CT"
        ds.PatientName = "TWO^SETS"; ds.PatientID = "TS"; ds.StudyInstanceUID = study; ds.SeriesInstanceUID = series; ds.FrameOfReferenceUID = frame
        ds.Rows = ds.Columns = 32; ds.PixelSpacing = [4.0, 4.0]; ds.SliceThickness = 4.0
        ds.ImagePositionPatient = [-62.0, -62.0, -22.0 + 4.0 * k]; ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.RescaleSlope = 1; ds.RescaleIntercept = -1024; ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 0
        ds.PixelData = np.full((32, 32), 1024, np.uint16).tobytes()
        ds.save_as(str(case / f"CT{k:02d}.dcm"), enforce_file_format=True)
        uids.append(str(ds.SOPInstanceUID))
    ctx = CaseContext(patient_name="TWO^SETS", patient_id="TS", study_instance_uid=study, frame_of_reference_uid=frame,
                      ct_series_instance_uid=series, ct_sop_instance_uids=uids, now=datetime(2026, 10, 21))
    def box(x0, x1):
        z = np.zeros((12, 32, 32), bool); z[3:9, 10:20, x0:x1] = True; return z
    a = write_rtstruct(ctx, [Structure("PTV", mask_zyx=box(4, 10))], case / "RS_A.dcm", origin_mm=(-62.0, -62.0, -22.0), spacing_mm=(4.0, 4.0, 4.0))
    b = write_rtstruct(ctx, [Structure("PTV", mask_zyx=box(20, 28)), Structure("Rectum", mask_zyx=box(12, 16))], case / "RS_B.dcm",
                       origin_mm=(-62.0, -62.0, -22.0), spacing_mm=(4.0, 4.0, 4.0))
    for k, v in {"RADIARCH_ARTIFACT_DIR": str(tmp_path / "art"), "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": ""}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    svc = GeometryService()
    grid = GridSpec(spacing_mm=(4.0, 4.0, 4.0))
    geo_b = svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="s", rtstruct_uid=b.sop_instance_uid), data_root_override=str(case), grid_spec=grid))
    arr = load_geometry_arrays(geo_b)
    assert set(arr.structure_index) == {"PTV", "Rectum"}
    ptv = arr.mask_zyx(arr.structure_index["PTV"])
    xs = np.argwhere(ptv)[:, 2]
    assert xs.min() >= 19 and xs.max() <= 28            # set B's PTV, not set A's
    geo_a = svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="s", rtstruct_uid=a.sop_instance_uid), data_root_override=str(case), grid_spec=grid))
    assert set(load_geometry_arrays(geo_a).structure_index) == {"PTV"}
    with pytest.raises(ValueError, match="not found"):
        svc.build(GeometryBuildRequest(patient_ref=PatientRef(dicom_study_uid="s", rtstruct_uid="1.2.3.999"), data_root_override=str(case), grid_spec=grid))
    get_settings.cache_clear()


def test_mc_reference_compact_storage_round_trips(tmp_path):
    rng = np.random.default_rng(7)
    dose = (rng.uniform(0.0, 1.0, (10, 12, 10)) * 5.8e-13).astype(np.float32)
    unc = rng.uniform(0.0, 0.3, dose.shape).astype(np.float32)
    path = tmp_path / "ref.npz"
    mc_reference.save_reference(path, dose, unc, 2.5, (-11.25, 1.25, -11.25), 50_000_000)
    d, u, s, o, n = mc_reference.load_reference_arrays(path)
    assert d.shape == dose.shape and n == 50_000_000 and s == (2.5, 2.5, 2.5) and o == (-11.25, 1.25, -11.25)
    assert np.allclose(d, dose, rtol=1e-3, atol=dose.max() * 1e-3) and np.allclose(u, unc, atol=6e-4)
    legacy = tmp_path / "legacy.npz"
    np.savez_compressed(legacy, dose=dose, uncertainty=unc, spacing_mm=np.array([2.5] * 3), origin_mm=np.array([0.0, 1.25, 0.0]), primaries=10)
    mc_reference.compact(legacy)
    assert "dose_rel" in np.load(legacy).files and np.allclose(mc_reference.load_reference_arrays(legacy)[0], dose, atol=dose.max() * 1e-3)


def test_mc_phantom_layers_stack_from_the_surface():
    assert mc_reference.phantom_layers("water_10x10") == [(0.0, 300.0, "G4_WATER")]
    assert mc_reference.phantom_layers("lung_slab") == [(0.0, 30.0, "G4_WATER"), (30.0, 110.0, "WATER_0.26"), (110.0, 300.0, "G4_WATER")]
    assert mc_reference.phantom_layers("bone_slab")[1] == (30.0, 60.0, "WATER_1.85")
    assert mc_reference._slab_material(1.0) == "G4_WATER" and mc_reference.CUT_MM == 0.1 and mc_reference.MAX_STEP_MM == 0.5


def test_report_merges_a_rerun_case(tmp_path):
    def run(name, results):
        d = tmp_path / name; d.mkdir()
        (d / "results.json").write_text(json.dumps({"radiarch_commit": "abc", "fast": False, "host": "h", "python": "3", "results": results}))
        return d
    case = lambda status: {"name": "photon_vs_pyradplan", "kind": "photon_vs_pyradplan", "status": status, "seconds": 1.0, "notes": [], "error": None,  # noqa: E731
                           "metrics": {}, "checks": []}
    main = run("20261022-1", [case("fail"), {**case("pass"), "name": "photon_pdd_10x10", "kind": "photon_pdd"}])
    rerun = run("20261022-2", [case("info")])
    merged = report.merge_runs(main, [rerun])
    assert merged["runs"] == ["20261022-1", "20261022-2"] and [r["status"] for r in merged["results"]] == ["info", "pass"]
    doc = report.render("ccc", merged, main)
    assert "`20261022-1` + `20261022-2`" in doc
