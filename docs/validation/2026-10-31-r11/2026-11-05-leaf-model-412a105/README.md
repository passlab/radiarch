# Rerun of the R11 record, 2026-11-05: the deliverable plans with the MLC leaf model

**What changed.** From commit `412a105` on, every photon dose computed from apertures uses the machine's leaf model:
the leaf transmission, a dosimetric leaf gap of 1.5 mm and a tongue-and-groove of 0.5 mm (representative values, not a
commissioned machine's). `docs/reports/mlc-leaf-model.md` gives the model, and the R8 record's rerun
(`../../2026-10-23-r8/2026-11-05-leaf-model-412a105/`) describes it. The Pareto sets are made from beamlets and do not
change. The deliverable plans are made from apertures (static fields or arcs), and so is the lung case's reweighting
plan, so `mco_front_tg119` and `mco_protocol_lung` are rerun. Their deliverable numbers in the record (`../`) and in
the correction of 2026-11-04 (`../2026-11-04-correction-8102454/`) are superseded by this rerun. The proton case has no
apertures and stands as recorded.

**These runs.** Two runs, one case per process, from a clean checkout of commit `412a105` on the 96-core server, in
the radiarch image built from `55ab566` with the checkout mounted over its code: `20261105-223821-412a105`
(`mco_front_tg119`, 6 BLAS threads) and `20261106-034544-412a105` (`mco_protocol_lung`, 32 threads, 6.4 hours).
`run-summary.md` lists every check, and `results.json` holds the full numbers.

**The baselines.** To separate the leaf model from the commits since the record:
- `mco_front_tg119` also ran from `55ab566`, the commit before the leaf model, in the same image and the same way: run
  `20261106-013131-55ab566`, in `baseline-55ab566/`.
- For `mco_protocol_lung` the baseline is the correction's run from `8102454`. The commits from `8102454` to `55ab566`
  change no planning code (they record the requesting user), and this rerun's Pareto sets, navigation and error bounds
  equal the correction's.

## A correction to the correction of 2026-11-04

The correction of 2026-11-04 and the record's guide say that the TG-119 case is unaffected by R11.9. That is wrong.
R11.9 changed every photon deliverable plan: it is made from the navigated blend, its metersets go through
goal-driven rounds, and its last solve holds the coverage and the hot spot as hard constraints (commits `632e151`,
`f5597f9` and `8102454`). The TG-119 case was not rerun then. Its baseline here, from `55ab566`, shows the change:

| TG-119 deliverable plan (static fields) | Record (b4085b0) | Baseline (55ab566) | Leaf model (412a105) | Target |
|---|---|---|---|---|
| Core D5 (Gy) | 6.16 | 17.65 | 22.40 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) |
| OuterTarget D10 (Gy) | 60.89 | 57.81 | 56.04 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) |
| OuterTarget D95 (Gy) | 50.1 | 50.1 | 50.1 | >= 50.0 |
| Core D5%, navigated → deliverable (Gy) | 9.14 → 6.16 | 10.00 → 17.65 | 10.00 → 22.40 | flagged when worse by more than 1.0 Gy |
| EUDMax(Core), navigated → deliverable (Gy) | 7.66 → 5.28 | 8.38 → 14.93 | 8.38 → 19.08 | flagged when worse by more than 1.0 Gy |
| Flagged rows of the deviation table | 1 | 2 | 2 | informative |
| Normalisation of the deliverable plan | (not graded) | 1.0075 | 1.0281 | 0.85 to 1.15 |

Every graded check passes in all three runs. In the baseline and with the leaf model, every meterset round misses the
goals for the core's D5 and the outer target's D10 (10 and 55 Gy), and the plan kept is the round whose
normalisation is nearest 1. Both runs pass the core's D5 only through the institutions' limit (mean plus two
standard deviations, 22.44 Gy). With the leaf model the margin is 0.04 Gy. The record's deliverable plan spared the
core better than the navigated plan did (6.16 against 9.14 Gy), with a hotter outer target (D10 60.89 Gy). Since
R11.9 the core receives 7.7 Gy more than the navigated plan in the baseline, and 12.4 Gy more with the leaf model.
The deliverable plans of nine static fields do not keep the navigated plan's core sparing. Pareto
plans that share their apertures (option B1 of `docs/reports/mco-deliverable-options.md`) are the open follow-up for
this, as for the lung case's arcs.

