"""Which radiarch made an output: the release and the commit.

Every DICOM object radiarch writes states both in Software Versions (General Equipment), e.g. ``["0.2.0", "git
d4190d2"]``, and an export's attribution carries the commit, so an output traces to its code and a defect found later
can be withdrawn by version.
- Release: the package version, raised with every change that changes output: the patch number for a fix, the
  minor number for a feature.
- Commit: ``RADIARCH_BUILD_COMMIT`` when set (a container image, built without its git history), else the git
  checkout the code runs from, with ``-dirty`` when tracked files have uncommitted changes. It is absent when neither
  is known.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def release() -> str:
    try:
        from importlib.metadata import version
        return version("radiarch")
    except Exception:  # pragma: no cover - not installed
        return "0.0.0+unknown"


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@lru_cache(maxsize=1)
def commit() -> Optional[str]:
    built = os.environ.get("RADIARCH_BUILD_COMMIT", "").strip()
    if built:
        return built
    sha = _git("rev-parse", "--short=7", "HEAD")
    if not sha:
        return None
    dirty = _git("status", "--porcelain", "--untracked-files=no")
    return f"{sha}-dirty" if dirty else sha


def software_versions() -> List[str]:
    """The values of Software Versions (0018,1020): the release, then ``git <commit>`` when the commit is known."""
    c = commit()
    return [release()] + ([f"git {c}"] if c else [])


def describe() -> str:
    """One line for logs and labels: ``radiarch 0.2.0 (git d4190d2)``."""
    c = commit()
    return f"radiarch {release()}" + (f" (git {c})" if c else "")


__all__ = ["release", "commit", "software_versions", "describe"]
