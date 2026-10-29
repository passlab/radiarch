# Radiarch implementation log

What each roadmap item did, in roadmap order: the files, the decisions made on the way, the fixes, the tests,
and what was left open. The plan and the task checklist are [`impl-plan.md`](impl-plan.md); the decisions behind each
item are in [`adr/`](adr/); the evaluation that set the roadmap is
[`reports/tps-evaluation-and-roadmap.md`](reports/tps-evaluation-and-roadmap.md). Earlier work (the six services,
February to October 2026) is summarized under "Before the roadmap" below; its documents are in the git
history (commit `2f7b506` is the last that has them).

## Before the roadmap (2026-10-20)

**State on 2026-10-20.** Features 1–6 (geometry, beam model, dose, optimization, beam-angle search, evaluation) had landed (Features 4–6 in `cbf097d`, PR #4): services, routes, Celery tasks, demos and ADRs 0002–0004 exist, and the full suite is **674 passed, 2 skipped** (the skips are the opt-in real-MCsquare V4 legs; set `RADIARCH_RUN_MCSQUARE_VALIDATION=1` to run them). Still open: V1–V4 sign-off on a machine with MCsquare and real CT, and the photon CCC engine, which remains a stub (ADR 0001).

**Removed 2026-10-20:** the 4D delivery simulator (`core/simulator.py`, `/simulations`), the synthetic planner fallback (`RADIARCH_FORCE_SYNTHETIC`, `_run_synthetic`) and the OHIF extension + `demo/index.html`. The first two returned invented numbers (random QA/gamma; the simulator's OpenTPS branch called methods that do not exist), and viewing belongs to an OHIF deployment outside this repo. A plan job now fails with the error on the job when OpenTPS is missing or a runner raises; API-contract tests inject a test-only fake runner from `tests/conftest.py`. Suite after removal: 666 passed, 2 skipped (668 collected).

**Direction 2026-10-20:** the evaluation and roadmap are `docs/reports/tps-evaluation-and-roadmap.md` (R0–R15). Decisions: the core (data model, DICOM in/out, plan model, optimizer, evaluation, writers) is radiarch's own code; MCsquare and the CCC binary are run as subprocess tools behind radiarch drivers; **OpenTPS is reference code, not a dependency** — the vendored 3.0.1 copy (`scripts/vendor-opentps.sh`, `src/opentps/patches/`) stays only until R1, R14, R2 and R15 replace what is still imported, then `src/opentps` goes and `engines/` keeps binaries, data and licences. pyRadPlan and matRad are offline cross-checks only. Work order: R0 hygiene → R1 CCC driver → R14 MCsquare driver → R2 DICOM RT readers → R15 own core → R3 … (see the report).

## R0 — hygiene (2026-10-20)

Photon plans are assembled with OpenTPS's real API (`build_photon_plan`; they used to end up with no beams), the robust workflow's setup errors reach OpenTPS (`configure_robustness`), the beam model is built on the persisted geometry (`geometry_bundle.load_opentps_geometry`) instead of re-reading the default phantom, the analytic engine is flagged `test_only` and refused outside `RADIARCH_ENVIRONMENT=dev`, the API key guards every router except `/info`, `LICENSE` (Apache-2.0) and `NOTICE` exist, and every result model, `/info` and every RTDOSE carry "not for clinical use". ADR 0005 records the direction. Tests: `tests/test_r0_hygiene.py`.

Committed 2026-10-20 (265b0cd).

## R1 — CCC through radiarch's own driver (2026-10-20)

Photon dose is real. `models/photon_plan.py` is radiarch's own plan model (beams, segments with jaws and MLC rows, beamlets on the same half-pixel grid OpenTPS used); `services/dose_engines/ccc_driver.py` speaks the WiscPlan binary's file protocol (geometry, beamlet specs, sparse output; exit code 1 = success) and is byte-for-byte compatible with OpenTPS's IO; `services/dose_engines/ccc.py` is the engine behind the `DoseEnginePlugin` protocol with a reference-field calibration (10 × 10 cm², SSD 100, 1 cGy/MU at d_max; cached under `artifacts/ccc/`) and setup-shift / density scenarios. The legacy `photon-ccc` workflow runs on it. Settings: `RADIARCH_CCC_ENGINE_DIR`, `RADIARCH_CCC_N_JOBS`, `RADIARCH_CCC_CALIBRATION_SPACING_MM`. Tests: `tests/test_ccc_engine.py` (protocol, OpenTPS parity, physics on water phantoms). Still open from R1: a run on a public lung CT (LCTSC) once the data is downloaded; no linac head model and generic 6 MV kernels remain the engine's limits.

Committed 2026-10-20 (caf6ee5).

## R7a — validation foundation (2026-10-21)

`src/radiarch/validation/` — phantoms, reference tables with citations (`references/*.json`), case files (`cases/*.yaml`), the runner (`run.py`: photon PDD/profile/heterogeneity/output-vs-field, proton range, LCTSC geometry volumes, DVH cross-check against dicompyler-core, gamma cross-check against pymedphys via `uv run --python 3.12`), and `goldens.py` + `tests/golden/` + `tests/test_goldens.py` (CCC beamlet matrix captured; SimpleFantom geometry, spots and MCsquare input files follow). Data fetched into the data directory outside the repo (`RADIARCH_VALIDATION_DATA`): TG-119 package, six LCTSC patients, five Pancreatic-CT-CBCT-SEG patients. CI: nightly `validation-harness` job. Findings of the first run (details in `docs/reports/validation-data-and-test-plan.md` §8): the WiscPlan CCC binary truncates scatter (`doseCutoffThreshold 0.005` per beamlet and `RSAFE 2 cm` in `defs.h`), so output factors are flat; rebuilt from source it is bit-identical, and with full scatter its kernels behave harder than 6 MV (PDD10 70 %) — the MC reference (R7) and the native engine (R8) gain priority; MCsquare maps HU 0 to a Schneider tissue blend, so water phantom tests use a water-only calibration; radiarch's gamma lacks sub-voxel interpolation (R5). matRad is GPL v3 (not BSD-3); R8 must not copy its base data. All goldens captured; 722 tests pass.

Committed 2026-10-21 (37afa07, 0070918).

## R7a finished; R14 — own MCsquare driver (2026-10-21)

R7a: PSTAR CSDA ranges (NIST, liquid water, 70–250 MeV) entered in `validation/references/proton_water.json` with a 1 % + 1 mm tolerance; the first full (non-fast) harness run recorded in `docs/validation/`.

R14: `models/proton_plan.py` (radiarch's PBS plan, `from_opentps` adapter) and `services/dose_engines/mcsquare_driver.py` (MHD CT, scanner tables, BDL, PBS plan text, config from the engine's template; subprocess through the launcher; MHD dose and sparse-beamlet readers; `(z, y, x)` frames) replace the OpenTPS wrapper inside the `mcsquare` engine plugin (0.3.0). Inputs are byte-identical to the frozen goldens and the dose equals the OpenTPS path at a fixed seed (ADR 0006). Settings: `RADIARCH_MCSQUARE_DIR`, `_N_THREADS`, `_SEED`, `_SCANNER`, `_BDL`, `_KEEP_WORKDIR`. The engine assets stay under `src/opentps/.../MCsquare` until R15 moves them to `engines/`. Tests: `tests/test_mcsquare_driver.py`.

Committed 2026-10-21 (15c46ec).

## R2 — DICOM RT in (2026-10-21)

`src/radiarch/dicom/` reads RT Plan → `PhotonPlan` (segments per control-point interval, arcs discretized per interval; since R8 an arc is read back as an arc), RT Ion Plan → `ProtonPlan`, RT Dose → `(z, y, x)` volume with resampling, and Spatial / Deformable Spatial Registration objects. `services/plan_import.py` stores an imported plan as a beam model with the plan's metersets (`plan_weights.npy`); `POST /beam-model/import` and `POST /dose/recalculate` expose it. Frame-of-reference mismatch is refused by default (registration is R9). ADR 0007. Tests: `tests/test_dicom_readers.py`, `tests/test_plan_import.py` (the last case shows a recalculated MCsquare dose equal to the engine's for the same plan).

Committed 2026-10-21 (7df0c3c).

## R15 — own core, OpenTPS removed (2026-10-21)

ADR 0008 records the decision, the evidence and the one deliberate deviation.

Done:
- Own loaders `dicom/{ct,rtstruct,case}.py` (identical arrays and polygons to the OpenTPS
  loader on SimpleFantom and LCTSC-Test-S1-101); rasterizer `services/contour_raster.py`
  (masks identical on 4 grids × SimpleFantom and 3 grids × 5 LCTSC structures); calibration
  `services/proton_rsp.py` (identical HU→density/RSP); spot placement
  `services/spot_placement.py` (bit-identical on the golden case and the oblique cases;
  posterior/lateral beams differ by edge spots or a layer shift because tiny direction
  components no longer make boundary spots crawl in 1 µm steps — 100× faster).
- Services rewired: `GeometryArrays`/`load_geometry_arrays`, `generate_proton_spots(geometry,
  machine_model, beam_set, params)`, machine model on the driver assets (`.rsp_model`),
  `StoichiometricModel` on the scanner table, no `ct_image` on `GeometryBundle`, geometry
  service and NRRD adapter on the own loaders, validation DVH cross-check on the own reader.
- Legacy `/plans` workflows rewritten on the services (`core/workflows/*`): basic =
  unit-MU MCsquare dose; optimized = Dij + inverse optimization + final dose; robust =
  robust optimization over `_helpers.robust_scenarios` (REDUCED_SET 8, ALL 20, RANDOM n;
  worst-case aggregation) + scenario doses; photon = open fields on CCC. Fixed on the way:
  the plan record never stored the workflow parameters the workflows read
  (`PlanParameters` on `PlanDetail`, `plans.parameters` JSON column, migration
  `b7e2c4d9a1f0`); legacy solver names map onto radiarch's (`solver_method`); the
  geometry is built on `scoring_spacing_mm` (2 mm default) instead of always the CT grid.
- Engine assets moved to `engines/mcsquare` and `engines/ccc` (`engines/README.md`,
  `scripts/fetch-engines.sh` replaces `vendor-opentps.sh`); `src/opentps` deleted; drivers
  default to `engines/` (or `/app/engines` in the image); Dockerfile, CI, compose, env
  templates, `install-dev.sh`, `pyproject` (radiarch* only, nibabel dropped) updated.
- Settings: `RADIARCH_DATA_ROOT`, `RADIARCH_BEAM_LIBRARY_DIR`; `opentps_venv` gone. Test
  data at `tests/data/SimpleFantomWithStruct`. `tests/opentps/` and
  `test_opentps_integration.py` removed; `test_api_backend.py` moved to `tests/`;
  `test_engine_assets.py` replaces `test_package_layout.py`; OpenTPS parity tests
  dropped (the goldens are the reference). README, NOTICE, demo.md, ADR 0006 updated.
- Isocenter: still the target centre of mass; the request's `isocenter_mm` is ignored
  (as before). Decide in R3.

- pydicom 3.0.2 (pin `pydicom>=3.0,<4`; `enforce_file_format=True`, no
  `is_little_endian` attributes; the DICOM tests pass with pydicom deprecations as errors).
- `tests/test_plans_workflows.py`: basic proton on every run; photon, optimized and robust
  opt-in (`RADIARCH_RUN_MCSQUARE_VALIDATION=1`).

Committed 2026-10-21 (091c0c0..5947ad2) and pushed.

## R3 — robust protons through the engine, Gy(RBE), craniospinal fields (2026-10-21)

ADR 0009. Done:
- `EngineScenarioSet` (ALL 81 / REDUCED_SET 21 / RANDOM n; systematic, random and range
  errors) on `ScenarioSetSpec.engine_native` and `RobustnessSpec.engine_native`; the MCsquare
  driver's robustness mode (`robustness_config`, `read_scenarios_file`, scenario doses and
  scenario beamlets from one run); `MCsquareEngine.compute_scenario_doses` /
  `build_scenario_influences`; `DoseService` native path and `build_native_influences`
  (per-scenario Dij cached under the single-scenario keys); the optimizer takes the set.
  `ScenarioSpec.setup_random_sigma_mm` records the per-fraction random error.
