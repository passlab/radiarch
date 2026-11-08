# Rerun of the R11 record, 2026-11-08: a second Pareto set on the deliverable plan's apertures

**What changed.** R11.11 (option B1 of `docs/reports/mco-deliverable-options.md`, section "B1 as built") adds a
second, small Pareto set over a deliverable photon plan's metersets: the segment MU of static fields, or the interval
MU of arcs. Its plans share the deliverable plan's apertures, so the plan made by navigating it is deliverable with
the navigated dose (static fields exactly; arcs up to the full kernel against the pencil beam). The validation cases
`mco_front` and `mco_protocol` build the second set after the deliverable plan, navigate it by the same goals, and
make that state the plan. They keep every earlier check under its name, add the second set's checks, and grade the
plan made on it. The same round of commits parks closed leaf pairs under an X jaw (the R8 record's rerun
`../../2026-10-23-r8/2026-11-07-parked-leaf-pairs-b11713b/` describes it). Both photon cases are rerun. Their numbers
in the rerun of 2026-11-05 (`../2026-11-05-leaf-model-412a105/`) are superseded by these runs. The proton case has
no apertures and stands as recorded.

**These runs.** Two runs, one case per process, from a clean checkout of commit `a36fc4f` on the 96-core server, in
the radiarch image built from `55ab566` with the checkout mounted over its code: `20261108-014402-a36fc4f`
(`mco_front_tg119`, 6 BLAS threads, 1.3 hours) and `20261108-072324-a36fc4f` (`mco_protocol_lung`, 32 threads,
7.0 hours). `run-summary.md` lists every check, and `results.json` holds the full numbers.

**Every graded check passes:** 19 in `mco_front_tg119` (8 in the rerun of 2026-11-05) and 38 in `mco_protocol_lung`
(22 before). The added checks are the second sets' and the plans made on them.

## Two earlier rounds, kept beside this one

The second set took three commits to pass its record. The two earlier rounds ran the same way and are kept here.

1. **From `b11713b`** (`results-b11713b.json`, `run-summary-b11713b.md`; runs `20261107-031801` and
   `20261107-084437`). Both cases failed one check.
   - TG-119: the plan on the second set was not deliverable. The likely cause was a segment that every plan holds at
     the 2 MU minimum, blended to 1.9999999999999998 MU by rounding. None of the five plans converged within the
     case's 200 iterations (error bound 0.80).
   - Lung, seven fields: "each converged plan is the best of the set in its own weighted sum" read 0.0538 (limit
     0.01). The arcs' second set had no converged plan (0 of 11), so its check had nothing to grade.
2. **From `e03cd6d`** (`results-e03cd6d.json`, `run-summary-e03cd6d.md`; runs `20261107-055230` and
   `20261107-112735`). A blend's metersets are held at the machine's minimum, and the second set has its own budget
   of 2000 iterations. TG-119 passed every check (5 of 5 plans converged, error bound 0.031). The lung case failed the
   best-of-set check in both second sets: 0.0538 with seven fields, 0.2033 with two arcs.
