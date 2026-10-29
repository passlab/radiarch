# Multi-criteria optimization in radiarch: research and design (R11)

Status: proposal, 2026-10-29, for review before R11 starts. Inputs: the published literature on multi-criteria
optimization (MCO) in radiotherapy planning, the public record of RayStation's and Eclipse's MCO, and radiarch's
optimizer as of commit `6ab2b82`. Section 6 states what was not verified. The decisions in §4 become ADR 0019 once R11
is built, as in earlier items.

## 1. The problem and why radiarch needs it

Radiarch plans by minimizing one weighted sum of objectives, `L(w) = Σ_i ω_i f_i(D w)`, over beamlet or spot weights
`w ≥ 0` (ADR 0002). The auto-planning loop of R10 adjusts the weights `ω_i` by rule: a failed goal gets three times
its weight and, for an organ, a 10 % lower level. Picking the weights is how a planner trades one organ against
another, and it is indirect. A weight says nothing about the plan it will give, and seeing a trade-off means a new
optimization.

MCO turns this around. It computes a set of Pareto-optimal plans up front: plans where no objective can improve without
another getting worse. The planner, or a rule, then moves between them and sees the dose and DVH change at once. Both
commercial systems radiarch is measured against have this (the evaluation report, row "MCO / Pareto navigation"):
RayStation since its MCO module, built with Massachusetts General Hospital, and Eclipse since version 15.5, with
technology licensed from Fraunhofer ITWM.

## 2. What the literature establishes

### 2.1 Convexity is the precondition

The planning problem is: minimize the vector `(f_1(d), …, f_N(d))` subject to `d = D x`, `x ≥ 0` and any hard
constraints `d ∈ C`. When every `f_i` is convex and `C` is convex, three properties hold. MCO rests on all three
(Craft 2013 review, arXiv:1305.1546; Bokrantz & Forsgren 2013):

1. **Weighted sums reach every Pareto point.** A solution of the weighted sum with all weights positive is Pareto
   optimal. Every Pareto point of a convex problem solves some weighted sum. Each solve also gives a supporting
   hyperplane of the set of attainable objective vectors.
2. **Blends stay feasible.** A convex combination `x = Σ_j λ_j x_j` of feasible plans is feasible. Its dose is exactly
   `Σ_j λ_j d_j`, because dose is linear in `x`.
3. **Blends are bounded.** `f_i(Σ λ_j x_j) ≤ Σ λ_j f_i(x_j)`. A blended plan is at least as good as the blend of its
   parents' objective values, so navigation can search with this linear bound and then show the exact values.

Convex objectives include:
- mean dose;
- generalized EUD with `a ≥ 1`, minimized for organs (Choi & Deasy, PMB 47:3579, 2002);
- generalized EUD with `a ≤ 1`, maximized for targets;
- one-sided quadratic over- and under-dose penalties;
- maximum and minimum dose;
- tail means of the dose (CVaR; Romeijn et al., Oper Res 54:201, 2006).

DVH objectives (`V20 ≤ 37 %`) are not convex. Two papers show that many clinical criteria can be replaced by convex
ones without changing the undominated plans: Romeijn, Dempsey & Li (PMB 49:1991, 2004) and Halabi, Craft & Bortfeld
(PMB 51:3809, 2006). The shared advice is to:
- keep negotiable wishes as objectives;
- make only non-negotiable limits constraints, because constraints that are too tight make the problem infeasible
  and ones that are too loose make the Pareto set needlessly large (Craft 2013);
- normalize each objective by the ideal and nadir values that the single-objective ("anchor") plans give.

### 2.2 Approximating the Pareto set

- **Random weights.** Weights drawn at random spread the plans badly (Das & Dennis 1997; Bokrantz & Forsgren 2013).
- **Sandwich algorithms.** These are the accepted method. They keep two approximations of the attainable set:
  - the inner one is the convex hull of the computed plans;
  - the outer one is the intersection of the supporting halfspaces those plans' weights give.

  The largest gap between the two bounds the approximation error. The next weight vector is chosen where the gap is
  largest. Papers:
  - Craft, Halabi, Shih & Bortfeld, Med Phys 33:3399, 2006, introduced it.
  - Rennen, van Dam & den Hertog, INFORMS J Comput 23:493, 2011, added "dummy points" so every facet normal is a
    usable weight.
  - Bokrantz & Forsgren, INFORMS J Comput 25:377, 2013, reformulated the error computation as one small linear
    program per vertex of the outer approximation. The worst vertex's dual multipliers are the next weight vector.
    With bookkeeping, this cut the work by one to two orders of magnitude and raised the tractable number of
    objectives from about six to eleven.
