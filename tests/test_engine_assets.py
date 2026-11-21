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


def test_mcsquare_radiarch_build():
    """radiarch's build of MCsquare (ADR 0023): its recipe, patches and build record, the licences. The binary is
    built, not committed (engines/mcsquare-build/build-in-docker.sh); when it is there it is a static ELF."""
    root = ENGINES / "mcsquare"
    binary = root / "MCsquare_radiarch"
    if binary.exists():
        assert os.access(binary, os.X_OK) and binary.read_bytes()[:4] == b"\x7fELF"
    assert "engines/mcsquare/MCsquare_radiarch" in (REPO / ".gitignore").read_text()
    build = ENGINES / "mcsquare-build"
    for script in ("build.sh", "build-in-docker.sh"):
        assert (build / script).is_file() and os.access(build / script, os.X_OK)
    assert len([l for l in (build / "BUILD.txt").read_text().splitlines() if l.startswith("sha256 ")]) == 1
    patches = sorted(p.name for p in (build / "patches").glob("*.patch"))
    assert [p[:4] for p in patches] == ["0001", "0002", "0003", "0004"], patches
    assert (build / "BUILD.txt").is_file()
    assert "Apache 2.0" in (build / "LICENSE-MCsquare").read_text()
    assert (root / "LICENSE-oneMKL.txt").read_text().startswith("Intel Simplified Software License")
    assert (root / "LICENSE-oneMKL-third-party-programs.txt").is_file()
    fetch = (REPO / "scripts" / "fetch-engines.sh").read_text()
    for kept in ("MCsquare_radiarch", "LICENSE-oneMKL*"):
        assert f"--exclude '{kept}'" in fetch, f"fetch-engines.sh would delete {kept}"


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


def test_pb_layout():
    """The native pencil-beam engine's kernel table and its provenance (R8)."""
    from radiarch.services.dose_engines.pb_kernel import default_kernel_path
    path = default_kernel_path()
    assert path == ENGINES / "pb" / "pb_6mv_kernel.npz"
    assert path.is_file() and path.with_suffix(".json").is_file()
