"""The engine assets under engines/ are where the drivers expect them (roadmap R15).

These tests assert the on-disk layout only; the engines themselves are exercised
by ``tests/test_mcsquare_driver.py`` and ``tests/test_ccc_engine.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENGINES = REPO / "engines"


def test_default_asset_dirs_resolve_to_the_repository():
    from radiarch.services.dose_engines.ccc_driver import default_engine_dir
    from radiarch.services.dose_engines.mcsquare_driver import default_assets_dir

    assert default_assets_dir() == ENGINES / "mcsquare"
    assert default_engine_dir() == ENGINES / "ccc"


def test_mcsquare_layout():
    root = ENGINES / "mcsquare"
    assert (root / "MCsquare").is_file() and os.access(root / "MCsquare", os.X_OK)
    assert (root / "Materials" / "list.dat").is_file()
    assert (root / "Materials" / "Water" / "G4_Stop_Pow.dat").is_file()
    assert (root / "BDL" / "BDL_default_DN_RangeShifter.txt").is_file()
    for scanner in ("UCL_Toshiba", "default"):
        assert (root / "Scanners" / scanner / "HU_Density_Conversion.txt").is_file()
        assert (root / "Scanners" / scanner / "HU_Material_Conversion.txt").is_file()
    binaries = sorted(p.name for p in root.glob("MCsquare_linux*"))
    assert "MCsquare_linux" in binaries and "MCsquare_linux_avx2" in binaries
    assert not list(root.rglob("__init__.py")), "engine assets are data, not a Python package"


def test_ccc_layout():
    root = ENGINES / "ccc"
    assert (root / "CCC_DoseEngine" / "CCC_DoseEngine").is_file()
    assert (root / "Kernels_differentFluence").is_dir() and (root / "Kernels_6MV").is_dir()
    assert (root / "licenseWiscPlan.txt").is_file()
    assert not list(root.glob("*.py")), "only the engine, its kernels and data live here"


def test_no_opentps_left():
    assert not (REPO / "src" / "opentps").exists()
    src = REPO / "src" / "radiarch"
    offenders = []
    for p in src.rglob("*.py"):
        for line in p.read_text().splitlines():
            if line.strip().startswith(("import opentps", "from opentps")):
                offenders.append(f"{p.relative_to(REPO)}: {line.strip()}")
    assert not offenders, offenders
    with pytest.raises(ImportError):
        import opentps  # noqa: F401
