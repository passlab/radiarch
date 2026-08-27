"""TrackRAD2025 adapter — input-path loading + determinism + placeholder guard.

Charter §3 / §2.2 / §2.4. TrackRAD is a smoke-test asset only. These tests verify
the *loader* and its *guard*, never dose values:

  * loading real-format ``.mha`` + JSON sidecars into a typed case,
  * deterministic case checksum (Phase 0 gate applied to data loading),
  * patient-level enumeration,
  * the quarantine barrier that stops fabricated density/beams from silently
    reaching an evaluation path.

Most tests run on a *format-faithful synthetic stand-in* written to ``tmp_path``,
so the suite needs no 269 GB download. One test activates automatically against a
real download if ``RADIARCH_TRACKRAD_DIR`` (or the default data dir) is present.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from radiarch.adapters import trackrad

sitk = pytest.importorskip("SimpleITK", reason="SimpleITK required to read .mha cine")


# ---------------------------------------------------------------------------
# Format-faithful stand-in (mirrors the TrackRAD2025 on-disk layout)
# ---------------------------------------------------------------------------
def _write_standin_patient(root: Path, patient_id: str = "A_001", seed: int = 0) -> Path:
    """Write one patient dir matching the REAL TrackRAD layout (verified on A_001/
    C_001): time is the LAST axis on disk, and the sidecar carries a ``b-`` prefix.
    Content is synthetic."""
    pdir = root / patient_id
    (pdir / "images").mkdir(parents=True)
    (pdir / "targets").mkdir(parents=True)

    H, W, T = 64, 64, 8                             # on disk numpy is (H, W, T) — time last
    rng = np.random.default_rng(seed)
    frames = (rng.random((H, W, T)) * 400).astype(np.uint16)  # MR-like intensities
    img = sitk.GetImageFromArray(frames)            # -> ITK size (T, W, H)
    img.SetSpacing((5.0, 1.0, 1.0))                 # (thickness_on_time_axis, in-plane, in-plane)
    sitk.WriteImage(img, str(pdir / "images" / f"{patient_id}_frames.mha"))

    mask = np.zeros((H, W, T), dtype=np.uint8)
    mask[24:40, 24:40, :] = 1                       # a tumour present in every frame
    m = sitk.GetImageFromArray(mask)
    m.CopyInformation(img)
    sitk.WriteImage(m, str(pdir / "targets" / f"{patient_id}_labels.mha"))

    (pdir / "b-field-strength.json").write_text(json.dumps(0.35))   # real prefix
    (pdir / "frame-rate.json").write_text(json.dumps(8.0))
    (pdir / "scanned-region.json").write_text(json.dumps("abdomen"))
    return pdir


@pytest.fixture()
def standin_patient(tmp_path: Path) -> Path:
    return _write_standin_patient(tmp_path)


# ---------------------------------------------------------------------------
# Loading + integrity
# ---------------------------------------------------------------------------
def test_load_case_reads_real_fields(standin_patient: Path):
    case = trackrad.load_case(standin_patient)
    assert case.patient_id == "A_001"
    assert case.frames.ndim == 3                 # canonicalised to (T, H, W)
    assert case.frames.shape == (8, 64, 64)      # time moved to the front
    assert case.mask is not None and case.mask.shape == (8, 64, 64)
    assert case.labeled is True
    assert case.in_plane_spacing_mm == (1.0, 1.0)
    assert case.frame_thickness_mm == 5.0
    assert case.field_strength_t == 0.35         # parsed despite the b- prefix
    assert case.frame_rate_hz == 8.0
    assert case.scanned_region == "abdomen"
    trackrad.assert_case_integrity(case)         # no NaN/Inf, shapes agree


def test_load_case_missing_cine_raises(tmp_path: Path):
    (tmp_path / "X_000" / "images").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        trackrad.load_case(tmp_path / "X_000")


def test_unlabeled_patient_has_no_mask(tmp_path: Path):
    pdir = _write_standin_patient(tmp_path, "F_002")
    # Remove the mask to simulate an unlabeled patient.
    for m in (pdir / "targets").glob("*.mha"):
        m.unlink()
    case = trackrad.load_case(pdir)
    assert case.mask is None and case.labeled is False
    trackrad.assert_case_integrity(case)         # still a valid input


# ---------------------------------------------------------------------------
# Determinism — Phase 0 gate on data loading
# ---------------------------------------------------------------------------
def test_case_checksum_is_stable_across_loads(standin_patient: Path):
    a = trackrad.case_checksum(trackrad.load_case(standin_patient))
    b = trackrad.case_checksum(trackrad.load_case(standin_patient))
    assert a == b and len(a) == 64               # same case twice -> same number


def test_case_checksum_changes_with_content(tmp_path: Path):
    p1 = _write_standin_patient(tmp_path / "a", "A_001", seed=0)
    p2 = _write_standin_patient(tmp_path / "b", "A_001", seed=1)
    assert trackrad.case_checksum(trackrad.load_case(p1)) != trackrad.case_checksum(
        trackrad.load_case(p2)
    )


def test_list_patient_dirs_is_sorted_and_patient_level(tmp_path: Path):
    for pid in ("C_001", "A_001", "B_002"):
        _write_standin_patient(tmp_path, pid)
    (tmp_path / "not_a_patient").mkdir()         # no images/ -> excluded
    dirs = trackrad.list_patient_dirs(tmp_path)
    assert [d.name for d in dirs] == ["A_001", "B_002", "C_001"]


# ---------------------------------------------------------------------------
# Placeholder quarantine (Charter §2.2)
# ---------------------------------------------------------------------------
def test_smoke_bundles_refuse_without_acknowledgement(standin_patient: Path):
    case = trackrad.load_case(standin_patient)
    with pytest.raises(RuntimeError, match="dose"):
        trackrad.to_smoke_test_bundles(case, acknowledge_synthetic=False)


def test_smoke_bundles_are_marked_as_placeholder(standin_patient: Path):
    case = trackrad.load_case(standin_patient)
    geom, bm, weights = trackrad.to_smoke_test_bundles(case, acknowledge_synthetic=True)
    assert trackrad.is_placeholder_geometry(geom.result.geometry_id)
    assert geom.ct_hu is None and geom.ct_image is None   # no CT -> MCsquare will reject
    assert bm.result.fluence_elements.total_count == 1
    assert weights.shape == (1,)


def test_analytic_engine_accepts_smoke_input_shape_only(standin_patient: Path):
    """Input-path smoke test: the analytic engine consumes a TrackRAD frame and
    emits a dose array of the right rank/shape. Asserts NOTHING about values —
    the density/beams are fabricated and no dose here is meaningful (Charter §2.6)."""
    from radiarch.services.dose_engines.analytic import AnalyticEngine

    case = trackrad.load_case(standin_patient)
    geom, bm, weights = trackrad.to_smoke_test_bundles(case, acknowledge_synthetic=True)
    engine = AnalyticEngine()
    assert not engine.validate(geom, bm, params={})       # no issues
    dose = engine.compute_dose(geom, bm, weights, params={}).dose
    assert dose.shape == geom.density.shape and dose.dtype == np.float32


# ---------------------------------------------------------------------------
# Real-data gate — auto-activates when a download is present
# ---------------------------------------------------------------------------
def _real_trackrad_root() -> Path | None:
    env = os.environ.get("RADIARCH_TRACKRAD_DIR")
    candidates = [Path(env)] if env else []
    candidates.append(
        Path(__file__).resolve().parent.parent
        / "data" / "trackrad" / "trackrad2025_labeled_training_data"
    )
    for c in candidates:
        if c.is_dir() and trackrad.list_patient_dirs(c):
            return c
    return None


@pytest.mark.skipif(
    _real_trackrad_root() is None,
    reason=(
        "No TrackRAD download on disk. Fetch a small slice with "
        "`python scripts/fetch_trackrad.py`, or set RADIARCH_TRACKRAD_DIR."
    ),
)
def test_real_trackrad_case_loads_and_is_deterministic():
    root = _real_trackrad_root()
    assert root is not None
    first = trackrad.list_patient_dirs(root)[0]
    case = trackrad.load_case(first)
    trackrad.assert_case_integrity(case)
    assert trackrad.case_checksum(case) == trackrad.case_checksum(trackrad.load_case(first))