- **How many plans.** Craft & Bortfeld (PMB 53:2785, 2008) found that N+1 plans kept the error under 15 % in all but
  one of their cases, and 75 plans always kept it within 5 %. Clinical use runs about 2N to 4N plans for N objectives.
- **Distributed generation.** Bokrantz (PMB 58:3501, 2013) chooses k weight vectors per batch on a cheap model
  surface, so a batch of up to 2N plans runs in parallel at about ten times the speed with comparable quality.

### 2.3 Navigation

**Selection and restriction.** Monz, Küfer, Bortfeld & Thieke (PMB 53:985, 2008) define navigation on the stored
plans by two operations:
- *selection*: improve this objective;
- *restriction*: never let that one exceed a bound.

Both become small linear programs over the blend weights `λ` once the objectives are replaced by their linear bound
`Σ λ_j f_i(x_j)`, so they solve in a fraction of a second.

**The navigation LP.** Craft & Monz (Med Phys 37:736, 2010) give the explicit form, a "piercing" LP:

```
minimize h
subject to  h ≥ y_i − z_i  (every i)
            y = Σ_j λ_j F_j
            Σ_j λ_j = 1,  λ ≥ 0
```

Here `F_j` is plan j's objective vector and `z` a reference point the sliders set. Locked objectives keep their value.
Running the same LP on several Pareto sets, one per beam arrangement, picks the best set automatically.

**Clinical use.** Thieke et al. (Radiother Oncol 85:292, 2007) report the first clinical use. Generating the plan
database took hours; navigation took minutes.

### 2.4 Making the navigated plan deliverable

A blend of fluence maps is not a blend of deliverable plans. Sequencing changes the dose, and leaf positions cannot
simply be averaged in VMAT (Craft & Richter, PMB 58:87, 2013; Craft, Papp & Unkelbach, Med Phys 41:021709, 2014).
The published answers fall into three groups.

**Navigate on fluence, then convert the chosen plan.**
- Dose mimicking optimizes a deliverable plan toward the navigated dose. RayStation:
  - penalizes over-dose relative to the navigated dose in organs and in the target voxels below 50 % cumulative
    volume (its hotter half);
  - penalizes under-dose in the rest of the target (its colder half);
  - mimics the dose voxel by voxel when its Pareto plans were made with machine parameters, and the DVH otherwise
    (RaySearch white paper 2020).
- For VMAT, Craft et al. (Med Phys 39:686, 2012) navigate a 180-beam fluence problem. They then merge neighbouring
  beams while the dose stays within a stated tolerance. Radiarch's VMAT (R8) already follows this paper's arc
  sequencing.
- Bokrantz (Med Phys 39:6712, 2012) converts the chosen plan, then navigates again over segment weights that share
  its apertures.

**Navigate on deliverable plans.**
- Salari & Unkelbach (PMB 58:621, 2013) generate every Pareto plan from one shared aperture pool by column generation.
- Fredriksson & Bokrantz (PMB 58:7683, 2013) share some apertures and give each plan a few of its own.
- Craft, Papp & Unkelbach (2014) average leaf passing times of unidirectional sliding-window sweeps. RayStation does
  this with sweeps whose start and end positions are common to every Pareto plan, over arc sectors of at most 24°.

**Project after navigation.** Bokrantz & Miettinen (Med Phys 42:5862, 2015) solve one more optimization: improve every
objective by as much as possible, as evenly as possible, from the navigated values (`min t` subject to
`f_i(x) ≤ f_i(x_nav) + t`). This removes the gap between the approximation and the true Pareto set, which they report
as a 3.1 Gy lower mean organ dose.

**Protons.** Spot weights are the variables, so a blend of spot weights is itself a plan. Only the minimum spot
meterset breaks this, and it is restored by a final re-optimization. Craft calls this representation "very good" for
scanning; no source quantifies the minimum-meterset effect.

### 2.5 Robustness and protons

**Objective-wise robust MCO.** Chen et al. (PMB 57:591, 2012):
- give each objective a worst-case version over 9 or 29 proton scenarios, alongside its nominal version;
- navigate between robust and nominal quality;
- keep every objective piecewise linear and convex.

**Scenario-wise worst case.** Bokrantz & Fredriksson (EJOR 262:682, 2017) show that the objective-wise worst case
guards against combinations of scenarios that cannot happen together. The scenario-wise worst case of the weighted
sum, `min max_s Σ_i ω_i f_i(x; s)`, protects exactly the scenarios that can occur.

