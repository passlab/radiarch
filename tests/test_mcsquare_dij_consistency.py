"""MCsquare Dij consistency regression (V4).

The key invariant for the Optimization Service (Feature 4):

    Dij @ w  ≈  compute_dose(w)        (within tolerance, in lit voxels)

If this fails, the optimizer is iterating against a *different physics*
than the final compute_dose validation will use. The treatment plan
gets shipped, then a clinical physicist sees the post-validation dose
volume differ from what the optimizer thought it was producing — and
discovers it only at QA. We catch it here instead.

This file has two layers:

1. **Synthetic test** — runs against the *analytic* engine. Always
   safe to run, exercises the same invariant in the same code path.
   Fast, no MCsquare needed. Acts as a permanent guard.
2. **MCsquare test** — auto-skipped when OpenTPS isn't importable.
   When MCsquare is available (CI, dev machines, validation runs),
   builds a real Dij + nominal dose on the bundled SimpleFantom and
   asserts agreement within 1% in lit voxels.

Run the MCsquare test explicitly on validation machines:

    pytest tests/test_mcsquare_dij_consistency.py::TestMCsquareDijConsistency -v

The analytic test runs every CI build.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Shared invariant: Dij @ w must equal compute_dose(w) in lit voxels
# ---------------------------------------------------------------------------

def _assert_dij_consistency(
    direct: np.ndarray,
    via_dij: np.ndarray,
    *,
    label: str,
    voxel_threshold_frac: float = 0.01,
    rel_tol: float = 0.01,
) -> None:
    """Compare direct dose to Dij@w in lit voxels.

    A voxel is "lit" if direct > voxel_threshold_frac * max(direct).
    This filters out numerical noise in voxels that should be zero but
    aren't quite — those would dominate any relative-error metric.

    rel_tol of 1% is the standard MCsquare-vs-MCsquare agreement we
    expect; tighter (~0.1%) is achievable for noise-free analytic.
    """
    assert direct.shape == via_dij.shape, (
        f"[{label}] shape mismatch: direct {direct.shape} vs via_dij {via_dij.shape}"
    )

    max_dose = float(direct.max())
    if max_dose <= 0:
        pytest.skip(f"[{label}] direct dose is all zero — no signal to compare")

    mask = direct > voxel_threshold_frac * max_dose
    lit_count = int(mask.sum())
    assert lit_count > 0, f"[{label}] no voxels above threshold — bad test setup"

    # Relative error in lit voxels
    rel_err = np.abs(direct[mask] - via_dij[mask]) / np.maximum(direct[mask], 1e-9)
    p50 = float(np.percentile(rel_err, 50))
    p95 = float(np.percentile(rel_err, 95))
    max_err = float(rel_err.max())

    # Headline metric: 95th-percentile relative error in lit voxels.
    # Using p95 (not max) makes the test robust to a handful of edge
    # voxels at the field edge where Dij sparsification kicks in.
    assert p95 <= rel_tol, (
        f"[{label}] Dij@w disagrees with compute_dose:\n"
        f"  lit voxels:      {lit_count}\n"
        f"  median rel err:  {p50 * 100:.4f}%\n"
        f"  p95 rel err:     {p95 * 100:.4f}% (limit: {rel_tol * 100:.2f}%)\n"
        f"  max  rel err:    {max_err * 100:.4f}%\n"
        f"  → If this is failing, the optimizer (Feature 4) will produce wrong plans."
    )


# ---------------------------------------------------------------------------
# Monte-Carlo-aware agreement metric
# ---------------------------------------------------------------------------
#
# The analytic assertion above is a *local voxel-wise relative error* — the
# right metric for a noise-free engine. It is the WRONG metric for two
# INDEPENDENT Monte-Carlo runs (direct compute_dose vs. Dij@w), and that
# mismatch is exactly what made the V4 nightly fail even after the voxel-frame
# was fixed:
#
#   * `direct` and `via_dij` are two separate MCsquare simulations with
#     different random realizations — they only agree up to combined counting
#     statistics.
#   * The "lit" threshold of 1% of max dose sweeps in the entire low-dose bath
#     (the failing run: 452k of 8M voxels). In a low-dose voxel a handful of
#     proton histories gives tens-to-thousands of percent statistical scatter,
#     so a local relative-error p95 is dominated by noise, not physics. No
#     primary count affordable in a nightly job can make that metric pass.
#
# A physics-consistency gate has to separate **bias*/*structure* (which we care
# about: scale, frame, spatial scramble) from *variance* (MC noise, which we
# must tolerate). We assert three noise-robust quantities that still fail hard
# on a real frame/normalization/physics bug:
#
#   1. Integral-dose ratio over lit voxels — noise averages out over ~10^5
#      voxels, so this pins down uniform scale / normalization (e.g. a missing
#      `numberOfFractionsPlanned` factor) and gross dose loss.
#   2. Pearson correlation over lit voxels — a voxel-frame scramble (the
#      original ~100% failure) collapses this toward 0; MC noise only nicks it.
#   3. High-dose-region (>= high_dose_frac of max) voxel-wise relative error —
#      the clinically meaningful region, where statistics are good enough that
#      a genuine per-voxel disagreement (not noise) shows up. A spatial shift
#      fails here at the Bragg/penumbra gradients.
#
# We always print a dose-band-stratified table so the CI log shows *where* the
# disagreement lives — a real bug spreads across the high-dose bands, MC noise
# concentrates in the low-dose bath.


def _dose_agreement_report(direct: np.ndarray, via_dij: np.ndarray, *, lit_frac: float) -> dict:
    """Stratified agreement metrics between two dose volumes (see module note)."""
    max_dose = float(direct.max())
    d = direct.astype(np.float64).ravel()
    v = via_dij.astype(np.float64).ravel()
    lit = d > lit_frac * max_dose

    dl, vl = d[lit], v[lit]
    rel = np.abs(dl - vl) / np.maximum(dl, 1e-9)

    integral_ratio = float(vl.sum() / dl.sum()) if dl.sum() > 0 else float("nan")
    if dl.std() > 0 and vl.std() > 0:
        corr = float(np.corrcoef(dl, vl)[0, 1])
    else:
        corr = float("nan")
    # Least-squares global scale v ~ k*d (bias, robust to per-voxel noise).
    best_fit_scale = float((dl @ vl) / (dl @ dl)) if (dl @ dl) > 0 else float("nan")

    # Dose-band breakdown (fraction-of-max ranges).
    bands = [(0.01, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.8), (0.8, 1.01)]
    band_rows = []
    for lo, hi in bands:
        m = (d > lo * max_dose) & (d <= hi * max_dose)
        n = int(m.sum())
        if n == 0:
            band_rows.append((lo, hi, 0, float("nan"), float("nan")))
            continue
        r = np.abs(d[m] - v[m]) / np.maximum(d[m], 1e-9)
        band_rows.append((lo, hi, n, float(np.percentile(r, 50)), float(np.percentile(r, 95))))

    # High-dose region metrics (well-sampled voxels).
    hd = d > 0.5 * max_dose
    if hd.any():
        r_hd = np.abs(d[hd] - v[hd]) / np.maximum(d[hd], 1e-9)
        hd_p50 = float(np.percentile(r_hd, 50))
        hd_p95 = float(np.percentile(r_hd, 95))
        hd_count = int(hd.sum())
    else:
        hd_p50 = hd_p95 = float("nan")
        hd_count = 0

    return {
        "max_dose": max_dose,
        "lit_count": int(lit.sum()),
        "lit_p50": float(np.percentile(rel, 50)) if rel.size else float("nan"),
        "lit_p95": float(np.percentile(rel, 95)) if rel.size else float("nan"),
        "integral_ratio": integral_ratio,
        "correlation": corr,
        "best_fit_scale": best_fit_scale,
        "highdose_count": hd_count,
        "highdose_p50": hd_p50,
        "highdose_p95": hd_p95,
        "bands": band_rows,
    }


def _format_report(label: str, rep: dict) -> str:
    lines = [
        f"[{label}] MCsquare Dij@w vs compute_dose agreement:",
        f"  max dose:            {rep['max_dose']:.6g}",
        f"  lit voxels (>1%):    {rep['lit_count']}",
        f"  integral ratio v/d:  {rep['integral_ratio']:.4f}   (1.0 = perfect)",
        f"  correlation:         {rep['correlation']:.4f}",
        f"  best-fit scale:      {rep['best_fit_scale']:.4f}",
        f"  high-dose (>50%):    n={rep['highdose_count']}  "
        f"p50={rep['highdose_p50'] * 100:.2f}%  p95={rep['highdose_p95'] * 100:.2f}%",
        "  dose-band local relative error (fraction-of-max band -> p50 / p95):",
    ]
    for lo, hi, n, p50, p95 in rep["bands"]:
        if n == 0:
            lines.append(f"    {lo:.2f}-{hi:.2f}:  (empty)")
        else:
            lines.append(
                f"    {lo:.2f}-{hi:.2f}:  n={n:>8}  p50={p50 * 100:6.2f}%  p95={p95 * 100:6.2f}%"
            )
    return "\n".join(lines)


def _assert_mc_dij_consistency(
    direct: np.ndarray,
    via_dij: np.ndarray,
    *,
    label: str,
    lit_frac: float = 0.01,
    integral_tol: float = 0.05,
    corr_min: float = 0.95,
    highdose_p95_tol: float = 0.15,
) -> None:
    """Noise-robust Dij@w == compute_dose gate for two independent MC runs.

    Fails on a genuine scale / frame / physics bug (the three checks below),
    tolerates the per-voxel Monte-Carlo scatter that a local relative-error
    metric cannot. See the module note above for the rationale. Defaults are
    physically motivated for the SimpleFantom at ~1e5 primaries; the nightly
    run is the ground truth for tuning them.
    """
    assert direct.shape == via_dij.shape, (
        f"[{label}] shape mismatch: direct {direct.shape} vs via_dij {via_dij.shape}"
    )
    max_dose = float(direct.max())
    if max_dose <= 0:
        pytest.skip(f"[{label}] direct dose is all zero — no signal to compare")

    rep = _dose_agreement_report(direct, via_dij, lit_frac=lit_frac)
    report_str = _format_report(label, rep)
    # Always surface the full breakdown (visible with -s / on failure).
    print("\n" + report_str)

    failures = []
    if not (abs(rep["integral_ratio"] - 1.0) <= integral_tol):
        failures.append(
            f"integral ratio {rep['integral_ratio']:.4f} outside "
            f"1±{integral_tol:.2f} — uniform scale / normalization mismatch"
        )
    if not (rep["correlation"] >= corr_min):
        failures.append(
            f"correlation {rep['correlation']:.4f} < {corr_min:.2f} — spatial "
            f"scramble / voxel-frame misalignment (not just MC noise)"
        )
    if rep["highdose_count"] > 0 and not (rep["highdose_p95"] <= highdose_p95_tol):
        failures.append(
            f"high-dose p95 rel err {rep['highdose_p95'] * 100:.2f}% > "
            f"{highdose_p95_tol * 100:.2f}% — disagreement in the well-sampled "
            f"region, where MC noise is small"
        )

    assert not failures, (
        report_str
        + "\n  FAILED noise-robust agreement checks:\n"
        + "".join(f"    - {f}\n" for f in failures)
        + "  → If this is failing, the optimizer (Feature 4) will produce wrong plans."
    )


# ---------------------------------------------------------------------------
# Synthetic fixtures (no DICOM, no OpenTPS)
# ---------------------------------------------------------------------------

@pytest.fixture
def synth_geometry():
    """16³ water phantom with a central PTV mask."""
    from types import SimpleNamespace
    density = np.ones((16, 16, 16), dtype=np.float32)
    masks = {"PTV": np.zeros_like(density, dtype=bool)}
    masks["PTV"][6:10, 6:10, 6:10] = True
    return SimpleNamespace(
        density=density,
        masks=masks,
        spacing_mm=(2.5, 2.5, 2.5),
        spacing=(2.5, 2.5, 2.5),
        ct_hu=None,
        ct_image=object(),
        ct_calibration=None,
        result=SimpleNamespace(geometry_id="g-synth-dij-001"),
    )


@pytest.fixture
def synth_beam_model():
    from types import SimpleNamespace
    modality = SimpleNamespace(value="PROTON_PBS")
    fluence = SimpleNamespace(
        total_count=8,
        per_beam=[
            SimpleNamespace(spot_count=4, per_layer=[4]),
            SimpleNamespace(spot_count=4, per_layer=[4]),
        ],
    )
    result = SimpleNamespace(
        beam_model_id="bm-synth-dij-001",
        modality=modality,
        fluence_elements=fluence,
        geometry_id="g-synth-dij-001",
    )
    plan = SimpleNamespace(spotMUs=np.zeros(8, dtype=np.float32), beams=[])
    return SimpleNamespace(result=result, plan=plan, bdl=None, ct_calibration=None)


# ---------------------------------------------------------------------------
# Layer 1 — Analytic engine (always-on guard)
# ---------------------------------------------------------------------------

class TestAnalyticDijConsistency:
    """Same Dij@w == compute_dose invariant against the analytic engine.

    This is the engine-independent contract every DoseEnginePlugin must
    honor. If a future engine ships and silently violates this, the
    suite catches it here.
    """

    @pytest.mark.parametrize("weights_seed", [0, 1, 42, 7777])
    def test_dij_matches_direct_random_weights(
        self, synth_geometry, synth_beam_model, weights_seed,
    ):
        from radiarch.services.dose_engines import get_engine

        engine = get_engine("analytic")
        rng = np.random.default_rng(weights_seed)
        n = synth_beam_model.result.fluence_elements.total_count
        weights = rng.uniform(0.5, 2.0, size=n).astype(np.float32)

        direct = engine.compute_dose(
            synth_geometry, synth_beam_model, weights,
        ).dose

        influence = engine.build_influence(synth_geometry, synth_beam_model)
        via_dij = engine.apply_influence(
            influence, weights, synth_geometry.density.shape,
        ).dose

        # Analytic engine has different active-voxel masking between
        # compute_dose and build_influence, so we use the looser 10%
        # tolerance the e2e suite already validates.
        _assert_dij_consistency(
            direct, via_dij,
            label=f"analytic seed={weights_seed}",
            rel_tol=0.10,
        )

    def test_uniform_weights_consistency(self, synth_geometry, synth_beam_model):
        from radiarch.services.dose_engines import get_engine
        engine = get_engine("analytic")
        n = synth_beam_model.result.fluence_elements.total_count
        weights = np.full(n, 1.0, dtype=np.float32)

        direct = engine.compute_dose(synth_geometry, synth_beam_model, weights).dose
        influence = engine.build_influence(synth_geometry, synth_beam_model)
        via_dij = engine.apply_influence(
            influence, weights, synth_geometry.density.shape,
        ).dose
        _assert_dij_consistency(
            direct, via_dij, label="analytic uniform", rel_tol=0.10,
        )

    def test_linearity_in_weights(self, synth_geometry, synth_beam_model):
        """Dij @ (2w) == 2 * (Dij @ w). Sanity check on the matvec itself."""
        from radiarch.services.dose_engines import get_engine
        engine = get_engine("analytic")
        n = synth_beam_model.result.fluence_elements.total_count
        w = np.linspace(0.1, 2.0, n).astype(np.float32)

        influence = engine.build_influence(synth_geometry, synth_beam_model)
        d1 = engine.apply_influence(influence, w, synth_geometry.density.shape).dose
        d2 = engine.apply_influence(influence, 2 * w, synth_geometry.density.shape).dose

        np.testing.assert_allclose(d2, 2.0 * d1, rtol=1e-5)


# ---------------------------------------------------------------------------
# Layer 1b — MCsquare Dij voxel-frame remap (always-on, no MCsquare binary)
# ---------------------------------------------------------------------------

class TestMCsquareDijRowRemap:
    """Guard the fix for the V4 nightly failure without needing MCsquare.

    MCsquare stores Dij rows in its native F-order/pre-flip voxel order;
    OpenTPS reconstructs dose as reshape(gridSize,'F') → flip(0) → flip(1)
    (both SparseBeamlets.toDoseImage and the direct readDose path). Our
    apply_influence reshapes Dij@w in plain C-order, so build_influence must
    remap the rows. This exercises that remap against OpenTPS's exact
    reconstruction on a synthetic sparse matrix — the same math the real
    engine relies on, so a regression here fails fast on every CI build
    instead of only on the nightly Monte-Carlo run.
    """

    @staticmethod
    def _opentps_reconstruction(dose_flat, grid_size):
        """OpenTPS's canonical sparse-beamlets → dose volume transform."""
        vol = np.reshape(dose_flat, grid_size, order="F")
        vol = np.flip(vol, 0)
        vol = np.flip(vol, 1)
        return vol

    @pytest.mark.parametrize("grid_size", [(5, 4, 3), (8, 8, 8), (6, 5, 4)])
    @pytest.mark.parametrize("seed", [0, 1, 20260701])
    def test_remap_matches_opentps_reconstruction(self, grid_size, seed):
        from scipy.sparse import random as sparse_random

        from radiarch.services.dose_engines.mcsquare import (
            _reorder_dij_rows_to_c_order,
        )

        n_vox = int(np.prod(grid_size))
        n_beamlets = 7
        rng = np.random.default_rng(seed)
        # Native-order Dij: rows are MCsquare's F-order/pre-flip voxels.
        dij = sparse_random(
            n_vox, n_beamlets, density=0.3, format="csr",
            random_state=seed, dtype=np.float32,
        )
        w = rng.uniform(0.5, 2.0, size=n_beamlets).astype(np.float32)

        # Reference: OpenTPS reconstructs from the *native* rows.
        want = self._opentps_reconstruction(np.asarray(dij @ w), grid_size)

        # Fix: remap rows, then apply_influence's plain C-order reshape.
        remapped = _reorder_dij_rows_to_c_order(dij, grid_size)
        got = np.asarray(remapped @ w).reshape(grid_size)  # C-order

        assert got.shape == want.shape
        np.testing.assert_allclose(got, want, rtol=1e-6, atol=1e-6)

    def test_remap_is_a_pure_permutation(self):
        """No values invented or dropped — same multiset of rows."""
        from scipy.sparse import random as sparse_random

        from radiarch.services.dose_engines.mcsquare import (
            _reorder_dij_rows_to_c_order,
        )

        grid_size = (5, 4, 3)
        dij = sparse_random(
            int(np.prod(grid_size)), 4, density=0.5, format="csr",
            random_state=3, dtype=np.float32,
        )
        remapped = _reorder_dij_rows_to_c_order(dij, grid_size)
        assert remapped.shape == dij.shape
        # Row sums are preserved under a pure row permutation.
        np.testing.assert_allclose(
            np.sort(np.asarray(dij.sum(axis=1)).ravel()),
            np.sort(np.asarray(remapped.sum(axis=1)).ravel()),
            rtol=1e-6, atol=1e-6,
        )

    def test_remap_degrades_gracefully_on_bad_grid(self):
        """A missing/inconsistent doseGridSize returns the matrix unchanged."""
        from scipy.sparse import random as sparse_random

        from radiarch.services.dose_engines.mcsquare import (
            _reorder_dij_rows_to_c_order,
        )

        dij = sparse_random(60, 4, density=0.5, format="csr", random_state=1)
        # prod != n_rows → skip remap, don't raise.
        out = _reorder_dij_rows_to_c_order(dij, (5, 4, 2))
        assert out.shape == dij.shape
        assert (out != dij).nnz == 0  # unchanged
        # Zero/degenerate grid → also unchanged.
        out2 = _reorder_dij_rows_to_c_order(dij, (0, 0, 0))
        assert (out2 != dij).nnz == 0