- RBE: `rbe` on dose, influence and optimization requests (null = 1.1 protons, 1.0 photons),
  `rbe_factor`/`dose_units` on results; legacy RTDOSE `DoseType EFFECTIVE`.
- Evaluation: `dvh_bands`, `robust_metrics` (lowest/highest envelope + per scenario),
  `robust_indices` (worst coverage, D95, D98, D2, hotspot, HI, CI, worst scenario),
  `include_scenarios`, `dose_units`.
- Beam sets: `BeamSpec.isocenter_mm`, `BeamSpec.target_z_range_mm`; `BeamSetSpec.isocenter_mm`
  optional and honoured (was ignored); `services/plan_templates.craniospinal_template`
  (posterior fields, optional posterior-oblique brain pair with `brain_oblique_deg`) and
  `POST /beam-model/templates/craniospinal`; `generate_proton_spots` places each beam on its slab.
- Legacy `proton-robust` uses the native set (random error now modelled).
- Tests: `tests/test_r3_robust_rbe_templates.py` (models, RBE through the dose service, native
  sets with a fake engine + evaluation bands, scenarios-file parser, MCsquare native doses and
  beamlets with the binary, split/template/spots on a synthetic craniospinal target).
Open: probabilistic robust objectives; clinical-goal pass/fail (R5); 4D scenarios (R9).
Fraction-wise junction shifts are deliberately not modelled (gradient junctions + robust
optimization replace them in PBS; ADR 0009). Committed 2026-10-21 (c776958..709b533).

## R4 — machine model and apertures (2026-10-21)

ADR 0010. Done:
- `models/machine.py` (PhotonMachineSpec: energies, MLC, jaws, limits; ProtonMachineSpec from the
  BDL); `radiarch/machines/synthetic-120.json`, `synthetic-160.json`; `PhotonMachineModel` on the
  spec (`default` = synthetic-120; custom `{beam_library_dir}/{id}/machine.json`);
  `GET /beam-model/machines[/photon|proton/{id}]`.
- Masks as a uint64 bitmask (`services/masks.py`; `GeometryResult.mask_encoding`); overlapping
  structures keep their voxels; every consumer reads through `structure_mask`. The geometry golden
  now hashes the per-structure boolean masks (re-captured; spots and MCsquare inputs unchanged).
- `services/structure_ops.py` (expand/erode by Euclidean distance, per-axis margins, ring,
  union/intersection/subtract, couch slab), `services/geometry_derive.py`, `GeometryService.derive`,
  `POST /geometry/{id}/derive` (`StructureOperation`, `GeometryDeriveRequest`); `GeometryResult`
  gains `parent_geometry_id`, `derived_operations`, `hu_to_density_model`.
- `services/sequencing.py` (fluence maps on leaf pairs, Bortfeld–Boyer segments, machine limits,
  coverage matrix, segment-weight optimization with the existing solvers, minimum MU/area,
  deliverability), `services/apertures.py` (`ApertureService`: aperture plan persisted as a new
  beam model, segment dose as a dose result, `ApertureStore`), `models/apertures.py`,
  `POST /optimize/{id}/sequence`, `GET /optimize/sequences/{id}`.
- Tests: `tests/test_r4_machine_structures.py`, `tests/test_r4_sequencing.py`,
  `tests/test_r4_apertures_service.py`.
Open: DAO refinement; leaf transmission / tongue-and-groove in the segment dose; asymmetric
margins; VMAT (R8); the RT writer on the aperture plan (R6). Committed 2026-10-21
(f906c51..a3c0b89).

## R5 — evaluation: clinical goals, radiobiology, gamma, comparisons (2026-10-21)

ADR 0011. Done:
- `services/clinical_goals.py` (TG-263 metric parser and evaluator, templates, structure
  resolution), `radiarch/goals/*.json` (rtog-0617, quantec, tg101-sbrt-3fx, tg101-sbrt-5fx,
  nccn-head-neck, pentec-pediatric [provisional]); `GoalSetSpec`, `GoalsReport` on the evaluation
  request/result; `GET /evaluate/goal-templates[/{id}]`.
- `services/radiobiology.py` (EQD2, BED, gEUD, LKB NTCP with 12 parameter sets, Poisson TCP with 3,
  default α/β); `NTCPSpec`/`TCPSpec` on the request, results with per-scenario values;
  `GET /evaluate/models`; `EvaluationRequest.fractions`.
- `services/gamma.py` rewritten: reference points, evaluated dose interpolated (5 steps per DTA),
  early-stopping vectorized search; 56.2 % on the harness's borderline case (pymedphys 56 %).
- `services/dose_compare.py` + `POST /evaluate/compare` (dvh_impact: metric/index deltas, goal state
  changes; by request or by evaluation id).
- Tests: `tests/test_r5_evaluation.py`.
Open: the goal tables need a physicist's check against the sources before answer-key use
(PENTEC marked provisional); relative-seriality NTCP; LQ-L for SBRT; structure-set comparison
metrics (Dice, HD95) belong to A2.

Committed 2026-10-21 (dfe907c..5612286).

## R6 — RT object writer (2026-10-21)

ADR 0012. Done:
- `dicom/writers/` — `common.py` (`CaseContext`, dataset skeleton, research labelling, stable UIDs),
  `rtstruct.py` (masks → contours, interpreted types), `rtplan.py` (RT Plan step-and-shoot, RT Ion
  Plan, prescription as dose reference, DRR references), `rtdose.py` (PLAN/BEAM, EFFECTIVE for RBE),
  `rtimage.py` (DRR RT Image), `records.py` (RT (Ion) Beams Treatment Record, RT Treatment Summary
  Record); `dicom/drr.py` (ray-marched DRR on the spot placer's beam frame).
- `CTMetadata` carries the CT's DICOM provenance (patient ID/sex/birth date/position, study date and
  description, slice UIDs); `CTVolume` reads them; old geometries fall back to `RADIARCH_DATA_ROOT`.
- `services/rt_export.py` + `models/rt_export.py` + `api/routes/rt.py`: `POST /rt/export` (sequence /
  proton optimization / beam model), manifest and files, `POST /rt/exports/{id}/records`,
  `POST /rt/exports/{id}/push`; per-beam doses through the dose service; STOW-RS push.
- `adapters/dicomweb.py` takes datasets, paths or bytes (the legacy push passed bytes to a client
  that wanted datasets); the legacy `/plans` RT Dose goes through the writer.
- Validation: `dicom-validator` (dev extra; every object type clean against 2026d) in the suite,
  `dciodvfy` (dicom3tools) as a CI step; opt-in DICOMweb round trip passed against the research
  Orthanc (STOW → QIDO → WADO → readers → delete).
- R4 fix found by the BEAM doses: `sequencing.fluence_maps` binned a beamlet onto the leaf pair of
  its centre only, so 10 mm beamlets over 5 mm leaves left every other pair out of the apertures (a
  comb) and `coverage_matrix` credited half the coverage; a beamlet now covers every pair it spans
  and the coverage sums over them, so beam doses sum to the plan dose.
- Tests: `tests/test_r6_rt_writers.py`, `tests/test_r6_rt_export_service.py`.
Open: view the objects in OHIF and 3D Slicer by hand on the next fixture load (contours written on
the geometry grid, not the CT grid, when the geometry was resampled); arcs as VMAT control points
(R8); wedges, compensators, blocks and bolus; DVH sequence in the dose; RT Beams Delivery
Instruction and UPS belong to the record system (an OIS).

