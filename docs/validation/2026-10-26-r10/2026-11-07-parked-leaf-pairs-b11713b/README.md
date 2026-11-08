# Rerun of the R10 record, 2026-11-07: the protocol plans with closed leaf pairs parked under an X jaw

**What changed.** From commit `b11713b` on, the sequencer parks closed leaf pairs 10 mm behind an X jaw: every
closed pair of a static segment, and an arc's pair that no control point opens, for the whole arc. The R8 record's
rerun of the same day (`../../2026-10-23-r8/2026-11-07-parked-leaf-pairs-b11713b/`) describes the change. Both
protocols of R10 plan VMAT arcs, so both cases are rerun. Their numbers in the rerun of 2026-11-05
(`../2026-11-05-leaf-model-412a105/`) are superseded by these runs.

**These runs.** Two runs, one case per process, from a clean checkout of commit `b11713b` on the 96-core server, in
the radiarch image built from `55ab566` with the checkout mounted over its code, each capped at 6 BLAS threads:
`20261107-022804-b11713b` (`protocol_batch_lctsc`) and `20261107-023423-b11713b` (`protocol_lung_vmat`).
`run-summary.md` lists every check, and `results.json` holds the full numbers.

**What the parking changes.**

- Every graded check passes, as before: `protocol_batch_lctsc` 79, `protocol_lung_vmat` 44.
- The batch is unchanged: every value of the six thoraces equals the rerun of 2026-11-05.
- The lung protocol still reproduces its harness case. All 18 of its RTOG 0617 goal values equal those of the R8
  record's rerun of `lung_vmat_lctsc` from the same commit. Like that case, only the second patient's
  (LCTSC-Test-S2-101) values move, by at most 0.19:

| Check | 2026-11-05 (890a575) | Parked (b11713b) | Target | Result |
|---|---|---|---|---|
| LCTSC-Test-S2-101: PTV V60Gy[%] >= 95.0 (protocol) | 95.62 | 95.43 | >= 95.0 | pass → pass |
| LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 65.25 | 65.22 | <= 72.0 | informative |
| LCTSC-Test-S2-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 14.01 | 13.99 | <= 37.0 | pass → pass |
| LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 15.65 | 15.6 | <= 50.5 | pass → pass |
| LCTSC-Test-S2-101: Esophagus Dmean[Gy] <= 34.0 (protocol) | 3.24 | 3.25 | <= 34.0 | informative |

The case's "protocol against the recorded harness run" checks still compare with the R8 rerun of 2026-11-05 (the
case's `record`), so they read the same moves against that record's values, within their 1 % tolerance.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout b11713b
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases protocol_batch_lctsc
.venv/bin/python -m radiarch.validation.run --cases protocol_lung_vmat
```

The cases read the LCTSC thoraces from `RADIARCH_VALIDATION_DATA`, outside the repository.
