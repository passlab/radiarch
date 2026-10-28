"""The lung demo: a public patient from TCIA (NBIA API, faked here) into a cache and a DICOMweb server, the
``radiarch fetch-tcia`` command, and the demo-lung-imrt protocol, which takes NSCLC-Radiomics' structure names."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from radiarch.adapters import tcia

LICENCE = "License Information. The NSCLC-Radiomics collection is distributed under the CC BY-NC 3.0."
SERIES = [
    {"SeriesInstanceUID": "1.1.1", "StudyInstanceUID": "9.1", "Modality": "CT"},
    {"SeriesInstanceUID": "1.1.2", "StudyInstanceUID": "9.1", "Modality": "RTSTRUCT"},
    {"SeriesInstanceUID": "1.1.3", "StudyInstanceUID": "9.1", "Modality": "SEG"},
    {"SeriesInstanceUID": "2.2.1", "StudyInstanceUID": "8.1", "Modality": "CT"},      # a diagnostic CT, no contours
]


def _zip(n: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(n):
            z.writestr(f"series/1-{i:02d}.dcm", b"DICM")
        z.writestr("series/LICENSE", LICENCE + "\nData Usage Policy\n")
        z.writestr("series/manifest.txt", "not DICOM")
    return buf.getvalue()


class Response:
    def __init__(self, payload=None, content=b""):
        self._payload, self.content = payload, content or (b"[]" if payload is None else b"x")

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeNBIA:
    def __init__(self, series=SERIES):
        self.series, self.calls = series, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url.rsplit("/", 1)[1], params))
        if url.endswith("/getSeries"):
            return Response(self.series)
        return Response(content=_zip(3 if params["SeriesInstanceUID"] in ("1.1.1", "2.2.1") else 1))


def test_the_planning_study_is_fetched_once(tmp_path):
    nbia = FakeNBIA()
    case = tcia.fetch_patient("NSCLC-Radiomics", "LUNG1-002", tmp_path, session=nbia)
    # the study with a structure set, its CT and structure set (not the SEG, not the other study's CT)
    assert case.study_instance_uid == "9.1" and {m: len(f) for m, f in case.series.items()} == {"CT": 3, "RTSTRUCT": 1}
    assert case.files[0].parent == tmp_path / "NSCLC-Radiomics" / "LUNG1-002" / "CT_1.1.1"
    assert not list(tmp_path.rglob("manifest.txt"))
    assert "CC BY-NC 3.0" in tcia.licence_notice(case) and "LUNG1-002" in tcia.licence_notice(case)
    assert [c[0] for c in nbia.calls] == ["getSeries", "getImage", "getImage"]
    # again: the completed series are not downloaded again
    tcia.fetch_patient("NSCLC-Radiomics", "LUNG1-002", tmp_path, session=nbia)
    assert [c[0] for c in nbia.calls].count("getImage") == 2


def test_an_unknown_patient_is_an_error(tmp_path):
    with pytest.raises(tcia.TCIAError, match="no public series"):
        tcia.fetch_patient("NSCLC-Radiomics", "NOBODY", tmp_path, session=FakeNBIA(series=[]))
    with pytest.raises(tcia.TCIAError, match="no CT/RTSTRUCT"):
        tcia.fetch_patient("NSCLC-Radiomics", "LUNG1-002", tmp_path, session=FakeNBIA(series=SERIES[2:3]))


def test_the_case_is_pushed_in_batches(tmp_path):
    case = tcia.fetch_patient("NSCLC-Radiomics", "LUNG1-002", tmp_path, session=FakeNBIA())

    class Notifier:
        batches = []

        def store_instances(self, files, raise_errors=False):
            assert raise_errors
            self.batches.append(len(files))
            return True

    assert tcia.push(case, Notifier(), batch=2) == 4 and Notifier.batches == [2, 2]


def test_the_command_prints_the_study_last(tmp_path, monkeypatch, capsys):
    from radiarch.cli import main

    case = tcia.FetchedCase("NSCLC-Radiomics", "LUNG1-002", "9.1", {"CT": [Path("a.dcm")]}, LICENCE)
    pushed = []
    monkeypatch.setattr(tcia, "fetch_patient", lambda collection, patient, cache, modalities: case)
    monkeypatch.setattr(tcia, "push", lambda c: pushed.append(c) or 1)
    assert main(["fetch-tcia", "--patient", "LUNG1-002", "--cache", str(tmp_path), "--push"]) == 0
    out = capsys.readouterr()
    assert out.out.strip().splitlines()[-1] == "9.1" and pushed == [case]
    assert "CC BY-NC 3.0" in out.err and "pushed 1 instances" in out.err


def test_the_lung_protocols_take_nsclc_radiomics_names():
    from radiarch.services.autoplan import load_protocol

    tcia_names = {"GTV": "GTV-1", "SpinalCord": "Spinal-Cord", "Lung_L": "Lung-Left", "Lung_R": "Lung-Right", "Heart": "Heart",
                  "Esophagus": "Esophagus"}
    for pid in ("demo-lung-imrt", "lung-60gy-30fx-vmat", "lung-sbrt-54gy-3fx-vmat"):
        p = load_protocol(pid)
        for name, tcia_name in tcia_names.items():
            assert tcia_name.lower() in {a.lower() for a in p.structure_aliases[name]} | {name.lower()}, (pid, name)
    demo = load_protocol("demo-lung-imrt")
    assert demo.beams.technique == "imrt" and demo.prescription.dose_gy == 60.0 and demo.engine.name == "pb"
    assert {g.structure for g in demo.goals} == {g.structure for g in load_protocol("lung-60gy-30fx-vmat").goals}


def test_the_compose_stack_shares_its_artifacts():
    """The API reads what the worker writes: both use the shared volume's path whatever .env says (a relative
    RADIARCH_ARTIFACT_DIR there made the API lose every job's result)."""
    import yaml

    compose = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8"))
    for name in ("api", "worker"):
        svc = compose["services"][name]
        env = dict(e.split("=", 1) for e in svc["environment"])
        assert env["RADIARCH_ARTIFACT_DIR"] == "/data/artifacts", name
        assert "radiarch-data:/data/artifacts" in svc["volumes"], name


@pytest.mark.parametrize("new_export", [None, "1"])
def test_the_demo_script_asks_for_a_copy_only_when_told(tmp_path, new_export):
    """``demo-lung.sh`` run again pushes the stored export; ``NEW_EXPORT=1`` passes ``--new-export`` (a stand-in
    ``docker`` records the commands)."""
    import os
    import shutil
    import subprocess

    if not shutil.which("bash"):
        pytest.skip("needs bash")
    log = tmp_path / "docker.log"
    fake = tmp_path / "bin" / "docker"
    fake.parent.mkdir()
    fake.write_text(f'#!/usr/bin/env bash\necho "$*" >> "{log}"\necho 9.1\n')
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}"}
    env.pop("NEW_EXPORT", None)
    if new_export:
        env["NEW_EXPORT"] = new_export
    script = Path(__file__).resolve().parents[1] / "scripts" / "demo-lung.sh"
    out = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    fetch, plan = log.read_text().splitlines()
    assert "fetch-tcia" in fetch and "radiarch plan" in plan and "--study 9.1" in plan and "--push" in plan
    assert ("--new-export" in plan) == bool(new_export)
    assert "plan-review?StudyInstanceUIDs=9.1" in out.stdout
