"""Structural / layout regression tests for the vendored OpenTPS tree.

These tests don't exercise any *behavior* — they assert that the
on-disk package layout and the resulting import graph are sound. They
exist because a previous incident shipped a vendored OpenTPS subtree
without ``__init__.py`` markers, which (a) made
``opentps.core.processing.doseCalculation.protons.MCsquare`` non-importable,
(b) silently routed it through PEP-420 namespace lookup under setuptools'
strict editable install, and (c) broke 10 beam-model tests with a
``ModuleNotFoundError`` that took a full debug cycle to root-cause.

If any of these tests fail, **do not push**. The fix is almost always
either:
* add the missing ``__init__.py`` file, or
* run ``./scripts/install-dev.sh`` to regenerate the editable-install
  finder against the current source tree.

The tests are intentionally cheap (< 100ms each) so they can run on
every commit / in pre-push hooks without slowing the loop down.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Required __init__.py files in the vendored OpenTPS tree.
#
# Every entry here is a package whose absence has broken (or could break)
# downstream Radiarch code. Add to this list whenever Radiarch starts
# importing from a new vendored subpackage.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"

REQUIRED_INIT_FILES = [
    # Top-level vendored package marker
    "opentps/__init__.py",
    "opentps/core/__init__.py",
    # Processing subtree — empty markers are required for setuptools
    # find_packages to treat these as regular packages (not PEP-420
    # namespaces), which in turn is required for strict-mode editable
    # install to map them in the finder's MAPPING rather than NAMESPACES.
    "opentps/core/processing/__init__.py",
    "opentps/core/processing/doseCalculation/__init__.py",
    "opentps/core/processing/doseCalculation/protons/__init__.py",
    "opentps/core/processing/doseCalculation/protons/MCsquare/__init__.py",
    # Calibration subtree — touched by ProtonMachineModel.calibration
    "opentps/core/data/__init__.py",
    "opentps/core/data/CTCalibrations/__init__.py",
    "opentps/core/data/CTCalibrations/MCsquareCalibration/__init__.py",
    # I/O — touched by ProtonMachineModel.bdl (reads BDL via mcsquareIO)
    "opentps/core/io/__init__.py",
]


@pytest.mark.parametrize("rel_path", REQUIRED_INIT_FILES)
def test_required_init_file_exists(rel_path: str) -> None:
    """Every package marker Radiarch depends on must exist on disk.

    A missing marker silently flips the package into a PEP-420
    namespace and breaks strict-mode editable installs.
    """
    full = _SRC / rel_path
    assert full.is_file(), (
        f"Missing __init__.py: {full}\n"
        "  → If you just deleted it: revert.\n"
        "  → If you just added a vendored subpackage: drop in an empty\n"
        "    __init__.py and re-run ./scripts/install-dev.sh"
    )


# ---------------------------------------------------------------------------
# Vendored data files used by ProtonMachineModel.from_default()
# ---------------------------------------------------------------------------

REQUIRED_DATA_FILES = [
    # Beam Data Library — read by ProtonMachineModel.bdl
    "opentps/core/processing/doseCalculation/protons/MCsquare/BDL/"
    "BDL_default_DN_RangeShifter.txt",
    # CT calibration — read by ProtonMachineModel.calibration
    "opentps/core/processing/doseCalculation/protons/MCsquare/Scanners/"
    "UCL_Toshiba/HU_Density_Conversion.txt",
    "opentps/core/processing/doseCalculation/protons/MCsquare/Scanners/"
    "UCL_Toshiba/HU_Material_Conversion.txt",
]


@pytest.mark.parametrize("rel_path", REQUIRED_DATA_FILES)
def test_vendored_data_file_exists(rel_path: str) -> None:
    """The BDL and CT calibration files must ship with the vendored tree.

    These are what ``_default_bdl_path()`` / ``_default_scanner_dir()``
    resolve to. Missing them surfaces as a ``MachineModelError`` at
    runtime — much later than we'd like.
    """
    full = _SRC / rel_path
    assert full.is_file(), f"Missing vendored data file: {full}"


# ---------------------------------------------------------------------------
# Import-chain regression — the exact import the failing tests were hitting
# ---------------------------------------------------------------------------

def test_import_mcsquare_submodule() -> None:
    """``opentps.core.processing.doseCalculation.protons.MCsquare`` must import.

    This is the regression test for the bug that broke 10 beam-model
    tests. ``radiarch.services.machine_model._default_mcsquare_path``
    calls ``MCsquareModule.__path__[0]`` on this module — if the import
    fails (or returns a namespace package with the wrong ``__path__``),
    every proton machine-model load fails downstream.
    """
    mod = importlib.import_module(
        "opentps.core.processing.doseCalculation.protons.MCsquare"
    )
    # Namespace packages have __path__ but no __file__; a real package
    # has both. We need a real package here because we resolve data files
    # relative to __path__[0] and depend on the directory being stable.
    assert hasattr(mod, "__path__"), "MCsquare must be a package, not a module"
    assert len(mod.__path__) >= 1, "MCsquare.__path__ must be non-empty"
    # The path must point at a real directory containing BDL/ and Scanners/.
    mcs_dir = Path(mod.__path__[0])
    assert mcs_dir.is_dir(), f"MCsquare.__path__[0] is not a directory: {mcs_dir}"
    assert (mcs_dir / "BDL").is_dir(), "BDL/ missing under MCsquare package"
    assert (mcs_dir / "Scanners").is_dir(), "Scanners/ missing under MCsquare package"


def test_import_doseCalculation_is_regular_package() -> None:
    """``doseCalculation`` must be a regular package, not a PEP-420 namespace.

    Under setuptools' strict editable install, a missing ``__init__.py``
    would make this a namespace package. Namespace packages have
    ``__file__ = None`` and can be silently merged across multiple
    locations — which broke our import chain in the previous incident.
    """
    mod = importlib.import_module(
        "opentps.core.processing.doseCalculation"
    )
    assert getattr(mod, "__file__", None) is not None, (
        "opentps.core.processing.doseCalculation is a PEP-420 namespace "
        "package — its __init__.py is missing or the editable install is "
        "stale. Run ./scripts/install-dev.sh to fix."
    )


# ---------------------------------------------------------------------------
# Smoke test: ProtonMachineModel.from_default() — the real path the
# failing tests were exercising.
# ---------------------------------------------------------------------------

def test_proton_machine_model_from_default_resolves_paths() -> None:
    """Constructing ``ProtonMachineModel.from_default()`` must succeed.

    This is the call site that originally surfaced the
    ``ModuleNotFoundError``. It triggers ``_default_mcsquare_path()``,
    which in turn imports the MCsquare submodule. If that import is
    broken, this test fails fast with a clear error before any
    downstream beam-model test runs.

    We deliberately *don't* touch ``.bdl`` or ``.calibration`` — those
    are lazy and would pull in the full BDL parser. We just want to
    verify the path resolution + import side of from_default().
    """
    from radiarch.services.machine_model import ProtonMachineModel

    model = ProtonMachineModel.from_default()
    assert model.machine_model_id == "default"
    assert os.path.isfile(model.bdl_path), (
        f"BDL path resolved by from_default() does not exist: {model.bdl_path}"
    )
    assert os.path.isdir(model.scanner_dir), (
        f"Scanner dir resolved by from_default() does not exist: {model.scanner_dir}"
    )


def test_photon_machine_model_from_default_constructs() -> None:
    """Same idea for the photon side — just constructs cleanly."""
    from radiarch.services.machine_model import PhotonMachineModel

    model = PhotonMachineModel.from_default()
    assert model.machine_model_id == "default"
    # Photon model doesn't touch the vendored MCsquare tree, but it
    # does live in the same module and would catch regressions in
    # the import graph of radiarch.services.machine_model itself.
