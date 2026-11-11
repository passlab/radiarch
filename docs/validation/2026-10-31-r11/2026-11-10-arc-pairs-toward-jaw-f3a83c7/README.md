# Rerun of the R11 record's lung case, 2026-11-10: an arc's closed leaf pairs moved toward an X jaw

**What changed.** From commit `f3a83c7` on (release 0.3.1), an arc moves a leaf pair that is closed for part of the
arc toward an X jaw while it stays closed, lengthening no interval. The R8 record's rerun of the same day
(`../../2026-10-23-r8/2026-11-10-arc-pairs-toward-jaw-f3a83c7/`) describes the change. It also gives how much leak
the move removes, measured on this run's arcs. `mco_protocol_lung` plans the same protocol with two arcs, so it is
rerun. Its numbers in the rerun of 2026-11-08 (`../2026-11-08-second-set-a36fc4f/`) are superseded by this run.
`mco_front_tg119` and the proton case have no arcs and stand as recorded.

**This run.** `20261111-013504-f3a83c7`, from a clean checkout of commit `f3a83c7` on the 96-core server, in the
radiarch image built from `e486b71` with the checkout mounted over its code, capped at 32 BLAS threads (6.9 hours).
Its work files were kept for the leak measurement. `run-summary.md` lists every check, and `results.json` holds the
full numbers.

**Every graded check passes (38), as before.** Only the parts built from arcs move:
- Unchanged, every value equal to the rerun of 2026-11-08: the seven static fields' Pareto set, navigation,
  deliverable plan, second set and plan on it; the R10 reweighting plan; and the arcs' Pareto set and its navigation.
  The arcs' leaves are placed after navigation.
- Changed: the arcs' deliverable plan, the arcs' second set, and the protocol's plan on that set.

## The arcs' deliverable plan

The deliverable arcs are a little farther from the navigated plan in the organs, and a little closer in the target.
Its deviation table flags 9 rows, as before.

| Arcs: navigated → deliverable | a36fc4f | f3a83c7 |
|---|---|---|
| UniformRMS(PTV) (Gy) | 0.55 → 6.60 | 0.55 → 6.28 |
| MeanDose(Lungs-PTV) (Gy) | 9.65 → 12.39 | 9.65 → 12.80 |
| MeanDose(Heart) (Gy) | 9.91 → 16.19 | 9.91 → 16.98 |
| MeanDose(Esophagus) (Gy) | 5.29 → 11.76 | 5.29 → 12.20 |
| SpinalCord Dmax (Gy) | 10.64 → 32.39 | 10.64 → 35.23 |
| Normalisation of the deliverable plan | 1.0034 | 0.9947 |

## The arcs' second set and the plan on it

| Arcs' second set | a36fc4f | f3a83c7 |
|---|---|---|
| Plans, on | 11, on 192 arc intervals | 11, on 192 arc intervals |
| Plans whose solve converged | 1 | 3 |
| Error bound, 6 → 11 plans (informative; the case's tolerance is 0.05) | 1.054 → 0.910 | 0.993 → 0.891 |
| Each converged plan is the best of the set (limit 0.01) | 0.0 (one plan) | 0.0 (three plans) |
| Plans dominated by another plan | 0 | 0 |
| PTV gEUD (a = −10), worst plan, against its limit | 64.820 against 64.820 | 64.623 against 64.623 |
| PTV Dmin, worst plan (at least 54, tolerance 0.1) | 54.274 | 54.111 |
| PTV Dmax, worst plan (at most 72, tolerance 0.72) | 72.673 | 72.385 |
| SpinalCord Dmax, worst plan (at most 45) | 33.397 | 32.852 |
| Plan on the second set: normalisation | 0.9999 | 0.9984 |
| Plan on the second set: flagged rows of its deviation table | 0 | 0 |

The gEUD limit is the deliverable plan's own gEUD, so it changes with that plan.

| Protocol goal, plan on the arcs' second set | a36fc4f | f3a83c7 | Target |
|---|---|---|---|
| PTV V60Gy (%) | 95.35 | 95.29 | >= 95.0 |
| PTV D0.03cc (Gy) | 72.50 | 72.08 | <= 72.0 (informative) |
| Lungs-GTV V20Gy (%) | 21.24 | 20.93 | <= 37.0 |
| Lungs-GTV Dmean (Gy) | 13.74 | 13.26 | <= 20.0 |
| SpinalCord D0.03cc (Gy) | 27.18 | 27.62 | <= 50.5 |
| Esophagus Dmean (Gy) | 10.67 | 9.71 | <= 34.0 (informative) |
| Heart V60Gy (%) | 0.73 | 0.46 | <= 33.0 (informative) |
| Heart V45Gy (%) | 3.16 | 2.77 | <= 66.0 (informative) |
| Heart V40Gy (%) | 4.86 | 4.39 | <= 100.0 (informative) |

At the same coverage, the protocol's arc plan gives the oesophagus 1.0 Gy less, the lungs 0.5 Gy less and the heart a
little less, and its PTV maximum is 0.4 Gy lower. The cord's maximum is 0.4 Gy higher.

## The arcs' second set: a known limitation

The arcs' second set still converges poorly: 3 of its 11 solves within 2000 iterations, with the error bound at 0.89
against the case's 0.05. Every plan meets the set's limits within their tolerances, and none is dominated. The plan
made on the set is deliverable, and its deviation table flags no row.

The diagnosis of 2026-11-08 (`docs/impl-log.md`, "R11.11: the arcs' second set, a diagnosis") found why. On the
arcs' apertures, with every meterset at or above the machine's minimum, no plan meets PTV Dmax within 0.25 Gy while
the gEUD limit holds. The plans' trade-offs lie inside the rest of that tolerance, at different depths. Scaled
metersets converge, but then fail the best-of-set check, and solving to a tenth of each tolerance fails. R11 closes
with this as a known limitation: the error bound is reported with every second set, so a user sees how far its
plans are from converged.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout f3a83c7
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases mco_protocol_lung    # about 7 hours on 32 threads
```

The case reads the demo patient (NSCLC-Radiomics LUNG1-002) from `RADIARCH_VALIDATION_DATA`, outside the repository.
