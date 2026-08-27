# PROGRESS

Tracks phase status against the Charter (`CLAUDE.md` §5). A phase is complete
only when its gate is *demonstrated*, not when code exists (§8).

## Current phase: 0 — Reproducibility floor  (IN PROGRESS)

Gate: "the same command twice gives the same number."

### Verified (with evidence)
- **Determinism + one-command run logging** — `src/radiarch/repro.py`.
  - `python -m radiarch.repro selftest` run twice → identical
    `reproducibility_checksum=65682307…` (2026-07-23). ✅ gate demonstrated for this layer.
  - `tests/test_repro.py` — 5/5 pass: checksum stable across calls, changes with
    seed, both RNGs pinned, run provenance (git SHA + seed + package versions)
    captured, run log written.
  - Each run logs git SHA, seed, package versions, runtime to `runs/` (gitignored).
- **TrackRAD input-path asset + loader** — `src/radiarch/adapters/trackrad.py`,
  `scripts/fetch_trackrad.py`, `tests/test_trackrad_loader.py`.
  - Typed `TrackRADCase` loader (real fields only — cine frames, tumour mask,
    JSON sidecars; fabricates nothing), deterministic `case_checksum`
    (Phase-0 gate applied to data loading), patient-level `list_patient_dirs`.
  - Placeholder quarantine (Charter §2.2): `to_smoke_test_bundles` refuses to run
    without `acknowledge_synthetic=True` and stamps every fabricated field
    `PLACEHOLDER_TRACKRAD_*`; `is_placeholder_geometry` lets any eval path reject it.
  - `tests/test_trackrad_loader.py` — **10/10 pass, INCLUDING on real data**
    (2026-07-30): load, integrity, checksum-stable-across-loads,
    checksum-changes-with-content, sorted patient-level enum, guard refuses/marks,
    analytic engine consumes a frame → dose of the right shape (shape only, no
    dose-value assertion — Charter §2.6), and the real-data gate now runs.
  - **Verified on real downloaded data (2026-07-30):** fetched labeled patients
    A_001 (0.35 T, 100×270×270, abdomen) and C_001 (1.5 T, 47×423×423, thorax)
    via `scripts/fetch_trackrad.py` (public dataset, no HF token needed) into
    gitignored `data/trackrad/`. Loader determinism gate holds on real bytes.
  - **Two card-vs-reality discrepancies found and fixed by reading the bytes**
    (Charter §6 "code/data is ground truth, docs drift"): (1) the sidecar is
    actually `b-field-strength.json`, not `field-strength.json` — now matched by
    suffix; (2) the `.mha` stores TIME as the LAST numpy axis (ITK axis 0), not
    axis 0 as the card's ASCII tree implied — loader now canonicalises to
    (T,H,W). Confirmed on two centers (A=0.35 T, C=1.5 T). The pre-existing
    `probe_trackrad_input.py` still assumes the old axis order; reconciling it is
    logged in `BACKLOG.md` (cosmetic — it asserts no values).

## Phase 1 — Data integrity  (STARTED on real data — TrackRAD ingestion only)

Gate (Charter §5): every case loads; image/mask geometry consistent; no NaN/Inf;
splits patient-level and asserted. **Scoped here to TrackRAD ingestion** — NOT a
dose-data gate (TrackRAD has no dose, §3). DoseRAD integrity is still blocked on data.

### Verified (with evidence)
- **Real multi-center integrity sweep PASSES** — `scripts/trackrad_integrity.py`,
  `src/radiarch/adapters/trackrad_integrity.py`.
  - **12/12 patients integrity-clean** across 3 centers / 2 field strengths
    (A×4 @0.35 T, B×4 @1.5 T, C×4 @1.5 T; abdomen/thorax/pelvis), 2026-07-30.
    Logged report in `runs/` (git SHA, seed, pinned pkg versions, per-center pass,
    stable `sweep_checksum=45bed45e…`).
  - Checks per case: loads, frames 3D/non-empty/finite, in-plane isotropic + ~1mm,
    sidecars present, field strength ∈ {0.35,1.5}, mask HxW matches frames, mask
    time-dim ∈ {T,1}, mask non-empty. Patient-level uniqueness ASSERTED in code (§2.4).
  - **The gate earned its keep:** first run FAILED B_002 on in-plane spacing
    0.998901≠1.0. Investigated → real MHA header rounding (0.11%), not corruption
    → fixed the *check* (isotropy + ~1mm tolerance), not the data (§2/§6 discipline).
  - `tests/test_trackrad_integrity.py` — **5/5 pass**: clean case passes all checks,
    gate CATCHES injected NaN + mask/frame size mismatch, uniqueness asserted, sweep
    deterministic + patient-level. Loader tests still 10/10. Suite collects 679.

### Not yet done in Phase 1
- **DoseRAD data integrity** — BLOCKED: no DoseRAD2026 data on disk (the dataset
  that actually has dose+beams). TrackRAD sweep does NOT substitute for it.
- **Coverage gaps in the TrackRAD sweep** (honest): only 12/50 labeled patients;
  centers D/E/F/X and the 2.8M-frame unlabeled cohort not swept; multi-scan
  (`_frames2/3`) patients not exercised; no cross-check of frame count vs sidecar
  frame-rate×duration.

### Not yet done in Phase 0
- **Pinned dependencies / lockfile** — `src/pyproject.toml` still uses loose `~=`
  pins and there is **no lockfile**, so byte-identical envs aren't guaranteed
  across machines. Package versions are *logged* per run, but not *pinned*. NEXT.
- **Deterministic data loading** — BLOCKED: no DoseRAD2026 data on disk yet
  (user: "not downloaded yet"). Cannot verify until data lands.

## Blockers / risks to the paper timeline
- **No challenge data on disk** (DoseRAD2026 or TrackRAD). Phases 1 (data
  integrity) and the data half of Phase 0 cannot be verified without it. Phase 2
  (metric parity) can proceed on synthetic identity/known cases + `pymedphys`.

## Next single task
Pin dependencies + add a lockfile (complete the Phase 0 non-data half), then
proceed toward Phase 2 metric-parity scaffolding (data-independent).

## Scope decisions logged
- Dropped earlier "TrackRAD motion-aware dose accumulation" idea — violates
  Charter §3 (TrackRAD cannot validate dose). TrackRAD retained only as an
  input/loading smoke-test asset — now realised as the loader/guard above.
- Deferred (written to `BACKLOG.md`, not built): accepting MRI as a first-class
  geometry input modality, and a cine tumour-tracking service. Both are adjacent
  to DoseRAD scope; not started per Charter §4.
