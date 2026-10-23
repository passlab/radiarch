"""Regression goldens (R7a): today's outputs, frozen under tests/golden, must
be reproduced exactly. Protects the OpenTPS replacements of R14, R2 and R15."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from radiarch.validation import goldens as G

GOLDEN = G.GOLDEN_DIR


def _ccc_available() -> bool:
    try:
        from radiarch.services.dose_engines.ccc import CCCEngine
        return CCCEngine().driver().availability()[0]
    except Exception:
        return False


def _mcsquare_available() -> bool:
    try:
        from radiarch.services.dose_engines.registry import engine_health
        return bool(engine_health("mcsquare").get("available"))
    except Exception:
        return False


@pytest.mark.skipif(not (GOLDEN / "ccc_water_10x10.npz").is_file(), reason="golden not captured")
@pytest.mark.skipif(not _ccc_available(), reason="CCC binary not available")
def test_ccc_beamlet_matrix_matches_golden():
    ref = np.load(GOLDEN / "ccc_water_10x10.npz")
    meta = json.loads((GOLDEN / "ccc_water_10x10.json").read_text(encoding="utf-8"))
    now = G.compute_ccc_golden()
    assert now["meta"]["kernel_fingerprint"] == meta["kernel_fingerprint"], "kernel set changed; recapture if intended"
    assert tuple(now["shape"]) == tuple(ref["shape"])
    assert np.array_equal(now["indptr"], ref["indptr"])
    assert np.array_equal(now["indices"], ref["indices"])
    assert np.allclose(now["data"], ref["data"], rtol=1e-6, atol=1e-9)


@pytest.fixture(scope="module")
def simplefantom():
    if not G.SIMPLEFANTOM.is_dir():
        pytest.skip("SimpleFantom test data not present")
    with tempfile.TemporaryDirectory(prefix="radiarch-golden-test-") as tmp:
        work = Path(tmp)
        yield (work,) + G.build_simplefantom(work)


@pytest.mark.skipif(not (GOLDEN / "geometry_simplefantom.json").is_file(), reason="golden not captured")
def test_geometry_matches_golden(simplefantom):
    work, geo, geo_svc, bm, bm_svc = simplefantom
    ref = json.loads((GOLDEN / "geometry_simplefantom.json").read_text(encoding="utf-8"))
    now = G.compute_geometry_golden(geo, geo_svc)
    assert now["structure_index"] == ref["structure_index"]
    assert now["voxel_counts"] == ref["voxel_counts"]
    assert now["shape_zyx"] == ref["shape_zyx"] and now["spacing_mm"] == ref["spacing_mm"]
    assert now["density"]["sha256"] == ref["density"]["sha256"]
    assert now["masks_sha256"] == ref["masks_sha256"]


@pytest.mark.skipif(not (GOLDEN / "proton_spots_simplefantom.json").is_file(), reason="golden not captured")
def test_proton_spots_match_golden(simplefantom):
    work, geo, geo_svc, bm, bm_svc = simplefantom
    ref = json.loads((GOLDEN / "proton_spots_simplefantom.json").read_text(encoding="utf-8"))
    now = G.compute_spots_golden(bm, bm_svc)
    assert now["total_spots"] == ref["total_spots"] and now["fluence_total_count"] == ref["fluence_total_count"]
    assert [l["energy_mev"] for l in now["layers"]] == [l["energy_mev"] for l in ref["layers"]]
    for a, b in zip(now["layers"], ref["layers"]):
        assert np.allclose(np.asarray(a["spots_xy_mm"]), np.asarray(b["spots_xy_mm"]), atol=1e-3)


@pytest.mark.skipif(not (GOLDEN / "mcsquare_inputs_simplefantom").is_dir(), reason="golden not captured")
@pytest.mark.skipif(not _mcsquare_available(), reason="MCsquare not available")
def test_mcsquare_input_files_match_golden(simplefantom):
    work, geo, geo_svc, bm, bm_svc = simplefantom
    now = G.compute_mcsquare_inputs_golden(geo, bm, geo_svc, bm_svc, work)
    for p in sorted((GOLDEN / "mcsquare_inputs_simplefantom").iterdir()):
        assert p.name in now, f"{p.name} no longer written"
        if p.name == "config.txt":
            # the primary count and the seed are run parameters, not the protocol
            strip = lambda t: "\n".join(l for l in t.splitlines() if not l.split()[:1] or l.split()[0] not in ("Num_Primaries", "RNG_Seed", "Num_Threads"))
            assert strip(now[p.name]) == strip(p.read_text(encoding="utf-8")), "MCsquare config differs from the golden"
        else:
            assert now[p.name] == p.read_text(encoding="utf-8"), f"{p.name} differs from the golden"
