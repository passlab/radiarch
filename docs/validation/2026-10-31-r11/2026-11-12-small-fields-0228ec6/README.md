# Rerun of the R11 record's photon cases, 2026-11-12: the leaf ends' tail, and no edge blur

**What changed.** From commit `0228ec6` on (`pb` 1.2.0, `LEAF_MODEL_VERSION` 4), a rounded leaf end passes half the
leaf gap as a tail beyond its tip, and the pencil beam no longer blurs a field's edge. The R8 record's rerun of the
same day (`../../2026-10-23-r8/2026-11-12-small-fields-0228ec6/`) describes the change and its checks against Monte
Carlo. Both photon cases of R11 make deliverable plans through apertures, so both are rerun:
- `mco_front_tg119` computes its Pareto set with CCC, which is unchanged. Only its apertures' dose moves, through the
  leaf ends' tail.
- `mco_protocol_lung` plans with the pencil beam, so its Pareto sets move too.

Their numbers in the reruns of 2026-11-08 (`../2026-11-08-second-set-a36fc4f/`, `mco_front_tg119`) and 2026-11-10
(`../2026-11-10-arc-pairs-toward-jaw-f3a83c7/`, `mco_protocol_lung`) are superseded by these runs. The proton case has
no apertures and stands as recorded.

**These runs.** One case per process, from a clean checkout of commit `0228ec6` on the 96-core server, in the radiarch
image built from `48c0cc4` with the checkout mounted over its code: `mco_front_tg119` (`20261112-144407-0228ec6`, 6
BLAS threads, 1.3 hours) and `mco_protocol_lung` (`20261112-185958-0228ec6`, 32 BLAS threads, 5.6 hours).
`run-summary.md` lists every check, and `results.json` holds the full numbers.

**The lung case passes every graded check (38), as before. TG-119 passes 18 of its 19.** The one that fails, the
first set's deliverable plan's core D5, is in the next section. Every check that grades a Pareto set's best-of-set
condition reads 0.0 against 0.01.

## TG-119: the first set's deliverable plan misses the core's limit by 0.01 Gy

`mco_front_tg119` passes 18 of its 19 graded checks. The one that fails grades the deliverable plan made from the
first Pareto set:

