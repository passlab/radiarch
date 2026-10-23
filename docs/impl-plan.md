# Radiarch — implementation plan and tasks

State: 2026-10-22. The design is in [`architecture.md`](architecture.md); what each item
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
| 13 | R8 Native pencil-beam engine, VMAT, SBRT | in progress (uncommitted) | — | 0015 |
| 14 | R9 Registration, 4D, replanning | not started | — | — |
| 15 | R10 Scripting SDK and planning protocols | not started | — | — |
| 16 | R13 Viewer integration | not started | — | — |
| 17 | R11 Multi-criteria optimization | not started | — | — |

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
- [ ] Objects checked by hand in OHIF and 3D Slicer **(open)**
- [ ] Wedges, compensators, blocks, bolus; DVH sequence in RT Dose **(open)**

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

### R8 — Native pencil-beam engine, VMAT, SBRT (in progress)
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

### R9 — Registration, 4D, replanning (not started)
- [ ] Rigid and deformable registration (SimpleITK) and contour propagation
- [ ] ITV from 4DCT phases; per-phase dose with deformable accumulation
- [ ] Replanning: register a re-CT or CBCT, propagate, recompute the plan, compare goals, re-optimize warm, write a new RT Plan with a predecessor and an accumulated RT Dose
- [ ] Recalculate imported plans across frames of reference (from R2)
- [ ] 4D robust scenarios (from R3)

### R10 — Scripting SDK and planning protocols (not started)
- [ ] A Python SDK that mirrors the domain (patient, course, plan, beam set, optimization, evaluation) over the REST API
- [ ] JSON planning protocols (site, prescription, structures, objectives, goals, beams, machine) for end-to-end auto-planning
- [ ] Tool wrappers for workflow engines; batch planning

### R13 — Viewer integration (not started)
- [ ] RT objects to an OHIF deployment through DICOMweb (works today by push; to be documented and tested)
- [ ] A viewer panel with DVH, clinical goals and the plan summary from `/evaluate`

### R11 — Multi-criteria optimization (not started)
- [ ] Pareto surface generation on the objective set
- [ ] Navigation and auto-navigation against goal priorities
