# Radiarch — implementation plan and tasks

State: 2026-10-29. The design is in [`architecture.md`](architecture.md); what each item
did, file by file, is in [`impl-log.md`](impl-log.md); the decisions
are in [`adr/`](adr/); the evaluation that set this roadmap is
[`reports/tps-evaluation-and-roadmap.md`](reports/tps-evaluation-and-roadmap.md).

Legend: `[x]` done · `[ ]` to do · **→ Rn** planned in roadmap item Rn · **(open)** a known gap
not yet scheduled in the roadmap · **(waiting)** blocked on something outside the code.

## Status

Items run in dependency order. Block one (1–11) is the "commercial-shaped" minimum; block two
(12–17) is where "close to commercial" is earned.

| Order | Item | Status | Commits | ADR |
|---|---|---|---|---|
| 1 | R0 Hygiene | done | 265b0cd | 0005 |
| 2 | R1 CCC through radiarch's own driver | done | caf6ee5 | 0001, 0005 |
| 3 | R7a Validation foundation | done | 37afa07, 0070918 | — |
| 4 | R14 Own MCsquare driver | done | 15c46ec | 0006 |
| 5 | R2 DICOM RT in | done | 7df0c3c | 0007 |
| 6 | R15 Own core, OpenTPS removed | done | 091c0c0..5947ad2 | 0008 |
| 7 | R3 Robust protons, Gy(RBE), craniospinal fields | done | c776958..709b533 | 0009 |
| 8 | R4 Machine model and apertures | done | f906c51..a3c0b89 | 0010 |
| 9 | R5 Evaluation | done | dfe907c..5612286 | 0011 |
| 10 | R6 RT object writer | done | d3deb77..a9b8cce | 0012 |
| 11 | R12 Versions, lineage, states | done | 3e653f2..fe0573e | 0013 |
| 12 | R7 Validation report | done; physicist review waiting | 2e21a28..2f7b506 | 0014 |
| 13 | R8 Native pencil-beam engine, VMAT, SBRT | done; physicist review waiting | 6e73aa2..cc5c047 | 0015 |
| 14 | R9 Registration, 4D, replanning | done; physicist review waiting | 658b8c7..316b6c6 | 0016 |
| 15 | R10 Scripting SDK and planning protocols | done; physicist review waiting | 0be71b1..92ce40d | 0017 |
| 16 | R13 Viewer integration | done; 3D Slicer check by the project lead waiting | fc7473d..26787db | 0018 |
| 17 | R11 Multi-criteria optimization | not started; design proposed | — | (0019) |

## Before the roadmap (done by 2026-10-20)

- [x] Service 1, geometry: CT + RTSTRUCT → density and masks, HU models, resampling, NIfTI outputs
- [x] Service 2, beam model: proton spots, photon beamlets
- [x] Service 3, dose: engine protocol and registry, MCsquare dose and Dij, scenarios
- [x] Service 4, optimization: objectives, constraints, three solvers, robust aggregation, checkpoints
- [x] Service 5, beam-angle search: greedy and top-k
- [x] Service 6, evaluation: DVH, indices, gamma
- [x] Operations: Docker Compose, Celery queues, Postgres, API key, audit log, store limits
- [x] Removed what returned invented numbers: the 4D simulator, the synthetic planner fallback; and the OHIF extension (viewing stays outside radiarch)
- [x] Handoff validation V1–V4: superseded by R7a and R7 (the V4 MCsquare Dij gate runs nightly)

## Block one

### R0 — Hygiene
- [x] Photon plans built with beams (the builder discarded them)
- [x] Robust proton settings reach the engine
- [x] The beam model uses the geometry it is given
- [x] The analytic engine is test-only
- [x] API key on every router except `/info`
- [x] `LICENSE` (Apache-2.0), `NOTICE`, "not for clinical use" in `/info`, every result and every DICOM object

### R1 — CCC through radiarch's own driver
- [x] Radiarch's own photon plan model (beams, segments, jaws, MLC rows, beamlets)
- [x] CCC file-protocol driver (geometry, beamlet specs, sparse output)
- [x] Reference-field calibration (1 cGy/MU at d_max, 10 × 10, SSD 100)
- [x] Setup-shift and density scenarios
- [x] A lung case on public CT (LCTSC) — done in R7

### R7a — Validation foundation
- [x] Regression goldens for every engine output (CCC matrix, geometry, spots, MCsquare inputs)
- [x] Public datasets fetched: TG-119, six LCTSC, five Pancreatic-CT-CBCT-SEG patients
- [x] Reference tables with citations (6 MV beam data, PSTAR proton ranges, TG-119 goals, tolerance sets)
- [x] Harness: phantoms, cases, runner, nightly CI job
- [x] DVH against dicompyler-core, gamma against pymedphys

