# ADR 0009 — Robust protons through the engine, Gy(RBE), craniospinal fields

Date: 2026-10-21. Status: accepted. Roadmap R3 ("Robust protons and craniospinal fields").

## Context

Robust evaluation and optimization existed on explicit scenario lists: one
engine run per scenario, systematic setup shifts and range scaling only, no
per-fraction random setup error. Proton doses were physical Gy although proton
prescriptions are in Gy(RBE). Beam sets had one isocenter for all beams and
spots were always placed on the whole target, so a craniospinal plan, which
needs several isocenters along the spine and matched junctions, could not be
expressed. Pediatric neuro-oncology needs proton craniospinal courses.

## Decisions

1. **Engine-native scenario sets.** `ScenarioSetSpec.engine_native` and
   `RobustnessSpec.engine_native` describe a set the engine samples itself:
   `ALL` (81 combinations of ±σ/0 setup shifts on each axis with ±r/0 range
   error), `REDUCED_SET` (21: single-axis shifts × range states) or `RANDOM`
   (`count` draws), with systematic setup errors, a per-fraction random setup
   error and a range error. The MCsquare driver runs the engine's robustness
   mode once (`Robustness_Mode`, `Scenario_selection`, the error settings) and
   reads `Dose_Nominal` plus one dose per scenario, or in beamlet mode one
   influence matrix per scenario; it parses `Robustness_scenarios.txt` so every
   scenario comes back as a `ScenarioSpec` with the errors the engine applied
   (`setup_random_sigma_mm` is the new field; with a zero random error the
   engine leaves out the scenario that coincides with the nominal plan, so
   REDUCED_SET yields 20 and ALL 80). The dose service persists them
   as scenario doses; the optimizer gets every scenario's Dij from one run and
   stores each under the cache key of the equivalent single-scenario request.
   The random setup error is modelled by the engine as a blur of each
   scenario's dose, which the per-scenario path cannot do; engines without a
   native mode refuse the set with a clear error.
2. **Gy(RBE).** `DoseComputeRequest`, `InfluenceBuildRequest` and
   `OptimizationRunRequest` carry `rbe` (null = 1.1 for protons, 1.0 for
   photons; part of the cache keys). The service multiplies the engine's
   physical dose or influence matrix by it; results carry `rbe_factor` and
   `dose_units` ("Gy" or "Gy(RBE)"); objectives, prescriptions and DVH metrics
   are then in Gy(RBE) for protons. The legacy RTDOSE writer sets
   `DoseType EFFECTIVE` and names the RBE in the dose comment.
3. **DVH bands and worst-case goals.** When a dose has scenario doses the
   evaluation reports, per structure, the DVH envelope (min and max volume at
   each dose over the scenarios, on shared bins) and the per-metric lowest and
   highest DVH metrics with every scenario's own; for the target the worst
   coverage, D95, D98, D2, hotspot, homogeneity and conformity over the
   scenarios and the scenario that gave the worst coverage. Pass/fail goal
   templates stay with R5.
4. **Multi-isocenter beam sets and the craniospinal template.** A `BeamSpec`
   may carry its own `isocenter_mm` and a `target_z_range_mm`: the spots of
   that beam are placed on the plan target restricted to that z slab, around
   that isocenter (else the beam set's, else the slab's centre of mass).
   `BeamSetSpec.isocenter_mm` is now optional and **honoured when given**; it
   was ignored before (the centre of mass was always used), so callers that
   want the centre of mass pass null. `services/plan_templates.py` and
   `POST /beam-model/templates/craniospinal` build posterior fields along the
   craniospinal target: the fewest slabs of at most `field_length_mm`
   (300 mm default, inside the 400 mm spot field of view) overlapping by
   `overlap_mm` (40 mm). The junctions are the overlaps: both fields place
   spots there, the optimizer feathers the gradient, and a robust
   optimization over setup scenarios keeps the junction dose within bounds
   (the gradient-junction technique of pencil-beam-scanning craniospinal
   plans). With `brain_oblique_deg` > 0 the brain slab is treated by a pair
   of posterior-oblique fields at gantry ± that angle sharing one isocenter.
   Decision of 2026-10-21: the `research` preset (default) keeps one
   posterior brain field so plans stay simple and symmetric; the `clinical`
   preset gives the pair at ±15°, the usual proton practice for the cranial
   part, and is what a pediatric craniospinal planning protocol should name.
   Fraction-wise junction shifts (the feathering of passive-scattering and
   photon craniospinal plans) are deliberately not modelled: with gradient
   junctions and a robust optimization they are unnecessary, and a plan is
   one object per course here (per-fraction variants would be R12 plan
   versions).
5. **Legacy robust workflow.** `proton-robust` maps its `RobustnessConfig`
   (strategy, systematic and random setup errors, range error, scenario count)
   onto the engine-native set, so the random error it always offered is now
   modelled; the explicit scenario builder `_helpers.robust_scenarios` stays
   for engines without a native mode.

## Consequences

- One MCsquare run replaces 21 or 81 for a robust evaluation or a robust Dij set.
- Stored proton doses change units: results, DVHs and plan summaries say so
  (`dose_units`). Doses cached before R3 are physical and are not reinterpreted.
- Beam-model cache keys include the per-beam isocenters and slabs; beam sets
  that passed a placeholder isocenter should pass null.
- Not done here: scenario-weighted (probabilistic) robust objectives, CVaR
  tuning, 4D scenarios (R9), clinical-goal pass/fail (R5), a vertex or
  anterior brain field in the template.
