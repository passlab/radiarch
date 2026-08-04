#!/usr/bin/env python3
"""Fetch a small, deterministic slice of TrackRAD2025 for the input-path smoke test.

Charter §3: TrackRAD2025 is an input/loading SMOKE-TEST asset only — it has no
dose and no beam parameters and cannot validate dose. This script pulls just a
few *labeled* patients (a few hundred MB) so the loader determinism gate and the
input-path probe can run against real MRI-linac data, without downloading the
full 269 GB release.

Source dataset (CC-BY-NC, non-commercial):
    https://huggingface.co/datasets/LMUK-RADONC-PHYS-RES/TrackRAD2025

Usage:
    python scripts/fetch_trackrad.py                 # 3 labeled patients -> data/trackrad
    python scripts/fetch_trackrad.py --num 2         # fewer patients
    python scripts/fetch_trackrad.py --dest /path    # custom destination
    python scripts/fetch_trackrad.py --labeled-all   # whole labeled training set (multi-GB)

The destination lives under a gitignored ``data/`` dir by default, so the
non-commercial dataset never gets committed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ID = "LMUK-RADONC-PHYS-RES/TrackRAD2025"
LABELED_SUBDIR = "trackrad2025_labeled_training_data"
# Labeled training patients are the small, mask-bearing cohort. The card lists
# centers A (0.35 T) and B/C (1.5 T). We pick a deterministic, sorted prefix so
# two people running this get the *same* patients — a Phase 0 requirement.
_CANDIDATE_PATIENTS = ["A_001", "A_002", "A_003", "B_001", "B_002", "C_001"]


def _require_hf_hub():
    try:
        from huggingface_hub import snapshot_download  # noqa: F401
    except ModuleNotFoundError:
        sys.exit(
            "huggingface_hub is not installed.\n"
            "  Install it into this environment first:\n"
            "      pip install 'huggingface_hub>=0.24'\n"
            "  (kept out of pyproject on purpose: TrackRAD is an optional smoke-test\n"
            "   asset, not a runtime dependency of the pipeline.)"
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dest", default="data/trackrad", help="download destination (gitignored)")
    p.add_argument("--num", type=int, default=3, help="number of labeled patients (default 3)")
    p.add_argument(
        "--labeled-all",
        action="store_true",
        help="download the ENTIRE labeled training set (multi-GB), overrides --num",
    )
    args = p.parse_args(argv)

    _require_hf_hub()
    from huggingface_hub import snapshot_download

    dest = Path(args.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    if args.labeled_all:
        patterns = [f"{LABELED_SUBDIR}/*"]
        print(f"Fetching the FULL labeled training set into {dest} (this is multi-GB)…")
    else:
        n = max(1, min(args.num, len(_CANDIDATE_PATIENTS)))
        chosen = _CANDIDATE_PATIENTS[:n]
        # Scope the download to just those patients' folders. If a candidate id
        # isn't present in the release, its pattern simply matches nothing.
        patterns = [f"{LABELED_SUBDIR}/{pid}/*" for pid in chosen]
        print(f"Fetching {n} labeled TrackRAD patient(s) {chosen} into {dest} …")

    snapshot_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        local_dir=str(dest),
        allow_patterns=patterns,
    )

    labeled_root = dest / LABELED_SUBDIR
    got = sorted(d.name for d in labeled_root.iterdir() if d.is_dir()) if labeled_root.is_dir() else []
    print(f"\nDone. Patients on disk under {labeled_root}: {got or '(none — check patterns/access)'}")
    print(
        "\nNext:\n"
        f"  - Point the loader/tests at: {labeled_root}\n"
        "  - Run the input-path probe on real data:  python probe_trackrad_input.py\n"
        "  - Reminder (Charter §3): smoke-test asset ONLY — never a dose benchmark."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