### R14 — Own MCsquare driver
- [x] Radiarch's PBS plan model
- [x] Driver: MHD CT, scanner tables, beam data library, plan text, config, sparse-beamlet and dose readers
- [x] Identical inputs to the goldens, identical dose to the previous path at a fixed seed
- [x] Engine assets with provenance (`engines/mcsquare/`, done in R15)

### R2 — DICOM RT in
- [x] RT Plan and RT Ion Plan readers into the internal plans
- [x] RT Dose and spatial registration readers
- [x] `POST /beam-model/import`, `POST /dose/recalculate`
- [ ] Recalculate across frames of reference → **R9** (needs registration)

### R15 — Own core, OpenTPS removed
- [x] Own CT, RT Structure Set and case loaders
- [x] Own contour rasterizer, CT calibration, proton spot placement
- [x] Legacy `/plans` workflows on the services
- [x] Engine assets under `engines/`; `scripts/fetch-engines.sh`; the vendored OpenTPS tree deleted
- [x] pydicom 3

### R3 — Robust protons, Gy(RBE), craniospinal fields
- [x] Engine-native scenario sets (81 / 21 / random) with random setup error
- [x] RBE on dose, influence and optimization; results in Gy(RBE)
- [x] DVH bands and worst-case indices over the scenario doses
- [x] Per-beam isocenters and target slabs; the craniospinal template (research and clinical presets)
- [ ] Probabilistic robust objectives **(open)**
- [ ] 4D robust scenarios → **R9**

### R4 — Machine model and apertures
- [x] Photon machines as data (two synthetic linacs); proton machine from its beam data library
- [x] Overlapping structures (bitmask); margins, rings, booleans, density overrides, couch
- [x] Leaf sequencing (sliding window), machine limits, segment metersets re-optimized, deliverability report
- [ ] Direct aperture optimization refinement **(open)**
- [ ] Leaf transmission and tongue-and-groove in segment doses **(open)**
- [ ] Asymmetric margins **(open)**

### R5 — Evaluation
- [x] Clinical goals with priority and pass/fail; templates (RTOG 0617, QUANTEC, TG-101, NCCN head and neck, PENTEC)
- [x] NTCP (LKB) and TCP (Poisson); EQD2, BED, gEUD
- [x] Interpolated gamma (validated against pymedphys)
- [x] Dose-impact comparison of two evaluations
- [ ] Goal tables checked against their sources by a physicist **(waiting)**
- [ ] Relative-seriality NTCP; LQ-L for SBRT **(open)**

### R6 — RT object writer
- [x] RT Structure Set, RT Plan (step and shoot), RT Ion Plan, RT Dose (plan and beam), RT Image (DRR)
- [x] RT Beams Treatment Record and RT Treatment Summary Record
- [x] Export service, STOW-RS push, conformance checks in CI
- [x] RT Plan with VMAT arcs (DYNAMIC beams) — done in R8
- [x] Objects checked by hand in OHIF (R13.3)
- [ ] Objects checked by hand in 3D Slicer with SlicerRT **(waiting: the project lead; see R13.3)**
- [ ] Wedges, compensators, blocks, bolus **(open)**
- [x] DVH sequence in RT Dose (R13.2a)

### R12 — Versions, lineage, states
- [x] Lineage graph over every store; descendants; attribution
- [x] States (draft, approved, superseded, retired) and recorded transitions; delete routes refuse locked versions
- [x] Dataset-manifest derivation record; capability declaration
- [ ] Store cleanup that respects the locks (it can evict an approved version today) **(open)**
- [ ] Engine binary digest in the attribution **(open)**
- [ ] Lineage across radiarch instances; an immutable audit trail **(open)**

## Block two

