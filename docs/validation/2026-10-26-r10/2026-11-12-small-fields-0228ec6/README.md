# Rerun of the R10 record, 2026-11-12: the protocol plans with the leaf ends' tail, and no edge blur

**What changed.** From commit `0228ec6` on (`pb` 1.2.0, `LEAF_MODEL_VERSION` 4), a rounded leaf end passes half the
leaf gap as a tail beyond its tip, and the pencil beam no longer blurs a field's edge. The R8 record's rerun of the
same day (`../../2026-10-23-r8/2026-11-12-small-fields-0228ec6/`) describes the change and its checks against Monte
Carlo. Both protocols of R10 plan VMAT arcs with the pencil beam, so both cases are rerun. Their numbers in the rerun
of 2026-11-10 (`../2026-11-10-arc-pairs-toward-jaw-f3a83c7/`) are superseded by these runs.

**These runs.** Two runs, one case per process, from a clean checkout of commit `0228ec6` on the 96-core server, in
the radiarch image built from `48c0cc4` with the checkout mounted over its code, each capped at 6 BLAS threads:
`20261112-140015-0228ec6` (`protocol_batch_lctsc`) and `20261112-140428-0228ec6` (`protocol_lung_vmat`).
`run-summary.md` lists every check, and `results.json` holds the full numbers.

## What the change does

- **The batch (`protocol_batch_lctsc`) passes every graded check (79), as before.** The PTV V100% stays at or above
  95.2 % in all six thoraces. The heart maximum falls in all six (by up to 5.9 Gy, to 14.94 Gy in LCTSC-Test-S1-102),
  and the cord maximum rises in four (by up to 2.8 Gy, to 8.47 Gy in LCTSC-Test-S3-101; limit 21.9 Gy). The lungs'
  V12.5Gy rises by 13 to 16 cc in three thoraces, to at most 251 cc (informative, limit 1000 cc). The first and
  third thoraces are the patients of the R8 SBRT case, and their 28 values equal that case's rerun.
- **The lung protocol (`protocol_lung_vmat`) fails 9 of its 44 graded checks.** All nine compare the protocol's plan
  with a recorded run of its harness case, as in the rerun of 2026-11-10. Every other check passes, among them every
  RTOG 0617 goal and every setting the protocol shares with the harness case.

## The lung protocol's failures, and the fix

**The cause.** The case compares each goal value of the protocol's plan with the harness case's value
(`lung_vmat_lctsc`) in the record its `record` names, within 1 %. That record is still the R8 rerun of 2026-11-10
(commit `f3a83c7`). The change moves the harness case itself, and nine of its values now differ from that run by more
than 1 %:

| Check: protocol against the recorded harness run | Protocol, 0228ec6 | Harness case, 0228ec6 | Recorded (f3a83c7) ± 1 % | Result |
|---|---|---|---|---|
| LCTSC-Test-S1-101: PTV D0.03cc[Gy] <= 72.0 | 66.16 | 66.16 | 64.8 ± 0.65 | fail |
| LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 | 14.96 | 14.96 | 14.4 ± 0.14 | fail |
| LCTSC-Test-S1-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.07 | 8.07 | 8.2 ± 0.08 | fail |
| LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 | 17.59 | 17.59 | 14.85 ± 0.15 | fail |
| LCTSC-Test-S1-101: Esophagus Dmean[Gy] <= 34.0 | 2.48 | 2.48 | 3.21 ± 0.05 | fail |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 | 13.72 | 13.72 | 13.88 ± 0.14 | fail |
| LCTSC-Test-S2-101: Lungs-GTV Dmean[Gy] <= 20.0 | 8.39 | 8.39 | 8.54 ± 0.09 | fail |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 | 18.85 | 18.85 | 16.4 ± 0.16 | fail |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 | 3.38 | 3.38 | 3.14 ± 0.05 | fail |

**The protocol still reproduces its harness case.** All 18 of its goal values equal those of the R8 record's rerun of
`lung_vmat_lctsc` from the same commit, to the reported precision.

**The fix, as on 2026-11-10 (the project lead agreed).** The case's `record` now names the R8 record's rerun from
`0228ec6` (`docs/validation/2026-10-23-r8/2026-11-12-small-fields-0228ec6/results.json`). The 1 % tolerance stays as
it is. `protocol_lung_vmat` runs again from the commit that makes the change; its run will be added here.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 0228ec6
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases protocol_batch_lctsc
.venv/bin/python -m radiarch.validation.run --cases protocol_lung_vmat
```

The cases read the LCTSC CTs and structures from `RADIARCH_VALIDATION_DATA`, outside the repository.
