# Rerun of the R10 record, 2026-11-10: the protocol plans with an arc's closed leaf pairs moved toward an X jaw

**What changed.** From commit `f3a83c7` on (release 0.3.1), an arc moves a leaf pair that is closed for part of the
arc toward an X jaw while it stays closed, lengthening no interval. The R8 record's rerun of the same day
(`../../2026-10-23-r8/2026-11-10-arc-pairs-toward-jaw-f3a83c7/`) describes the change and how much leak it removes.
Both protocols of R10 plan VMAT arcs, so both cases are rerun. Their numbers in the rerun of 2026-11-07
(`../2026-11-07-parked-leaf-pairs-b11713b/`) are superseded by these runs.

**These runs.** One case per process on the 96-core server, in the radiarch image built from `e486b71` with a clean
checkout mounted over its code, each capped at 6 BLAS threads:
- `20261110-191147-f3a83c7` (`protocol_batch_lctsc`) and `20261110-191603-f3a83c7` (`protocol_lung_vmat`, which
  failed), from commit `f3a83c7`. They are kept as `results-f3a83c7.json` and `run-summary-f3a83c7.md`.
- `20261111-023616-48c0cc4` (`protocol_lung_vmat`), from commit `48c0cc4`, which names the R8 record's rerun from
  `f3a83c7` as the case's record.

`results.json` and `run-summary.md` hold the batch from `f3a83c7` and the lung protocol from `48c0cc4`.

## What the move changes

- **The batch (`protocol_batch_lctsc`) passes every graded check (79), as before.** Its values move by at most
  0.66 Gy, 0.5 percentage points and 1.9 cc (the lungs' V12.5Gy, about 220 cc). LCTSC-Test-S1-102's cord maximum
  rises from 10.10 to 10.76 Gy (its planning goal; limit 21.9 Gy). The PTV V100% rises in three thoraces (by 0.16 to
  0.50 percentage points), falls by 0.16 in one, and is unchanged in two. The first and third thoraces are the
  patients of the R8 SBRT case, and their values equal that case's rerun.
- **The lung protocol (`protocol_lung_vmat`) failed 6 of its 44 graded checks from `f3a83c7`.** All six compare the
  protocol's plan with a recorded run of its harness case. Every other check passed, among them every RTOG 0617 goal
  and every setting the protocol shares with the harness case. From `48c0cc4`, against the harness case's rerun from
  `f3a83c7`, it passes all 44.

## The lung protocol's failures, and the fix

**The cause.** The case compares each goal value of the protocol's plan with the harness case's value (`lung_vmat_lctsc`)
in the record its `record` names, within 1 %. That record is still the R8 rerun of 2026-11-05 (commit `412a105`). The
move changes the harness case itself. Six of its values now differ from the 2026-11-05 run by more than 1 %:

| Check: protocol against the recorded harness run | Protocol, f3a83c7 | Harness case, f3a83c7 | Recorded (412a105) ± 1 % | Result |
|---|---|---|---|---|
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 14.4 | 14.4 | 14.78 ± 0.15 | fail |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.2 | 8.2 | 8.37 ± 0.08 | fail |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 3.21 | 3.21 | 3.38 ± 0.05 | fail |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.54 | 8.54 | 8.68 ± 0.09 | fail |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 16.4 | 16.4 | 15.65 ± 0.16 | fail |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 3.14 | 3.14 | 3.24 ± 0.05 | fail |

**The protocol still reproduces its harness case.** All 18 of its goal values equal those of the R8 record's rerun of
`lung_vmat_lctsc` from the same commit, to the reported precision. Against that rerun, all 18 comparisons read a
difference of 0. In the rerun of 2026-11-07 the harness case had moved by at most 0.19, within the 1 % tolerance,
so the record the case names was not changed then.

**The fix (the project lead agreed).** From commit `48c0cc4`, the case's `record` names the R8 record's rerun from
`f3a83c7` (`docs/validation/2026-10-23-r8/2026-11-10-arc-pairs-toward-jaw-f3a83c7/results.json`). The 1 % tolerance
is unchanged. The case's run from `48c0cc4` passes all 44 graded checks. All 18 comparisons with the harness case
read a difference of 0, and every other value equals the run from `f3a83c7`.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 48c0cc4    # f3a83c7 for the first round
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases protocol_batch_lctsc
.venv/bin/python -m radiarch.validation.run --cases protocol_lung_vmat
```

The cases read the LCTSC thoraces from `RADIARCH_VALIDATION_DATA`, outside the repository.
