# Validation record R11, 2026-10-31: guide for the reviewing physicist

Radiarch is a research treatment-planning system. These documents record how its multi-criteria optimization (MCO)
makes a set of Pareto-optimal plans, navigates it and makes the navigated plan deliverable, on a commissioning
phantom, a lung patient and a robust proton phantom. **They are research evidence, not a clinical commissioning:
radiarch is not for clinical use, and signing records a review of research evidence, not a clinical release.**

R11 adds MCO: convex trade-off objectives and hard constraints, the sandwich algorithm for the Pareto set with an
error bound, navigation as a linear program over the blend, automatic navigation by goal priority, a deliverable plan
that mimics the navigated dose and reports the difference, and robust sets by the scenario-wise worst case. ADR 0019
(`docs/adr/0019-multi-criteria-optimization.md`) gives the decisions; the research report
(`docs/reports/mco-research-and-design.md`) gives the literature and the design. The three cases ran from commit
`b4085b0`, one case per process: `20261031-012024` (TG-119) and `20261031-015552` (proton) on a 20-core workstation
with Python 3.14, `20261031-131756` (lung) on a 96-core server with Python 3.12 (the lung case's two-arc stage needs
more memory than the workstation had free). No engine changed in R11; the engines' records are R8's
(`../2026-10-23-r8/`, with its correction of 2026-10-24).

## What to review and sign

| Document | Contents | Signed by |
|---|---|---|
| [`2026-10-31-mco-v0.2.0-b4085b0.md`](2026-10-31-mco-v0.2.0-b4085b0.md) | The TG-119 C-shape Pareto set, navigation and deliverable plan against the TG-119 institutional results; the lung demo patient planned by the protocol's `mco` section, with seven static fields and with two arcs, against the R10 reweighting plan; the robust proton set against its nominal set over range and setup scenarios | medical physicist and project lead |

`run-summary.md` lists every check of the three runs in one table, and `results.json` holds their full numbers.

## What the record shows

1. **The Pareto set's machinery holds** on all three cases: the error bound never grows as plans are added, no plan is
   dominated by another, every hard constraint holds in every plan within its tolerance (TG-119: OuterTarget Dmin
   24.98 Gy against 25, Dmax 60.07 against 60; lung: PTV Dmin 53.91 against 54, spinal cord Dmax 45.04 against 45;
   proton: CTV Dmin 1.68 Gy against 1.7 in all five scenarios), and each converged plan is the best of its set in its
   own weighted sum.
2. **TG-119 (`mco_front_tg119`, 7 pass).** Two trade-offs (OuterTarget RMS under 50 Gy, Core gEUD), nine plans,
   automatic navigation to the TG-119 goals, then seven static fields sequenced. The deliverable plan meets the
   TG-119 targets: OuterTarget D95 50.1 Gy, D10 60.9 Gy (within the institutional band, 57.0 ± 2 SD = 61.4), Core D5
   6.2 Gy. Against the R10 reweighting plan it spares the core more (D5 6.2 against 10.2 Gy) and is hotter in the
   target (D10 60.9 against 53.9 Gy): the set's trade-offs contain no term on the target's hot dose beyond the 60 Gy
   hard constraint, so navigation cannot buy a lower D10. The deviation table flags this one row (navigated 58.4,
   deliverable 60.9 Gy).