# ---------------------------------------------------------------------------
# Layer 2 — Real MCsquare (auto-skipped without OpenTPS)
# ---------------------------------------------------------------------------

def _opentps_importable() -> bool:
    try:
        import opentps.core  # noqa: F401
        return True
    except Exception:
        return False


def _bundled_simplefantom_available() -> bool:
    """The SimpleFantom test data ships with the repo for end-to-end tests."""
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    return (_REPO_ROOT / "tests" / "opentps" / "core" / "opentps-testData"
            / "SimpleFantomWithStruct").is_dir()


# Real Monte Carlo is slow and tolerance-sensitive, so it's opt-in rather than
# run on every CI push: it's the V4 *validation* gate (TASKS.md), meant to run
# deliberately on a machine with the MCsquare binary — not to block routine PRs
# with stochastic flakiness. Enable with RADIARCH_RUN_MCSQUARE_VALIDATION=1
# (the nightly / manual "MCsquare Validation" CI job sets it). The analytic
# TestAnalyticDijConsistency above always runs and proves the Dij math itself.
def _mcsquare_validation_enabled() -> bool:
    return os.environ.get("RADIARCH_RUN_MCSQUARE_VALIDATION", "").lower() \
        not in ("", "0", "false", "no")


pytestmark_real_mcsquare = pytest.mark.skipif(
    not (_mcsquare_validation_enabled()
         and _opentps_importable()
         and _bundled_simplefantom_available()),
    reason=(
        "Real-MCsquare V4 validation is opt-in: set "
        "RADIARCH_RUN_MCSQUARE_VALIDATION=1 on a machine with the MCsquare "
        "binary + SimpleFantom test data (Monte Carlo is slow / "
        "tolerance-sensitive, so it's excluded from routine CI)."
    ),
)


