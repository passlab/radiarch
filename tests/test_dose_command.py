"""The ``radiarch dose`` command: an RT Plan's dose recomputed on a CT with its structures, in this process, and written
as an RT Dose that references the given structure set. Uses a phantom case on disk and a photon plan in its frame."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pydicom
import pytest

import dicom_fixtures as F
from radiarch.cli import main


@pytest.fixture()
def dose_env(monkeypatch, tmp_path):
    """The app in this process with a scratch artifact directory and the real geometry loader (the CLI reads files)."""
    import radiarch.app as radiarch_app
    from radiarch.config import get_settings

    for k, v in {"RADIARCH_ENVIRONMENT": "dev", "RADIARCH_ORTHANC_USE_MOCK": "true", "RADIARCH_DATABASE_URL": "",
                 "RADIARCH_BROKER_URL": "memory://", "RADIARCH_RESULT_BACKEND": "cache+memory://",
                 "RADIARCH_ARTIFACT_DIR": str(tmp_path / "artifacts"), "RADIARCH_API_KEY": "", "RADIARCH_DICOMWEB_URL": ""}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("RADIARCH_SERVER", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    import radiarch.api.routes.beam_model as bm_route
    import radiarch.api.routes.dose as dose_route
    from radiarch.core import store as store_module

    store_module.reset_store()
    bm_route._service.cache_clear()
    dose_route._service.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _case(tmp_path: Path):
    """A 24-voxel water cube at 5 mm with a 4 cm PTV at its centre, as a CT series and a structure set; the plan is one
    anterior 10 x 10 cm field of 200 MU at the centre, in the CT's frame of reference."""
    from radiarch.validation.phantoms import write_case

    n = 24
    hu = np.zeros((n, n, n), dtype=np.int16)
    body = np.ones((n, n, n), bool)
    ptv = np.zeros((n, n, n), bool)
    ptv[8:16, 8:16, 8:16] = True
    case = write_case(tmp_path / "case", hu, 5.0, (-57.5, -57.5, -57.5), {"Body": body, "PTV": ptv}, "dose-command")
    for_uid = str(pydicom.dcmread(str(case / "CT000.dcm"), stop_before_pixels=True).FrameOfReferenceUID)
    cps = [{"cmw": 0.0, "gantry": 0.0, "iso": [0, 0, 0], "xj": [-50, 50], "yj": [-50, 50]}, {"cmw": 1.0}]
    plan = F.save(F.photon_rtplan([{"number": 1, "name": "AP", "cps": cps}], {1: 200.0}, for_uid=for_uid), tmp_path / "RP-in.dcm")
    return case, Path(plan)


def test_the_dose_of_a_plan_on_a_ct_with_a_structure_set_elsewhere(dose_env, tmp_path, capsys):
    case, plan = _case(tmp_path)
    rs = tmp_path / "structures" / "RS.dcm"          # outside the CT directory: the command links the two together
    rs.parent.mkdir()
    (case / "RS.dcm").rename(rs)
    rs_uid = str(pydicom.dcmread(str(rs), stop_before_pixels=True).SOPInstanceUID)
    code = main(["dose", "--ct", str(case), "--structures", str(rs), "--plan", str(plan), "--engine", "auto",
                 "--export", str(tmp_path / "rt"), "--json", str(tmp_path / "dose.json"), "--poll", "0.01"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "dose " in out and "pb " in out and "PHOTON_IMRT" in out and "max " in out
    record = json.loads((tmp_path / "dose.json").read_text())
    assert record["dose"]["engine_name"] == "pb" and record["dose"]["statistics"]["max_gy"] > 0.5
    assert record["export"]["export_id"]
    files = {p.name: p for p in (tmp_path / "rt").iterdir()}
    assert "RD.dcm" in files and "RP.dcm" in files and "RS.dcm" not in files, sorted(files)
    rd = pydicom.dcmread(str(files["RD.dcm"]))
    rp = pydicom.dcmread(str(files["RP.dcm"]))
    assert rp.RTPlanLabel == "RESEARCH"
    assert rp.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID == rs_uid
    assert rd.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID == rp.SOPInstanceUID
    assert float(np.asarray(rd.pixel_array).max() * float(rd.DoseGridScaling)) == pytest.approx(record["dose"]["statistics"]["max_gy"], rel=0.02)
    assert not list(Path("/tmp").glob("radiarch-dose-*")), "the staging directory is removed"


def test_the_structure_set_in_the_ct_directory_and_the_errors(dose_env, tmp_path, capsys):
    case, plan = _case(tmp_path)
    code = main(["dose", "--ct", str(case), "--plan", str(plan), "--engine", "pb", "--export", str(tmp_path / "rt"), "--poll", "0.01"])
    assert code == 0, capsys.readouterr().out
    names = sorted(p.name for p in (tmp_path / "rt").iterdir())
    assert names == ["RD.dcm", "RP.dcm", "RS.dcm"]          # no structure set named: radiarch writes one
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit, match="no CT image"):
        main(["dose", "--ct", str(empty), "--plan", str(plan), "--poll", "0.01"])
    with pytest.raises(SystemExit, match="not an RT Structure Set"):
        main(["dose", "--ct", str(case), "--structures", str(plan), "--plan", str(plan), "--poll", "0.01"])
    with pytest.raises(SystemExit, match="plan file not found"):
        main(["dose", "--ct", str(case), "--plan", str(tmp_path / "none.dcm"), "--poll", "0.01"])


def test_the_command_runs_in_this_process_whatever_the_server_environment_says(dose_env, tmp_path, monkeypatch, capsys):
    """A container image's defaults name its compose services (production, a Postgres host, a Redis broker); the command
    without --server runs self-contained all the same: jobs in this process, no database, an in-memory broker."""
    from radiarch.config import get_settings

    monkeypatch.setenv("RADIARCH_ENVIRONMENT", "production")
    monkeypatch.setenv("RADIARCH_DATABASE_URL", "postgresql+psycopg://radiarch:radiarch@postgres.invalid:5432/radiarch")
    monkeypatch.setenv("RADIARCH_BROKER_URL", "redis://redis.invalid:6379/0")
    monkeypatch.setenv("RADIARCH_RESULT_BACKEND", "redis://redis.invalid:6379/1")
    get_settings.cache_clear()
    case, plan = _case(tmp_path)
    code = main(["dose", "--ct", str(case), "--plan", str(plan), "--engine", "pb", "--json", str(tmp_path / "dose.json"), "--poll", "0.01"])
    assert code == 0, capsys.readouterr().out
    assert json.loads((tmp_path / "dose.json").read_text())["dose"]["statistics"]["max_gy"] > 0.5
    assert get_settings().database_url == "" and get_settings().broker_url == "memory://"
