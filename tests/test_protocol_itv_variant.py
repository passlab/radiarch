"""The ``lung-60gy-30fx-vmat-itv`` protocol: the lung VMAT protocol for a patient whose target is an ITV. It differs
from ``lung-60gy-30fx-vmat`` only in where the targets come from (CTV = ITV + 5 mm; the template's Lungs-GTV is the
lungs less the ITV), and it plans a phantom whose target is named ``iGTV``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pydicom
import pytest

from radiarch.cli import main
from radiarch.services.autoplan import load_protocol

from test_dose_command import dose_env  # noqa: F401  (the app in this process with the real geometry loader)


def test_the_variant_differs_from_the_lung_protocol_only_in_its_target_source():
    base, itv = load_protocol("lung-60gy-30fx-vmat").model_dump(), load_protocol("lung-60gy-30fx-vmat-itv").model_dump()
    for key in ("protocol_id", "name", "description", "structure_aliases", "structures"):
        base.pop(key), itv.pop(key)
    assert base == itv                                   # prescription, goals, arcs, machine, engine, rounds, template
    b, v = load_protocol("lung-60gy-30fx-vmat"), load_protocol("lung-60gy-30fx-vmat-itv")
    assert set(v.structure_aliases) == (set(b.structure_aliases) - {"GTV"}) | {"ITV"}
    assert {"ITV", "ITV_Primary", "iGTV", "ITVp"} <= set(v.structure_aliases["ITV"])
    ops_b = {o.name: o.model_dump() for o in b.structures}
    ops_v = {o.name: o.model_dump() for o in v.structures}
    assert set(ops_b) == set(ops_v)
    assert ops_v["CTV"] == {**ops_b["CTV"], "source": "ITV"}
    assert ops_v["Lungs-GTV"] == {**ops_b["Lungs-GTV"], "sources": ["ITV"]}
    assert {n: o for n, o in ops_v.items() if n not in ("CTV", "Lungs-GTV")} == {n: o for n, o in ops_b.items() if n not in ("CTV", "Lungs-GTV")}


def _thorax(tmp_path: Path):
    """A 5 mm phantom with the structures the protocol needs, the target contoured as ``iGTV``."""
    from radiarch.validation.phantoms import write_case

    n = 32
    hu = np.full((n, n, n), -1000, dtype=np.int16)
    body = np.zeros((n, n, n), bool)
    body[2:30, 4:28, 2:30] = True
    hu[body] = 0
    lung_l = np.zeros((n, n, n), bool); lung_l[6:26, 8:24, 17:27] = True
    lung_r = np.zeros((n, n, n), bool); lung_r[6:26, 8:24, 5:15] = True
    hu[lung_l | lung_r] = -700
    igtv = np.zeros((n, n, n), bool); igtv[13:19, 13:18, 19:24] = True
    hu[igtv] = 20
    cord = np.zeros((n, n, n), bool); cord[4:28, 23:26, 15:18] = True
    eso = np.zeros((n, n, n), bool); eso[4:28, 19:22, 15:18] = True
    heart = np.zeros((n, n, n), bool); heart[12:22, 9:16, 13:19] = True
    structures = {"Body": body, "iGTV": igtv, "Lung_L": lung_l, "Lung_R": lung_r, "SpinalCord": cord, "Esophagus": eso, "Heart": heart}
    case = write_case(tmp_path / "thorax", hu, 5.0, (-77.5, -77.5, -77.5), structures, "itv-variant")
    study = str(pydicom.dcmread(str(case / "CT000.dcm"), stop_before_pixels=True).StudyInstanceUID)
    return case, study


def test_the_variant_plans_a_patient_whose_target_is_an_igtv(dose_env, tmp_path, capsys):  # noqa: F811
    case, study = _thorax(tmp_path)
    code = main(["plan", "--protocol", "lung-60gy-30fx-vmat-itv", "--study", study, "--data", str(case),
                 "--json", str(tmp_path / "run.json"), "--poll", "0.01"])
    out = capsys.readouterr().out
    assert code == 0, out
    run = json.loads((tmp_path / "run.json").read_text())
    assert run["aliased"]["ITV"] == "iGTV" and "GTV" not in run["aliased"]
    assert run["deliverable"] and run["normalisation"] > 0
    assert "PTV D95 >= 60" in out and "Lungs-PTV D37 <= 20" in out
