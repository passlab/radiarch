# Rerun of the R10 record, 2026-11-05: the protocol plans with the MLC leaf model

**What changed.** From commit `412a105` on, every photon dose computed from apertures uses the machine's leaf model:
the leaf transmission, a dosimetric leaf gap of 1.5 mm and a tongue-and-groove of 0.5 mm (representative values, not a
commissioned machine's). `docs/reports/mlc-leaf-model.md` gives the model, and the R8 record's rerun
(`../../2026-10-23-r8/2026-11-05-leaf-model-412a105/`) describes it. Both protocols of R10 plan VMAT arcs, so both
cases are rerun. Their numbers in the record (`../`, commit `92ce40d`) are superseded by these runs.

**These runs.** Two runs, one case per process, on the 96-core server, in the radiarch image built from `55ab566`
with a clean checkout mounted over its code, each capped at 6 BLAS threads:

- `20261105-181257-412a105` (`protocol_batch_lctsc`), from commit `412a105`: `run-summary.md` and `results.json`.
- `20261106-034538-890a575` (`protocol_lung_vmat`), from commit `890a575`: `run-summary-890a575.md` and
  `results-890a575.json`. This case compares the protocol's plans with the R8 record's rerun of `lung_vmat_lctsc`, so
  it ran from `890a575`, the commit that adds that rerun and points the case at it. After `412a105`, that commit
  changes only records, the case's record and one note's wording.

**The baseline.** The commits between the record and the leaf model also change the planning. To separate the leaf
model from them, the batch case ran from `55ab566`, the commit before the leaf model, in the same image and the same
way: run `20261106-001709-55ab566`, in `baseline-55ab566/`. The comparisons below are against this baseline.

**The protocol reproduces its harness case** (`protocol_lung_vmat`, 44 pass). All 16 shared settings are equal, as in
the record. On both patients every RTOG 0617 goal value equals the R8 rerun's `lung_vmat_lctsc` value, to the reported
precision: all 18 values are equal, where the check allows 1 %. The protocol's values therefore move with the leaf
model exactly as the harness case's do. The R8 rerun gives those changes; the four that move by 1 or more are listed
below.

**What the leaf model changes in the batch.**

- All six LCTSC thoraces are planned and deliverable, and the PTV D95 is 54.11 Gy after normalisation, as before. All
  79 graded checks pass, in the baseline and with the leaf model. No check changes status.
- The organ maxima fall in every patient: the spinal cord's D0.03cc by 0.4 to 1.3 Gy, and the heart's by 0.3 to
  1.8 Gy. The PTV's hottest 0.03 cc falls by 0.1 to 2.1 percentage points of the prescription.
- The low doses rise, through the closed leaves: the lungs' V12.5Gy by 0.5 to 8 cc, and their D1000cc by 0.06 to
  0.33 Gy. The oesophagus D5cc rises by up to 0.5 Gy in five patients and falls by 0.4 Gy in one.
- `LCTSC-Test-S1-101` and `LCTSC-Test-S2-101` give the same values in all 28 checks they share with the R8 rerun's
  `lung_sbrt_vmat`, which plans them with the same settings, in the baseline and with the leaf model.

## Checks whose value changed by 1 or more (Gy, %, or cc) with the leaf model

| Case | Check | Baseline (55ab566) | Leaf model (412a105) | Target | Result |
|---|---|---|---|---|---|
| protocol_batch_lctsc | LCTSC-Test-S1-101: planning goal Heart Dmax <= 30.0 | 18.04 | 16.83 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S1-101: Heart D0.03cc[Gy] <= 30.0 | 17.94 | 16.69 | <= 30.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 223.1 | 229.9 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S1-102: planning goal SpinalCord Dmax <= 21.9 | 11.18 | 10.1 | <= 21.9 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S1-102: planning goal Heart Dmax <= 30.0 | 22.71 | 20.9 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S1-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.97 | 9.74 | <= 21.9 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S1-102: SpinalCord D0.35cc[Gy] <= 18.0 | 10.25 | 9.1 | <= 18.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S1-102: Heart D0.03cc[Gy] <= 30.0 | 22.52 | 20.77 | <= 30.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S1-102: Lungs V12.5Gy[cc] <= 1000.0 | 224.4 | 225.59 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-101: planning goal Esophagus Dmax <= 25.2 | 7.31 | 5.62 | <= 25.2 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 21.9 | 10.21 | 9.21 | <= 21.9 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-101: Esophagus D0.03cc[Gy] <= 25.2 | 7.14 | 5.43 | <= 25.2 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-101: Lungs V12.5Gy[cc] <= 1000.0 | 211.65 | 219.65 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-102: planning goal SpinalCord Dmax <= 21.9 | 10.68 | 9.25 | <= 21.9 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-102: PTV D0.03cc[%] <= 140.0 | 119.28 | 117.15 | <= 140.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.53 | 9.2 | <= 21.9 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.84 | 8.72 | <= 18.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-102: Lungs V12.5Gy[cc] <= 1000.0 | 235.44 | 237.52 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-101: planning goal SpinalCord Dmax <= 21.9 | 7.73 | 6.2 | <= 21.9 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-101: planning goal Heart Dmax <= 30.0 | 19.31 | 17.93 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-101: SpinalCord D0.03cc[Gy] <= 21.9 | 6.83 | 5.61 | <= 21.9 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-101: Heart D0.03cc[Gy] <= 30.0 | 19.11 | 17.72 | <= 30.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-102: planning goal SpinalCord Dmax <= 21.9 | 11.15 | 9.93 | <= 21.9 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-102: planning goal Heart Dmax <= 30.0 | 20.67 | 19.02 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-102: PTV D0.03cc[%] <= 140.0 | 112.2 | 110.19 | <= 140.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-102: SpinalCord D0.03cc[Gy] <= 21.9 | 10.98 | 9.76 | <= 21.9 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-102: SpinalCord D0.35cc[Gy] <= 18.0 | 9.76 | 8.47 | <= 18.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-102: SpinalCord D1.2cc[Gy] <= 12.3 | 8.03 | 6.94 | <= 12.3 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-102: Heart D0.03cc[Gy] <= 30.0 | 20.55 | 18.78 | <= 30.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-102: Lungs V12.5Gy[cc] <= 1000.0 | 232.47 | 236.44 | <= 1000.0 | informative → informative |

## The protocol case against the record

| Case | Check | Record (92ce40d) | Leaf model (890a575) | Target | Result |
|---|---|---|---|---|---|
| protocol_lung_vmat | LCTSC-Test-S1-101: Lungs-GTV V20Gy[%] <= 37.0 (protocol) | 13.72 | 14.78 | <= 37.0 | pass → pass |
| protocol_lung_vmat | LCTSC-Test-S1-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 17.89 | 14.89 | <= 50.5 | pass → pass |
| protocol_lung_vmat | LCTSC-Test-S2-101: PTV D0.03cc[Gy] <= 72.0 (protocol) | 66.87 | 65.25 | <= 72.0 | informative → informative |
| protocol_lung_vmat | LCTSC-Test-S2-101: SpinalCord D0.03cc[Gy] <= 50.5 (protocol) | 20.19 | 15.65 | <= 50.5 | pass → pass |

Most of the spinal cord's fall comes from the commits before the leaf model (the R8 rerun's baseline gives 15.20 and
16.77 Gy). Each row's comparison with the recorded harness run passes, against the R8 rerun's value.

