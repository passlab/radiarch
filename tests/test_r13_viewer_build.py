"""``viewer/scripts/build-ohif.sh`` with ``OHIF_DIR``: an existing OHIF checkout in place of the clone. ``node`` and
``npx`` are stubbed, so the packages are placed and registered and the build steps are called without a network or
an OHIF build (CI's job "Viewer" runs the real build on a clone)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "viewer" / "scripts" / "build-ohif.sh"


def _stub(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def _run(env_extra: dict, tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "npx.log"
    _stub(bin_dir, "node", 'echo 10.0.0')
    _stub(bin_dir, "npx", f'echo "$@" >> {log}')
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", **env_extra}
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60), log


def test_an_existing_checkout_is_used_in_place(tmp_path):
    ohif = tmp_path / "Viewers"
    (ohif / "platform" / "app").mkdir(parents=True)
    (ohif / "extensions").mkdir()
    (ohif / "modes").mkdir()
    (ohif / "package.json").write_text(json.dumps({"packageManager": "pnpm@10.0.0"}))
    cfg = ohif / "platform" / "app" / "pluginConfig.json"
    cfg.write_text(json.dumps({"extensions": [{"packageName": "@ohif/extension-default", "default": True}], "modes": []}))
    out, log = _run({"OHIF_DIR": str(ohif)}, tmp_path)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith(f"{ohif}/platform/app/dist")
    for d in ("extensions/radiarch-rt-dose-core", "extensions/radiarch-ohif-extension-radiarch", "modes/radiarch-plan-review"):
        assert (ohif / d / "package.json").is_file()
    got = json.loads(cfg.read_text())
    assert {e["packageName"] for e in got["extensions"]} >= {"@radiarch/ohif-extension-rt-dose", "@radiarch/ohif-extension-radiarch"}
    assert {m["packageName"] for m in got["modes"]} == {"@radiarch/mode-plan-review"}
    calls = log.read_text().splitlines()
    assert any("install" in c for c in calls) and any(c.endswith("run build") for c in calls)
    assert not (tmp_path / "Viewers" / ".git").exists()                       # not cloned


def test_a_directory_that_is_not_a_checkout_is_refused(tmp_path):
    out, _ = _run({"OHIF_DIR": str(tmp_path)}, tmp_path)
    assert out.returncode == 2 and "not an OHIF checkout" in out.stderr
    out, _ = _run({"OHIF_DIR": str(tmp_path / "missing")}, tmp_path)
    assert out.returncode == 2 and "no such directory" in out.stderr
