# Correction to the R11 record, 2026-11-04: the lung case's deliverable plans

**What was wrong.** Item 7 of the record's guide: on the lung demo patient the deliverable plans made from the
navigated plans were not acceptable plans. The apertures under-covered the PTV, and the normalisation to the coverage
goal then scaled each plan up (by 1.17 with seven fields, 1.42 with two arcs), and its hot spots with it: the PTV's
hottest 0.03 cc received 85.8 and 149 Gy on a 60 Gy prescription, and the arcs' spinal cord maximum went from 10.6 to
41.8 Gy. For those plans the record's run `20261031-131756-b4085b0` is superseded by this one.

**The correction** (R11.9; `docs/reports/mco-deliverable-options.md` compares the designs). It came in two steps.

1. Commit `f5597f9` (option A of the design note). The last solve of the deliverable step, over the segment
   metersets (fields) or the control-point-interval metersets (arcs), holds two hard constraints by the augmented
   Lagrangian of R11.2: the PTV's gEUD with exponent -10 (close to its minimum) at or above the 60 Gy coverage goal,
   and the PTV's maximum at or below 1.2 times the prescription (72 Gy). The record also grades the normalisation:
   within 15 % of 1. Its run at 4 mm, `20261104-000104-f5597f9`, passed every graded check, but the plans still
   needed normalisation 1.111 and 1.108, and their PTV D0.03cc was 80 Gy. A gEUD at 60 Gy is not the coverage goal
   (V60 at least 95 %): it holds with a cold edge, which the normalisation then scales up with the hot spots. That
   run is kept here as the intermediate step (`run-summary-f5597f9.md`, `results-f5597f9.json`).
2. Commit `8102454`. The gEUD's level is calibrated on the plan: while a round's normalisation is more than 3 % from
   1, the next round's level is the last level times that normalisation, at most 0.95 times the maximum's limit. The
   plan kept is a round whose goals hold, then the one whose normalisation is nearest 1.

An earlier step of R11.9 (the deliverable plan made from the navigated blend instead of its projection onto the Pareto
set, commit `632e151`) did not correct the fault at 4 mm (normalisation 1.37 and 1.27) and is not recorded as a run.

**This run.** `20261104-151641-8102454`: the lung case from a clean checkout of commit `8102454` on the 96-core
server with Python 3.12, in 6.3 hours (`run-summary.md` lists every check, `results.json` holds the full numbers).
The Pareto sets, their error bounds and hard constraints, and the R10 reweighting plan give the same numbers as in the
record: only the deliverable step changed.

**What changes for review.**

- Every graded check passes. Both plans took two meterset rounds; their normalisation is 0.967 (seven fields) and
  1.029 (two arcs), against 1.17 and 1.42 in the record and 1.111 and 1.108 in the intermediate run.
- Seven fields: the PTV's hottest 0.03 cc receives 69.7 Gy, under the protocol's informative 72 Gy and level with the
  reweighting plan's 69.5 Gy (record 85.8, intermediate 80.0). The PTV RMS against the navigated plan is 5.7 Gy
  (11.2, 9.8). The organ doses are close to the record's: spinal cord D0.03cc 4.9 Gy (4.9, 7.6), heart mean 9.5 Gy
  (6.0, 12.1; navigated 7.5), lungs V20 20.6 % (18.9, 21.0). The deviation table flags 3 rows (2, 6).
- Two arcs: the PTV's hottest 0.03 cc receives 74.3 Gy (record 149.2, intermediate 79.9), still 2.3 Gy above the
  protocol's informative 72 Gy. In the second round, with the coverage level raised, the solve could not meet both
  hard constraints: it ended 3.0 Gy short of one of them (the run's log; the first round ended within 0.2 Gy, and
  both rounds of the seven fields within 0.4 Gy). The kept round's normalisation, 1.029, lies inside the 3 % band
  and scales the maximum with the plan. The PTV RMS is 7.8 Gy (24.2, 9.9). The spinal cord
  D0.03cc is 34.5 Gy (38.9, 26.9; navigated 10.6), the heart mean 13.6 Gy (4.9, 15.9; navigated 9.9), and the
  esophagus mean 9.4 Gy (2.0, 11.3; navigated 5.3). All are within the protocol's limits. The deviation table flags
  9 rows (4, 8).
- This correction replaces item 7's conclusion. The deliverable lung plans are acceptable by the protocol's graded
  goals and the normalisation check. The seven-field plan is close to the navigated plan; the arcs plan is not: its
  organ doses are well above the navigated plan's, and its hot spot is above 72 Gy. Three follow-ups are open: the
  maximum's limit divided by the normalisation in the calibration, so that the hot spot stays under 72 Gy after
  scaling; each round's constraint values kept in the record (this run's results give the number of rounds and the
  kept plan only); and
  Pareto plans that share their apertures (option B1 of the design note), so that the deliverable plan can keep the
  navigated plan's organ doses. The TG-119 and proton cases of the record are unaffected.

Please review the lung case's deliverable rows from this correction.

## Checks of the lung case whose value changed by 1 or more (Gy, %, or rows), and the new checks

