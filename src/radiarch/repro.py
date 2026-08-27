"""Phase 0 — reproducibility floor: determinism + one-command run logging.

Charter §5 (Phase 0) and §6 ("every run must log config, git SHA, seed, dataset
version/split, per-case metrics, wall-clock runtime"). This module is the spine
every experiment run goes through, so results are reproducible and auditable and
no unlogged number can reach the paper.

It also provides a reproducibility SELF-TEST that computes a deterministic
checksum from a fixed seed. That checksum is *infrastructure verification*, not a
scientific result — it never touches real data or any evaluation path (Charter
§2.6: "it ran" ≠ "it is correct").

Gate (Charter §5, Phase 0): ``python -m radiarch.repro selftest`` twice → the
same checksum.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

DEFAULT_SEED = 1234

# Packages whose exact versions affect numerical output — logged with every run
# so a result can be tied to the environment that produced it (Charter §2.1).
_TRACKED_PACKAGES = ("numpy", "scipy", "SimpleITK", "pydicom", "pandas", "torch")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def set_determinism(seed: int = DEFAULT_SEED) -> int:
    """Seed every RNG that can affect a run. Returns the seed for logging.

    Covers Python ``random``, NumPy's global RNG, ``PYTHONHASHSEED``, and (if
    installed) PyTorch incl. CUDA + deterministic algorithms. Torch is optional
    — absence is not an error.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    try:  # torch is optional; only seed it if present
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:  # noqa: BLE001 — torch missing / no CUDA is fine
        pass
    return seed


# ---------------------------------------------------------------------------
# Environment capture
# ---------------------------------------------------------------------------
def git_sha(short: bool = False) -> str:
    """Current commit SHA, or ``"unknown"`` outside a git checkout."""
    try:
        args = ["git", "rev-parse"] + (["--short"] if short else []) + ["HEAD"]
        return subprocess.check_output(
            args, cwd=Path(__file__).resolve().parent, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def git_dirty() -> bool:
    """True if the working tree has uncommitted changes (result provenance)."""
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=Path(__file__).resolve().parent, stderr=subprocess.DEVNULL,
        ).decode().strip()
        return bool(out)
    except Exception:  # noqa: BLE001
        return False


def package_versions() -> dict:
    """Exact installed versions of the numerically-relevant packages."""
    from importlib import metadata

    out: dict[str, str] = {}
    for name in _TRACKED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not-installed"
    return out


# ---------------------------------------------------------------------------
# Run record — the logging spine (Charter §6)
# ---------------------------------------------------------------------------
@dataclass
class RunRecord:
    """One row of the run log. ``checksum`` is the reproducible 'number'; the
    metadata fields (timestamps, runtime) are provenance and are NOT part of the
    reproducibility gate."""

    kind: str                       # e.g. "reproducibility_selftest", "eval"
    seed: int
    git_sha: str
    git_dirty: bool
    python_version: str
    packages: dict
    config: dict = field(default_factory=dict)
    dataset_version: Optional[str] = None      # None until real data lands
    split: Optional[str] = None
    checksum: Optional[str] = None              # the reproducible result
    metrics: dict = field(default_factory=dict)  # per-case / summary metrics
    started_at_unix: float = 0.0
    runtime_s: float = 0.0

    def write(self, runs_dir: Path | str = "runs") -> Path:
        runs_dir = Path(runs_dir)
        runs_dir.mkdir(parents=True, exist_ok=True)
        # Filename is provenance (timestamp+sha); content carries the checksum.
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(self.started_at_unix or time.time()))
        path = runs_dir / f"{stamp}_{self.git_sha[:8]}_{self.kind}.json"
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True))
        return path


def new_run(kind: str, *, seed: int = DEFAULT_SEED, config: Optional[dict] = None,
            dataset_version: Optional[str] = None, split: Optional[str] = None) -> RunRecord:
    """Start a run: seed determinism and capture the environment."""
    set_determinism(seed)
    return RunRecord(
        kind=kind, seed=seed, git_sha=git_sha(), git_dirty=git_dirty(),
        python_version=platform.python_version(), packages=package_versions(),
        config=config or {}, dataset_version=dataset_version, split=split,
        started_at_unix=time.time(),
    )


# ---------------------------------------------------------------------------
# Reproducibility self-test (infrastructure check, NOT a result)
# ---------------------------------------------------------------------------
def reproducibility_checksum(seed: int = DEFAULT_SEED) -> str:
    """Deterministic checksum over seeded Python + NumPy RNG draws.

    Verifies that :func:`set_determinism` actually pins both RNGs. This is an
    infrastructure self-test — it uses no real data and produces no metric.
    """
    set_determinism(seed)
    py = [random.random() for _ in range(256)]
    npg = np.random.random(256)
    blob = np.asarray(py, dtype=np.float64).tobytes() + npg.astype(np.float64).tobytes()
    return hashlib.sha256(blob).hexdigest()


def run_selftest(seed: int = DEFAULT_SEED, runs_dir: Path | str = "runs") -> tuple[str, Path]:
    """Run the self-test, log it, return (checksum, log_path)."""
    rec = new_run("reproducibility_selftest", seed=seed)
    t0 = time.time()
    checksum = reproducibility_checksum(seed)
    rec.checksum = checksum
    rec.runtime_s = time.time() - t0
    path = rec.write(runs_dir)
    return checksum, path


# ---------------------------------------------------------------------------
# CLI — "one command to reproduce any run" (Charter §5, Phase 0)
# ---------------------------------------------------------------------------
def _main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="radiarch.repro", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("selftest", help="run the reproducibility self-test")
    s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s.add_argument("--runs-dir", default="runs")
    args = p.parse_args(argv)

    if args.cmd == "selftest":
        checksum, path = run_selftest(args.seed, args.runs_dir)
        print(f"seed={args.seed}  git={git_sha(short=True)}  dirty={git_dirty()}")
        print(f"reproducibility_checksum={checksum}")
        print(f"logged -> {path}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(_main())