**Gaps.**
- No clinical study of robust proton MCO was found.
- RayStation combines MCO with robust constraints.
- No Eclipse support for protons in MCO was found.

### 2.6 Automatic navigation and prioritized planning

**Lexicographic optimization.** It optimizes the goals in priority order, holding each level within a slip of its
optimum (Jee, McShan & Fraass, PMB 52:1845, 2007; Wilkens et al., PMB 52:1675, 2007). Without slip, the first level
decides the whole plan.

**The wish-list method (2pεc).** Erasmus MC's 2-phase ε-constraint method (Breedveld et al., PMB 52:6339, 2007;
iCycle, Med Phys 39:951, 2012) takes hard constraints and prioritized goals. Phase one meets the goals in order and
phase two tightens them. It costs about two optimizations per objective, and its plans were preferred in 32 of 33
prospective cases (Voet et al., IJROBP 85:866, 2013).

**Automatic navigation on a computed Pareto set.**
- RayStation does it "by lexicographic optimization where the plan coefficients constitute optimization variables",
  against a prioritized list of clinical goals (white paper; RayStation 10A, photons). No peer-reviewed description of
  that algorithm was found.
- The reference-point idea that underlies such methods is Wierzbicki's (1980).

### 2.7 Clinical evidence and known weaknesses

**Evidence for MCO.**
- **Planning time.** It falls, for example 135 → 12 minutes in glioblastoma and pancreas, where physicians preferred
  every MCO plan blind (Craft et al., IJROBP 82:e83, 2012).
- **Novice planners.** They match experienced ones in head and neck with MCO (Kierkels et al., Radiat Oncol 10:87,
  2015).
- **Organ sparing.** Lung plans spare normal tissue better (Kamran et al., Radiother Oncol 118:515, 2016).

**Weaknesses, reported for both vendors.**
- **The conversion to a deliverable plan.** Kyroudi et al. (Radiother Oncol 120:346, 2016) warn that "dosimetric
  differences can arise between the two steps". Wong et al. (2024) measured −0.89 % (Eclipse 16.1) and +3.56 %
  (RayStation 12A) PTV D98 between navigated and deliverable plans. RaySearch's reply traced the gap to objectives
  that duplicated constraints and an organ objective set to 50 Gy instead of 0 Gy.
- **Repeatability.** Eclipse 18's plan-collection generation was not repeatable: a constraint was restrictable in 7 of
  10 identical runs (Howard et al., JACMP 2025).
- **Dependence on the starting plan.** Eclipse's Pareto set depends on its starting ("balanced") plan
  (Miguel-Chumacero et al., Radiat Oncol 13:229, 2018).

## 3. How RayStation and Eclipse do it