| Check | Record (b4085b0) | Intermediate (f5597f9) | Corrected (8102454) | Target | Result |
|---|---|---|---|---|---|
| PTV D0.03cc[Gy] <= 72.0: MCO plan | 85.8 | 80.03 | 69.66 | <= 72.0 | informative → informative |
| PTV D0.03cc[Gy] <= 72.0: MCO against the reweighting plan | 85.80 vs 69.46 | 80.03 vs 69.46 | 69.66 vs 69.46 | informative | informative → informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan | 18.92 | 20.97 | 20.55 | <= 37.0 | pass → pass |
| Lungs-GTV V20Gy[%] <= 37.0: MCO against the reweighting plan | 18.92 vs 19.82 | 20.97 vs 19.82 | 20.55 vs 19.82 | informative | informative → informative |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan | 4.87 | 7.57 | 4.89 | <= 50.5 | pass → pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO against the reweighting plan | 4.87 vs 35.67 | 7.57 vs 35.67 | 4.89 vs 35.67 | informative | informative → informative |
| Heart V45Gy[%] <= 66.0: MCO plan | 4.59 | 6.43 | 5.09 | <= 66.0 | informative → informative |
| Heart V45Gy[%] <= 66.0: MCO against the reweighting plan | 4.59 vs 1.25 | 6.43 vs 1.25 | 5.09 vs 1.25 | informative | informative → informative |
| Heart V40Gy[%] <= 100.0: MCO plan | 4.88 | 7.69 | 5.49 | <= 100.0 | informative → informative |
| Heart V40Gy[%] <= 100.0: MCO against the reweighting plan | 4.88 vs 2.34 | 7.69 vs 2.34 | 5.49 vs 2.34 | informative | informative → informative |
| deliverable (seven static fields): UniformRMS(PTV) navigated → deliverable (Gy) | 0.48 → 11.18 | 0.48 → 9.82 | 0.48 → 5.68 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (seven static fields): MeanDose(Heart) navigated → deliverable (Gy) | 7.53 → 6.04 | 7.53 → 12.09 | 7.53 → 9.46 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (seven static fields): EUDMax(SpinalCord) navigated → deliverable (Gy) | 2.68 → 3.19 | 2.68 → 4.74 | 2.68 → 3.13 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (seven static fields): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 3.93 → 5.13 | 3.93 → 7.84 | 3.93 → 4.91 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (seven static fields): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 4.77 → 2.34 | 4.77 → 11.71 | 4.77 → 7.71 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (seven static fields): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 1.33 → 1.22 | 1.33 → 3.15 | 1.33 → 2.04 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (seven static fields): flagged rows of the deviation table | 2 | 6 | 3 | informative | informative → informative |
| deliverable (seven static fields): normalisation of the deliverable plan within 15 % of 1 | (new) | 1.111 | 0.9672 | 0.85 to 1.15 | pass |
| deliverable (seven static fields): meterset rounds | (new) | 1 | 2 | informative | informative |
| deliverable (two arcs): UniformRMS(PTV) navigated → deliverable (Gy) | 0.55 → 24.20 | 0.55 → 9.91 | 0.55 → 7.80 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): MeanDose(Heart) navigated → deliverable (Gy) | 9.91 → 4.88 | 9.91 → 15.88 | 9.91 → 13.63 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): MeanDose(Esophagus) navigated → deliverable (Gy) | 5.29 → 2.03 | 5.29 → 11.26 | 5.29 → 9.39 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): EUDMax(SpinalCord) navigated → deliverable (Gy) | 7.74 → 23.94 | 7.74 → 18.19 | 7.74 → 23.64 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): SpinalCord Dmax[Gy] <= 45 navigated → deliverable (Gy) | 10.64 → 41.79 | 10.64 → 27.76 | 10.64 → 34.52 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): Esophagus Dmean[Gy] <= 34 navigated → deliverable (Gy) | 5.29 → 2.03 | 5.29 → 11.26 | 5.29 → 9.39 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): Heart D33%[Gy] <= 60 navigated → deliverable (Gy) | 10.51 → 3.18 | 10.51 → 18.27 | 10.51 → 15.37 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): Lungs-PTV D37%[Gy] <= 20 navigated → deliverable (Gy) | 5.34 → 2.34 | 5.34 → 8.71 | 5.34 → 7.50 | flagged when worse by more than 1.0 Gy or 1.0 % volume | informative → informative |
| deliverable (two arcs): flagged rows of the deviation table | 4 | 8 | 9 | informative | informative → informative |
| deliverable (two arcs): normalisation of the deliverable plan within 15 % of 1 | (new) | 1.108 | 1.029 | 0.85 to 1.15 | pass |
| deliverable (two arcs): meterset rounds | (new) | 1 | 2 | informative | informative |
| PTV D0.03cc[Gy] <= 72.0: MCO plan (two arcs) | 149.2 | 79.9 | 74.33 | <= 72.0 | informative → informative |
| Lungs-GTV V20Gy[%] <= 37.0: MCO plan (two arcs) | 18.02 | 17.76 | 19.3 | <= 37.0 | pass → pass |
| SpinalCord D0.03cc[Gy] <= 50.5: MCO plan (two arcs) | 38.91 | 26.88 | 34.51 | <= 50.5 | pass → pass |
| Esophagus Dmean[Gy] <= 34.0: MCO plan (two arcs) | 2.03 | 11.26 | 9.39 | <= 34.0 | informative → informative |
| Heart V40Gy[%] <= 100.0: MCO plan (two arcs) | 1.7 | 4.44 | 3.26 | <= 100.0 | informative → informative |

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 8102454
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases mco_protocol_lung    # about 6.5 hours on 32 threads
```

The case reads the demo patient (NSCLC-Radiomics LUNG1-002) from `RADIARCH_VALIDATION_DATA`, outside the repository.