3. **The cause.** A rerun from `e03cd6d` with its work files kept reproduced both values. A solve may stop anywhere
   inside a limit's tolerance. Inside the target's coverage limit (gEUD at least the deliverable plan's, within 1 %),
   a plan gives less dose, and less dose scores better on every objective. With seven fields, the UniformRMS anchor
   used 13 % of that tolerance and the balance plan 91 %, so the balance plan beat the anchor on all five
   objectives. The second set's spans are narrow (UniformRMS 1.33 Gy with seven fields, 0.16 Gy with arcs), so the
   check, normalised by the span, sees it. A stricter stall rule, scaled variables and a re-solve from the beating
   plan did not pass the check (0.017 at best).
4. **From `a36fc4f`** (this round). Each solved plan's metersets are scaled up until it meets every lower limit
   exactly, stopping where an upper limit reaches its tolerance. The dose is linear in the metersets, so the scaling
   is exact. Both checks read 0.0. The check's limit (0.01) and every tolerance are unchanged.

## TG-119 (`mco_front_tg119`)

The first Pareto set, its navigation and its deliverable plan equal the rerun of 2026-11-05 to within 0.01 Gy
(Core D5 22.40 Gy, OuterTarget D10 56.05 Gy, normalisation 1.028).

- **The second set:** 5 plans on the deliverable plan's 70 segments. All 5 converged, and the error bound falls
  0.128 → 0.112 → 0.031, within the case's 0.05. No plan is dominated, and the best-of-set check reads 0.0.
- **Its limits.** OuterTarget Dmin 39.23 Gy (at least 25). Dmax 60.10 Gy, at the first set's limit of 60 Gy plus its
  tolerance of 0.1. Two checks carry the name "OuterTarget Dmax <= 60.0 Gy": the first set's limit (tolerance 0.1)
  and the second set's maximum at the prescription times `max_dose_factor`, also 60 Gy here (tolerance 0.6). The
  target's gEUD is 52.84 Gy against the deliverable plan's 53.31, within its 1 % tolerance (0.53). The scaling to
  the lower limits stopped at the Dmax limit, before the gEUD reached 53.31.
- **The plan on the second set** is deliverable, with normalisation 1.002 and no flagged row in its deviation table.

| TG-119 goal | Deliverable plan (first set) | Plan on the second set | Target |
|---|---|---|---|
| OuterTarget D95 (Gy) | 50.1 | 50.1 | >= 50.0 |
| OuterTarget D10 (Gy) | 56.05 | 58.40 | <= 55.0 (or <= 61.42: institutional mean 57.02 ± 2 SD) |
| Core D5 (Gy) | 22.40 | 19.32 | <= 10.0 (or <= 22.44: institutional mean 16.3 ± 2 SD) |

On the second set, navigation by the TG-119 goals lowers the core's D5 by 3.1 Gy at the same coverage, for 2.4 Gy
more in the target's D10. Both plans pass only through the institutions' limits. The core's D5 is still nearly
twice TG-119's goal of 10 Gy; the navigated plan on the beamlets reached 10.00 Gy, and the navigated plan on the second
set 19.28 Gy. The second set only reweights the deliverable plan's 70 segments; it does not change their shapes.

## Lung (`mco_protocol_lung`)

The first Pareto sets, their navigations, their deliverable plans and the reweighting plan equal the rerun of
2026-11-05 to within 0.11 (Gy or percentage points). The protocol's plan is now the plan on the second set, so the
protocol's goal rows ("MCO plan") change.

| Second set | Seven static fields | Two arcs |
|---|---|---|
| Plans, on | 11, on 75 segments | 11, on 192 arc intervals |
| Plans whose solve converged | 11 | 1 |
| Error bound, 6 → 11 plans (informative; the case's tolerance is 0.05) | 0.475 → 0.337 | 1.054 → 0.910 |
| Each converged plan is the best of the set (limit 0.01) | 0.0 | 0.0 (one plan) |
| Plans dominated by another plan | 0 | 0 |
| PTV gEUD (a = −10), worst plan, against its limit | 64.358 against 64.358 | 64.820 against 64.820 |
| PTV Dmin, worst plan (at least 54, tolerance 0.1) | 54.005 | 54.274 |
| PTV Dmax, worst plan (at most 72, tolerance 0.72) | 72.631 | 72.673 |
| SpinalCord Dmax, worst plan (at most 45) | 6.885 | 33.397 |
| Plan on the second set: normalisation | 0.9917 | 0.9999 |
| Plan on the second set: flagged rows of its deviation table | 0 | 0 |

| Protocol goal | Seven fields: 2026-11-05 | Seven fields: second set | Two arcs: 2026-11-05 | Two arcs: second set | Target |
|---|---|---|---|---|---|
| PTV V60Gy (%) | 95.27 | 95.32 | 95.24 | 95.35 | >= 95.0 |
| PTV D0.03cc (Gy) | 69.66 | 72.02 | 72.32 | 72.50 | <= 72.0 (informative) |
| Lungs-GTV V20Gy (%) | 20.91 | 20.99 | 21.64 | 21.24 | <= 37.0 |
| Lungs-GTV Dmean (Gy) | 12.38 | 12.56 | 14.18 | 13.74 | <= 20.0 |
| SpinalCord D0.03cc (Gy) | 5.56 | 4.56 | 32.32 | 27.18 | <= 50.5 |
| Esophagus Dmean (Gy) | 1.59 | 1.14 | 11.76 | 10.67 | <= 34.0 (informative) |
| Heart V60Gy (%) | 3.64 | 4.23 | 0.68 | 0.73 | <= 33.0 (informative) |
| Heart V45Gy (%) | 5.25 | 5.31 | 3.29 | 3.16 | <= 66.0 (informative) |
| Heart V40Gy (%) | 5.69 | 6.12 | 5.28 | 4.86 | <= 100.0 (informative) |

- **Seven fields.** The plan on the second set gives the cord and the oesophagus less dose (by 1.0 and 0.45 Gy) and
  the heart and the lungs a little more, with a hotter PTV. Its hottest 0.03 cc is 72.02 Gy, 0.02 Gy above the protocol's informative 72 Gy; the second
  set's limit on the PTV maximum is 72 Gy within 1 %.
- **Two arcs.** The plan on the second set lowers the cord's maximum by 5.1 Gy, the oesophagus mean by 1.1 Gy and
  the lungs' mean by 0.4 Gy at the same coverage. The arcs' deliverable plan was far from its navigated plan (9
  flagged rows; cord maximum 10.6 Gy navigated, 32.3 Gy deliverable). The second set recovers part of that gap by
  reweighting the arcs' intervals; it does not change their leaf positions.
- **The arcs' second set converges poorly:** 1 of 11 plans, with the error bound at 0.91. The best-of-set check
  grades that one plan. The plans are reported, and none is dominated. This is open (below).

## Open

- **The arcs' second set.** Only 1 of its 11 solves converged within 2000 iterations. In the diagnosis, the metersets
  scaled by their dose per MU converged 11 of 11 (error bound 0.285), before the scaling to the lower limits. The
  two together have not been run.
- **Two checks share a name** in TG-119 ("OuterTarget Dmax <= 60.0 Gy in every plan"), as above. Both pass.

## How to reproduce (optional)

```bash
git clone https://github.com/passlab/radiarch && cd radiarch && git checkout a36fc4f    # b11713b, e03cd6d for the earlier rounds
python3 -m venv .venv && .venv/bin/pip install -e "./src[dev,validation]"     # Python 3.12 or later
.venv/bin/python -m radiarch.validation.run --cases mco_front_tg119
.venv/bin/python -m radiarch.validation.run --cases mco_protocol_lung    # about 7 hours on 32 threads
```

The cases read the TG-119 phantom and the demo patient (NSCLC-Radiomics LUNG1-002) from `RADIARCH_VALIDATION_DATA`,
outside the repository.