| | RayStation | Eclipse |
|---|---|---|
| Start | Objectives and constraints; a feasibility check first that lists the violated constraints | An existing optimized plan (the "balanced plan"), whose objectives the trade-offs are chosen from |
| Pareto plans | Anchor plans, a balance plan, then auxiliary plans from the inner/outer approximation (Bokrantz & Forsgren) when there are fewer than ten objectives; pairs of the most anti-correlated objectives otherwise; the count is the user's | 3N + 1 plans around the balanced plan (from two clinical papers; no Varian document found) |
| Objectives | "Ideal" objectives (uniform target dose, organ EUD toward 0 Gy, dose fall-off); bare minimums as constraints | Trade-off objectives chosen from the plan's objectives; a target only through its own objectives or a homogeneity objective |
| Generation mode | Fluence, or machine parameters (DMPO) with shared unidirectional leaf sweeps and ≤ 24° sectors; PBS and tomotherapy always by machine parameters | Native VMAT, or a faster hybrid IMRT surrogate for VMAT on the GPU (about 2 minutes instead of about 34) |
| Navigation | A slider per objective; clamps on the others; dose, DVH and clinical goals updated live; automatic navigation by lexicographic order of clinical goals (10A, photons) | A selector and a restrictor per slider; restriction on clinical goals; undo and isodose dragging in 18 |
| Deliverable | Dose mimicking from the interpolated machine parameters, voxel by voxel or by DVH; can be continued as an ordinary optimization | Fluence converted with the machine limits; VMAT by a separate "create deliverable VMAT plan" step (algorithm not published) |
| Robust, protons | Robust constraints; PBS | Not found |
| Scripting | `Mco`: `GenerateParetoPlans`, `RunAutomaticMcoNavigation`, `CreateDeliverablePlan`, navigation states with plan weights and clamps (from unofficial type stubs) | `TradeoffExplorationContext`: add trade-off objectives, `CreatePlanCollection`, get and set objective cost (0–1), restrictors, `CreateDeliverableVmatPlan` (Varian's PyESAPI stubs and sample code) |

Sources: the RaySearch MCO white paper (2020) and RayStation 10A notes; Bokrantz's thesis (KTH 2013); Varian's
Fraunhofer licence announcement (2015); Varian's PyESAPI stubs and the `AutoPlanningWithMCO` sample on GitHub; the
clinical papers above.

## 4. Design for radiarch

The design takes RayStation's model because it needs no prior plan and its algorithms are published:
- convex objectives;
- hard constraints;
- anchors, a balance plan and sandwich plans;
- navigation over blend weights with clamps;
- automatic navigation by goal priority;
- dose mimicking.

It reuses radiarch's optimizer, dose matrices, sequencer and arcs unchanged. Every element is fixed by a test that can
fail.

**D1. Trade-off objectives are convex, and every one reads in Gy.** An MCO run takes a list of trade-off objectives and
refuses any type that is not convex. New objective types:
- `MeanDose`;
- `EUDMax`: generalized EUD with `a ≥ 1`, minimized; an organ's objective toward 0 Gy, as RayStation advises;
- `EUDMin`: `a ≤ 1`, maximized, for a target;
- `RMSOver` and `RMSUnder`: the root mean square of the dose above or below a level. This is convex, and it reads in
  Gy, unlike today's squared penalties;
- `UniformRMS`: target homogeneity around the prescription.

Tail-mean (CVaR) objectives, the convex stand-in for DVH limits, come later. The existing `DVHMin`, `DVHMax` and
two-sided `EUD` stay for ordinary optimization and are refused as trade-offs. Ideal and nadir values from the anchor
plans normalize the objectives to [0, 1] for the algorithms. Sliders and reports show Gy.

**D2. Constraints are hard, within a stated tolerance, and checked first.**
- **Today.** A `ConstraintSpec` is a weighted penalty.
- **In MCO.** Constraints are enforced by an augmented-Lagrangian loop around L-BFGS-B: a few outer rounds that raise
  the multipliers until each constraint holds within its tolerance. Ordinary optimization keeps its penalties.
- **The feasibility run.** An MCO run starts with one, minimizing the constraint violations alone. If any constraint
  cannot be met, it stops and lists them, as RayStation does.
- **Redundant objectives.** A trade-off objective that is already met at its ideal value by every anchor is reported
  as redundant. This is the failure behind the published deliverable gap.

**D3. The Pareto set: anchors, balance, then sandwich plans to a stated error.**
1. **Anchors.** N anchor plans, each minimizing one objective with a weight of 10⁻³ on the others, so that it is
   Pareto optimal and not only weakly so.
2. **Balance plan.** One plan with equal normalized weights.
3. **Sandwich plans.** Auxiliary plans by the sandwich algorithm:
   - the inner set `conv(P) + R^n_+`, the plans' hull with everything worse than it (the role of Rennen's dummy
     points);
   - Bokrantz & Forsgren's vertex enumeration of the outer set (Qhull through `scipy.spatial`, one HiGHS linear program
     per vertex through `scipy.optimize.linprog`);
   - the worst vertex's duals give the next weights.

Generation stops when the error bound falls below a tolerance (default 5 % of the normalized range) or at a plan
budget (default 3N + 1, at most 4N + 1). Each plan warm-starts from the nearest stored plan, and the dose matrices are
computed once and cached. Solver tolerances are tight and fixed in the run's key, and the run is deterministic. The
error bound is recorded after every plan, so the record shows how the approximation converged. A run takes at most
eight trade-offs; RayStation's rule for more (pairs of the most anti-correlated objectives) is not built.

**D4. Storage keeps navigation fast.**
- **What is stored.** An MCO run stores each Pareto plan's weights, objective vector and dose, the last on the
  *navigation voxels*: the union of the structures the objectives and goals name. For a thorax with 16 plans this is
  tens of megabytes, not gigabytes.
- **On demand.** The full dose of a blended plan is `Dij · Σ λ_j w_j`, computed only when a plan is made from it.
- **Cache key and lineage.** The run is a job with a cache key: geometry, beam model, engine, objectives,
  constraints, solver and generation settings. Its lineage records each Pareto plan.