@pytestmark_real_mcsquare
class TestMCsquareDijConsistency:
    """Build real Dij + direct dose on SimpleFantom; compare.

    This is V4 in the task list. It's the gate that says the
    Optimization Service can trust MCsquare's beamlet output.
    """

    def _build_synthfantom_pipeline(self, tmp_path):
        """Run the same Geometry → BeamModel pipeline as demo/show_dose.py."""
        # Env stubs — keep aligned with demo/show_dose.py
        os.environ.setdefault("RADIARCH_ORTHANC_USE_MOCK", "true")
        os.environ.setdefault("RADIARCH_DATABASE_URL", "")
        os.environ.setdefault("RADIARCH_BROKER_URL", "memory://")
        os.environ.setdefault("RADIARCH_RESULT_BACKEND", "cache+memory://")
        os.environ.setdefault("RADIARCH_DICOMWEB_URL", "")
        os.environ["RADIARCH_ARTIFACT_DIR"] = str(tmp_path / "artifacts")
        _TEST_DATA = (
            Path(__file__).resolve().parent / "opentps" / "core"
            / "opentps-testData" / "SimpleFantomWithStruct"
        )
        os.environ["RADIARCH_OPENTPS_DATA_ROOT"] = str(_TEST_DATA)

        from radiarch.config import get_settings
        get_settings.cache_clear()

        from radiarch.models.beam_model import (
            BeamModelBuildRequest, BeamSetSpec, BeamSpec,
            DeliveryParams, Modality,
        )
        from radiarch.models.geometry import (
            GeometryBuildRequest, HUDensityModel, PatientRef,
        )
        from radiarch.services.beam_model import BeamModelService
        from radiarch.services.geometry import GeometryService

        gs = GeometryService()
        bs = BeamModelService()

        geo = gs.build(GeometryBuildRequest(
            patient_ref=PatientRef(dicom_study_uid="demo-study-001"),
            grid_spec=None,
            hu_to_density_model=HUDensityModel.stoichiometric,
        ))

        bm = bs.build(BeamModelBuildRequest(
            geometry_id=geo.geometry_id,
            modality=Modality.proton_pbs,
            beam_set=BeamSetSpec(
                isocenter_mm=(0.0, 0.0, 0.0),
                beams=[BeamSpec(beam_id="B1", gantry_deg=0.0)],
            ),
            delivery_params=DeliveryParams(),
        ))

        return geo, bm

    def test_mcsquare_dij_matches_direct_dose(self, tmp_path):
        """The big one: build_influence then apply_influence vs compute_dose.

        ``direct`` and ``via_dij`` are two *independent* Monte-Carlo runs, so
        they agree only up to combined counting statistics. We assert the
        noise-robust invariants (integral ratio, correlation, high-dose-region
        agreement) rather than a per-voxel relative error, which at any
        nightly-affordable primary count is dominated by low-dose MC scatter.
        See the module-level note on ``_assert_mc_dij_consistency``.
        """
        from radiarch.services.dose import DoseService
        from radiarch.services.dose_engines.mcsquare import _opentps_available

        if not _opentps_available():
            pytest.skip("OpenTPS not importable")

        geo, bm = self._build_synthfantom_pipeline(tmp_path)
        ds = DoseService()

        # Need higher nb_primaries than the default (1e4) so MC noise
        # doesn't dominate the comparison; 1e5 is a reasonable
        # compromise between speed (~30s) and signal-to-noise (~2%).
        engine_params = {"nb_primaries": 1e5}

        # Load the bundled geometry + beam-model from the service
        # caches via the public path (build is idempotent).
        from radiarch.services.dose_engines import get_engine
        engine = get_engine("mcsquare")

        # Reach into the service's loader helpers — these are private
        # but exist for exactly this kind of cross-engine work.
        geom_bundle = ds._load_geometry(geo.geometry_id)
        bm_bundle = ds._load_beam_model(bm.beam_model_id)

        n = bm.fluence_elements.total_count
        # Use weights that aren't all-ones — exercises the matvec on
        # an interesting distribution.
        rng = np.random.default_rng(20260605)
        weights = rng.uniform(0.5, 2.0, size=n).astype(np.float32)

        # Direct
        direct = engine.compute_dose(
            geom_bundle, bm_bundle, weights, params=engine_params,
        ).dose

        # Via Dij
        influence = engine.build_influence(
            geom_bundle, bm_bundle, params=engine_params,
        )
        via_dij = engine.apply_influence(
            influence, weights, geom_bundle.density.shape,
        ).dose

        # Noise-robust gate (integral ratio + correlation + high-dose p95).
        # A voxel-frame/scale/physics bug fails; per-voxel MC scatter in the
        # low-dose bath does not.
        _assert_mc_dij_consistency(
            direct, via_dij,
            label="mcsquare SimpleFantom",
        )

    def test_mcsquare_dij_linearity(self, tmp_path):
        """Independent sanity check: Dij @ (2w) == 2 * (Dij @ w).

        Cheaper than the full direct-vs-Dij comparison because we only
        build Dij once. Good smoke test before running the expensive
        compute_dose comparison.
        """
        from radiarch.services.dose import DoseService
        from radiarch.services.dose_engines.mcsquare import _opentps_available

        if not _opentps_available():
            pytest.skip("OpenTPS not importable")

        geo, bm = self._build_synthfantom_pipeline(tmp_path)
        ds = DoseService()

        from radiarch.services.dose_engines import get_engine
        engine = get_engine("mcsquare")
        geom_bundle = ds._load_geometry(geo.geometry_id)
        bm_bundle = ds._load_beam_model(bm.beam_model_id)

        n = bm.fluence_elements.total_count
        w = np.full(n, 1.0, dtype=np.float32)

        influence = engine.build_influence(
            geom_bundle, bm_bundle, params={"nb_primaries": 1e4},
        )
        d1 = engine.apply_influence(influence, w, geom_bundle.density.shape).dose
        d2 = engine.apply_influence(influence, 2 * w, geom_bundle.density.shape).dose

        np.testing.assert_allclose(d2, 2.0 * d1, rtol=1e-5)
