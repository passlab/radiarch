"""TrackRAD Phase-1 integrity gate — proves it PASSES clean data and CATCHES bad.

Charter §5 Phase 1 / §2.4. Runs on synthetic stand-ins (no download needed); the
real-data sweep is exercised by `scripts/trackrad_integrity.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from radiarch.adapters import trackrad_integrity as ti

sitk = pytest.importorskip("SimpleITK")

# Reuse the format-faithful stand-in writer from the loader test.
from test_trackrad_loader import _write_standin_patient  # noqa: E402


def test_clean_case_passes_every_check(tmp_path: Path):
    pdir = _write_standin_patient(tmp_path, "A_001")
    r = ti.check_case(pdir)
    assert r.ok is True and not r.failures
    assert r.center == "A" and r.field_strength_t == 0.35
    assert r.n_frames == 8 and (r.height, r.width) == (64, 64)
    assert r.mask_frames_labeled == 8            # tumour in every frame
    assert all(r.checks.values())


def test_gate_catches_nonfinite_frames(tmp_path: Path):
    """A NaN in the cine must fail the finite check (Charter §5: 'no NaN/Inf')."""
    pdir = _write_standin_patient(tmp_path, "A_002")
    # Corrupt the frames on disk with a NaN (write float with a NaN).
    p = pdir / "images" / "A_002_frames.mha"
    arr = sitk.GetArrayFromImage(sitk.ReadImage(str(p))).astype(np.float32)
    arr[0, 0, 0] = np.nan
    bad = sitk.GetImageFromArray(arr)
    bad.SetSpacing((5.0, 1.0, 1.0))
    sitk.WriteImage(bad, str(p))
    r = ti.check_case(pdir)
    assert r.ok is False
    assert r.checks["frames_finite"] is False
    assert any("NaN" in f for f in r.failures)


def test_gate_catches_mask_frame_mismatch(tmp_path: Path):
    """A mask whose HxW disagrees with the frames must fail."""
    pdir = _write_standin_patient(tmp_path, "A_003")
    # Overwrite the mask with a wrong in-plane size.
    wrong = np.zeros((32, 32, 8), dtype=np.uint8)   # (H,W,T) 32x32 vs frames 64x64
    m = sitk.GetImageFromArray(wrong)
    m.SetSpacing((5.0, 1.0, 1.0))
    sitk.WriteImage(m, str(pdir / "targets" / "A_003_labels.mha"))
    r = ti.check_case(pdir)
    assert r.ok is False and r.checks["mask_hw_matches_frames"] is False


def test_patient_level_uniqueness_is_asserted(tmp_path: Path):
    a = ti.check_case(_write_standin_patient(tmp_path / "s1", "A_001"))
    b = ti.check_case(_write_standin_patient(tmp_path / "s2", "A_001"))  # dup id
    with pytest.raises(ValueError, match="uniqueness"):
        ti.assert_patient_level_unique([a, b])


def test_sweep_is_deterministic_and_patient_level(tmp_path: Path):
    for pid in ("C_004", "A_001", "B_002"):
        _write_standin_patient(tmp_path, pid)
    r1 = ti.sweep(tmp_path)
    r2 = ti.sweep(tmp_path)
    assert [x.patient_id for x in r1] == ["A_001", "B_002", "C_004"]   # sorted
    assert [x.checksum for x in r1] == [x.checksum for x in r2]        # stable
    ti.assert_patient_level_unique(r1)                                 # no dupes