**D5. Navigation is a linear program over the blend weights.** A navigation request carries:
- a target value for one objective (a slider moved), or a reference point;
- clamps, as upper bounds on other objectives.

The service solves Craft & Monz's piercing LP over `λ` with the clamps as constraints and locked objectives held. It
then evaluates the blended dose exactly on the navigation voxels: objective values, the DVH, and the goals of a
template. The answer is a *navigation state*, holding the blend weights, the clamps, the exact and bound values, and
the goal outcomes. States are stored and named. The balance plan's state is the reference every other state is shown
against, as in RayStation. A request takes milliseconds to a fraction of a second, with no dose calculation.

**D6. Automatic navigation by goal priority, then projection.**
- **What it takes.** A goal template's priorities: 1 must, 2 should, 3 would like (R5).
- **What it does.** It navigates lexicographically over `λ`. At each priority level it minimizes that level's summed
  normalized goal violation, evaluated exactly on the blended dose. Every higher level is held: a goal it met stays
  met, and a goal it missed may slip by 1 % of its value. After the last level it minimizes the normalized objectives
  with every level held. (As first drafted every goal could slip; the toy problem in the tests showed a met
  priority-1 goal lost to the slip, so met goals do not slip.)
- **How it solves.** DVH goals are not linear in `λ`, so each level is a small constrained problem in at most a few
  dozen variables, solved by `scipy.optimize` (SLSQP from the starting state, then COBYLA while a shortfall remains).
  Each evaluation is one weighted sum of the plans' doses on the goal's structure.
- **Projection.** It is optional and on by default, and it runs as the first step of making the deliverable plan
  (D7), because it is an optimization on the full dose matrix rather than a navigation step. It moves the navigated
  plan onto the Pareto set by minimizing the sum of the normalized trade-offs with none of them above its navigated
  value, under the hard constraints. This is a variant of Bokrantz & Miettinen's projection (`min t` subject to
  `f_i ≤ f_i(nav) + t`), which improves the objectives evenly; both give a plan at least as good in every objective.
- **Provenance.** This is radiarch's own method, built from published parts. RayStation's algorithm for the same task
  is not published, and the record says so.

