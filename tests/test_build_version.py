"""Which radiarch made an output: Software Versions = [release, "git <commit>"] in every DICOM object, the commit in an
export's attribution and in /info (radiarch.build)."""

from __future__ import annotations

import subprocess
from importlib.metadata import version
from pathlib import Path

import pydicom
import pytest

from test_r6_rt_export_service import env  # noqa: F401
from test_r13_viewer import _export

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    from radiarch import build

    monkeypatch.delenv("RADIARCH_BUILD_COMMIT", raising=False)
    build.release.cache_clear()
    build.commit.cache_clear()
    yield build
    build.release.cache_clear()
    build.commit.cache_clear()


def _git(*args):
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def test_the_commit_of_the_checkout(fresh):
    sha = _git("rev-parse", "--short=7", "HEAD")
    if sha is None:
        pytest.skip("not a git checkout")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    assert fresh.commit() == (f"{sha}-dirty" if dirty else sha)
    assert fresh.software_versions() == [version("radiarch"), f"git {fresh.commit()}"]
    assert fresh.describe() == f"radiarch {version('radiarch')} (git {fresh.commit()})"


def test_a_built_image_states_its_commit_and_without_one_only_the_release(fresh, monkeypatch):
    monkeypatch.setenv("RADIARCH_BUILD_COMMIT", "abc1234")
    assert fresh.software_versions() == [version("radiarch"), "git abc1234"]

    monkeypatch.delenv("RADIARCH_BUILD_COMMIT")
    fresh.commit.cache_clear()
    monkeypatch.setattr(fresh, "_git", lambda *a: None)              # no git, no build argument
    assert fresh.commit() is None and fresh.software_versions() == [version("radiarch")]
    assert fresh.describe() == f"radiarch {version('radiarch')}"


def test_every_object_of_an_export_states_release_and_commit(env, fresh, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RADIARCH_BUILD_COMMIT", "feed123")
    svc, res = _export()
    for o in res.objects:
        ds = pydicom.dcmread(o.path, stop_before_pixels=True)
        assert list(ds.SoftwareVersions) == [version("radiarch"), "git feed123"], o.kind
        assert ds[0x7779, 0x1002].value == f"radiarch {version('radiarch')} (git feed123)"
    assert res.attribution["capability_version"] == version("radiarch") and res.attribution["capability_commit"] == "feed123"


def test_info_states_release_and_commit(env, fresh, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    import radiarch.app as radiarch_app

    monkeypatch.setenv("RADIARCH_BUILD_COMMIT", "feed123")
    monkeypatch.setattr(radiarch_app, "init_db", lambda: None)
    with TestClient(radiarch_app.create_app()) as client:
        info = client.get("/api/v1/info").json()
    assert info["version"] == version("radiarch") and info["commit"] == "feed123"
