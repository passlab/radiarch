# R11.9: two designs for the MCO deliverable plan

Status: a note for the project lead's choice, 2026-11-03. Radiarch is not for clinical use.

## The problem

A Pareto set in radiarch is a set of fluence plans, and navigation shows a blend of them. The deliverable plan is made
afterwards: apertures are cut from the navigated fluence, their metersets are optimized toward the navigated dose,
and the plan is normalised to the target's coverage goal. On the lung patient of the R11 record that last step does
the damage. The apertures under-cover the target, so the normalisation has to scale the plan up, and it scales the hot
spots with it.

| Lung demo patient, 4 mm grid, 60 Gy | Normalisation | PTV D0.03cc |
|---|---|---|
| R10 reweighting plan (seven fields, the reference) | 1.065 | 69.5 Gy |
| R11 record, seven fields / two arcs (commit `b4085b0`) | 1.17 / 1.42 | 86 / 149 Gy |
| R11.9 as pushed, seven fields / two arcs (commit `632e151`) | 1.37 / 1.27 | 102 / 93 Gy |

What the runs established:
- The navigated blend is smooth: on the seven fields, 2,904 of 3,080 beamlets are open and no beam's peak is above five
  times its median. Sequencing it at the protocol's 5 fluence levels gives 42 to 57 segments, close to the R10 plan's 43.
- The apertures cannot reproduce the blend's dose, and the meterset solve then has nothing that holds coverage. It
  meets the mimic and the organ goals, and leaves the target short for the normalisation to fix.
- Three corrections did not help: goal-driven meterset rounds (every goal passes after normalisation, so only one round
  runs); a cap on the target's maximum (it drove all metersets down); and re-optimizing the fluence before
  sequencing (normalisation 4.57, reverted).

## Option A: coverage as a hard constraint in the meterset solve

**What.** Make coverage a hard constraint of the last solve, the one over segment metersets (fields) or
control-point-interval metersets (arcs). The mimic and the organ goals stay its objective. The augmented-Lagrangian loop
of R11.2 (`services/hard_constraints.py`) already does this for fluence. Only convex constraints fit it, so coverage
would be stated as gEUD with a negative exponent (close to a minimum dose) at or above the prescription. The hot spot
would be a second hard constraint, Dmax at or below 1.15 times the prescription, which is the R10 plan's level. The
normalisation becomes a check, near 1, instead of a correction.

**Cost.** About a day of code and tests: the two meterset solvers gain constraint terms, and the deliverable request
gains the two limits. Then a fast check and a 4 mm rerun on the compute server (about 5 hours).

**For it.** It is small, reuses tested machinery, and works for fields and arcs alike. It turns the record's graded
check (normalisation within 15 % of 1) into a real test of the deliverable plan.

**Against it.** It treats the symptom: the apertures still come from a blend whose dose they may not reach. If no
meterset choice covers the target within the hot-spot limit, the feasibility run says so, and the fix is more fluence
levels or another round of sequencing. The deliverable plan will also still differ from the navigated one; the
deviation table shows by how much.

## Option B: Pareto plans that share their apertures

**What.** Navigate over plans that are already deliverable, so the plan on the screen is the plan delivered. A blend of
metersets on the same apertures is itself a deliverable plan. The research report (section 2.4) lists the published
forms; two fit radiarch:
- **B1, two stages** (Bokrantz, Med Phys 39:6712, 2012). Navigate on fluence as now, sequence the navigated plan once,
  then build a second, small Pareto set over the segment metersets of those apertures and navigate again. In radiarch
  the second set is an MCO run whose fluence elements are segments; the sequencing service's segment dose matrix gives
  its dose.
- **B2, one shared pool** (Salari & Unkelbach, PMB 58:621, 2013; Fredriksson & Bokrantz, PMB 58:7683, 2013). Generate
  every Pareto plan from one shared aperture pool. For arcs, the published form uses sweeps whose start and end
  positions are common to every plan (Craft, Papp & Unkelbach, Med Phys 41:021709, 2014).

**Cost.** B1: about three days, plus a second navigation step in the API, the SDK and the viewer's MCO panel. B2: one to
two weeks. The Pareto generation changes, and the arcs need shared sweeps.

