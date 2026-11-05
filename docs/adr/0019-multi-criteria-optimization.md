# ADR 0019 — Multi-criteria optimization: Pareto sets, navigation, deliverable plans

Date: 2026-10-29. Status: accepted. Roadmap R11 ("Multi-criteria optimization").

## Context

Before R11, radiarch made a plan by weighted-sum optimization with goal-driven reweighting rounds (R10): a goal that
failed got more weight, and the planner saw one plan at a time. Trading one organ's dose against another's meant
replanning. The commercial systems radiarch is compared with offer multi-criteria optimization (MCO) instead:
RayStation computes a set of Pareto-optimal plans and lets the planner move between them with sliders; Eclipse's
MCO does the same on its own optimizer. The literature behind both is open: the sandwich algorithm, the navigation
linear program, dose mimicking for the deliverable plan, and the scenario-wise worst case for robust plans.

The research report `docs/reports/mco-research-and-design.md` reviews that literature and the two products and
states nine design decisions (D1 to D9), each with what was built. This ADR records the decisions in brief and their
consequences. The validation record `docs/validation/2026-10-31-r11/` tests them on TG-119, a lung patient and a
proton phantom.

## Decisions

1. **Convex trade-offs that read in Gy; hard constraints that hold** (D1, D2). A Pareto set takes two to eight
   trade-off objectives: mean dose, gEUD above or below a level, RMS above or below a level, RMS around a dose. Each is
   convex, so a blend of plans is bounded by the blend of their values; DVH surrogates and the two-sided EUD are
   refused. Hard constraints (Dmax, Dmin, Dmean, gEUD) are met within a tolerance by an augmented-Lagrangian loop
   around L-BFGS-B, after a feasibility run that refuses an impossible set and names its constraints.