Committed 2026-10-21 (d3deb77..a9b8cce).

## R12 — versions, lineage, attribution and states (2026-10-21)

ADR 0013. Done:
- `models/lineage.py` (`VersionRef`, `Attribution` with `DatasetRef`, `StateRecord`, `VersionStatus`,
  `LineageGraph`, `DerivationRecord`; states draft/approved/superseded/retired and their transitions).
- `services/lineage.py` (`LineageService`: nodes with parents per kind over the existing stores,
  `lineage`, `descendants`, `attribution`, `status`/`transition` with the JSON state store and audit,
  `locked_keys`/`assert_deletable` (ever-approved versions and their ancestors), `derivation_record`
  in a dataset manifest's shape, `capability` declaration).
- `api/routes/lineage.py` (`/lineage/capability`, `/lineage/{kind}/{id}[/descendants|/attribution|
  /derivation|/state]`); `api/routes/_lineage_guard.py` on every delete route (409 when locked).
- The RT export manifest carries `attribution`; the DICOM private block names the engine and machine.
- Tests: `tests/test_r12_lineage.py` (service, API, schema validation of the derivation record when
  the manifest schema is installed).
Open: the engine binary's container digest in the attribution; the state route's caller will be a
record system (an OIS); lineage across radiarch instances; audit-trail immutability.

Committed 2026-10-21 (3e653f2..fe0573e).

## R7 — validation report (2026-10-22)

ADR 0014. Done:
- `engines/ccc/CCC_DoseEngine` rebuilt from source with `CCC_DOSE_CUTOFF` / `CCC_RSAFE_CM` as run-time
  parameters (shipped constants as defaults; goldens bit-identical; `engines/ccc/BUILD.md`); driver
  `params["scatter"]` shipped|full, `RADIARCH_CCC_SCATTER`; calibration keyed by the setting; `shipped`
  stays the default (full overshoots at depth).
- `validation/mc_reference.py`: OpenGATE 10.1.1 through uv/Python 3.12; Mohan 6 MV point source (the
  kernels' own spectrum) through the Versa jaws and MLC; phantoms as stacked sibling boxes, one dose actor
  each; step-converged (e-/e+ max step 0.5 mm, 0.1 mm cut); compact storage (float16 relative dose,
  per-mille uncertainty, 4.4 MB each); references `references/mc/{water_10x10,lung_slab,bone_slab}`
  at 5e7 primaries (96–112 min each on 18 threads).
- `validation/pyradplan_crosscheck.py` (pyRadPlan 0.5.0 photon SVD pencil beam, own uv environment,
  `pydantic<2.12`) → `references/pyradplan/`; informative.
- `validation/cases_r7.py` (`photon_vs_mc` with heterogeneity correction factors and both scatter settings,
  `photon_vs_pyradplan`, `dij_consistency`, `proton_bragg_peak`, `tg119_planning` with goal-driven reweighting
  rounds and institutional-spread grading, `lung_e2e_lctsc`); `validation/common.py`; CCC dose cache
  `validation/cache/ccc` (gitignored); DVH cross-check runs dicompyler-core in its own uv environment.
- `validation/report.py`: one signed document per engine (identity with binary/BDL digests, checks with
  sources, limitations, signature block); `--also` merges a rerun case; nightly CI writes them.
- Fixed on the way: the geometry service ignored the patient reference's structure set and CT series on
  disk, upload and PACS loads (TG-119's four sets were merged; the prostate was planned on the head-and-neck
  PTV); numpy bools in check results; the MCsquare launcher's build is recorded.
- Record (`validation/results/20261022-123318-fe0573e` + `20261022-123414-fe0573e`; documents in
  `validation/reports/`): MCsquare all pass; TG-119 24/24; lung 2/2; CCC vs Monte Carlo in water PDD10
  68.1 vs 68.0 %, gamma 3 %/3 mm 98.0 %, 7 % low at 25 cm; bone correction factors within 3 %; lung 5 %
  low inside, 4 % high far beyond; DVH max 3 of 25 structures 3.5–4.6 % off dicompyler-core; one LCTSC
  oesophagus volume +5.0 %.
- Tests: `tests/test_r7_validation.py`.
- Record for review: `docs/validation/2026-10-22-r7/` (reviewer guide, the three documents, run summary and
  results of the clean-commit run `20261022-150018-20fc3bf`; the outcome is identical to the earlier run).
Open: physicist sign-off of the three documents; new CCC kernels from the OpenGATE reference or the native
engine (R8) for the deep-water and lung errors; matRad needs MATLAB (not done); the full Versa head
reference (hours) for the record; reference output factors with a head model.

Committed 2026-10-22 (2e21a28..2f7b506).

## R8 — native pencil-beam engine, VMAT, SBRT (2026-10-22 to 2026-10-23)

ADR 0015. Done:
- CCC gantry convention fixed (IEC 61217 frame of the DRRs, mapped into the engine's axes); CCC 1.1.0.
  `EngineSpec.key_version()`: "default" resolves to the engine's version in every cache key.
- `validation/mc_reference.py --pencil` (OpenGATE pencil kernel, 3e7 primaries) →
  `services/dose_engines/pb_kernel.py` (stitch, isocenter-plane remap conserving each depth's integral, radius
  bins, deep continuation; SVD of the cumulative kernel at load) → `engines/pb/pb_6mv_kernel.{npz,json}`.
- `services/dose_engines/pb.py`, engine `pb` 1.0.0: radiological depth on a divergent ray grid, full-kernel
  fluence convolution (beamlets or apertures), influence matrix with an 80 mm cutoff and Weyl-sequence
  roulette below 0.3 %, `segment_dose_matrix`, Gaussian fluence penumbra, output calibration, enclosed
  cavities dosed, NumPy/CuPy backend (`RADIARCH_PB_DEVICE`; `gpu` extra; on GPU doses equal the CPU's to
  3e-6, 6–25 times faster; `test_gpu_matches_cpu`). Production kernel 3e7 primaries, fingerprint
  f046d6a503757f17, four components, penumbra FWHM 4.0 mm fitted to the Monte Carlo 80-20 % penumbra.
- Plan model: `PhotonArc`/`ArcControlPoint`, `PhotonBeam.arc`, `PhotonSegment.gantry_deg`; CCC and pb honour
  sector angles; RT Plan writer writes DYNAMIC beams, reader reads arcs back; the collimator now reaches the
  open-field plan.
- `models/vmat.py`, `services/vmat.py`, `POST /optimize/{id}/arcs`: arc sequencing of sector fluence maps,
  alternating sweeps, interval timing (gantry, leaf, dose-rate floor) per fraction, meterset re-optimization.
- `services/sbrt.py` (R100, R50, D2cm, GI, lung V20, RTOG 0813/0915 table); templates `sbrt-lung-54gy-3fx`,
  `sbrt-lung-50gy-5fx`; NCCN template alias `Mandible: Bone_Mandible`.
- Harness: `cases_r8.py` (`pb_vs_mc` with Monte Carlo field-size checks, `pb_vs_ccc`, `lung_sbrt_vmat`, `lung_vmat_lctsc`, `hn_sib_vmat`), `photon_*_pb` variants
  (`common._photon_engine`), `pb` in `dij_consistency`, a fourth document in `report.py`; the R7 lung case now
  keeps its organs (one structure set) and plans on Lungs-PTV without a maximum-dose term; run records give the
  CPU, not the host. A beam set holds up to 180 beams (sector beams of arcs).
- Docs: the evaluation and the validation study in `docs/reports/`; an index, `docs/README.md`; no references to other projects.
- Tests: `tests/test_r8_{pb_engine,arcs,vmat,sbrt}.py` (the cross-engine gamma against CCC included).
Findings: CCC's shipped scatter cut-off makes the central dose independent of field size and the depth dose
depend on the beamlet size, and gives zero dose ~2 cm outside the beamlets (ADR 0015).
- Delivered plans: `PhotonSegment.coverage_beamlets()` (every aperture cell with its open fraction),
  `ccc_driver.delivered_beamlet_geometry`, `CCCEngine.compute_delivered_dose`; the harness's second-engine
  recompute of arcs uses it. The first full run (`20261022-225008-dcdc7f3`) had recomputed arcs through the
  optimizer's beamlet cut, which drops leaf pairs no wider than one beamlet: CCC PTV D95 0.63–0.72 of pb.
- Harness files are read and written as UTF-8 (the summary failed in a shell without a UTF-8 locale).
- The lung arcs' second-engine gap that remained (CCC / pb PTV D95 0.70–0.87, 1.04–1.09 with the body as
  water) was pb overdosing narrow fields in lung: a new OpenGATE reference `lung_slab_2x2` gave pb 22–27 % high
  in the lung. `pb` 1.1.0 scales the kernel laterally: the part within 30 mm stretched by rho_eff^-0.9 (5 mm
  smoothed density, five precomputed scales, log interpolation), fitted to both lung slabs (within 2 %); lung
  checks in `pb_vs_mc` graded as consistency checks; `TestLateralScaling`.
- GPU: the CUDA driver sets the thread's locale to C on first use; `backend()` launches a first kernel and
  restores it (`test_gpu_backend_keeps_the_locale`); golden tests read their files as UTF-8.
- `lung_sbrt_vmat`: the far ring reaches the skin (`ring_far_outer_mm: 400`): with pb 1.1.0 the unconstrained
  entrance dose of heavy beamlets 18–22 cm from the PTV gave D2cm 70–83 %; now 49 % on the second patient.
- `pb` 1.1.1: CuPy 14's constant-mode `map_coordinates` on float32 reads one element past the array for a
  coordinate just below the last index (mixed float32/float64 index arithmetic): rare garbage voxels (up to
  1e30) in GPU doses, the 0 % CCC gamma of one lung arc patient. `_lookup` pads on the GPU and zeroes points
  outside the array; repeated GPU doses bit-identical; `test_gpu_lookup_stays_inside_the_array`.
Open: a Monte Carlo tumour-in-lung reference and whole-plan Monte Carlo as the second engine; direct leaf
optimization for VMAT; the R8 record for the physicist.

## DICOMweb push for research write endpoints (2026-10-23)

- `adapters/dicomweb.py`: OAuth2 client-credentials bearer token (`RADIARCH_DICOMWEB_TOKEN_URL`, `_CLIENT_ID`,
  `_CLIENT_SECRET` as a `SecretStr`, `_TOKEN_SCOPE`), fetched on first use, shared per endpoint and client,
  refreshed before `expires_in`; basic auth kept for plain PACS (an explicit username wins).
  `DICOMwebPushError` carries a refusal's HTTP status and body.
- `RTPushResult.http_status` and `.response` (the refusal body, parsed when JSON); the export label defaults to
  `RESEARCH`; two docstrings lose an external plan identifier.
- Tests: `tests/test_dicomweb_push_auth.py` (a local token and STOW-RS stand-in: token reuse and refresh, the
  secret kept out of settings' repr, a 409 with findings, a bad secret).

## Derived geometries stored transposed (fixed 2026-10-24)

- `GeometryStore.save` takes (x, y, z) arrays; `geometry_derive` (R4) passed its (z, y, x) arrays unchanged, so
  every derived geometry (PTV, rings, overrides) was stored with x and z swapped against its parent. Planning and
  evaluation read the same swapped arrays, so plans were self-consistent and passed their checks, but the anatomy
  was mirrored against the beams and the CT, and exported structure sets were misplaced (an exported tumour
  centroid 46 mm from the clinical one). The R4 test used a centred cube. Fixed: the derive step transposes before
  saving; `DERIVE_VERSION` "2" in its cache key; `test_derived_volumes_keep_the_parent_orientation` (a 40 × 30 × 20
  grid, an off-centre CTV).
- Affected harness cases (clean run `20261024-152201-d458e46`, the R8 record's correction folder
  `2026-10-24-correction-d458e46/`, and an erratum in the R7 guide): `lung_e2e_lctsc` (R7 and R8 records), `lung_sbrt_vmat`,
  `lung_vmat_lctsc`, `hn_sib_vmat`. All checks pass as before; organ doses change: spinal cord D0.03cc from
  0–0.7 Gy to 10–20 Gy, heart D0.03cc in the SBRT case from 0.3–0.6 Gy to 17 Gy, and in the head-and-neck case
  the optic structures fall from 16–23 Gy to under 1 Gy while the parotid mean rises from 2–11 Gy to 22–30 Gy.
  The engine, Monte Carlo, phantom, TG-119 and cross-check cases do not derive geometries and are unchanged.

## RT Dose round-off below zero wrapped (fixed 2026-10-24)

- The RT Dose writer (R6) scaled the dose into unsigned 32-bit pixels without clipping: a voxel at -1.9e-5 Gy (the
  pencil beam's FFT round-off; 48 682 voxels of a lung VMAT dose) became 2^32 x the scaling, about twice the plan's
  maximum (133.6 Gy against 66.8 Gy), so every exported RT Dose of such a dose had false hot spots. The writer now
  clips below zero and NaN to zero; `test_rtdose_round_off_below_zero_does_not_wrap`. Found by a position check
  before a push (the 95 % dose region of the exported RT Dose 222 mm from the PTV). The validation records are not
  affected: they grade the dose arrays, not exported RT Doses.

## RT Plan metersets per fraction (fixed 2026-10-25)

- DICOM's fraction group states one fraction's metersets (`BeamMeterset`, the control points' cumulative weights,
  a session's specified meterset in a treatment record). radiarch's photon plans hold the course's MU (they are
  optimized against the course dose), and the R6 writer wrote them as they were: a 60 Gy in 30 fractions VMAT
  plan said 26 200 MU per fraction for one arc instead of 873. The R2 photon reader did the reverse (an imported
  plan's metersets taken as the course's, so its recomputed dose was one fraction's). Proton plans were consistent
  on import (the plan's fraction count multiplies the dose) but written the same way on export.
- Fixed: `per_fraction(plan, n)` (photon: MU / n; proton: MU × the plan's own fractions / n) at the entry of the RT
  Plan, RT Ion Plan and both treatment-record writers; the photon reader multiplies by the fractions planned;
  metersets written to 10 significant digits (the conversion made 6 too few for a round trip).
  `PhotonPlan.scaled`. The R6 tests that asserted course MU in the files now assert one fraction's.
- Found by the R10 protocol test, which compared an exported plan's metersets with its plan's. The validation
  records are not affected (they grade dose arrays); every exported RT Plan was.

## R9 — registration, contour propagation, dose mapping, 4D, replanning (2026-10-24)

- `services/registration.py` (SimpleITK 2.5): rigid Euler 3D with Mattes MI over a pyramid, then diffeomorphic
  Demons (CT to CT) or B-spline with normalised correlation and L-BFGS-B (CT to CBCT); the composite written as one displacement field
  on the fixed grid; quality after TG-132 (similarity inside the body before, after rigid, after; Jacobian and
  folding; landmark errors between structure centroids; largest displacement). `RegistrationStore` with a cache
  index; fixed metric seeds.
- Propagation: a derived geometry of the fixed one with the moving structures pulled back through the field
  (partial-volume level 0.5); a name clash needs a suffix. Dose mapping: a new dose on the fixed geometry with
  `mapped_from` (source dose, registration).
- `registration` is a lineage kind: a registration derives from both geometries, a propagated geometry from the
  fixed geometry and the registration, a mapped dose from its source dose and the registration.
- Routes: `POST /registrations`, `GET /registrations/{id}`, `GET …/field`, `POST …/propagate`,
  `POST …/map-dose`, `DELETE`. ADR 0016.
- `services/contour_metrics.py`: Dice, HD95 and mean surface distance.
- B-spline metric: normalised correlation. Mattes MI was OOM-killed on a thorax (its derivative buffers,
  bins^2 x parameters per work unit, passed 10 GB for ~11k parameters and follow ITK's global thread count, not
  the method's); joint-histogram MI used 0.4 GB but did not move the B-spline. Correlation: 0.04 mm on the test
  phantom with a linear "cone-beam" recalibration, 3 s, 0.3 GB.
- Harness `registration_4d_lung` (`cases_r9.py`): 4D-Lung, phase 50 % registered to 0 % for five patients with
  4–11 mm tumour motion; propagated contours against the 0 % contours, markers and carina as landmarks; rigid
  only, Demons, B-spline; graded on Demons against TG-132 tolerances (markers as point landmarks; the carina,
  a contoured region whose centroid moves 2–3 mm with the extent drawn, informative). Patient 111's tumour
  contours differ by 11 % in volume between the phases (83 and 75 cc): Demons and B-spline give a lower tumour
  Dice than no registration (0.77 and 0.73 against 0.79) while its lymph node goes from 0.03 to 0.40; kept as a
  graded finding, not tuned away. Data findings: patient 118's 0 % and 50 %
  images are identical (contours differ by 6 mm), skipped by an NCC guard; 109 and 112 have the same tumour
  contour on both phases; markers only on 100–106; organs on both phases only on 100–103.
- Tests: `tests/test_r9_registration.py` (a synthetic thorax: rigid recovery, Demons without folding, B-spline,
  volume mapping, the API with propagation, dose mapping and lineage).
- 4D (`services/four_d.py`, routes `/four-d/…`): the average-intensity CT (mean HU of phases on one grid and frame of
  reference, a derived geometry of the reference phase), the ITV (union of the drawn tumours, or propagated ones
  through registrations), a plan's metersets recomputed on each phase (photon apertures through the engine's
  aperture path), accumulation through registrations with equal or given shares (`DoseResult.accumulated_from`).
  Lineage: a geometry's parents now come from the operations it added itself (a derived geometry inherits its
  parent's list), so the phases of an average CT or ITV are parents of that geometry only.
- Harness `lung_4d_itv` (`cases_r9.run_lung_4d`): plan on the average CT with PTV = ITV + 5 mm, every phase's tumour
  D95 and the accumulated reference tumour D95 graded at 95 % of the prescription.
- Tests: `tests/test_r9_four_d.py` (three synthetic breathing phases: average CT, ITV drawn and propagated, phase
  doses of an open-field plan, accumulation through Demons equal to the mean of the phase doses at the tumour, the
  routes and the lineage).
- Replanning (`services/replan.py`, `POST /replan/assess`): the day's image fixed, the planning CT moving; planning
  structures propagated; for a cone-beam CT the planning CT's HU deformed onto it as the density (a derived geometry,
  op `density_from_registration`); the isocenter moved by the rigid part (the couch shift), the rotation reported; the
  plan recomputed on the day; goals planned and of the day side by side; the planned dose mapped. The day's beam
  model keeps the planned one in its cache key (`replan:{beam model}:…`), which the lineage reads.
- Accumulation with absolute weights (`AccumulateRequest.absolute`) for a course: a plan's whole-course dose times
  the fraction of it delivered.
- RT export: `predecessor_plan_uid` (ReferencedRTPlanSequence, RTPlanRelationship PREDECESSOR) and a MULTI_PLAN RT
  Dose referencing every plan it sums (`dose_summation`, `summed_plan_uids`).
- Harness `replan_pancreas_cbct` (`cases_r9.run_replan_cbct`): planning CT to each contoured cone-beam CT, propagated
  stomach-duodenum and bowel against the cone-beam contours, the clinical dose mapped onto the day.
- Tests: `tests/test_r9_replan.py` (a shifted, recalibrated "cone-beam" day: the couch shift recovered within 1 mm,
  the planning HU as density, the tumour dose of the day within 3 % of planned, cache and lineage; a course with
  absolute weights; the writers' predecessor and MULTI_PLAN references).
- DICOM registrations (`dicom/writers/reg.py`, `POST /registrations/{id}/dicom`): a Spatial Registration with the
  rigid part (source points into the registered frame, the inverse of radiarch's matrix) and a Deformable Spatial
  Registration with the whole field, in the fixed geometry's frame. The standard (PS3.3 C.20.3) applies the deformable
  grid to registered-frame points and yields source points, as ITK does; the R2 reader's docstring said the opposite
  and is corrected (nothing used it).
- Imports across frames of reference: `import_rtplan(to_geometry=…)` and the import route's `registration_id` or
  `registration_path` move the plan's isocenters into the geometry's frame (angles kept, rotation over 1 degree
  logged).
- Test: `test_dicom_registration_objects_round_trip_and_bring_a_plan_across_frames` (read back with the R2 reader;
  the deformable vector at the fixed tumour lands on the moving tumour; a plan from the moving frame imports onto
  the fixed tumour through either registration; without one it is refused).
- 4D robust evaluation: `AccumulateRequest.phases_as_scenarios` keeps each mapped phase dose as a scenario of the
  accumulated dose, so `include_scenarios` evaluation grades each goal's worst phase
  (`test_phases_as_scenarios_give_the_worst_phase`). Robust optimization over phases is left for a later item.
- Cone-beam finding (registration 1.1.0): on the first pancreas pair the B-spline diverged (stomach-duodenum Dice
  0.38 rigid → 0.17, the field folding in 44 % of body voxels, 22 minutes): the aligned cone-beam CT is 83 % padding
  at -1000 outside its field of view, where the planning CT has tissue. Fixed: the metric masked to the fixed body
  plus 10 mm (rigid and B-spline), and the B-spline coefficients bounded to 0.4 of the control-point spacing (a
  sufficient condition for a one-to-one cubic B-spline, Choi and Lee 2000). Rigid 0.525, B-spline 0.635, no
  folding. A body-only mask, or one that drops voxels at the image minimum, let the rigid step slide 2 cm (the
  collection clips air at -1000 too). `bspline_sampling` (default 10 %: 94 s; 20 %: 210 s, Dice 0.635; 5 %: 68 s,
  0.619). Demons is not for cone-beam CT (Dice 0.06 on that pair): same-calibration only. Cache keys of
  registrations carry the algorithm version, so a change of algorithm needs its bump (a trial reused a cached
  result before it).
- R9 record `docs/validation/2026-10-25-r9/` from commit `316b6c6`, one case per process (the first attempt in one
  process was stopped by memory pressure; `lung_4d_itv` needs about 18 GB at 3 mm): `registration_4d_lung` 29 pass,
  2 fail (patient 111's tumour contours, 11 % apart in volume); `lung_4d_itv` 22 pass; `replan_pancreas_cbct` 15 pass,
  5 fail (the B-spline above rigid alignment of the stomach-duodenum in five of ten cone-beam CTs; never folds).
  The replanning case's days had repeated series descriptions; the label now carries the date (`316b6c6`).

## CI red since 2026-10-21 (fixed 2026-10-26)

- Full tests: one test failed on every push, `test_iod_validation_with_dciodvfy` (dicom3tools is on the CI runner,
  not on the workstation, where it skipped). Reproduced with Ubuntu 24.04's dciodvfy in a container. Fixed: the RT
  Structure Set carries a complete Frame of Reference module (U in the IOD, PS3.3 A.19.3; its UID is Type 1 once the
  module is there); a DRR no longer writes ReportedValuesOrigin (PS3.3 C.8.8.2: SIMULATOR and PORTAL images only).
  Two messages are the validator's tables against the current standard and are listed in the test with their
  sections: Treatment Verification Status VERIFIED (C.8.8.21 lists it; the tables accept only VERIFIED_OVR) and
  Modulated Scan Mode Type with Scan Mode MODULATED (C.8.8.25 requires it only for MODULATED_SPEC).
- Nightly validation harness: red by design, as any graded failure failed it, the recorded CCC findings included.
  `known_findings.yaml` names the failures the records explain; `run --known-findings` (CI) fails only on errors and
  on graded failures not listed (`tests/test_validation_known_findings.py`). In fast mode the two pencil-beam lung
  consistency checks are informative: the lateral scaling was fitted at full resolution.
- Nightly MCsquare: red on every night on record (from 2026-08-28), either the runner shut down after about 22 minutes
  inside `test_mcsquare_dij_matches_direct_dose` or a high-dose disagreement of 36 %. One cause: MCsquare's
  Num_Primaries is per beamlet in beamlet mode and per plan otherwise, and the test gave both runs 1e5, so the Dij
  carried 1e5 primaries per spot on the 200³ CT grid (out of memory; over 8 GB already at 2e3) and the direct dose
  about 120 per spot. Fixed in the test (the services were right: the proton workflow already uses separate beamlet
  and final primaries): 2e3 per spot in both, a 4 mm dose grid; 18 pass in 28 s, 1 GB, high-dose p95 3 %.

## R10 — scripting SDK, auto-planning, planning protocols, command line (2026-10-25 to 2026-10-26)

- SDK `radiarch.sdk`: `Radiarch` over HTTP or in process (`Radiarch.local()`, the app through Starlette's test client);
  `submit` follows a 202 answer through the service's jobs route to the result; domain objects (`Geometry`,
  `BeamModel`, `Optimization`, `Sequence`, `Arcs`, `Dose`, `Evaluation`, `Export`, `Registration`, `ProtocolRun`)
  wrap the services' own result models and chain the planning steps; `ops` shorthands for structure operations and
  objectives; `RadiarchError` carries the service's detail. The R0 `client.py` stays for the plan and workflow routes.
- Auto-planning `services/autoplan.py`: the harness's goal-driven loops (`plan_static`, R7; `plan_vmat`, R8) and their
  helpers moved there unchanged (each function diffed against its original; the harness calls them under its old
  names, so the recorded plans are the service's). `plan_static` gained extra objectives and engine parameters,
  defaulting to what the harness used. `AutoplanService` runs a protocol: aliases copied to the protocol's names,
  its derivations, the loop, apertures or arcs, the plan normalised in its metersets (a `scaled:` beam model and its
  dose; the harness had scaled only the dose array), goals, the template evaluation. A job like optimization's
  (`autoplan_jobs` table, `radiarch.autoplan.run` on the optimize queue, the beam-angle time budget).
- Protocols `models/protocol.py`, routes `/protocols` (list, show, run, jobs, runs); shipped
  `lung-60gy-30fx-vmat`, `lung-sbrt-54gy-3fx-vmat`, `hn-70-56gy-35fx-vmat`, the three R8 harness plans as data.
- Command line `radiarch` (`protocols`, `protocol`, `plan`, `batch`), in process or against a server; `batch` writes
  a summary table, the runs as JSON lines and optionally each case's RT objects, recording a failed case and going on.
  CWL tools `cwl/radiarch-plan.cwl`, `cwl/radiarch-batch.cwl` (`cwltool --validate` passes).
- Tests: `test_r10_sdk.py`, `test_r10_protocols.py` (which found the per-fraction meterset fault, fixed in
  `3a98b85`), `test_r10_cli.py`.
- R10.5 harness (`cases_r10.py`): `protocol_lung_vmat` (the shipped lung protocol against the harness case it encodes:
  16 shared settings compared, all equal; then its run on the case's patients against the recorded harness run, within
  1 %) and `protocol_batch_lctsc` (the SBRT protocol through `radiarch batch` over every LCTSC thorax on disk, each with
  a synthetic peripheral GTV). Smoke run (fast): 21 and 27 pass, none fail. ADR 0017.
- R10 record `docs/validation/2026-10-26-r10/` from commit `92ce40d`, one case per process: `protocol_lung_vmat` 44 pass
  (the 16 settings equal; every RTOG 0617 goal value equal to the recorded harness run on both patients),
  `protocol_batch_lctsc` 79 pass (six thoraces planned and deliverable, PTV D95 54.1 Gy, the SBRT template's priority-1
  goals met).

## R13 — viewer integration (2026-10-27 to 2026-10-29)

- R13.1: OHIF 3.13.13's SOP class handlers (read at tag `v3.13.13`) cover the RT Structure Set, not RT Dose or RT
  Plan; `docs/viewing.md` says what OHIF and 3D Slicer show and how to set up the push and the viewer. Setting
  `RADIARCH_VIEWER_URL`; `viewer_url` on `RTExportResult` and `RTPushResult` after a successful push
  (`services/rt_export.viewer_link`). `tests/test_r13_viewer.py`: the structure set's references as OHIF's RT
  loader walks them (it iterates Contour Image Sequence unguarded), contour planes on CT slices, the viewer link,
  and a STOW-RS push of a CT and an export with QIDO/WADO read-back (`RADIARCH_TEST_DICOMWEB_URL`). CI: an
  Orthanc service container (DICOMweb plugin) in Full Tests. Local run against a throwaway Orthanc: 3 pass.
- R13.2a (ADR 0018, the viewer as one OHIF extension, standalone or embedded): `RTExportService.find` and
  `GET /rt/exports` (by study, series or SOP instance UID, every filter must match, newest first; SDK
  `find_exports`), so a viewer finds the export of what it shows. The plan dose carries the RT DVH module
  (`dicom/writers/rtdose.dvh_items`): per exported ROI a cumulative DVH in cm³ from the dose as stored, uniform
  bins (`dvh_bin_width`: 1, 2 or 5 × 10^k Gy, at least 0.01 Gy, at most 1000 bins, as DVH Data is DS and capped at
  64 KiB in explicit VR), minimum, maximum and mean; `RTExportRequest.dvh` (default true). dciodvfy passes on the
  writers' test dose with DVHs. Tests: `tests/test_r13_viewer.py` (the DVH against `dvh_on_bins` on the
  geometry's masks, bin widths, the lookup through service, API and SDK).
- R13.2b: `viewer/rt-dose-core` (plain JavaScript, no dependencies):
  - `readDose`: grid from IPP, IOP, Pixel Spacing and Grid Frame Offset Vector (relative or absolute, uneven frames);
    16- or 32-bit, signed or not, × Dose Grid Scaling;
  - `resampleToGrid`: trilinear onto any oriented grid, zero outside;
  - `readDVHs` and `roiInfo`: the file's DVHs, cumulative or differential, named and coloured by the structure set;
  - `referenceDose`: the plan's target prescription, else the maximum;
  - `isodoseLevels`, `doseColormap`: Cornerstone takes opacity points as data values but rescales RGB points onto
    the window, so the map returns its range.
  `tests/test_r13_viewer_core.py` writes fixtures and runs `core.test.js` with Node: radiarch's export plus synthetic
  doses (rotated orientation with absolute uneven offsets and 16-bit pixels; prone orientation with 32-bit signed
  pixels), checked against Python's stored doses, indices, scipy trilinear interpolation onto an axial and a
  rotated grid, and DVH curves. A mutation (row and column spacing swapped) fails two tests.
  `viewer/ohif-extension-rt-dose` (OHIF 3.13.13):
  - RT Dose display sets with Modality `PMAP`, since OHIF's cache service draws a derived overlay volume only for
    that pseudo-modality;
  - the dose resampled onto the CT of its frame of reference, in % of the prescription;
  - the isodose colormap registered at preRegistration; the dose viewport, modelled on OHIF's parametric map
    viewport; a DVH panel.
  `viewer/scripts/build-ohif.sh` puts the packages in a clean OHIF 3.13.13 workspace and builds; the CI job
  "Viewer" runs it on every push. Built locally: OHIF 3.13.13 with the extension compiles (rspack, its own three
  size and chunk warnings only), the app imports `@radiarch/ohif-extension-rt-dose`, peak 2.6 GB. The script runs the
  pnpm OHIF pins through npx (corepack before 0.35 cannot unpack pnpm 12) and OHIF's plain `build`, since `build:ci`
  also bumps OHIF's release version.
- R13.2c:
  - `viewer/radiarch-client` (plain JavaScript): `createClient({apiUrl, headers})` with `findExports`,
    `goalTemplates`, `evaluateExport` (follows a 202 through `/evaluate/jobs/{id}`; refuses an export without a dose
    or a prescription before any request) and `lineage`; `planSummary`, `goalRows`, `evaluationCurves`.
    `tests/test_r13_viewer_client.py` serves radiarch with uvicorn in a thread (API key required, route service
    caches cleared), writes an export, and runs the Node tests against it:
    - a 401 without the host's headers;
    - the export found by the plan instance and by the dose series;
    - the summary's metersets;
    - an evaluation through the job, then from the cache, which is the evaluation radiarch's service holds.
  - `viewer/ohif-extension-radiarch`: the panel finds the export of the dose in the active viewport and shows the
    plan; it evaluates against a chosen template (remembered in the browser) and shows the goals and radiarch's
    DVHs with the structure set's colours. The API URL comes from the extension's configuration or the app
    config's `radiarch` block (default `/radiarch/api/v1`); headers come from OHIF's user authentication service.
  - `viewer/ohif-mode-plan-review`: OHIF's basic mode with the RT Dose handler first, the dose viewport, the DVH,
    plan and segmentation panels, valid for CT + RT Dose, and the hanging protocol `radiarch-rt-dose` (registered
    by the dose extension).
  - `build-ohif.sh` puts the five packages in the workspace and registers both extensions and the mode; local
    build passes. CI checks all three in the bundle.

## Release and commit in every output (2026-10-27)

- Asked after a withdrawal of defective outputs had to fall back on run dates, because every object said 0.1.0.
- `radiarch/build.py`: `release()` (the package version), `commit()` (`RADIARCH_BUILD_COMMIT`, else the git
  checkout, `-dirty` with uncommitted changes to tracked files), `software_versions()`, `describe()`.
- Software Versions is now `[release, "git <commit>"]` in every written object, and the private attribution line
  reads `radiarch <release> (git <commit>)`.
- Exports' attribution gains `capability_commit`; `/info` gives `version` and `commit`; the app and the
  validation report take the release from the same place.
- Dockerfile and docker-compose pass `RADIARCH_BUILD_COMMIT` as a build argument.
- Release 0.2.0: the first stamped one, after the output-changing fixes and features since 0.1.0. From now on a fix
  that changes output raises the patch number and a feature the minor number (`docs/PRODUCTION.md`).
- Tests: `tests/test_build_version.py`.
- R13.2d:
  - `viewer/standalone`: a Dockerfile (node 24 runs `build-ohif.sh`; nginx 1.27.5-alpine serves the dist) and
    `default.conf.template` (`/dicom-web` to Orthanc with the Host kept, so Orthanc's bulk data URIs point back at
    the proxy; `/radiarch/api` to radiarch with `X-API-Key` added; empty variables leave a header out). `app-config.js`
    points at the same origin and sets `radiarch.apiUrl`. Compose profile `viewer` on 127.0.0.1:3000.
  - Fixes found with the browser:
    - the mode names its hanging protocol; offered with `default`, it lost on score;
    - the protocol matches RTDOSE studies;
    - the dose volume is invalidated and marked modified after its data is set;
    - the panels no longer overflow the sidebar: a long goal template name had widened the radiarch panel;
    - the DVH chart scales to its panel, with tick labels at the chart's precision.
  - `tests/test_r13_viewer_browser.py`:
    - a patterned CT (`_ct_slices(hu=...)`) and an export pushed to Orthanc;
    - radiarch with an API key; the image on the host network;
    - headless Chromium with SwiftShader through the plan review mode;
    - checks: the hanging protocol, the DVH panel, the CT drawn, the dose volume inside OHIF (values = the file's
      dose in % of the prescription, the isodose map, opacity, window, one colour per band), the radiarch panel's
      plan and an RTOG 0617 evaluation.
  - Found while debugging: headless Chromium draws the CT but no second volume with SwiftShader; with the GPU (ANGLE
    on EGL or Vulkan) it reads nothing back. So the overlay on screen goes to the hand check (R13.3).
  - CI's Viewer job: builds the image, checks the bundle in it, installs radiarch with `viewer-test` (Playwright
    1.64.1, Pillow) and Chromium, runs the test against an Orthanc service, and uploads screenshots.
- R13.2b′ and panel fixes (2026-10-27):
  - `rt-dose-core/src/rasterize.js`: each closed planar contour goes to the dose frame within half a frame of its plane;
    a scanline fills voxel centres with the even-odd rule, so holes work. `computeDVHs` gives cumulative DVHs in cm³ and
    % with radiarch's bin rule (`dvhBinWidth`), marked `source: 'computed in the browser'`.
  - The dose extension uses them when a dose has no DVH module. It finds the structure set through the dose, its plan,
    or the study's structure set of the same frame of reference, and fetches the whole object when OHIF's metadata holds
    the contour points as bulk data.
  - Tests:
    - in `core.test.js`, on radiarch's fixtures the computed DVHs equal the written ones bin for bin; a contour inside
      another is a hole;
    - in `test_r13_viewer_browser.py`, a second case exports without DVHs and checks the panel computes and labels them.
  - The goals table shows the priority, the structure with its goal beneath it, and the achieved value with its status,
    so it fits the sidebar.
  - `docs/reports/ohif-overlay-volume-proposal.md`: a draft proposal to OHIF, not filed.
- R13.3 hand check, first finding (2026-10-27): the project lead saw no colour wash in a browser with a GPU, so it was not a
  headless limit. The cause: Cornerstone's ray caster scales opacity by sample distance / opacity unit distance
  (default 1 mm). Through a 0.05 mm MPR slab the bands' 0.45 came to about 0.03, nearly black, and only faintly visible
  in air.
  - Found by hiding the CT in the browser: the dose was drawn in the right shape, but almost black.
  - The fix: the dose viewport sets the actor's opacity unit distance to 0.15 mm when OHIF mounts the volumes
    (`VIEWPORT_VOLUMES_CHANGED`) and marks the opacity function modified. Cornerstone caches the opacity texture by
    that function's time stamp, which is why changing the property alone did nothing. 0.15 mm was chosen against 0.05
    and 0.3 on the lung plan.
  - The browser test now checks the unit distance and that the dose changes 90 % of the viewport's pixels (threshold
    25 %), comparing screenshots with the dose shown and hidden. Headless SwiftShader does draw the second volume:
    the earlier "no second volume" was this same opacity.
- R13.3 hand check, second finding (2026-10-27): still no colour wash in the project lead's browser, while full
  Chromium on this workstation's NVIDIA GPU (ANGLE on Vulkan) showed it.
  - The cause was the view: the hanging protocol opened the middle slice, at the edge of this tumour. There the dose is
    30–64 %, drawn as dark blue and teal, invisible over black lung.
  - The dose viewport now opens on the slice through the dose maximum (`hotspotWorld`, set when the dose loads; the
    camera moves along the view-plane normal once).
  - The 30 % and 50 % bands are lighter: (0.35, 0.5, 1) and (0, 0.8, 1).
  - The browser test checks the opening slice is within half a slice of the maximum.

## Launch from a fresh clone (2026-10-27)

A fresh clone was taken through the README's Docker Compose quick start, the smoke test and a new viewer walkthrough.
That found the following, now fixed.
- **The Orthanc adapter's DICOMweb root.** The adapter gave the DICOMweb client Orthanc's base URL, where Orthanc
  answers its own REST API, so no study was ever found in a real Orthanc (the tests used the mock). It now uses
  `orthanc_dicomweb_root` (`/dicom-web`). `tests/test_orthanc_fetch.py`: the root, and a geometry built from Orthanc
  in CI; it fails without the fix.
- **HTTP basic pushes.** These passed `username` and `password` to dicomweb-client, which takes neither, so every
  basic-auth push failed. They now go through a requests session. `tests/test_dicomweb_push_auth.py` covers basic auth.
- **The compose file.**
  - The API and the worker had no DICOMweb login for its Orthanc; they now get `RADIARCH_DICOMWEB_USERNAME` and
    `RADIARCH_DICOMWEB_PASSWORD`.
  - They now get `RADIARCH_VIEWER_URL` and `RADIARCH_VIEWER_ROUTE=plan-review`.
- **The viewer link.** It always used OHIF's generic `/viewer` route, which does not load the dose extension. The
  route is now `RADIARCH_VIEWER_ROUTE`: `viewer` by default, `plan-review` for radiarch's viewer.
- **The dose display set's CT.** It was matched by Frame of Reference UID only. The bundled phantom's CT has none,
  which other CTs can share. It now falls back to the image series the dose's structure set refers to, then to the
  study's only CT. A browser test covers a CT without a frame of reference.
- **The smoke test** planned a study absent from the compose stack's Orthanc. `scripts/load-phantom.sh` now puts the
  phantom in as one study and completes it on the way in. The OpenTPS phantom's CT has no Frame of Reference UID, and
  its structure set has its own study, Modality RTDOSE and no CT reference.
- **`.dockerignore`** let virtual environments (`src/.venv` in the README's own local-dev step) into the API image.
- **New:**
  - `radiarch plan --push`, which pushes the RT objects and prints the viewer link;
  - the shipped `demo-phantom-imrt` protocol;
  - `scripts/demo-viewer.sh`;
  - the README's quick starts, which state prerequisites, the viewer profile, the build commit and Docker Hub's pull
    limit;
  - `docs/demo.md` section 5.
- **Verified on the fresh clone:** build, start, the smoke test (proton plan by MCsquare), and the demo (5-field IMRT
  by the pencil-beam engine, every goal met, 8 RT objects pushed). The printed link, opened in Chromium on an NVIDIA
  GPU, shows the dose wash on the maximum's slice, the DVHs and the radiarch plan panel, with no console errors.


## A lung-cancer patient in the viewer (2026-10-27)

The phantom demo showed a dose over a water cylinder, and no contours: the dose viewport drew only the CT and the
dose, and OHIF loads a structure set only when it is dropped into a viewport of its own.
- **Contours in the dose viewport.** The dose display set records the structure set it was matched with
  (`structureSetSOPInstanceUID`); once Cornerstone has mounted the volumes, the viewport loads that structure set
  with OHIF's RT handler and adds it as a contour representation, so OHIF's segmentation panel lists the structures.
  Added earlier, before the volumes are mounted, Cornerstone's contour display threw "No actor found" on every render.
- **Planning aids hidden.** `planningAids` (rt-dose-core): ROIs interpreted as avoidance, control and the like, rings
  and optimisation helpers, and organ-minus-target structures such as `Lungs-PTV`. They start hidden in the viewport,
  and the DVH panel shows them on request.
- **One name per structure.** A protocol copies a patient's structure to its own name (`structure_aliases`:
  `Spinal-Cord` → `SpinalCord`). The run now records the copies (`aliased`), and its export leaves out the originals,
  so the structure set, the DVHs and the goals use the same names and no structure is drawn twice.
- **`radiarch fetch-tcia`** (`adapters/tcia.py`): a public patient's planning CT and structure set from TCIA's NBIA
  API into a cache, optionally pushed to the DICOMweb server; the collection's licence line is printed.
- **`demo-lung-imrt`**: the lung protocol's structures and RTOG 0617 goals with seven static fields, which plan in
  minutes on a CPU (the two VMAT arcs of `lung-60gy-30fx-vmat` take about twenty). The lung protocols take
  NSCLC-Radiomics' names (`GTV-1`, `Spinal-Cord`, `Lung-Left`, `Lung-Right`).
- **`scripts/demo-lung.sh`**: NSCLC-Radiomics `LUNG1-002` into the stack's Orthanc, planned and pushed, the link
  printed. README, `docs/demo.md` (5.1, with the data's licence and citation) and `docs/viewing.md` lead with it; the
  phantom demo remains for machines without internet access.
- **Compose:** the API and worker set `RADIARCH_ARTIFACT_DIR=/data/artifacts`, the shared volume. A relative value
  in `.env` had given each container its own directory, and the API answered 404 for the worker's geometry.
- **Tests:** `tests/test_tcia_demo.py` (fetch, cache, push, the command, the protocols' names, the compose file);
  `test_r10_protocols` checks the export names each structure once; rt-dose-core tests `planningAids`; the browser
  test checks the structure set is drawn as contours in the dose viewport.
- **Verified** on the compose stack: `demo-lung.sh` in under six minutes (download, a 7-field plan with every goal
  met: PTV D95 60.1 Gy, cord max 35.7 Gy, oesophagus mean 9.6 Gy, heart D33 20.2 Gy, lungs-PTV D37 6.3 Gy). In
  Chromium on an NVIDIA GPU, the link shows the GTV, CTV, PTV and organ contours over the dose wash, and the DVHs.

## Black image in Chrome on Linux; planning progress; log messages (2026-10-28)

- **Chrome's default backend on Linux draws 3D volumes black.** In Chrome on a Linux workstation with an NVIDIA GPU, the
  dose viewport showed contours and DVHs over a black image. Firefox showed everything. With ANGLE on OpenGL (Chrome's
  Linux default), every volume viewport is black without an error, OHIF's own MPR of the CT included. With ANGLE on
  Vulkan, the same page draws the CT and the dose. The hand checks that saw no colour wash were probably this.
  - The dose viewport samples its canvas every 3 s once the volumes are mounted (`isBlankImage`, rt-dose-core); black
    three times running, it shows a warning naming the fix (Firefox, or `chrome://flags/#use-angle` set to Vulkan).
  - README and `docs/viewing.md` (Browsers) say the same; the browser test checks that no warning shows when the image
    is drawn.
- **Planning progress.** `radiarch plan` was silent for the minutes a plan takes, which looked like a hang. The SDK
  client takes `on_progress`, called when a job's state, stage, progress or message changes; the command prints it.
  The protocol job reports each goal-driven round (`imrt planning, round 1 of up to 2`).
- **Log messages.** 75 log calls used `%s` placeholders, which loguru prints as they stand (`Using real Orthanc adapter
  at %s`); they use `{}` now, and `tests/test_log_messages.py` keeps it so.

## A plan exported again is the same export (2026-10-28)

- **Duplicates in the study.** Each run of `demo-lung.sh` reused the stored plan but exported it again with new UIDs, so
  the study gained another structure set, plan, dose and DRR series per run, identical but for their UIDs.
- **Reuse.** An export is keyed by its plan and every setting that shapes its objects (`compute_cache_key`; not
  `push`). Asked again, the service returns the stored export (`reused: true`) and, with `push`, sends the same
  objects again; Orthanc keeps an instance it already holds. An export whose files are gone is written anew.
- **A marked copy.** `new_export` (`radiarch plan --new-export`) writes a copy: new UIDs, `copy N` in the RT Plan and
  structure set labels (within 16 characters) and in every series description, and the latest earlier plan referenced
  with RTPlanRelationship PREDECESSOR. The manifest records `copy_number` and `copy_of`. Later default runs return the
  latest copy.
- **No replace.** DICOMweb has no delete, and a deletion in an archive cannot be undone. Eclipse and RayStation keep a
  plan's identity in their database and retire a superseded plan rather than delete it; radiarch links copies the same
  way and leaves deleting to the archive.
- **Tests:** `tests/test_rt_export_reuse.py` (the same export, a setting that changes the key, copies and their
  references, missing files, the label); `test_r10_cli` checks a rerun pushes the same UIDs and `--new-export` a copy.
- **Documentation and the demo scripts.** README section "Exporting a plan again" (behaviour, API, command, SDK, the
  clean-up of older duplicates); `docs/demo.md` 5.1 and `docs/viewing.md` say what a rerun does. `demo-lung.sh` and
  `demo-viewer.sh` take `NEW_EXPORT=1` for a marked copy; `test_tcia_demo` runs `demo-lung.sh` with a stand-in
  `docker` and checks the option reaches `radiarch plan`.

## R13.3 record; R13 closed (2026-10-29)

- **Record** `docs/validation/2026-10-28-r13/`: the two cases (the LCTSC VMAT plan, the `LUNG1-002` IMRT demo with its
  goal numbers), the project lead's OHIF hand check (CT, dose colour wash, contours, DVHs, the plan panel; Firefox on
  Linux), and the eight findings of the hand checks with the commits that fixed them.
- **Open:** the objects read by 3D Slicer with SlicerRT, left to the project lead; the record gives the steps and an
  empty results table. R6's hand check is done in OHIF and waits on the same Slicer check.

## R11 — multi-criteria optimization (from 2026-10-29)

Design and research: `docs/reports/mco-research-and-design.md` (`268b0f0`).

### R11.1 Convex trade-off objectives and hard constraints

- **Trade-off objectives** (`services/objectives.py`, D1): `MeanDose`, `EUDMax` (gEUD, `a >= 1`), `EUDMin` (`a <= 1`),
  `RMSOver`, `RMSUnder`, `UniformRMS`. Each is the amount in Gy by which the structure misses its `dose_gy` level,
  zero when met, and convex in the dose, so a blend of plans is bounded by its parents. The gEUD scales the dose by
  its maximum before the power, so exponents up to 100 stay finite. `ObjectiveSpec.eud_a` carries the exponent (the
  older `EUD` takes it too, 10 when unset as before); `is_tradeoff` and `check_tradeoffs` refuse the DVH surrogates,
  the two-sided `EUD` and the squared penalties as trade-offs.
- **Hard constraints** (`services/hard_constraints.py`, D2): `HardConstraint` (`Dmax <=`, `Dmin >=`, `Dmean <=`,
  `gEUD` with the convex direction only), enforced by the method of multipliers around the request's solver: one
  residual per voxel for `Dmax` and `Dmin`, one for `Dmean` and `gEUD`; `rho` starts at 10 and grows tenfold when the
  worst violation has not fallen to a quarter; up to 12 rounds. A feasibility run (the constraint terms alone) comes
  first; when it cannot meet them, `InfeasibleConstraintsError` names the constraints (the job fails with that message). An objective
  the feasibility plan already meets is noted ("trades nothing"), the cause of the deliverable gap reported for a
  commercial MCO. Nominal scenario only: the request refuses hard constraints with robustness until R11.6.
- **Results:** `ConvergenceInfo.objective_values` (every objective's unweighted value, in Gy for trade-offs),
  `hard_constraints` (achieved, violation, met), `constraint_rounds`, `notes`. An objective without `eud_a` and a
  request without hard constraints keep their earlier hashes and cache keys (a test pins both).
- **Tests** (`tests/test_r11_tradeoffs.py`): values in Gy; gradients against finite differences; convexity on random
  doses (and the DVH surrogate's counterexample); spec ranges; the augmented Lagrangian against SciPy's SLSQP with the
  constraints written out (organ maximum; organ mean and gEUD; target minimum); an impossible set; the service on the
  analytic engine (an organ limit held and reported, a redundant objective noted, an infeasible set refused).

### R11.2 The Pareto set

- **Algorithm** (`services/pareto.py`, D3), independent of doses: it asks a `solve(weights, warm)` for weighted-sum
  plans. N anchor plans (weight 1 on one trade-off, 10⁻³ on the others) fix the ideal and nadir; a balance plan has
  equal normalized weights; then sandwich plans. The inner set is the plans' hull plus everything worse
  (`conv(P) + R^n_+`, which is what Rennen's dummy points stand for); the outer set is the intersection of the
  halfspaces the plans' weights support. Its vertices come from Qhull (`HalfspaceIntersection`, a Chebyshev centre
  from HiGHS as the interior point; a box only bounds the set), and each vertex's distance to the inner set is one
  HiGHS linear program. The largest distance is the error bound (Bokrantz & Forsgren 2013); that program's duals at
  the worst vertex are the next plan's weights, floored at 10⁻³ so the plan is Pareto optimal, and the plan
  warm-starts from the plan the program blended most. It stops at the tolerance (default 0.05 of the normalized
  range), at the budget (3N + 1 by default, at most 4N + 1), or when the next weights repeat a plan's.
- **Service** (`services/mco.py`, D4): `MCOService.run` assembles the problem once through `OptimizationService`
  (the cached dose matrix, the trade-offs at weight 1), runs the feasibility run when there are hard constraints, and
  solves each weighted sum with the request's solver, under the hard constraints by the augmented Lagrangian of
  R11.1. It stores every plan's weights, and every plan's dose on the navigation voxels (the structures the
  trade-offs, constraints and `navigation_structures` name) with a mask per structure: `mco/{id}/weights.npy`,
  `navigation_index.npy`, `navigation_dose.npy`, `navigation_masks.npz`, `meta.json`. A trade-off the anchors do not
  spread is noted ("trades nothing on these beams").
- **Convergence at a bound.** An organ's anchor is often zero fluence, where L-BFGS-B reports a failed line search;
  a plan counts as converged when the solver says so or its projected gradient vanishes. For that, the trade-offs
  now return the one-sided gradient at their level (`MeanDose` and `EUDMax` at 0 Gy with a 0 Gy level give the
  mean's gradient, a subgradient), not zero, so adding dose to an organ at its level still shows a cost.
- **Interfaces:** `MCORunRequest` and `MCOResult` (`models/mco.py`); `POST /api/v1/mco/run` (200 cached or 202 job),
  `GET /mco/jobs/{id}`, `GET /mco/{id}`; the Celery task `radiarch.mco.run` on the optimize queue; jobs in both
  stores (`mco_jobs` table); lineage kind `mco` (parents: geometry, beam model); SDK `BeamModel.mco(...)` returning
  `ParetoSet` (`.table()`), and `ops.mean_dose`, `eud_max`, `eud_min`, `rms_over`, `rms_under`, `uniform_rms`,
  `hard`.
- **Tests** (`tests/test_r11_pareto.py`): a two-objective front known in closed form (every plan on it, the bound
  covering the true error); three- and four-objective quadratic fronts (the bound never grows and covers the error
  sampled with random weights); supporting weights and no dominated plan; the anchors fixing ideal and nadir; the
  request's limits and cache key; the service on the analytic engine (anchors, balance, the stored doses reproducing
  each plan's values, hard constraints holding in every plan, an infeasible set, a trade-off that trades nothing);
  the SDK, route, job, cache and lineage on the stub patient.

### R11.3 Navigation

- **Navigator** (`services/navigation.py`, D5): a navigated plan is a blend of the Pareto plans; its dose on the
  navigation voxels is the same blend of theirs, and each trade-off's exact value is at most the blend of the plans'
  values (convexity). The search is Craft & Monz's piercing linear program over the blend weights in normalized
  objectives (HiGHS), with a small term (10⁻³ times their sum) that keeps the answer off weakly dominated blends.
  - A slider (`move`) holds one objective at no more than its value; the others share the cost or the gain evenly
    from where they were. A move beyond reach under the clamps goes as far as it can and says how far.
  - A `reference` point pulls every objective toward its value, the unlisted ones toward where they are.
  - `clamps` (Gy) hold whatever else moves; a lock clamps an objective at its current value; a clamp set no blend
    meets is refused.
  - The state reports the blend, the exact values on the blended dose next to the bound, the normalized values,
    the clamps, a DVH per navigation structure on one axis, and a goal set graded on the blended dose (physical or
    EQD2). Goals on structures outside the navigation voxels are reported missing, with the advice to add them to
    the run's `navigation_structures`.
- **States**: stored as `mco/{id}/states/{state_id}.json`; the balance plan's state (`balance`) is made on first use
  and is the reference every request starts from unless it names another state.
- **Shared grader**: `clinical_goals.grade_goal_set` grades a goal set on one dose given each structure's voxel doses;
  the navigator uses it (the evaluation service keeps its own, which also grades scenario doses).
- **A plan without dose.** On the synthetic problem the balance plan switched every beamlet off: with no hard
  constraint on target coverage, an organ's anchor has zero fluence, the target's nadir is "no dose", and equal
  normalized weights favour the organs. RayStation's advice, minimum coverage as a constraint, is the cure; an MCO
  run now notes any plan that delivers no dose and names it.
- **Interfaces:** `POST /api/v1/mco/{id}/navigate` (`NavigateRequest` → `NavigationState`), `GET /mco/{id}/states`,
  `GET /mco/{id}/states/{state_id}`; SDK `ParetoSet.navigate(move=, reference=, clamps=, locks=, from_state=,
  goals=)` and `ParetoSet.states()`. `MCOResult.voxel_cc` keeps the voxel volume for goals in cc.
- **Tests** (`tests/test_r11_navigation.py`): on a synthetic three-structure Pareto set, the balance blend reproduces
  the balance plan, blends are the blends of doses with exact values never above the bound, a slider reaches its
  value and is paid for elsewhere, locks and clamps hold, a move beyond reach is limited and said so, better slider
  values give better values, a reference point, the refusals, goals and DVHs from the blended dose; on the stub
  patient through the SDK, routes and stored states (onward from a state, unsaved states, 404 and 422).

### R11.4 Automatic navigation and projection

- **Automatic navigation** (`Navigator.auto_navigate`, D6): lexicographic over the blend weights against a goal set's
  priorities (a template, inline goals, or both; physical or EQD2). Each goal's shortfall is its miss over its value;
  level 1's summed shortfall is minimized, then level 2's with level 1 held, then level 3's, then the trade-offs' sum
  with every goal held. The blend weights are parametrized as `mu / sum(mu)` with `mu` in [0, 1], so the solvers need
  no equality constraint; each level runs SLSQP (finite differences) and then COBYLA while a shortfall remains,
  keeping the best feasible point. Clamps and locks hold throughout. Goals on structures outside the navigation voxels
  are left out and named. The state reports each level's goals, passes and shortfall before and after.
- **Met goals do not slip.** As designed, every held goal could slip by 1 % of its value. The hand-solved toy problem
  showed the final step trading a met priority-1 goal (P ≥ 8 Gy became 7.92 Gy) for the trade-offs' sum: a met goal
  is now held at zero shortfall, and only a goal a level could not meet may slip. The design report says so.
- **Projection** (`MCOService.project`, `project_blend`): the sum of the normalized trade-offs minimized with each
  capped at its navigated value (`ObjectiveCap`, a trade-off as a hard constraint with a 0.01 Gy tolerance) and the
  run's hard constraints, from the blended weights (which meet every cap). The result is at least as good in every
  trade-off; when the solve cannot hold the caps the navigated plan is kept and said so. A variant of Bokrantz &
  Miettinen's even projection. It is an optimization on the full dose matrix, so it runs inside R11.5's deliverable
  job rather than as a navigation request. An MCO run now stores its request (`mco/{id}/request.json`) for it.
- **Interfaces:** `POST /api/v1/mco/{id}/auto-navigate` (`AutoNavigateRequest` → `NavigationState` with `levels`);
  SDK `ParetoSet.auto_navigate(goals, clamps=, locks=, from_state=, ...)`.
- **Tests** (`tests/test_r11_auto.py`): a three-plan, three-voxel problem solved by hand (each level's result, the
  order deciding which organ pays, a lower level never undoing a higher one, a missed goal using its slip), clamps,
  missing structures, refusals (EQD2 without fractions, a percentage goal without a prescription); the projection on a
  synthetic dose-matrix problem (no trade-off worse, their sum better) and through the service (the hard constraint
  held); the route and SDK on the stub patient.
