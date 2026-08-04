#!/usr/bin/env python3
"""Run the TrackRAD2025 data-integrity gate (Charter §5, Phase 1) on real data.

Sweeps every patient under a root, checks ingestion integrity per case, asserts
patient-level uniqueness (§2.4), prints a per-center scorecard, and writes a
reproducible logged report to ``runs/`` (§6 — every run logs config + git SHA +
a stable checksum). It reports honestly: failures are shown, never repaired.

Usage:
    python scripts/trackrad_integrity.py
    python scripts/trackrad_integrity.py --root /path/to/labeled_training_data
"""

from __future__ import annotations

import argparse
import hashlib
import time
from collections import defaultdict
from pathlib import Path

from radiarch import repro
from radiarch.adapters import trackrad_integrity as ti

_DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent
    / "data" / "trackrad" / "trackrad2025_labeled_training_data"
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=str(_DEFAULT_ROOT), help="dir of patient folders")
    p.add_argument("--runs-dir", default="runs")
    args = p.parse_args(argv)

    root = Path(args.root)
    t0 = time.time()
    results = ti.sweep(root)
    sweep_runtime_s = time.time() - t0
    if not results:
        print(f"No patients found under {root}. Fetch some with scripts/fetch_trackrad.py.")
        return 1

    # Charter §2.4 — assert, don't comment. Raises on any duplicate patient id.
    ti.assert_patient_level_unique(results)

    # --- per-case table ----------------------------------------------------
    print(f"\nTrackRAD integrity sweep — {len(results)} patients under {root}\n")
    hdr = f"{'patient':8s} {'ok':3s} {'B(T)':5s} {'frames':16s} {'Hz':5s} {'region':9s} {'mask':18s}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        shape = f"{r.n_frames}x{r.height}x{r.width}"
        mask = (f"{r.mask_frames_labeled}f {r.mask_px_min}-{r.mask_px_max}px"
                if r.labeled else "unlabeled")
        flag = "OK " if r.ok else "FAIL"
        print(f"{r.patient_id:8s} {flag:3s} {str(r.field_strength_t):5s} {shape:16s} "
              f"{str(r.frame_rate_hz):5s} {str(r.scanned_region):9s} {mask:18s}")
        for f in r.failures:
            print(f"         ↳ {f}")

    # --- per-center summary ------------------------------------------------
    by_center: dict[str, list[ti.CaseIntegrity]] = defaultdict(list)
    for r in results:
        by_center[r.center].append(r)
    print("\nPer-center summary:")
    for c in sorted(by_center):
        rs = by_center[c]
        npass = sum(1 for r in rs if r.ok)
        bs = sorted({r.field_strength_t for r in rs})
        regions = sorted({r.scanned_region for r in rs if r.scanned_region})
        print(f"  center {c}: {npass}/{len(rs)} pass | field={bs} | regions={regions}")

    n_pass = sum(1 for r in results if r.ok)
    n_labeled = sum(1 for r in results if r.labeled)
    gate = n_pass == len(results)
    print(f"\nGATE (all cases integrity-clean): {'PASS' if gate else 'FAIL'} "
          f"— {n_pass}/{len(results)} pass, {n_labeled} labeled")

    # --- reproducible logged report (§6) -----------------------------------
    # A stable checksum over the whole sweep: hash of sorted per-case checksums.
    sweep_ck = hashlib.sha256(
        "".join(f"{r.patient_id}:{r.checksum}" for r in sorted(results, key=lambda x: x.patient_id))
        .encode()
    ).hexdigest()
    rec = repro.new_run(
        "trackrad_integrity",
        config={"root": str(root), "n_patients": len(results)},
        dataset_version="TrackRAD2025-labeled (smoke-test asset; NO dose — Charter §3)",
        split="labeled_training_sample",
    )
    rec.checksum = sweep_ck
    rec.runtime_s = sweep_runtime_s
    rec.metrics = {
        "n_patients": len(results),
        "n_pass": n_pass,
        "n_labeled": n_labeled,
        "gate_pass": gate,
        "centers": {c: sum(1 for r in rs if r.ok) for c, rs in by_center.items()},
        "failures": {r.patient_id: r.failures for r in results if r.failures},
    }
    path = rec.write(args.runs_dir)
    print(f"\nsweep_checksum={sweep_ck}\nlogged -> {path}")
    print("Reminder (Charter §3): TrackRAD is an ingestion smoke-test asset — "
          "these checks say NOTHING about dose.")
    return 0 if gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