3. **The error bound is loose on the photon cases, and why.** At TG-119's 200 iterations per solve no solve met the
   convergence test (the cost stopped falling by at most 1e-5 of itself over 50 iterations); the costs were still
   falling by 0.1 to 13 % per 50 iterations. An unconverged plan proves no supporting hyperplane, so the bound stays
   the box bound (0.64 from 3 plans to 9) and says nothing about the set's quality; the plans themselves are
   reported and none is dominated. On the lung's seven fields (1000 iterations) 5 of 16 plans converged and the bound
   fell from 0.76 to 0.56; on its arcs' sectors (24 beams, 19,008 beamlets) none of 8 converged and the bound stayed
   near 0.8. The proton solves (2000 iterations) all converged, and their bounds fall (robust 0.150 → 0.071 over 7
   plans; nominal 0.086 → 0.020, the case's tolerance). The bound is approximate even then: it takes a plan whose cost
   stopped falling as optimal. A certified bound is a follow-up (ADR 0019).
4. **The robust proton set (`mco_robust_proton`, 11 pass).** Two fields on MCsquare, five scenarios (nominal, range
   ±3.5 %, setup ±3 mm). Every plan's worst case is at least its nominal value, the robust gap (0.070) lies within
   the error bound (0.071), the navigated state's worst cases lie within the linear bound, and every goal is met in
   every scenario on the navigated blend. The nominal set is not a fair comparison for the robust one: no nominal
   plan meets the CTV minimum in every scenario (0 of 7), so the check "robust plans protect their worst scenario
   better than any nominal plan" had nothing to compare. The balance plans are compared as information: CTV RMS worst
   case 0.196 (robust) against 0.184 Gy (nominal, which violates the minimum), OAR mean 0.081 against 0.090 Gy.
5. **The deliverable proton plan misses the navigated D95.** Spot optimization of the navigated state gives CTV D95
   1.79 Gy against the navigated 1.90 (the goal); the deviation table flags it (tolerance 0.04 Gy). The trade-offs
   themselves are met or bettered (CTV RMS 0.33 → 0.16, OAR mean 0.11 → 0.07 Gy).
6. **Lung (`mco_protocol_lung`, 20 pass).** The demo patient planned by the `demo-lung-imrt-mco` protocol: five
   trade-offs (PTV uniformity, lung, heart and esophagus mean dose, spinal cord gEUD), two hard constraints, a Pareto
   set of 16 plans on seven static fields, automatic navigation by the protocol's goals, the deliverable plan; then
   the same protocol on two arcs (a Pareto set of 8 plans on the arcs' sectors). Both deliverable plans pass the
   protocol's graded goals: seven fields PTV V60 95.2 %, lungs V20 18.9 %, lungs mean 11.9 Gy, cord D0.03cc 4.9 Gy
   (the R10 reweighting plan: 95.4 %, 19.8 %, 11.0 Gy, 35.7 Gy); two arcs 95.1 %, 18.0 %, 13.1 Gy, 38.9 Gy.
7. **A fault found by this run: the deliverable lung plans are not acceptable plans.** The navigated plans are
   uniform (PTV RMS 0.5 Gy), but the deliverable plans made from them are not: with seven fields the PTV RMS goes
   0.48 → 11.2 Gy and the PTV's hottest 0.03 cc receives 85.8 Gy on a 60 Gy prescription (the protocol's informative
   limit is 72 Gy; the reweighting plan gives 69.5); with two arcs the RMS goes 0.55 → 24.2 Gy, the hottest 0.03 cc
   receives 149 Gy, the spinal cord's maximum goes 10.6 → 41.8 Gy (the hard constraint is 45), and the plan needs
   319,505 MU against 37,000 for the fields. The graded goals pass because they are coverage and organ limits; the
   deviation tables (2 and 4 flagged rows) and the hot-spot rows show the fault. The mechanism, from the run's log:
   the deliverable step sequences the navigated fluence once (18 segments for the seven fields, where the R10 loop's
   three rounds make 43) and re-optimizes the metersets for 200 iterations against the navigated dose, the result
   under-covers the PTV, and the normalisation to the coverage goal then scales the plan by 1.17 (fields) and 1.42
   (arcs), inflating the hot spots. TG-119's and the proton's deliverable plans did not show this; the fault appears
   on a real geometry. **The deliverable step is to be corrected (sequencing and meterset rounds as in R10, a
   hot-spot term in the mimic, more iterations, the judgement made after normalisation) and the lung case rerun as a
   dated correction of this record**, as R8's record was corrected on 2026-10-24. Until then the lung deliverable
   plans of this record are evidence of the fault, not plans to compare with.
8. **Faults found by the record's development runs, corrected before it ran** (ADR 0019): solves stopped by
   L-BFGS-B's absolute gradient test before they moved; a single stalled step counted as convergence; the nominal dose
   in float32; unconverged plans tightening the bound; the RMS trade-offs' corner at zero; the penalty of the
   augmented Lagrangian starting far above the objectives' cost; the robust smoothing's fixed width; and a
   robust-against-nominal check that compared with nominal plans that violate the hard constraints in the scenarios.

## Questions we would most like answered

1. **Trade-off choice.** The TG-119 set trades target uniformity (RMS under the prescription) against core gEUD, and
   the result is hotter in the target than the reweighting plan. Which trade-offs would a planner want on the
   sliders for a C-shape or a lung case, and should a hot-dose term (RMS over the prescription) be a default trade-off
   rather than only a hard constraint?
2. **Convergence.** Is "the cost stopped falling" (1e-5 of itself over 50 iterations) an acceptable statement of a
   plan's convergence for a research record, and what iteration budget per plan would you accept for a 9-plan set
   (TG-119 took 33 minutes at 200 iterations; the lung's arc plans took 35 minutes each at 1000)?
3. **The deliverable plan's deviation.** The deviation table flags one row on TG-119 (D10) and one on the proton
   phantom (D95), and the lung's deliverable plans fail outright (item 7). Must the deliverable plan meet every goal
   the navigated plan met, and which deviation would you accept when the planner sees it?
4. **Robustness.** Are range ±3.5 % and setup ±3 mm, as five scenarios with the worst case taken over them, the
   scenarios you would want, and should a robust set report the nominal set beside it as this record does?

## How to sign

Either reply to the covering email with your comments and a statement that you reviewed the named document at
commit `b4085b0`, which we then record in its signature table with the date and a reference to your email; or print
its signature section, sign and date it, and return a scan. Comments that lead to changes produce a new run and new
documents; a signature always refers to one commit.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout b4085b0
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases mco_front_tg119      # about 55 minutes
.venv/bin/python -m radiarch.validation.run --cases mco_robust_proton    # about 35 minutes; needs MCsquare
.venv/bin/python -m radiarch.validation.run --cases mco_protocol_lung    # about 8 hours; about 7 GB of memory at the arc stage
.venv/bin/python -m radiarch.validation.report --engines mco --results validation/results/<first run> --also validation/results/<second run> validation/results/<third run>
```

The lung case reads the demo patient (NSCLC-Radiomics LUNG1-002) from a data directory outside the repository,
`RADIARCH_VALIDATION_DATA` (default `../data/public`); the TG-119 and proton cases are synthetic phantoms and need no
data. The proton case needs MCsquare (`RADIARCH_MCSQUARE_DIR`).