2. **The Pareto set by the sandwich algorithm to a stated error** (D3, D4). Anchor plans, a balance plan, then plans
   at the weights the worst vertex of the outer set gives, until the error bound (the largest distance from any
   Pareto point to the plans' hull, normalized) reaches a tolerance or the plan budget (default 3N + 1). The bound is
   recorded after every plan. It is approximate: it takes the plans whose cost stopped falling as optimal (see the
   consequences). Each plan's dose is stored on the navigation voxels only.
3. **Navigation is a linear program over the blend; automatic navigation works by goal priority** (D5, D6). A slider
   move, a reference point, clamps and locks are one LP over the blend weights; the blended dose is evaluated exactly,
   with goals and DVHs, in well under a second. Automatic navigation meets a goal template level by level, a met
   higher goal held. Radiarch's own method, built from published parts; RayStation's is not published.
4. **The deliverable plan mimics the navigated dose and reports the difference** (D7). The navigated blend is made
   deliverable: static fields as sequenced apertures, arcs, or proton spots. A one-sided reference-dose objective
   pulls the deliverable dose toward the navigated one; for photons the metersets are also driven by each target's
   hot-spot term and the goals, in reweighting rounds judged after normalisation, and the meterset solve holds the
   target's coverage (a gEUD, its level calibrated over the rounds until the normalisation is near 1) and its maximum
   as hard constraints. Projecting the blend onto the
   Pareto set first (no trade-off worse) is an option, off by default (see the consequences). A deviation table gives
   every trade-off and goal, navigated against deliverable, flagged past a tolerance.
5. **Robust sets use the scenario-wise worst case** (D8). Each plan minimizes the worst scenario of its weighted sum,
   smoothed; trade-offs report their worst case over the scenarios and their nominal value; hard constraints hold in
   every scenario. The outer bound comes from each solve's own lower bound and stays valid; the gap it leaves is
   reported. Robust sets are made deliverable for protons only.
6. **One interface everywhere** (D9). API routes (run, navigate, auto-navigate, deliverable, states, the lookup by
   dose), the SDK's `ParetoSet`, the command line, a protocol's `mco` section that makes `radiarch plan` plan by MCO,
   and an MCO panel in the OHIF extension.

## Consequences

- A protocol can plan by MCO or by reweighting rounds. Protocols without an `mco` section keep their digests and
  their cached runs.
- Navigation shows the blend of fluence plans. A deliverable plan can differ from it; the deviation table makes the
  difference visible, and the validation record measures it. Shared-aperture Pareto sets, so that navigation shows
  the deliverable dose itself, are the follow-up if the tables show the difference matters.
- A robust photon set cannot yet be made deliverable: a sequenced photon plan would need its own scenario doses.
- Not built: nonconvex trade-offs, tail-mean (CVaR) objectives, Pareto sets across beam arrangements, more than eight
  trade-offs, isodose dragging.
- The validation record found faults in the code of R11.1 to R11.7, corrected before it ran (report, D1 and D3):
  solves stopped by L-BFGS-B's absolute gradient test before they moved, a single stalled step counted as
  convergence, the nominal dose was computed in float32, unconverged plans tightened the error bound, the RMS
  trade-offs' corner at zero stalled the solver, the augmented Lagrangian's penalty started far above the objectives'
  cost, and the robust smoothing was a fixed width at every dose scale. A solve now counts as converged when its cost
  has stopped falling (by at most 1e-5 of itself over 50 iterations). That is not a proof of optimality, so the error
  bound is approximate. A test on the gain still on offer (a Frank–Wolfe gap) was tried and dropped: on fluence
  problems it is too loose to pass. Each plan still records that gain. A certified bound is a follow-up. The Pareto
  set's key carries a version, so sets computed before the corrections are not reused.
- The record itself found that the photon deliverable step fails on the lung patient (PTV D0.03cc 86 Gy with seven
  fields, 149 Gy with two arcs, on 60 Gy; the spinal cord's maximum 41.8 Gy where the navigated plan had 10.6). The
  cause, found in the correction (R11.9, 2026-11-01): the projection onto the Pareto set that preceded sequencing
  left a sparse, spiky fluence (600 of 3,080 beamlets, three beams with no aperture above the machine's minimum
  area, 12 segments in all) where the navigated blend was smooth; the sequenced plan under-covered the target and the
  coverage normalisation inflated what was left. The deliverable plan is now made from the blend, and the projection
  is an option, off by default. The metersets are also driven by the goals and a hot-spot term in reweighting rounds
  judged after normalisation, and a beam's peaks are capped before sequencing; the record grades the normalisation
  (within 15 % of 1). At 4 mm that was not enough (normalisation 1.37 and 1.27): the apertures still under-covered the
  target and nothing in the meterset solve held coverage. The meterset solve now holds the target's gEUD (a = -10) at
  or above the coverage goal and its maximum at or below 1.2 times the prescription as hard constraints, by R11.2's
  augmented Lagrangian (`docs/reports/mco-deliverable-options.md`, option A). At 4 mm these held and the plans still
  needed 1.11: a gEUD is not the coverage goal. Its level is therefore set on the plan, multiplied by each round's
  normalisation until that is within 3 % of 1 (in fast mode 0.985 and 0.971, PTV D0.03cc 71 and 70 Gy, organ doses
  higher within their limits). The record's correction of 2026-11-04
  (`docs/validation/2026-10-31-r11/2026-11-04-correction-8102454/`) reruns the lung case at 4 mm: normalisation 0.967
  (fields) and 1.029 (arcs), PTV D0.03cc 69.7 and 74.3 Gy, every graded check passing. The fields plan is close to the
  navigated plan; the arcs plan's organ doses are well above it, within their limits, and its hot spot is above 72 Gy
  because the normalisation inside the band scales the maximum too. Keeping the deliverable plan's organ doses near
  the navigated plan's is left to shared-aperture Pareto sets (B1).
- The algorithm tests of the report's section 5 run in CI on problems with known answers (`tests/test_r11_*.py`).
  The validation cases (`mco_front`, `mco_protocol`, `mco_robust`) run on a workstation with the public data; the
  proton phantom case also runs in the nightly harness.