### R7 — Validation report
- [x] OpenGATE Monte Carlo references (water, lung and bone slabs), step-converged
- [x] CCC with the scatter truncation as run-time parameters
- [x] Cases: CCC against Monte Carlo, pyRadPlan cross-check, Dij consistency for every engine, proton Bragg peak, TG-119 planning, lung end to end
- [x] One document per engine version; the record for review in [`validation/2026-10-22-r7/`](validation/2026-10-22-r7/)
- [ ] Physicist's review and signature **(waiting)**
- [ ] Full linac head Monte Carlo reference **(open)**
- [ ] matRad cross-check **(open; needs MATLAB)**
- [ ] New CCC kernels **(open; R8's pencil beam addresses the same errors)**

### R8 — Native pencil-beam engine, VMAT, SBRT (done; committed 6e73aa2..cc5c047)
- [x] CCC gantry turned as IEC 61217 (CCC 1.1.0); engine versions in every cache key
- [x] Pencil kernel from OpenGATE (Monte Carlo run of the Mohan 6 MV spectrum)
- [x] Kernel table (integral-conserving, SVD of the cumulative kernel) and the engine `pb`: dose path, influence matrix with unbiased sampling, per-segment doses, scenarios, calibration
- [x] Production kernel table (3 × 10⁷ primaries), four components, penumbra FWHM 4.0 mm fitted to Monte Carlo
- [x] NumPy path; CuPy path tested on GPUs (`gpu` extra, `test_gpu_matches_cpu`)
- [x] Cross-engine gamma against CCC in CI
- [x] Arcs in the plan model; RT Plan writes and reads them as DYNAMIC beams
- [x] VMAT: arc sequencing of sector fluence, gantry, leaf and dose-rate limits per fraction, control-point doses recomputed, metersets re-optimized; `POST /optimize/{id}/arcs`
- [x] SBRT templates (TG-101 limits with target goals) and RTOG 0813/0915 indices
- [x] Cases: pencil beam against Monte Carlo and CCC, lung SBRT with one arc, lung 60/30 with two arcs, head and neck 70/56 Gy integrated boost with two arcs
- [x] Delivered plans recomputed by CCC through coverage beamlets, so that narrow arc apertures are dosed
- [ ] Monte Carlo field-size references (4 × 4, 20 × 20 cm) and the graded field-size check
- [x] Full-mode harness run and the R8 record for review ([`validation/2026-10-23-r8/`](validation/2026-10-23-r8/), from the clean-commit run at `52ed834`)
- [ ] Physicist's review and signature of the R8 record **(waiting)**
- [ ] Direct leaf optimization for VMAT (progressive sampling or sequential convex programming) **(open)**
- [x] Lateral kernel scaling for lung (`pb` 1.1.0; fitted to the 2 × 2 and 10 × 10 cm Monte Carlo lung slabs)
- [x] Monte Carlo 2 × 2 cm lung-slab reference and the narrow-field lung check

### R9 — Registration, 4D, replanning (done; physicist review waiting)
Data: 4D-Lung (planning 4DCT, ten phases in one frame of reference, contoured on every phase, markers;
seven weekly 4D cone-beam CTs, each its own frame of reference) and Pancreatic-CT-CBCT-SEG (planning CT,
CBCTs and RT Dose, each contoured).
- [x] R9.1 Registration service (SimpleITK): rigid, then Demons (CT to CT) or B-spline with normalised correlation (CT to CBCT); the total transform as a displacement field on the fixed grid; quality after AAPM TG-132 (similarity before and after, Jacobian and folding, landmark error); `POST /registrations`
- [x] R9.2 Contour propagation (a derived geometry on the fixed CT) and dose mapping between grids
- [x] R9.3 Harness case on 4D-Lung: propagated contours against the clinician's (Dice, HD95, mean surface distance), marker landmark error, rigid-only baseline
- [x] R9.4 4D: average-intensity CT, ITV over phases (from contours or propagated), per-phase dose and deformable accumulation; a lung 4D case
- [x] R9.5 Replanning: register a re-CT or CBCT (density from the deformed planning CT for CBCT), propagate, recompute the plan, compare goals, re-optimize warm, write a new RT Plan with a predecessor and an accumulated RT Dose
- [x] R9.6 DICOM Spatial Registration objects; recalculate imported plans across frames of reference (from R2)
- [x] R9.7 4D robust scenarios (from R3): the phases as scenarios of the accumulated dose, graded worst-case; robust optimization over phases **moved to a later item**
- [x] R9 validation record `docs/validation/2026-10-25-r9/`: the three R9 cases from commit `316b6c6`, one per process; physicist sign-off open

### R10 — Scripting SDK and planning protocols (done; physicist review waiting)
A Python SDK over the REST API, planning protocols that drive end-to-end auto-planning, and the tools to run
them in batches and from workflow engines.
- [x] R10.1 SDK `radiarch.sdk`: one client over HTTP or in process; domain objects (geometry, beam model,
  optimization, arcs and sequences, dose, evaluation, export, registration) whose methods chain the planning steps;
  the services' own request and result models; asynchronous jobs polled to completion; errors with the service's
  detail. The R0 `client.py` stays for the plan and workflow routes.
- [x] R10.2 Auto-planning service: the goal-driven loop the harness plans with (fluence rounds that reweight failed
  goals, sequencing or arcs, normalisation to the coverage goal) moved from the validation cases into
  `services/autoplan.py`; the harness calls the service.
- [x] R10.3 Planning protocols: a JSON schema (site, prescriptions, structure operations, objectives and goal
  template, beams or arcs, machine, engine, rounds, normalisation, export); shipped protocols for the harness's
  lung, lung SBRT and head-and-neck plans; `GET /protocols`, `POST /protocols/run` (a job), the result with its
  goals.
- [x] R10.4 Command line and wrappers: `radiarch plan`, `radiarch batch` (a protocol over a list of cases, a summary
  table of goals per case), `radiarch protocols`; CWL tool descriptions for workflow engines.
- [x] R10.5 Harness and record (`docs/validation/2026-10-26-r10/`, commit `92ce40d`): a protocol run reproduces its harness case; a batch case over the LCTSC thoraces;
  ADR 0017.

### R13 — Viewer integration (done; 3D Slicer check waiting)
Viewing stays outside radiarch: the RT objects go to a DICOMweb server that OHIF reads, and a radiarch
OHIF extension shows what OHIF cannot (the dose) and what radiarch computes (DVH, goals).
- [x] R13.1 RT objects to OHIF through DICOMweb (`docs/viewing.md`): what OHIF 3.13.13 and 3D Slicer show
  (OHIF draws the structure set; it has no RT Dose or RT Plan handler); the structure set checked against
  what OHIF's RT loader reads; `RADIARCH_VIEWER_URL` and `viewer_url` on a pushed export; STOW-RS push and
  QIDO/WADO read-back against Orthanc in CI (`tests/test_r13_viewer.py`, an Orthanc service in Full Tests)
- [x] R13.2a What a viewer needs from the server (ADR 0018): `GET /rt/exports` by study, series or instance
  UID (service, API, SDK `find_exports`); the plan dose carries the RT DVH module, one cumulative DVH per
  exported ROI from the dose as stored (`dvh: true`, the default)
- [x] R13.2b The dose layer (`viewer/`): `rt-dose-core` (RT Dose volume, resampling onto the CT, the file's
  DVHs, prescription and isodose colour wash; Node tests against radiarch's and synthetic doses through
  `tests/test_r13_viewer_core.py`) and `ohif-extension-rt-dose` (RT Dose display sets, the dose viewport, the DVH
  panel); `viewer/scripts/build-ohif.sh` and the CI job "Viewer" build it inside OHIF 3.13.13
- [x] R13.2b′ DVHs computed in the browser for an RT Dose without the DVH module: `rasterize.js` (closed planar
  contours on the dose grid, even-odd), `computeDVHs` with radiarch's bins; the structure set found through the dose,
  its plan, or the frame of reference; labelled as computed; reproduces radiarch's written DVHs bin for bin
- [ ] Draft proposal to OHIF for overlay volumes without the `PMAP` label (`docs/reports/ohif-overlay-volume-proposal.md`);
  filing it is the project lead's decision
- [x] R13.2c The radiarch panel and the plan review mode: `radiarch-client` (tested from Node against a live
  radiarch, API key required: `tests/test_r13_viewer_client.py`), `ohif-extension-radiarch` (plan summary, goal
  template, goals graded and radiarch's DVHs through the export lookup; API URL from the config, headers from the
  host), `ohif-mode-plan-review` (on OHIF's basic mode; hanging protocol `radiarch-rt-dose` in the dose extension);
  all built in OHIF 3.13.13 by the CI job "Viewer"
- [x] R13.2d The standalone delivery: `viewer/standalone` (an OHIF build and nginx; one origin for OHIF,
  Orthanc's DICOMweb and radiarch's API; the API key added by the proxy), the compose profile `viewer`, and
  the browser test `tests/test_r13_viewer_browser.py` in CI's Viewer job (headless Chromium through the plan
  review mode; the dose checked inside OHIF and in pixels, shown against hidden)
- [x] Hand-check fixes (2026-10-27): the dose colour wash shows on a GPU (the dose actor's opacity unit distance), the
  viewport opens on the dose maximum with lighter low bands (`340ef3b`, `5e64d0f`); a fresh clone launches with
  Orthanc fetch and push fixed and a phantom demo, `scripts/demo-viewer.sh` (`bd0982d`)
- [x] A lung-cancer patient in the viewer (`6ba1105`): `radiarch fetch-tcia` (a public TCIA patient into a cache and
  the PACS), the `demo-lung-imrt` protocol (seven IMRT fields, RTOG 0617 goals, minutes on a CPU),
  `scripts/demo-lung.sh`; the dose viewport draws the dose's structure set as contours; planning aids (rings,
  helpers, organ-minus-target) start hidden; each structure named once in the export
- [x] A black image in Chrome on Linux (`e3adcd2`): Chrome's default ANGLE-on-OpenGL backend draws every volume
  viewport black on an NVIDIA workstation; the dose viewport detects a blank image and names the fix (Firefox, or
  ANGLE on Vulkan); planning progress printed by `radiarch plan` (`e3adcd2`, `ffece91`)
- [x] A plan exported again is the same export (`737d2c5`, `26787db`): the same plan and settings return the stored
  export and its UIDs, so a rerun keeps one plan in the study; `new_export` writes a marked copy ("copy N", the
  earlier plan as its predecessor); nothing is deleted
- [x] Hand check in OHIF by the project lead: the lung demo (NSCLC-Radiomics LUNG1-002) and the LCTSC VMAT plan,
  CT, dose colour wash, contours, DVHs and the plan panel, in Firefox on a Linux workstation
- [x] R13.3 Record (`docs/validation/2026-10-28-r13/`): the cases, the OHIF hand check and the findings with their
  fixes; closes R6's hand check in OHIF
- [ ] The objects read by 3D Slicer with SlicerRT (structures, dose, beams, DRRs; Slicer's DVHs against the DVHs
  radiarch wrote), steps and an empty results table in the record **(waiting: the project lead)**

### R11 — Multi-criteria optimization (not started; design proposed)
A set of Pareto-optimal plans computed up front, navigated by sliders or automatically by goal priority, and made
deliverable by dose mimicking. The research and the design: [`reports/mco-research-and-design.md`](reports/mco-research-and-design.md)
(§4 D1–D9; ADR 0019 when built). Estimate about 4.5 ew, against the roadmap's 2: the roadmap counted generation and
navigation only, not hard constraints, deliverable conversion or the viewer panel.
- [ ] R11.1 Convex trade-off objectives and hard constraints (D1, D2): `MeanDose`, `EUDMax`, `EUDMin`, `RMSOver`,
  `RMSUnder`, `UniformRMS`, each read in Gy; nonconvex types refused as trade-offs; constraints by an
  augmented-Lagrangian loop around L-BFGS-B; a feasibility run that names the violated constraints; redundant
  objectives reported (about 0.5 ew)
- [ ] R11.2 The Pareto set (D3, D4): anchors with a small weight on the others, a balance plan, sandwich plans (inner set
  with dummy points, vertex enumeration of the outer set, HiGHS duals as the next weights) to an error bound or a plan
  budget (3N + 1 by default); warm starts; navigation voxels; the error bound per plan; `POST /mco/run` as a job with
  a cache key and lineage (about 1 ew)
- [ ] R11.3 Navigation (D5): the piercing LP over the blend weights with clamps and locks; exact values, DVH and goals
  on the blended dose; stored, named states with the balance plan as reference; `POST /mco/{id}/navigate`,
  `GET /mco/{id}/states` (about 0.5 ew)
- [ ] R11.4 Automatic navigation and projection (D6): lexicographic over the blend weights by a goal template's
  priorities with slip; projection onto the Pareto set; `POST /mco/{id}/auto-navigate` (about 0.5 ew)
- [ ] R11.5 The deliverable plan (D7): a `ReferenceDose` mimicking objective; static fields sequenced (R4), arcs (R8)
  and proton spots with their minimum meterset, each re-optimized against the navigated dose; normalisation (R10);
  the deviation table with its flags; `POST /mco/{id}/deliverable` (about 0.75 ew)
- [ ] R11.6 Robust MCO (D8): the scenario-wise worst case in generation; nominal and worst-case values in navigation
  (about 0.25 ew)
- [ ] R11.7 SDK, command line, protocols and viewer (D9): `ParetoSet` in the SDK; a protocol's `mco` section used by
  `radiarch plan`; the navigation panel in the OHIF extension (sliders, clamps, live DVH and goals) (about 0.5 ew)
- [ ] R11.8 Record and ADR 0019: the algorithm tests of report §5 in CI; the TG-119 C-shape front, the lung demo
  (automatic navigation against the R10 protocol plan, navigated against deliverable, plans against the error bound),
  a robust proton case; physicist sign-off (about 0.5 ew)
- [ ] Later **(open)**: shared-aperture or shared-sweep Pareto plans so navigation shows the deliverable dose;
  tail-mean (CVaR) trade-offs; Pareto sets across beam arrangements; the TROTS benchmark