The Pareto set and the navigated plan also differ slightly from the record's (error bound with nine plans 0.6443
against 0.6425; navigated core D5 10.00 against 9.14 Gy), from the commits since. The leaf model does not change them.

## What the leaf model changes in the lung case

Against the correction's run from `8102454`:

- Every graded check passes. The Pareto sets, their error bounds and hard constraints, and the navigated plans are
  unchanged. Both deliverable plans took two meterset rounds, as before.
- Seven fields: the normalisation stays at 0.967. The organ doses rise a little: heart mean 9.46 → 10.14 Gy, spinal
  cord maximum 4.91 → 5.62 Gy, oesophagus mean 1.35 → 1.59 Gy, lungs V20 20.55 → 20.91 %. With these rises, the
  deviation table flags 6 rows, up from 3 (the cord's maximum and EUD and the lungs' D37 % join the PTV's RMS and the
  heart's mean and D33 %).
- Two arcs: the normalisation moves from 1.029 to 1.003, and the PTV's hottest 0.03 cc falls from 74.3 to 72.3 Gy, 0.3
  Gy above the protocol's informative 72 Gy. The spinal cord's maximum falls from 34.5 to 32.3 Gy (navigated 10.6). The
  low and mean doses rise: heart mean 13.6 → 16.2 Gy, oesophagus mean 9.4 → 11.8 Gy, lungs V20 19.3 → 21.6 %, lungs
  mean 12.9 → 14.2 Gy. All are within the protocol's limits. The deviation table flags 9 rows, as before.
- The reweighting plan (`demo-lung-imrt`, R10's reweighting rounds on the same seven fields, sequenced into
  apertures) moves as the R8 rerun's lung plans do: PTV D0.03cc 69.5 → 68.5 Gy,
  lungs V20 19.8 → 20.1 %, spinal cord maximum 35.7 → 35.2 Gy.

The correction's conclusion stands: the seven-field plan is close to the navigated plan, and the arcs plan's organ
doses are well above the navigated plan's. The leaf model widens that gap for the heart and the oesophagus.

## Checks of the lung case whose value changed by 1 or more (Gy, %, or rows) with the leaf model

| Check | Correction (8102454) | Leaf model (412a105) | Target | Result |
|---|---|---|---|---|
| deliverable (seven static fields): MeanDose(Heart) navigated → deliverable (Gy) | 7.53 → 9.46 | 7.53 → 10.14 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.77 → 7.71 | 4.77 → 8.40 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (seven static fields): flagged rows of the deviation table | 3 | 6 | informative | informative |
| deliverable (two arcs): UniformRMS(PTV) navigated → deliverable (Gy) | 0.55 → 7.80 | 0.55 → 6.60 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Lungs-PTV) navigated → deliverable (Gy) | 9.65 → 11.01 | 9.65 → 12.39 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Heart) navigated → deliverable (Gy) | 9.91 → 13.63 | 9.91 → 16.19 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): MeanDose(Esophagus) navigated → deliverable (Gy) | 5.29 → 9.39 | 5.29 → 11.76 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 10.64 → 34.52 | 10.64 → 32.39 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 10.51 → 15.37 | 10.51 → 18.23 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| deliverable (two arcs): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 5.34 → 7.50 | 5.34 → 9.69 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 74.33 | 72.32 | <= 72.0 | informative → informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 19.3 | 21.64 | <= 37.0 | pass → pass |
| Lungs-GTV Dmean[Gy] <= 20.0: MCO plan (two arcs) | 12.86 | 14.18 | <= 20.0 | pass → pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 34.51 | 32.32 | <= 50.5 | pass → pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 9.39 | 11.76 | <= 34.0 | informative → informative |
| Heart V45Gy[%] <= 66.0: MCO plan (two arcs) | 2.15 | 3.29 | <= 66.0 | informative → informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 3.26 | 5.28 | <= 100.0 | informative → informative |

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 412a105    # 55ab566 for the baseline
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases mco_front_tg119
.venv/bin/python -m radiarch.validation.run --cases mco_protocol_lung    # about 6.5 hours on 32 threads
```

The cases read the TG-119 phantom and the demo patient (NSCLC-Radiomics LUNG1-002) from `RADIARCH_VALIDATION_DATA`,
outside the repository.