**For it.** It removes the gap between navigated and deliverable plans instead of measuring it. It is the follow-up
ADR 0019 already names.

**Against it.** It is larger. B1 makes the planner navigate twice. Neither variant has been tried here, so the first
lung run is the first evidence.

## Comparison

| | A: coverage constraint | B1: two stages | B2: shared pool |
|---|---|---|---|
| Change | meterset solve | new second Pareto set | Pareto generation |
| Effort | about 1 day | about 3 days | 1 to 2 weeks |
| Navigated equals delivered | no (gap shown in the table) | after the second navigation | yes |
| Fields and arcs | both | both | fields first; arcs need shared sweeps |
| Risk | infeasible with few levels | apertures fixed by the first plan | the largest change |

## Recommendation

A first. It is small, it makes the deliverable plans acceptable, and it gives the record's check meaning. Then B1, which
reuses A's constrained meterset solve as the second stage. B2 only if the deviation tables after A and B1 still show
gaps that matter. Each step is checked on the lung case at 4 mm before it is called done, and the R11 record gets its
dated correction once a run passes.

## B1 as built (R11.11, 2026-11-06)

Option A was built first (R11.9) and corrected the lung case's normalisation. B1 follows, as recommended.

**The second set.** `POST /mco/deliverables/{id}/pareto` builds a small Pareto set over a deliverable photon plan's
metersets: the segment MU of static fields, or the interval MU of arcs (`services/mco_apertures.py`). Its trade-offs
are the first set's, and it is stored like any Pareto set, so navigation, automatic navigation and
`POST /mco/{id}/deliverable` work on it unchanged. Every plan keeps the deliverable plan's apertures, so a blend of
plans is a meterset vector on those apertures. Making a navigated state the plan changes only the metersets.

**Its dose.** Static fields: the open-field dose matrix times each segment's coverage of the beamlets, the
sequencer's own computation. The plan's dose is therefore the navigated dose exactly (a test holds it to 1e-3 Gy).
Arcs: the pencil beam's dose per MU of each control-point interval, which the VMAT meterset solve also uses. The plan's
dose is then the full kernel's, as for any arc plan, so the deviation table measures the difference.

**Its limits.**
- The first set's hard constraints.
- With `hard_coverage`, the target's gEUD (a = -10) no lower than the deliverable plan's own, and the target's maximum at
  or below `max_dose_factor` times the prescription. Both hold within 1 % of their level.
- Every meterset at or above the machine's minimum (a segment's minimum MU, an interval's dose-rate floor). The solves
  run on the metersets above it.

A feasibility run starts from the deliverable plan. Where it cannot meet a limit with the others, that limit is relaxed
to the value the run reaches, and a note names it. The second set therefore always exists, and no plan in it is worse
than that run on any limit. A blend keeps every convex limit, so the navigated plan keeps the coverage too, and its
normalisation is a check near 1.

**In a protocol.** The `mco` section's `second_set` (default on) navigates the second set automatically by the same
goals and makes that state the plan. The run's `mco_id`, `state_id` and `deliverable_id` are then the second set's;
its `source_deliverable_id` leads back to the first.

**With it, the two follow-ups of the R11 correction:**
- *The maximum's limit divided by the normalisation.* A meterset round within the normalisation band whose target
  maximum, once normalised, passes its limit is no longer accepted. The next round keeps the coverage level and takes
  the maximum's limit divided by that normalisation. The kept round prefers one whose normalised maximum holds.
- *Each round's constraint values in the record.* Every round keeps its coverage and maximum limits, the gEUD and
  maximum reached, the maximum once normalised, and each constraint's excess.

**Closed leaf pairs.** These now wait 10 mm behind an X jaw, under the jaw's 0.2 % transmission. Before, they waited at
the edge of the field (static fields) or at its centre (arc pairs that never open). Touching rounded tips leak a line of
up to 16 % of the open dose (`docs/reports/mlc-leaf-model.md`). An arc pair that opens in some sectors still waits
where its sweep leaves it. A machine without interdigitation keeps its closed pairs where the sequencer closed them.
