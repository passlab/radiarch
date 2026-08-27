"""Phase 0 gate tests — reproducibility floor (Charter §5).

Gate: the same seeded computation yields the same checksum across independent
calls, and every run captures its provenance (git SHA, seed, package versions).
These run on no challenge data — they verify the harness itself.
"""

from __future__ import annotations

import json

import numpy as np

from radiarch import repro


def test_checksum_is_stable_across_calls():
    """Same seed -> identical checksum (the Phase 0 'same command twice' gate)."""
    a = repro.reproducibility_checksum(1234)
    b = repro.reproducibility_checksum(1234)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_checksum_changes_with_seed():
    """Determinism is real, not a constant: a different seed -> different draw."""
    assert repro.reproducibility_checksum(1234) != repro.reproducibility_checksum(9999)


def test_set_determinism_pins_both_rngs():
    import random as _random

    repro.set_determinism(7)
    py1, np1 = _random.random(), np.random.random()
    repro.set_determinism(7)
    py2, np2 = _random.random(), np.random.random()
    assert py1 == py2 and np1 == np2


def test_new_run_captures_provenance():
    rec = repro.new_run("unit_test", seed=42, config={"k": "v"})
    assert rec.seed == 42
    assert rec.git_sha and rec.git_sha != ""      # captured (SHA or "unknown")
    assert "numpy" in rec.packages
    assert rec.config == {"k": "v"}
    # Data-dependent fields stay None until real data lands (Charter §2.1).
    assert rec.dataset_version is None and rec.split is None


def test_run_selftest_writes_a_log(tmp_path):
    checksum, path = repro.run_selftest(1234, runs_dir=tmp_path)
    assert path.exists()
    logged = json.loads(path.read_text())
    assert logged["checksum"] == checksum
    assert logged["kind"] == "reproducibility_selftest"
    assert logged["seed"] == 1234
    assert "numpy" in logged["packages"]
    assert logged["runtime_s"] >= 0.0
