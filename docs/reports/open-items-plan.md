# The open items after block two: a plan (draft for the project lead)

State: 2026-11-11. Block one and block two are built (`docs/impl-plan.md`, items 1 to 17). This note gathers what
is still open and proposes an order. The open items are the plan's open rows, plus the two graded checks that fail in
R8's current run. Efforts are engineer-weeks (ew), as in `tps-evaluation-and-roadmap.md`. Radiarch is not for
clinical use.

## 1. One rule for the order: output changes travel together

The validation records name the commits their runs came from. An item that changes a dose or a plan makes a new
rerun of every record it touches, and moves the runs a reviewer reads. So:

- Items that change no output can go out in any release.
- Items that change outputs are batched into one release with one round of reruns.
- While a physicist is reviewing the records, no output change is released.

Each item below says whether it changes outputs.

## 2. The items

### A. Small items that change no existing output

Built 2026-11-11 (`docs/impl-plan.md`, `docs/impl-log.md`).

| Item | What it gives | Effort | Changes outputs |
|---|---|---|---|
| The engine binary's digest in the attribution (R12) | A result names the exact engine build, not only its version | 0.25 | no (one more attribution field) |
| Asymmetric margins (R4) | A margin per direction, such as a larger one superior-inferior for a moving lung target | 0.25 | no (a new option; protocols unchanged) |
| Relative-seriality NTCP; LQ-L for SBRT (R5) | The serial-organ NTCP model, and a dose conversion that stays sound at SBRT fraction sizes | 0.5 | no (new metrics) |
| An import's registration recorded as the plan's parent (ADR 0021's known limits) | The plan's lineage, and its access check, include the registration it was recomputed through | 0.25 | no |

About 1.25 ew in all.

### B. Dose accuracy

Small fields and narrow gaps: built 2026-11-11 (`pb` 1.2.0, `LEAF_MODEL_VERSION` 4; `docs/reports/mlc-leaf-model.md`). The records' reruns follow on the compute server.

| Item | What it gives | Effort | Needs | Changes outputs |
|---|---|---|---|---|
| Small fields and narrow gaps (R8's two failed checks) | `pb` within tolerance for the 1 × 1 cm field (was −5.9 %) and under a 5 mm leaf gap (was +3.2 points). Likely a source-size term in the kernel's edge, and the leaf tip's model refitted to the gap field | 1–1.5 | the Monte Carlo references already made | yes: `pb`'s version; R8 to R11's aperture cases rerun |
| An independent lung reference (R8, question 2) | A whole-plan Monte Carlo of a lung VMAT plan on a patient CT, so `pb`'s lung scaling is checked against data it was not fitted to | 1.5 | the physicist's choice of reference | no (a new check) |
| A full linac-head Monte Carlo reference (R7) | References with a head model instead of a collimated point source | 2–3 | head geometry or phase-space files; the physicist's answer to R7, question 1 | no (new references); a refit after it would |
| A matRad cross-check (R7) | A second planning system's dose. matRad also runs in GNU Octave, which would remove the MATLAB need (to confirm) | 0.5–1 | — | no |
| New CCC kernels (R7) | CCC's depth and lung errors fixed at the kernel | 1–2 | the physicist's answer to R8, question 3: if `pb` becomes the plan engine, CCC stays a check and this is not needed | yes, for CCC |

### C. Photon plan quality

| Item | What it gives | Effort | Changes outputs |
|---|---|---|---|
| Direct aperture and leaf optimization (R4, R8) | The optimizer works on the apertures and metersets themselves, for step-and-shoot (column generation) and for arcs (progressive sampling or sequential convex programming). It removes the loss between the optimized fluence and the delivered plan. It is the likely cure for the arcs' second set that does not converge, and for the closed leaf pairs' leak | 3–4 | yes: every aperture plan; `AUTOPLAN_VERSION`; every record with apertures rerun |
| MCO: one shared aperture pool (R11, option B2 of `mco-deliverable-options.md`) | Every Pareto plan from one pool of apertures, so the navigated plan is the delivered plan. Builds on direct aperture optimization | 1–2 | yes: the MCO deliverables |
| MCO: tail-mean (CVaR) trade-offs (R11) | Convex trade-offs that stand in for DVH limits | 0.5–1 | no (new trade-offs) |
| MCO: Pareto sets across beam arrangements (R11) | The navigation's linear program run on several sets, one per arrangement, picks the best | 0.5 | no (a new option) |
| MCO: the TROTS benchmark (R11) | Radiarch's optimizer on a public set of planning problems with published results | 0.5–1 | no (a new check) |
| Wedges, compensators, blocks, bolus (R6) | Three-dimensional conformal and chest-wall techniques, and their DICOM | 1.5–2 | no (new plan types) |

### D. Robustness, 4D and adaptive planning

| Item | What it gives | Effort | Needs | Changes outputs |
|---|---|---|---|---|
| Robust optimization over the breathing phases (moved from R9.7) | The phases as scenarios of the optimization, not only of the evaluation. Matters most for protons in lung | 1 | memory: one influence matrix per phase | no (a new option) |
| Probabilistic robust objectives (R3) | The expected value and spread over scenarios, beside the worst case | 0.5–1 | — | no (new objectives) |
| Cone-beam CT registration (R9's five failed checks) | A metric that follows day-to-day gas and filling: local correlation, histogram matching or contour guidance | 1 | the physicist's answer to R9, question 2 | yes: the registration's version; R9 rerun |

### E. Provenance across instances

| Item | What it gives | Effort | Changes outputs |
|---|---|---|---|
| Lineage across radiarch instances; an audit trail that cannot be changed (R12) | Results that move between sites keep their history; the audit log is append-only and verifiable | 1.5–2 | no |

A host that keeps its own audit may already cover this. It waits until a deployment needs it.

### F. Waiting on people, not on code

- The physicist's review of R7 to R11 and of the goal templates (`docs/validation/README.md` is the way in).
- The project lead's 3D Slicer check (R13's record).
- Whether to file the OHIF overlay-volume proposal (`ohif-overlay-volume-proposal.md`).

## 3. Proposed order

1. **A, the small items** (about 1.25 ew). No output changes, one release.
2. **Small fields and narrow gaps** (1–1.5 ew). The first output change: `pb`'s version, one round of reruns. Do it
   before the physicist's review starts, or after it ends.
3. **Direct aperture and leaf optimization** (3–4 ew), then the MCO items on it: shared pool, CVaR, beam
   arrangements, TROTS (2.5–4.5 ew). A design note comes first, comparing the methods, for the project lead to
   choose, as `mco-deliverable-options.md` did for MCO. Items 2 and 3 can share one rerun round if 2 waits for 3.
4. **D, robustness, 4D and cone-beam CT** (2.5–3 ew), after the physicist's answer to R9, question 2.
5. **Deferred** until a physicist's answer or a user asks:
   - an independent lung reference;
   - the head Monte Carlo;
   - matRad;
   - new CCC kernels;
   - wedges and bolus;
   - lineage across instances.

Items 1 to 4 come to about 10–14 ew. The deferred items are about 8–12 ew.

## 4. Decisions for the project lead

1. The order above, or another.
2. When output changes may land: before the physicist's review starts, or held until it ends.
3. Whether direct aperture optimization starts with a design note (recommended) or goes straight to a build.
