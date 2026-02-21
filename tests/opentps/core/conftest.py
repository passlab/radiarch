"""
Shared fixtures and path setup for OpenTPS core tests.

Adds service/ to sys.path so vendored opentps.core is importable,
and provides path fixtures for test data directories.
"""

import os
import sys

import pytest

# ── Path setup ──────────────────────────────────────────────────────
# Ensure vendored opentps (service/opentps/) is importable
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
_service_dir = os.path.join(_repo_root, "service")
if _service_dir not in sys.path:
    sys.path.insert(0, _service_dir)

# MCsquare python_interface Process modules
_mcsquare_interface_dir = os.path.join(os.path.dirname(__file__), "MCsquare-python_interface")
if _mcsquare_interface_dir not in sys.path:
    sys.path.insert(0, _mcsquare_interface_dir)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def opentps_testdata_dir():
    """Path to opentps-testData (SimpleFantomWithStruct, etc.)."""
    d = os.path.join(os.path.dirname(__file__), "opentps-testData")
    if not os.path.isdir(d):
        pytest.skip("opentps-testData not found")
    return d


@pytest.fixture(scope="session")
def simple_fantom_dir(opentps_testdata_dir):
    """Path to SimpleFantomWithStruct DICOM dataset."""
    d = os.path.join(opentps_testdata_dir, "SimpleFantomWithStruct")
    if not os.path.isdir(d):
        pytest.skip("SimpleFantomWithStruct not found")
    return d


@pytest.fixture(scope="session")
def mcsquare_interface_dir():
    """Path to MCsquare-python_interface root."""
    d = os.path.join(os.path.dirname(__file__), "MCsquare-python_interface")
    if not os.path.isdir(d):
        pytest.skip("MCsquare-python_interface not found")
    return d


@pytest.fixture(scope="session")
def mcsquare_sample_data_dir(mcsquare_interface_dir):
    """Path to MCsquare python_interface sample DICOM data."""
    d = os.path.join(mcsquare_interface_dir, "data")
    if not os.path.isdir(d):
        pytest.skip("MCsquare sample data not found")
    return d