| Check | a36fc4f | 0228ec6 | Target | Result |
|---|---|---|---|---|
| Deliverable plan (first set): Core D5 (Gy) | 22.40 | 22.45 | at most 10.0, or 22.44 (the institutions' mean 16.3 Gy plus two SD) | pass → fail |
| Plan on the second set: Core D5 (Gy) | 19.32 | 19.14 | the same | pass |
| Plan on the second set: OuterTarget D10 (Gy) | 58.40 | 58.35 | at most 55.0, or 61.42 | pass |

**The cause.** The navigated plan meets the core's limit (10.00 Gy). Turning its fluence into apertures loses most of
that sparing: the core's D5 rises to 22.45 Gy. This is the first set's known loss from fluence to apertures
(`docs/reports/mco-deliverable-options.md`), which the second set was built to recover. The plan on the second set,
which reweights the deliverable plan's own apertures, recovers 3.3 Gy of it (19.14 Gy) and passes. The leaf ends' tail
adds 0.05 Gy to the first set's loss, enough to cross the institutions' limit by 0.01 Gy. Direct aperture
optimization, the open item that removes the loss at its source (`docs/reports/open-items-plan.md`, item C), is the
cure.

The check stays failing in this record, and no tolerance changed. It is recorded as a finding in
`src/radiarch/validation/known_findings.yaml` (the project lead's decision), so the nightly validation run does not
report it as a new failure.

## The lung case: the seven-field plan lands on another trade-off

The pencil beam's beamlets change, so every Pareto set of the case changes. The seven static fields' set keeps its
shape: 16 plans, 5 of them converged, none dominated, and an error bound of 0.560 with 16 plans (0.555 before). The
automatic navigation meets the same goals, then sets the trade-offs as low as the goals allow, as their sum over the
set's range. On the new set that sum is lowest at another blend: the cord and the oesophagus get more dose, and the
heart's high doses fall. Every goal still passes, and the cause was not diagnosed further.

| Protocol goal, plan on the seven fields' second set | f3a83c7 | 0228ec6 | The reweighting plan, 0228ec6 | Target |
|---|---|---|---|---|
| PTV V60Gy (%) | 95.32 | 95.33 | 95.28 | >= 95.0 |
| PTV D0.03cc (Gy) | 72.02 | 71.35 | 69.80 | <= 72.0 (informative) |
| Lungs-GTV V20Gy (%) | 20.99 | 20.91 | 20.09 | <= 37.0 |
| Lungs-GTV Dmean (Gy) | 12.56 | 12.13 | 11.24 | <= 20.0 |
| SpinalCord D0.03cc (Gy) | 4.56 | 21.38 | 33.03 | <= 50.5 |
| Esophagus Dmean (Gy) | 1.14 | 3.25 | 9.93 | <= 34.0 (informative) |
| Heart V60Gy (%) | 4.23 | 0.33 | 0.18 | <= 33.0 (informative) |
| Heart V45Gy (%) | 5.31 | 2.98 | 1.26 | <= 66.0 (informative) |
| Heart V40Gy (%) | 6.12 | 3.92 | 2.43 | <= 100.0 (informative) |

The MCO plan still gives the cord and the oesophagus less than the reweighting plan of the same case. The first
set's deliverable plan now flags 8 rows of its deviation table (6 before). The second set converges in all 11 plans,
as before, and the plan made on it flags none.

## The lung case's arcs

| Arcs' second set | f3a83c7 | 0228ec6 |
|---|---|---|
| Plans, on | 11, on 192 arc intervals | 11, on 192 arc intervals |
| Plans whose solve converged | 3 | 1 |
| Error bound, 6 → 11 plans (informative; the case's tolerance is 0.05) | 0.993 → 0.891 | 1.031 → 0.854 |
| Each converged plan is the best of the set (limit 0.01) | 0.0 (three plans) | 0.0 (one plan) |
| Plans dominated by another plan | 0 | 0 |
| PTV Dmin, worst plan (at least 54, tolerance 0.1) | 54.111 | 54.124 |
| PTV Dmax, worst plan (at most 72, tolerance 0.72) | 72.385 | 72.469 |
| SpinalCord Dmax, worst plan (at most 45) | 32.852 | 39.495 |
| Plan on the second set: normalisation | 0.9984 | 1.0020 |
| Plan on the second set: flagged rows of its deviation table | 0 | 0 |

| Protocol goal, plan on the arcs' second set | f3a83c7 | 0228ec6 | Target |
|---|---|---|---|
| PTV V60Gy (%) | 95.29 | 95.39 | >= 95.0 |
| PTV D0.03cc (Gy) | 72.08 | 72.46 | <= 72.0 (informative) |
| Lungs-GTV V20Gy (%) | 20.93 | 22.29 | <= 37.0 |
| Lungs-GTV Dmean (Gy) | 13.26 | 14.65 | <= 20.0 |
| SpinalCord D0.03cc (Gy) | 27.62 | 32.26 | <= 50.5 |
| Esophagus Dmean (Gy) | 9.71 | 10.97 | <= 34.0 (informative) |
| Heart V60Gy (%) | 0.46 | 0.67 | <= 33.0 (informative) |
| Heart V45Gy (%) | 2.77 | 2.76 | <= 66.0 (informative) |
| Heart V40Gy (%) | 4.39 | 5.13 | <= 100.0 (informative) |

The protocol's arc plan gives the lungs 1.4 Gy more and the cord 4.6 Gy more than before, at the same coverage. The
deliverable arcs' deviation table flags 9 rows, as before. The arcs' second set stays the known limitation the rerun
of 2026-11-10 describes: 1 of its 11 solves converges, with the error bound at 0.85 against the case's 0.05. Every
plan meets the set's limits within their tolerances, none is dominated, and the plan made on the set is deliverable.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout 0228ec6
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases mco_front_tg119
.venv/bin/python -m radiarch.validation.run --cases mco_protocol_lung    # about 6 hours on 32 threads
```

The cases read TG-119's phantom and the demo patient (NSCLC-Radiomics LUNG1-002) from `RADIARCH_VALIDATION_DATA`,
outside the repository.