## Before the leaf model: the baseline against the record

These changes in the batch come from the commits between `92ce40d` and `55ab566`, not from the leaf model. Every
graded check passed in both.

| Case | Check | Record (92ce40d) | Baseline (55ab566) | Target | Result |
|---|---|---|---|---|---|
| protocol_batch_lctsc | LCTSC-Test-S1-101: PTV D0.03cc[%] <= 140.0 | 117.95 | 115.52 | <= 140.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S1-101: Lungs V12.5Gy[cc] <= 1000.0 | 229.85 | 223.1 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S1-102: planning goal Heart Dmax <= 30.0 | 20.35 | 22.71 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S1-102: Heart D0.03cc[Gy] <= 30.0 | 20.28 | 22.52 | <= 30.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S1-102: Lungs V12.5Gy[cc] <= 1000.0 | 227.23 | 224.4 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-101: planning goal Heart Dmax <= 30.0 | 17.69 | 18.79 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-101: PTV D0.03cc[%] <= 140.0 | 115.2 | 113.82 | <= 140.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-101: Esophagus D5cc[Gy] <= 17.7 | 1.77 | 3.83 | <= 17.7 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-101: Heart D0.03cc[Gy] <= 30.0 | 17.5 | 18.57 | <= 30.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-102: planning goal Heart Dmax <= 30.0 | 11.4 | 9.34 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-102: PTV D0.03cc[%] <= 140.0 | 118.11 | 119.28 | <= 140.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S2-102: Heart D0.03cc[Gy] <= 30.0 | 11.38 | 9.34 | <= 30.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-102: Heart D15cc[Gy] <= 24.0 | 6.95 | 5.73 | <= 24.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S2-102: Lungs V12.5Gy[cc] <= 1000.0 | 217.73 | 235.44 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-101: planning goal SpinalCord Dmax <= 21.9 | 3.87 | 7.73 | <= 21.9 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-101: SpinalCord D0.03cc[Gy] <= 21.9 | 3.45 | 6.83 | <= 21.9 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-101: SpinalCord D0.35cc[Gy] <= 18.0 | 3.06 | 4.87 | <= 18.0 | pass → pass |
| protocol_batch_lctsc | LCTSC-Test-S3-101: Lungs V12.5Gy[cc] <= 1000.0 | 185.92 | 187.19 | <= 1000.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-102: planning goal Heart Dmax <= 30.0 | 19.55 | 20.67 | <= 30.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-102: PTV D0.03cc[%] <= 140.0 | 113.49 | 112.2 | <= 140.0 | informative → informative |
| protocol_batch_lctsc | LCTSC-Test-S3-102: Heart D0.03cc[Gy] <= 30.0 | 19.2 | 20.55 | <= 30.0 | pass → pass |

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 412a105    # 55ab566 for the baseline
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases protocol_batch_lctsc
git checkout 890a575 && .venv/bin/python -m radiarch.validation.run --cases protocol_lung_vmat
```

The cases read the LCTSC patients from `RADIARCH_VALIDATION_DATA`, outside the repository.