**D7. The deliverable plan mimics the navigated dose, and the difference is reported.** A new objective type,
`ReferenceDose`, mimics a reference dose one-sidedly, as RayStation describes:
- it penalizes over-dose in organs and in the hotter half of a target (the voxels above the reference's median there);
- it penalizes under-dose in the colder half of the target;
- a target-priority weight sets targets against organs.

(The first draft of this section had the target's halves the wrong way round; the white paper's "target voxels below
50 % cumulative volume" are the voxels above the median dose, its hotter half.)

How each technique uses it:
- **Static fields (IMRT):** the blended fluence is sequenced as in R4, and the segment metersets are re-optimized
  against `ReferenceDose`.
- **VMAT:** the blended sector fluence becomes arcs as in R8, and the arc metersets are re-optimized the same way.
- **Protons:** the projected spot weights are the plan. Radiarch's proton machine model has no minimum spot meterset,
  so there is nothing to re-optimize; the plan is exported by its optimization record.

First the navigated plan is projected onto the Pareto set (D6), and its dose is the reference the deliverable plan
mimics. Then:
- the plan is normalized to the main target's coverage goal when asked (R10; photons);
- it is stored as a beam model and dose like any other plan;
- it carries a *deviation table*: every trade-off and goal, navigated (and projected) against deliverable. A
  deliverable value worse by more than a stated tolerance (default 1 Gy for doses, 1 percentage point or 1 cc for
  volumes) is flagged.

Shared-aperture generation, so that navigation shows the deliverable dose itself (Salari & Unkelbach; Fredriksson &
Bokrantz; shared sweeps in VMAT), is the planned follow-up when the deviation tables show it is needed.

**D8. Robust MCO uses the scenario-wise worst case.**
- **How objectives are evaluated.** With robustness on, each Pareto plan minimizes the scenario-wise worst case of its
  weighted sum (Bokrantz & Fredriksson), which radiarch's `WORST_CASE` aggregation already computes. Navigation reports
  each objective's worst case over the scenarios, as well as its nominal value.
- **Why the bound still holds.** The worst case of convex functions is convex.
- **Later.** Objective-wise robust objectives (Chen et al.) are an option for later.

**D9. One interface across API, SDK, command line and protocols.**
- **API:**
  - `POST /mco/run` (a job) returns the Pareto set;
  - `POST /mco/{id}/navigate` and `POST /mco/{id}/auto-navigate` return a navigation state;
  - `POST /mco/{id}/deliverable` returns the deliverable plan and its deviation table;
  - `GET /mco/{id}/states` lists the stored states.
- **SDK:** `BeamModel.mco(...)` returns a `ParetoSet` with `.navigate`, `.auto_navigate`, `.states` and `.deliverable`.
- **Protocols:** a protocol may carry an `mco` section (trade-offs, constraints, budget). `radiarch plan` then makes
  the protocol's plan by automatic navigation instead of the reweighting rounds, and keeps the Pareto set for
  interactive navigation.
- **Viewer:** a navigation panel in the OHIF extension (R13): a slider and a clamp per objective, live DVH and goals
  from the API, and the dose wash replaced when a state is applied.

The vocabulary follows RayStation's, which the literature shares: Pareto plans, anchor, balance plan, navigation,
clamp, deliverable plan, dose mimicking.

**What R11 does not do:**
- no nonconvex trade-offs;
- no beam-angle trade-offs across several Pareto sets (Craft & Monz 2010; a natural extension of the BAO search);
- no knowledge-based Pareto sets;
- no isodose dragging.

## 5. Validation

**Tests that fix the algorithms.** These run in CI on small convex problems with known answers.
- **Analytic fronts.** Two- and three-objective quadratics whose Pareto front is known in closed form, and Bokrantz &
  Forsgren's scalable test problem. The sandwich error bound must be at least the true error, never increase as plans
  are added, and reach the tolerance.
- **Supporting normals.** Every Pareto plan's weight vector must support the set:
  `ωᵀ F_k ≤ ωᵀ F_j + tol` for every plan j. No stored plan may dominate another.
- **Linearity and the bound.** `D(Σ λ x) = Σ λ D x` to rounding, and `f(Σ λ x) ≤ Σ λ f(x)` for every trade-off type.
  A nonconvex type must be refused.
- **Navigation.**
  - The LP's state is feasible and honours its clamps and locks.
  - Moving a slider toward better moves that objective and no clamped one.
  - The exact values never exceed the bound values.
- **Automatic navigation.** A three-level problem solved by hand. Each level stays within its slip; a lower level
  never worsens a higher one.
- **Projection.** The projected plan weakly dominates the navigated plan.
- **Constraints.**
  - The augmented-Lagrangian solution meets every constraint within its tolerance.
  - An infeasible set is refused with the violated constraints named.
- **Deliverable.**
  - The deviation table is computed and its flags fire past their tolerances.
  - A proton blend keeps every spot at or above its minimum.

**The validation record** (`docs/validation/…-r11/`), from a stated commit:
- **TG-119 C-shape.** The classic two-objective trade-off (target coverage against the core). The Pareto front is
  drawn from the computed plans, and its error bound is followed as plans are added.
- **The lung demo (NSCLC-Radiomics `LUNG1-002`).** Five trade-offs: PTV homogeneity, lungs mean, heart mean,
  oesophagus mean, cord EUD at a high exponent. RTOG 0617 constraints and priorities. Three comparisons:
  - the automatically navigated plan against the R10 protocol plan, goal by goal;
  - navigated against deliverable, IMRT and VMAT;
  - plans and minutes needed against the error bound.
- **A proton case.** Robust MCO on a head-and-neck or phantom case with MCsquare, nominal and worst-case values in
  the navigation.
- **Optional benchmark:** TROTS (Breedveld & Heijmen, Data Brief 12:143, 2017), an open set of planning problems with
  dose matrices. It is fetched like the other public data and never stored in the repository.

**Signatures.** A physicist signs, as for R7 to R10.

## 6. What was not verified

- **RayStation's list of objective types allowed in MCO.** It was not found; only the advice on "ideal" objectives
  and the convexity argument are on record.
- **RayStation's automatic-navigation algorithm.** Only the white paper's one sentence on it was found.
- **RayStation's "reference" navigation state.** It is known only from type stubs.
- **Eclipse's 3N + 1 plan count.** It comes from two clinical papers, not from Varian.
- **Eclipse's deliverable conversion and proton support.** Not found.
- **Full texts not read.** Craft 2006, Monz 2008, Rennen 2011, Fredriksson & Bokrantz 2013 and Bokrantz & Miettinen
  2015 were read only through their abstracts and later papers that describe them.
- **Open-source references.** matRad has an MCO branch (sandwich, navigation LP, 2pεc) under GPL-3, unlike matRad's
  BSD-3 main line. Radiarch reads it as a reference and copies nothing from it. pyRadPlan and OpenTPS have no MCO.

## 7. References

Literature:
- Bokrantz R. Multicriteria optimization for volumetric-modulated arc therapy by decomposition into a fluence-based
  relaxation and a segment weight-based restriction. Med Phys 39:6712, 2012. doi:10.1118/1.4754652
- Bokrantz R. Distributed approximation of Pareto surfaces in multicriteria radiation therapy treatment planning.
  PMB 58:3501, 2013. doi:10.1088/0031-9155/58/11/3501
- Bokrantz R. Multicriteria optimization for managing tradeoffs in radiation therapy treatment planning. PhD thesis,
  KTH, 2013.
- Bokrantz R, Forsgren A. An algorithm for approximating convex Pareto surfaces based on dual techniques. INFORMS J
  Comput 25:377, 2013. doi:10.1287/ijoc.1120.0508
- Bokrantz R, Fredriksson A. Necessary and sufficient conditions for Pareto efficiency in robust multiobjective
  optimization. EJOR 262:682, 2017. arXiv:1308.4616
- Bokrantz R, Miettinen K. Projections onto the Pareto surface in multicriteria radiation therapy optimization. Med
  Phys 42:5862, 2015. doi:10.1118/1.4930252
- Breedveld S, Storchi PRM, Keijzer M, Heinen AW, Heijmen BJM. A novel approach to multi-criteria inverse planning for
  IMRT. PMB 52:6339, 2007. doi:10.1088/0031-9155/52/20/016
- Breedveld S, Storchi PRM, Voet PWJ, Heijmen BJM. iCycle: integrated, multicriterial beam angle, and profile
  optimization for generation of coplanar and noncoplanar IMRT plans. Med Phys 39:951, 2012. doi:10.1118/1.3676689
- Breedveld S, Heijmen B. Data for TROTS — the radiotherapy optimisation test set. Data Brief 12:143, 2017.
  doi:10.1016/j.dib.2017.03.037
- Breedveld S, Craft D, van Haveren R, Heijmen B. Multi-criteria optimization and decision-making in radiotherapy.
  EJOR, 2019. doi:10.1016/j.ejor.2018.08.019
- Chen W, Unkelbach J, Trofimov A, Madden T, Kooy H, Bortfeld T, Craft D. Including robustness in multi-criteria
  optimization for intensity-modulated proton therapy. PMB 57:591, 2012. doi:10.1088/0031-9155/57/3/591
- Choi B, Deasy JO. The generalized equivalent uniform dose function as a basis for intensity-modulated treatment
  planning. PMB 47:3579, 2002. doi:10.1088/0031-9155/47/20/302
- Craft D. Multi-criteria optimization methods in radiation therapy planning: a review of technologies and
  directions. arXiv:1305.1546, 2013.
- Craft D, Bortfeld T. How many plans are needed in an IMRT multi-objective plan database? PMB 53:2785, 2008.
  doi:10.1088/0031-9155/53/11/002
- Craft D, Halabi T, Shih HA, Bortfeld T. Approximating convex Pareto surfaces in multiobjective radiotherapy
  planning. Med Phys 33:3399, 2006. doi:10.1118/1.2335486
- Craft D, Hong TS, Shih HA, Bortfeld T. Improved planning time and plan quality through multicriteria optimization
  for intensity-modulated radiotherapy. IJROBP 82:e83, 2012. doi:10.1016/j.ijrobp.2010.12.007
- Craft D, McQuaid D, Wala J, Chen W, Salari E, Bortfeld T. Multicriteria VMAT optimization. Med Phys 39:686, 2012.
  doi:10.1118/1.3675601
- Craft D, Monz M. Simultaneous navigation of multiple Pareto surfaces, with an application to multicriteria IMRT
  planning with multiple beam angle configurations. Med Phys 37:736, 2010. doi:10.1118/1.3292636
- Craft D, Papp D, Unkelbach J. Plan averaging for multicriteria navigation of sliding window IMRT and VMAT. Med
  Phys 41:021709, 2014. doi:10.1118/1.4859295
- Craft D, Richter C. Deliverable navigation for multicriteria step and shoot IMRT treatment planning. PMB 58:87,
  2013. doi:10.1088/0031-9155/58/1/87
- Fredriksson A, Bokrantz R. Deliverable navigation for multicriteria IMRT treatment planning by combining shared
  and individual apertures. PMB 58:7683, 2013. doi:10.1088/0031-9155/58/21/7683
- Halabi T, Craft D, Bortfeld T. Dose-volume objectives in multi-criteria optimization. PMB 51:3809, 2006.
  doi:10.1088/0031-9155/51/15/014
- Jee KW, McShan DL, Fraass BA. Lexicographic ordering: intuitive multicriteria optimization for IMRT. PMB 52:1845,
  2007. doi:10.1088/0031-9155/52/7/006
- Kamran SC et al. Multi-criteria optimization achieves superior normal tissue sparing in a planning study of
  intensity-modulated radiation therapy for RTOG 1308-eligible non-small cell lung cancer patients. Radiother Oncol
  118:515, 2016. doi:10.1016/j.radonc.2015.12.028
- Kierkels RGJ et al. Multicriteria optimization enables less experienced planners to efficiently produce high
  quality treatment plans in head and neck cancer radiotherapy. Radiat Oncol 10:87, 2015.
  doi:10.1186/s13014-015-0385-9
- Kyroudi A et al. Analysis of the treatment plan evaluation process in radiotherapy through eye tracking and
  multicriteria optimization. Radiother Oncol 120:346, 2016. doi:10.1016/j.radonc.2016.05.018
- Monz M, Küfer KH, Bortfeld TR, Thieke C. Pareto navigation: algorithmic foundation of interactive multi-criteria
  IMRT planning. PMB 53:985, 2008. doi:10.1088/0031-9155/53/4/011
- Rennen G, van Dam ER, den Hertog D. Enhancement of sandwich algorithms for approximating higher-dimensional convex
  Pareto sets. INFORMS J Comput 23:493, 2011. doi:10.1287/ijoc.1100.0419
- Romeijn HE, Dempsey JF, Li JG. A unifying framework for multi-criteria fluence map optimization models. PMB
  49:1991, 2004. doi:10.1088/0031-9155/49/10/011
- Romeijn HE, Ahuja RK, Dempsey JF, Kumar A. A new linear programming approach to radiation therapy treatment
  planning problems. Oper Res 54:201, 2006. doi:10.1287/opre.1050.0261
- Salari E, Unkelbach J. A column-generation-based method for multi-criteria direct aperture optimization. PMB
  58:621, 2013. doi:10.1088/0031-9155/58/3/621
- Thieke C et al. A new concept for interactive radiotherapy planning with multicriteria optimization: first
  clinical evaluation. Radiother Oncol 85:292, 2007. doi:10.1016/j.radonc.2007.06.020
- Voet PWJ et al. Fully automated volumetric modulated arc therapy plan generation for prostate cancer patients.
  IJROBP 85:866, 2013. doi:10.1016/j.ijrobp.2012.04.015
- Wierzbicki AP. The use of reference objectives in multiobjective optimization. In: Multiple Criteria Decision
  Making Theory and Application, LNEMS 177:468, Springer, 1980.
- Wilkens JJ, Alaly JR, Zakarian K, Thorstad WL, Deasy JO. IMRT treatment planning based on prioritizing
  prescription goals. PMB 52:1675, 2007. doi:10.1088/0031-9155/52/6/009

Commercial systems:
- RaySearch Laboratories. Multi-criteria optimization in RayStation. White paper, 2020.
  https://www.raysearchlabs.com/siteassets/media/publications/white-papers/wp-pdfs/wp-mco-in-raystation_2020_web.pdf
- RaySearch Laboratories. RayStation 10A news. https://www.raysearchlabs.com/globalassets/raystation_10a-news-flyer.pdf
- Varian Medical Systems. Licensing agreement with Fraunhofer for a multi-criteria optimization tool, 2015.
  https://www.biospace.com/varian-medical-systems-inks-licensing-deal-with-b-fraunhofer-b-for-novel-multi-criteria-optimization-mco-tool-for-radiotherapy-treatment-planning
- Varian. PyESAPI stubs and code samples (`AutoPlanningWithMCO`). https://github.com/VarianAPIs/PyESAPI,
  https://github.com/VarianAPIs/Varian-Code-Samples
- Miguel-Chumacero E et al. Effectiveness of multi-criteria optimization-based trade-off exploration in combination
  with RapidPlan for head & neck radiotherapy planning. Radiat Oncol 13:229, 2018. doi:10.1186/s13014-018-1175-y
- Howard et al. JACMP, 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC12256579/
- Wong et al., 2024, and RaySearch's reply. https://pmc.ncbi.nlm.nih.gov/articles/PMC10931516/,
  https://pmc.ncbi.nlm.nih.gov/articles/PMC12191525/
