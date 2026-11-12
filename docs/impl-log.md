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

### R11.5 The deliverable plan

- **Steps** (`services/mco_deliverable.py`, D7): a navigation state's blend is projected onto the Pareto set (R11.4)
  and stored as an optimization record (`cache_key` `mco:{mco_id}:{key}`, so lineage links it to its Pareto set); its
  dose is the reference. Static photon fields are sequenced into apertures (R4) and arcs given in the request are
  swept (R8), the segment or control-point metersets re-optimized against a `ReferenceDose` objective on every
  navigation structure; proton spots are the plan as projected (the proton machine model has no minimum spot
  meterset). Optional normalisation scales the photon plan's metersets to a coverage metric (R10's `_scaled`).
- **`ReferenceDose`** (`services/objectives.py`): the mean squared one-sided difference from a reference dose: an organ
  above it; a target above it in its hotter half (voxels above the reference's median there) and below it in its
  colder half. Targets are the structures a target-type trade-off or a lower-bound constraint names, or the request's
  `targets`; `target_priority` weighs them. The design report had the target's halves reversed; corrected there.
- **Deviation table:** every trade-off (exact, on the navigation voxels) and every goal of an optional goal set,
  navigated, projected and deliverable; flagged when the deliverable value is worse than the navigated one by more
  than `tolerance_gy` (doses) or `tolerance_volume` (volumes in % or cc).
- **Interfaces:** `POST /api/v1/mco/{id}/deliverable` (`DeliverableRequest`; 200 cached, 202 job),
  `GET /mco/deliverables/jobs/{job_id}`, `GET /mco/deliverables/{id}` (`MCODeliverable`); the Celery task
  `radiarch.mco.deliverable`; jobs in both stores (`mco_deliverable_jobs`); SDK `ParetoSet.deliverable(state, ...)`
  returning `MCOPlan` (`.dose()`, `.beam_model()`, `.deviation_table()`, `.export()`).
- **Tests** (`tests/test_r11_deliverable.py`, `tests/test_r11_deliverable_vmat.py`): `ReferenceDose` one-sided by role,
  its gradient and spec; protons on the stubbed service (the projected spots, no trade-off worse, the record's lineage
  key, the cache); static photon fields through the SDK on the stub patient (apertures, normalisation, the deviation
  table and its flags against the tolerance, lineage to the Pareto set, export, 404s); VMAT arcs from a pencil-beam
  Pareto set (each trade-off within 0.5 Gy of the navigated plan on the stub patient).

### R11.6 Robust MCO

- **Generation** (`services/robust_mco.py`, `services/mco.py`, D8): with `robustness` on, the set is solved on stacked
  scenario doses of the navigation voxels (each scenario's dose matrix restricted to them). Each plan minimizes the
  worst scenario of its weighted sum (Bokrantz & Fredriksson), smoothed by a log-sum-exp of 0.01 Gy per unit weight;
  hard constraints get one term per scenario, and an infeasible one is named with its scenario. Only the
  `WORST_CASE` aggregation applies, and it is the default; the cache key changes only when robustness is on.
- **Values and the bound:** a plan reports each trade-off's worst case over the scenarios (`values_gy`, convex, so the
  navigation bound holds) and its nominal value (`nominal_gy`). The sandwich takes each solve's own lower bound
  (`Solved.bound`: the smoothed optimum less 0.01 Gy · Σw · ln S) for the outer set, because a scenario-wise plan does
  not minimize the weighted sum of worst cases. The bound stays valid. It also includes the gap between the two
  measures, which more plans do not remove, and `robust_gap` reports it.
- **Navigation:** scenario doses are stored (`navigation_dose_scenarios.npy`, scenarios x plans x voxels, memory-mapped
  when read). A state reports worst-case values and `nominal_gy`. Goals are graded on the nominal dose with their worst
  case (`grade_goal_set` takes scenario doses; `robust_all_passed`). Automatic navigation uses each goal's worst-case
  shortfall.
- **Deliverable:** a robust proton set is projected with worst cases capped, and its deviation table compares worst
  cases. A robust photon set is refused (422): the sequenced plan would need its own scenario doses.
- **Single optimizations** still refuse hard constraints with robustness, and the message points to MCO.
- **Tests** (`tests/test_r11_robust.py`):
  - the pieces: adjoint stacked operators; the worst case and its gradient; the smoothed sum's gradient against finite
    differences, and its bound under the worst scenario; a constraint on one scenario;
  - on a two-scenario problem: every attainable vector of worst cases lies in the outer set and within the error bound
    of the plans' hull, and the scenario-wise plan has a lower worst-scenario sum than the nominal plan;
  - the request: the default aggregation, and nominal keys unchanged;
  - on the stub patient: worst-case and nominal values against the stored scenario doses, coverage in every scenario,
    an infeasible band named by scenario, navigation and goals on worst cases, automatic navigation's shortfall equal to
    the worst case's, the robust proton deliverable with no worst case worse, and the photon refusal.

### R11.7 Protocols, command line and viewer

- **Protocols** (`models/protocol.py`, `services/autoplan.py`): an optional `mco` section (`MCOSection`: trade-offs,
  hard constraints, budget, tolerance, `navigation_goals`, `navigation_structures`). A protocol with one:
  - computes the Pareto set on its beams (static fields, or the arcs' sectors with the pencil-beam engine);
  - navigates automatically by its goals (the planning goals as clinical goals, the main target's at priority 1);
  - makes the navigated state deliverable, normalised to the coverage goal, in place of the reweighting rounds.

  The run records `mco_id`, `state_id` and `deliverable_id`. A protocol without the section keeps its digest, so
  earlier runs stay cached. The beam arrangements moved into `static_beam_model` and `sector_beam_model`, unchanged.
- **Command line:** `radiarch plan` prints the Pareto set, the state to navigate from and the flagged deviations.
  The SDK adds `ProtocolRun.pareto_set()`.
- **API:**
  - `GET /mco/deliverables?dose_id=&beam_model_id=` finds the plans that made a dose.
  - A deliverable plan stores its `request`, so another state is made deliverable the same way.
- **Viewer:**
  - `@radiarch/client` adds `findDeliverables`, `paretoSetOf(export)`, `navigate`, `autoNavigate`, `makeDeliverable`
    (following the job) and `exportPlan`, and the helpers `tradeoffRows`, `stateCurves` and `deviationRows`.
  - `@radiarch/ohif-extension-radiarch` has a second panel, `radiarch-mco`, in the plan review mode. It shows a slider,
    a value field and a lock per trade-off (worst case and nominal on a robust set), automatic navigation by a goal
    template, the state's goals and DVHs, "Make deliverable" with the deviation table, and "Export and open" (the new
    plan beside the one on screen, referencing its structure set, sent to the image server).
  - A navigated blend is shown by its DVHs and goals. The dose on screen changes only when a plan is exported and
    opened: a blend has no dose file.
- **Tests:**
  - `tests/test_r11_protocol.py`: the section, its default goals and digest; an MCO protocol planning the stub patient;
    navigation from its state; export; the command's output.
  - `viewer/radiarch-client/test/mco.test.js`: offline helpers in CI's viewer job; live, through
    `tests/test_r11_viewer_client.py`, against a served API with a key.
  - `tests/test_r11_viewer_browser.py`: the panel in headless Chromium (CI's viewer job).
  - The test conftest now clears every cached route service between tests (`_navigation`, `_deliverables` too).

### R11.8 Record and ADR 0019 (2026-10-31)

- **The record** `docs/validation/2026-10-31-r11/`: README for the reviewing physicist, the MCO document
  (`report --engines mco`), `results.json` and `run-summary.md`. Three cases from `b4085b0`, one per process: TG-119
  (55 min) and the robust proton phantom (35 min) on the 20-core workstation; the lung patient (8 h) on a 96-core
  server, because its two-arc stage (24 beams, 19,008 beamlets) needs about 7 GB and two workstation attempts were
  stopped by a memory guard with the results unwritten (the runner writes them at the end). Heavy validation runs now
  go to a server, the tree synced at a commit; the record stamps the commit, `-dirty` when `src/` differs.
- **Findings.** The Pareto machinery holds on all three cases (bounds non-increasing, no dominated plan, hard
  constraints within tolerance, converged plans best in their own sums). The bound is loose on the photon cases: at
  200 iterations no TG-119 solve met the convergence test, so the bound stays the box bound (0.64); the lung's seven
  fields reach 0.56 (5 of 16 converged at 1000 iterations), its arcs 0.79 (none of 8); the proton sets converge
  (0.071 robust, 0.020 nominal). The TG-119 deliverable plan is hotter in the target than the reweighting plan (D10
  60.9 against 53.9 Gy; no hot-dose trade-off in the set) and spares the core more; the proton deliverable plan's
  CTV D95 is 1.79 against the navigated 1.90 Gy.
- **A fault found by the record: the lung deliverable plans are not acceptable plans.** The navigated plans are
  uniform (PTV RMS 0.5 Gy); the deliverable plans are not: seven fields RMS 11.2 Gy and PTV D0.03cc 85.8 Gy, two arcs
  RMS 24.2 Gy, D0.03cc 149 Gy, cord maximum 41.8 Gy (navigated 10.6) and 319,505 MU, on a 60 Gy prescription. The
  graded goals pass (coverage and organ limits); the deviation tables and hot-spot rows show it. Mechanism: the
  deliverable step sequences the navigated fluence once (18 segments for seven fields; the R10 loop's rounds make
  43) and mimics for 200 iterations, the result under-covers the PTV, and the coverage normalisation (×1.17, ×1.42)
  inflates the hot spots. Correction planned as R11.9 (sequencing and meterset rounds as in R10, a hot-spot term in
  the mimic, more iterations, the judgement after normalisation) with the lung case rerun as a dated correction of
  the record, the project lead's choice. ADR 0019 records the fault among its consequences.

## `radiarch dose`: an RT Plan's dose recomputed from a shell (2026-10-31)

- **Command** (`cli.py`): `radiarch dose --ct DIR [--structures FILE] --plan FILE [--engine auto|ccc|pb|mcsquare]
  [--spacing MM] [--machine ID] [--any-frame] [--export DIR] [--push] [--label] [--json FILE]`. The CT directory's
  study and series UIDs are read from its first CT image; a structure set given outside that directory is linked
  beside the CT's files in a temporary directory, since the geometry service reads one directory. Then, through the
  SDK in this process (or on `--server`): the geometry, `POST /beam-model/import` with the plan's path,
  `POST /dose/recalculate` with the engine (`auto` picks the pencil beam for a photon plan and MCsquare for a proton
  plan), and the export of the RT Dose and the plan as re-written, which reference the given structure set
  (`rtstruct_uid`) instead of writing a new one; without `--structures` the structure set is written too. The
  command prints the engine, modality, element count and the dose's maximum and mean, and writes the records as
  JSON. Exit 3 when a push is refused, as `radiarch plan`.
- **SDK** (`sdk/objects.py`): `Geometry.import_plan(path, machine=, strict_frame=, beamlet_mm=, registration=)` and
  `BeamModel.recalculate(engine="auto", rbe=)`.
- **CWL**: `cwl/radiarch-dose.cwl`, checked by `test_cwl_tools_match_the_command`.
- **Tests** (`tests/test_dose_command.py`): a 24-voxel water phantom written as a CT series and a structure set, one
  anterior field of 200 MU in its frame of reference; the structure set moved outside the CT directory, the command
  run with `--engine auto`, the written RT Plan references the given structure set, the RT Dose the written plan, and
  its maximum equals the dose record's; the structure set written when none is given; the three refusals.

## The ITV variant of the lung VMAT protocol (2026-10-31)

- `src/radiarch/protocols/lung-60gy-30fx-vmat-itv.json`: `lung-60gy-30fx-vmat` for a patient whose target is an
  ITV, the tumour over the breathing phases, contoured as ITV, ITV_Primary, iGTV, ITVp, ITV-1 or ITV1. CTV = ITV +
  5 mm and PTV = CTV + 5 mm; the RTOG 0617 template's `Lungs-GTV` is derived as the lungs less the ITV, since the GTV
  of one phase is not what such a case contours. Prescription, goals, arcs, machine, engine, rounds and template are
  the base protocol's. Generated from the base protocol's file, so a change there is a change here to make too.
- Tests (`tests/test_protocol_itv_variant.py`): the two protocols compared field by field outside the target's
  derivation; a 5 mm thorax phantom with lungs, cord, oesophagus, heart and an `iGTV` planned by the variant through
  `radiarch plan` (about a minute), the run's alias map naming the iGTV as the ITV.

## The image runs the command line; CI builds the image (2026-11-01)

- The first R11.8 image (from `b0d296b`) built but `radiarch protocols` in it found no module: the builder stage's
  editable install leaves a path file pointing at the build stage, which the runtime stage does not have, and only
  the compose services set `PYTHONPATH=/app`. The Dockerfile now sets it, so the image runs the command line on its
  own (a workflow system's tool or `docker run` calls `radiarch dose` without compose).
- CI's new job "Image (build and the command line)" builds the image from the commit and runs `radiarch protocols`
  (the ITV variant listed), `radiarch dose --help` and an import in it, so an image that builds but cannot run the
  package is caught.

## The command line runs self-contained in the image (2026-11-01)

- A standalone `docker run … radiarch plan` in the R11.8 image failed: the image's defaults name its compose services
  (production, so jobs wait for a worker; a Postgres host; a Redis broker). Found by the one-patient round trip's
  first run. The fix is in the command, not the defaults: `Radiarch.local()` (the client without `--server`, which
  the command line and notebooks use) now runs self-contained whatever RADIARCH_ENVIRONMENT, RADIARCH_DATABASE_URL
  and RADIARCH_BROKER_URL say: jobs eager in this process, no database, an in-memory broker and result backend. The
  server's and the compose services' settings are untouched.
- `tests/test_dose_command.py`: `radiarch dose` under production-style settings that name unreachable hosts; the
  phantom plan in the image with the fixed package mounted, by hand.

## R11.9: the deliverable step corrected (2026-11-01)

- **The cause.** The R11 record's lung deliverable plans (PTV D0.03cc 86 and 149 Gy on 60 Gy) came from the
  projection onto the Pareto set that preceded sequencing. Analysed on a kept fast-mode run: the navigated blend has
  2,904 of 3,080 beamlets open, peaks under five times a beam's median and 5 to 10 apertures above the machine's
  minimum area per beam at the protocol's 5 fluence levels; the projection's solve (the sum of the normalized
  trade-offs, each capped at its navigated value, under the hard constraints, up to 1,000 iterations) left 600
  beamlets, peaks up to 95 times the median and three beams with no valid aperture: 12 segments in all, a plan that
  under-covered the target, and a coverage normalisation (2.46 in fast mode) that inflated what was left. The same
  held for the arcs' sectors (1,163 of 13,440 beamlets). The old code and the first correction (goal objectives,
  rounds, a hot-spot term) failed the fast case alike (191 and 189 Gy); a cap on the peaks alone brought the
  normalisation to 1.65; sequencing the blend brought it to 1.185 with 42 segments, the arcs to 1.27 with 67,000 MU
  (2.7 million before), and PTV D0.03cc to 78 Gy against the R10 reweighting plan's 77 Gy in the same fast run.
- **The correction** (`services/mco_deliverable.py`, `models/mco.py`): the deliverable plan is made from the
  navigated blend; `project` is an option, off by default. For photons the metersets are optimized against the mimic
  with each target's hot-spot term (`hot_spot_gy`; null = the navigated maximum plus `tolerance_gy`) and, with
  `goals` and a prescription, the planner's goal objectives (`objectives_for`; `planning_goals` turns the clinical
  goal set into its rows), in `rounds` like the reweighting planner's (normalise, judge the goals, a failed goal's
  weight x3, an organ limit x0.95; default 3). Before sequencing, `capped_fluence` caps a beam's peaks at
  `peak_ratio` (6) times its median nonzero weight, with at least 2 x peak_ratio fluence levels when it triggers.
  The deliverable records its `rounds`. The protocol path passes its rounds (`arc_rounds` for arcs). The record
  grades the deliverable's normalisation within 15 % of 1 and reports the rounds.
- **Tests** (`tests/test_r11_deliverable.py`): the goal rows from a clinical goal set; the objectives the sequencing
  receives (mimic, hot spot, goals) and the reweighting between rounds, a goal set that holds stopping at one, the
  bare request's terms; the cap. The projection's tests pass `project=True`; the SDK test checks the default makes
  a different plan with no projected column. The heavy check is the lung case in fast mode on a server, through
  a site-run script with the working tree synced.
- **Follow-up.** The Pareto anchors are themselves spiky (PTV maxima of 96 to 216 Gy on the navigation voxels for the
  single-objective solves under the hard constraints); a fluence smoothness regularizer in the MCO solves
  (`SolverConfig.regularization`, which the MCO request already carries) would address that upstream and is not
  turned on here.

## A 3 mm default dose grid; the data folder in the geometry's cache key (2026-11-01)

- **Default spacing.** A one-patient round trip in the image (a lung patient, 133 CT slices, two arcs) took 5 h 40 min:
  without `--spacing` the geometry inherits the CT's own grid (about 1 x 1 x 3 mm, 35 million voxels), which no record
  plans on (the lung protocols' records use 3 mm; the R11 lung demo 4 mm). `radiarch plan`, `batch` and `dose` now
  default to 3 mm (`DEFAULT_SPACING_MM`); `--spacing 0` keeps the CT's own grid; a cases file's `spacing_mm` still wins
  for its case. The CWL tools say so. Tests built on the stub CT, whose masks exist only on its own grid, pass
  `--spacing 0`.
- **Cache key.** The same round trip at 3 mm then failed with an empty structure index: an earlier invocation on a
  folder without the structure set had built and cached a 3 mm geometry with no structures, and the key, which left
  out the data folder, matched the later run on the right folder. The key now carries the resolved data folder when
  the CT series or the structure set is not named (keys for named UIDs and uploads are unchanged).
- Tests (`tests/test_dose_command.py`): a folder without its structure set and the folder with it give two
  geometries, the second reused on a rerun; the three commands' default is 3 mm and `--spacing 0` gives the CT's grid.

## R11.10: the requesting user from a trusted proxy; an export that fails when its push is refused (2026-11-01)

- **Why.** A deployment can put radiarch behind a gateway that authenticates people, with one API key for the
  gateway. The planning then needs to say who asked for each result, and an export written to an archive through
  that gateway must not count as done when the archive refused it.
- **The user** (`api/security.py` `requester`, settings `trusted_user_header`, `trusted_proxy_secret`,
  `trusted_proxy_secret_header`): when both are set, a request that carries the user header and the proxy's secret
  names its user; the name is cleaned for the records and a DICOM person name (printable, no `^ \ =`, at most 64
  characters). A user header without the right secret is refused with 401, so a caller that reaches radiarch around
  the gateway cannot claim a user; radiarch does not authenticate the user itself and must be reachable only through
  the gateway. The optimization, MCO run, navigate, auto-navigate, deliverable and export routes set the request's
  `requested_by` from it, replacing any value in the body; the services keep it on `OptimizationResult`,
  `MCOResult`, `NavigationState`, `MCODeliverable` and `RTExportResult`, and the export writes it as Operators' Name
  (otherwise "radiarch"). It is not part of any cache key: a cached result keeps its first requester.
- **The push** (setting `dicomweb_push_required`): an export with `push` whose STOW-RS push is refused raises
  `RTPushRefused`; a new export's objects are removed and nothing is recorded, a stored export pushed again keeps its
  record with `pushed: false`; the routes answer 502 (`POST /rt/export`, `POST /rt/exports/{id}/push`). Off by
  default: an export is kept with `pushed: false` and the error, as before.
- **Tests** (`tests/test_trusted_proxy.py`): the header ignored when not configured and a body value replaced; the
  user read with the secret, cleaned and truncated; refused without it or with a wrong one, and when no secret is
  set; the user on each of the five results and as Operators' Name in RP, RD and RS, a cached optimization keeping
  its first requester, an export without a user naming "radiarch"; with the push refused, an export kept with
  `pushed: false` when not required and failing with 502 (nothing left in the store, a stored export pushed again
  refused, the push route refused) when required.

## A recomputed photon plan goes through its apertures (2026-11-01)

- **Found** by the one-patient round trip: `radiarch dose` on a VMAT plan's exported RT Plan gave a dose well below
  the plan's own RT Dose (gamma 3 %/3 mm pass 48 %, mean difference 4 Gy); on a phantom VMAT plan, a median ratio of
  1.19 with the same metersets, while a seven-field static plan recomputed within 0.6 %. `POST /dose/recalculate`
  computed an imported plan through the beam model's beamlet columns, which keep a cell only when its centre is open
  and drop leaf pairs no wider than a beamlet: most of a sliding-window arc's narrow apertures. The arc plan's own
  dose goes through the exact apertures (`segment_dose_matrix`, `fluence: apertures`).
- **Fix.** The recalculation route gives a photon plan's `pb` or `ccc` engine `fluence: apertures` (an explicit value
  stays): `pb` computes every aperture at its segment's meterset (`compute_plan_dose` without weights), `ccc` its
  delivered dose through coverage beamlets (`compute_delivered_dose`, which R8 used for the same reason). Both refuse
  weights other than the plan's own (`own_metersets`). A plan whose every aperture is narrower than a beamlet has no
  fluence elements to carry its metersets and is refused with a clear 422. The phantom VMAT plan now recomputes equal
  to its RT Dose (median ratio 1.0000, mean difference 0.00 Gy).
- **And** the re-export of an imported photon plan stated one fraction with the course's metersets; the RT Plan writer
  now takes the source plan's fractions when no prescription is given.
- Tests (`tests/test_dose_command.py`): an arc whose leaf pairs sweep 3 mm and 10 mm slits recomputes through the
  apertures to about 13/10 of the beamlet columns' dose; an arc of 3 mm slits only is refused; weights other than the
  plan's own are refused; the re-exported RT Plan keeps the source's two fractions and its per-fraction meterset.

## A protocol's evaluation template follows its prescription (2026-11-02)

- **Why.** A batch plans each patient at its own prescription (60 Gy in 30 fractions to 70 Gy in 35) with copies of
  `lung-60gy-30fx-vmat-itv`. Its evaluation template, `rtog-0617`, is written for 60 Gy: its target rows (PTV V60Gy[%]
  >= 95, PTV D0.03cc[Gy] <= 72, 120 % of 60 Gy) graded a 70 Gy plan against 60 Gy.
- **The option** (`models/evaluation.py` `GoalSetSpec.scale_to_prescription`, `services/clinical_goals.py`
  `scaled_goal`, `services/evaluation.py`): when on and the request's prescription differs from the template's, the
  template's goals on the request's target structure scale with the ratio (a dose value times it, a volume goal's dose
  argument times it: V60Gy[%] -> V70Gy[%]; D0.03cc <= 72 -> 84 Gy; relative goals such as V95%[%] unchanged) and say
  so in their note; goals on other structures keep their absolute limits. Off by default; in the goal set's hash only
  when on. Protocol runs turn it on.
- Tests (`tests/test_protocol_itv_variant.py`): the scaling of each metric form; the variant at 70 Gy in 35 fractions
  plans the thorax phantom, and its evaluation has PTV V70Gy[%] and D0.03cc <= 84 Gy, the cord and oesophagus rows at
  RTOG 0617's limits.
- **Not done** (decided): a free-breathing variant. `lung-60gy-30fx-vmat` already plans a GTV-only case (CTV = GTV +
  5 mm, PTV = CTV + 5 mm, the R8 harness's margins); a free-breathing variant would need a motion margin that no
  record or physicist has set, and no case of the batch needs it.

## The viewer packages move to their own repository (2026-11-02; radiarch-ohif created 2026-10-31)

- **Why.** One OHIF installation can hold several projects' extensions. Each project then adds its packages to one
  OHIF checkout, and the installation builds once. That works best when the viewer packages are a repository of their
  own, usable with radiarch's API or, for the RT Dose layer, with any DICOMweb server.
- **Where.** passlab/radiarch-ohif holds what was `viewer/`, with its history: both extensions, the plan review mode,
  `rt-dose-core`, `radiarch-client`, `scripts/build-ohif.sh` and the standalone image. Its CI runs the packages' own
  tests and builds the image.
- **Names.** OHIF's convention: `@radiarch/extension-rt-dose` (was `ohif-extension-rt-dose`),
  `@radiarch/extension-planning` (was `ohif-extension-radiarch`) and `@radiarch/mode-plan-review`, in
  `extensions/rt-dose`, `extensions/planning` and `modes/plan-review`; `libs/rt-dose-core` and `libs/radiarch-client`.
  The mode's route stays `plan-review`, so radiarch's viewer links do not change.
- **`--add-only`.** `scripts/build-ohif.sh --add-only OHIF_DIR` places and registers the packages in an OHIF checkout
  and neither installs nor builds. The clone-and-build mode and `OHIF_DIR` stay as they were. A Node test runs the
  script on a stub checkout with `node` and `npx` stubbed.
- **Radiarch.** `viewer.ref` pins the radiarch-ohif commit radiarch is tested with. `scripts/fetch-viewer.sh` checks it
  out into `viewer/` (now ignored by git), for CI, `docker compose --profile viewer` and the demo scripts. CI's full
  suite runs the tests against radiarch's objects and API there (`test_r13_viewer_core`, `test_r13_viewer_client`,
  `test_r11_viewer_client`), and the Viewer job builds the image from it and runs the browser tests. Without the
  checkout those tests skip and say why; `RADIARCH_OHIF_DIR` points them at another checkout. ADR 0018 records the
  move; README, `docs/viewing.md` and `docs/demo.md` add the fetch step.

## R11.9, option A: coverage and the hot spot as hard constraints of the meterset solve (2026-11-03)

- **Why.** At 4 mm the pushed R11.9 left the lung case's deliverable plans needing normalisation 1.37 (seven fields)
  and 1.27 (two arcs); the cause and two designs are in `docs/reports/mco-deliverable-options.md`, and the project lead
  chose A. A third attempt (re-optimizing the fluence before sequencing) gave 4.57 in fast mode and was reverted.
- **The solves** (`services/sequencing.py` `constrained_metersets`, `optimize_segment_weights`; `services/vmat.py`
  `optimize_interval_mu`, `plan_arcs`): with `hard_terms`, the segment or interval metersets minimize the objectives
  subject to R11.2's hard-constraint terms by the augmented Lagrangian (the arcs on the metersets above each interval's
  minimum). The convergence record gives each constraint's excess (0 when met). `SequenceRequest` and `ArcRequest` take
  `hard_constraints`, in their cache keys only when given; `hard_constraint_terms` builds the terms on the dose grid.
- **The deliverable step** (`DeliverableRequest.hard_coverage`, default on, and `max_dose_factor`, 1.2): with a
  `normalise` goal, the metersets must hold the target's gEUD (a = -10) at or above the goal's dose and its maximum at
  or below 1.2 times the prescription (RTOG 0617's 120 %), each within 0.5 Gy. The normalisation is then a check near 1,
  not a correction that scales the hot spots with the coverage. Each round records the constraints' excess.
- **Fast-mode lung case** (8 mm, on the compute server): normalisation 1.09 (seven fields) and 1.10 (arcs), both inside
  the record's 15 % check; PTV D0.03cc 74.8 and 78.0 Gy, against 189 and 191 Gy before and the R10 reweighting plan's
  77 Gy in the same run; PTV V60Gy 95.4 % and 95.1 %. The 4 mm check follows before the record's correction.
- Tests (`tests/test_r11_deliverable.py`): a two-segment problem whose objective gives up the target, held at its
  minimum by the segment and the arc-interval solves; the deliverable's two limits, off with `hard_coverage=false` and
  without `normalise`.

## `radiarch dose`: the structure set and the plan as their series folders (2026-11-03)

- **Why.** A workflow engine that hands each input over as the folder of its series passed
  `--plan <folder>`, and the command stopped: it took only a file there.
- **Command** (`cli.py` `_the_one`): `--structures` and `--plan` take a file as before, or a folder. In a folder the
  command reads each file's header and takes the one RT Structure Set or the one RT Plan (an RT Ion Plan too); copies
  of one instance count once. A folder with none, or with more than one, is refused with a message that says which.
  The CWL tool (`cwl/radiarch-dose.cwl`) takes a File or a Directory for both.
- Test (`tests/test_dose_command.py`): the structure set and the plan each in its own series folder, outside the CT's,
  with the written RT Plan referencing that structure set; a folder with no plan, one with no structure set, and one
  with two plans refused.

## The command line under another uid: a temporary artifact store (2026-11-03)

- **Why.** A workflow engine ran the image's `radiarch dose` as its job account's uid. The image's artifact folder
  (`/data/artifacts`) is root's, so the geometry store's first `mkdir` failed with permission denied.
- **Change** (`sdk/client.py` `Radiarch.local`): when the configured artifact folder cannot be created or written, the
  in-process app keeps its artifacts in a fresh temporary folder (under `TMPDIR`) and removes it when the client
  closes; `RADIARCH_ARTIFACT_DIR` is then restored. A writable folder is used as before. Nothing else in the command
  writes outside `TMPDIR` and `--export`: the engines' working folders are temporary already.
- Tests: `tests/test_dose_command.py` runs the command with an artifact folder no one can create, and checks the RT
  objects, that the store was temporary and removed, and the environment restored. The CI image job now runs
  `radiarch dose` as uid 12345 on a read-only image with only `/tmp` and the output folder writable, the plan given
  as a folder.

## `radiarch dose --dose-only`: the RT Dose of the plan as given (2026-11-03)

- **Why.** A regeneration takes a structure set and a plan and returns their dose. The export wrote the RT Dose with a
  re-written plan, and the dose referenced that plan's new SOP Instance UID, not the plan it was given.
- **Export** (`models/rt_export.py`, `services/rt_export.py`): `rtplan_uid` references an existing RT Plan (an RT Ion
  Plan for protons) instead of a written one, as `rtstruct_uid` does for the structure set; the dose's
  ReferencedRTPlanSequence names it. Refused with `rtplan` among the objects, and with per-beam doses or DRRs, which
  name the written plan's beam numbers. In the cache key only when given, so earlier exports keep their keys.
- **Command** (`cli.py`, `cwl/radiarch-dose.cwl`): `--dose-only` exports only the RT Dose, with `rtplan_uid` the given
  plan's SOP Instance UID. The dose carries the CT's study and frame of reference (the plan's, checked on import).
- Test (`tests/test_dose_command.py`): with `--dose-only` the export holds one RD whose referenced plan is the input's
  SOP class and instance, in the CT's study and frame; the two refusals; the cache key differs with the reference.

## R11.9: the coverage constraint calibrated on the plan (2026-11-04)

- **Why.** At 4 mm, option A met its two limits on the lung case (run `20261104-000104-f5597f9` on the compute server,
  every graded check passing) and still needed normalisation 1.111 (seven fields) and 1.108 (arcs), with the PTV
  D0.03cc at 80 Gy on 60 Gy. A gEUD (a = -10) at 60 Gy is not the coverage goal (D95 at 60 Gy): it holds with a cold
  edge, which the normalisation then scales up with the hot spots.
- **Change** (`services/mco_deliverable.py`, `DeliverableRequest.normalise_band`, default 0.03): while a round's
  normalisation is further than the band from 1, the next round's gEUD level is its level times that normalisation,
  at most 0.95 times the maximum's limit. The rounds stop when every goal holds and the normalisation is within the
  band. The plan kept is a round whose goals hold, then the one whose normalisation is nearest 1 (before, the last
  round's). Each round's log gives the gEUD level (`coverage_gy`), and the kept round is marked.
- **Fast-mode lung case** (8 mm, on the compute server, from the uncommitted change): both plans in two rounds,
  normalisation 1.091 then 0.985 (seven fields) and 1.104 then 0.971 (arcs); PTV D0.03cc 71.0 and 70.0 Gy, under the
  protocol's 72 Gy and the reweighting plan's 77 Gy in the same run; PTV V60Gy 95.3 %. Every graded check passes.
  Organ doses rise within their limits: heart mean 15.1 and 19.4 Gy against the navigated plans' 8.9 and 4.9,
  esophagus mean 8.1 and 9.9 Gy; the deviation tables flag 6 and 9 rows. The 4 mm run of this commit follows, and its
  result is the R11 record's correction.
- Test (`tests/test_r11_deliverable.py`): with scripted normalisations, the gEUD level follows them and stops at the
  cap, and the round nearest 1 is kept; a wider band stops sooner; a first round inside the band is the only one.

## Store cleanup keeps what an approval locks (2026-11-04)

- **Why.** The periodic cleanup evicted dose, influence, optimization, beam-angle and evaluation entries by size and
  last read only. An approved version, or one it derives from, could be deleted, although the delete routes refuse
  both (R12, ADR 0013).
- **Change** (`tasks/cleanup_tasks.py`): each sweep keeps the entries whose `kind:id` is in the lineage service's
  lock set (every version ever approved and its ancestry), and reports them as `locked_kept`. With no state file
  nothing was approved and the sweep runs as before. A state file that cannot be parsed stops the whole sweep (the
  lineage service reads one as "nothing approved"), with a `failed` audit event.
- Test (`tests/test_r12_lineage.py`): two sequenced plans, one segment dose approved, every store over its cap with no
  entry young enough to be spared. With the state file cut in half, nothing is evicted. With it intact, only the
  approved dose and its optimization are left.
- Docs: `architecture.md` (the known gap removed), ADR 0013 decision 4, `PRODUCTION.md` (disk hygiene).

## R11 record: the lung case's deliverable plans corrected (2026-11-04)

- **Run.** `20261104-151641-8102454`: the lung case at 4 mm from a clean checkout of `8102454` (R11.9 with the
  calibrated coverage level) on the compute server, 6.3 hours. The Pareto sets and the reweighting plan reproduce the
  record's numbers exactly. The run of `f5597f9` (option A without the calibration, `20261104-000104`) is kept beside
  it as the intermediate step.
- **Result.** Every graded check passes. Normalisation 0.967 (seven fields) and 1.029 (two arcs), each after two
  meterset rounds; 1.17 and 1.42 in the record, 1.111 and 1.108 in the intermediate run. PTV D0.03cc 69.7 and
  74.3 Gy, from 85.8 and 149.2; PTV RMS 5.7 and 7.8 Gy, from 11.2 and 24.2. The fields plan stays near the record's
  organ doses (heart mean 9.5 Gy, cord D0.03cc 4.9 Gy). The arcs plan's are higher within their limits: cord
  D0.03cc 34.5 Gy, heart mean 13.6 Gy, esophagus mean 9.4 Gy, against the navigated plan's 10.6, 9.9 and 5.3. The
  deviation tables flag 3 and 9 rows.
- **Finding.** In the arcs' second round the meterset solve ended 3.0 Gy short of one of its two hard constraints
  (the raised coverage level against the 72 Gy maximum), and the kept round's 1.029, inside the 3 % band, scaled the
  maximum to 74.3 Gy. The run's results give the number of rounds but not each round's constraint values.
- **Record.** `docs/validation/2026-10-31-r11/2026-11-04-correction-8102454/` (guide, both runs' summaries and
  results) and a correction notice in the record's guide, as R8's of 2026-10-24. ADR 0019's consequences and the
  R11.9 plan row ([x]) follow; R11.11 (B1, the second navigation on the deliverable plan's apertures, with the
  maximum's limit divided by the normalisation and the rounds in the record) is added; the status table is brought
  to 2026-11-04.

## A worker that starts, and the trusted proxy's check on every route (2026-11-04)

Found by a gateway deployment of `4682273`: its Celery worker died at start, and a user header without the proxy's
secret was refused on some routes only.

- **Worker.** radiarch pinned celery and redis-py but not kombu, which celery allows up to 6.0. kombu 5.7.0 refuses
  redis-py below 6.1 in its Redis transport, so any image built after its release had a worker that exited at start
  (`VersionMismatch`). Tests and the command line run jobs in-process, so nothing had started a real worker. kombu is
  now pinned below 5.7 (`src/pyproject.toml`). CI's Image job starts a worker from the built image beside Redis, waits
  for its ping, and runs the store cleanup through the broker and the result backend.
- **Every route.** The check that a request naming a user carries the proxy's secret ran only in the dependency that
  reads the user, on six routes. It is now a middleware too (`api/security.py` `user_header_untrusted`, `app.py`),
  registered inside CORS so the 401 carries CORS headers. Without the setting, or without the header, nothing changes.
- **Protocol runs.** `POST /protocols/run` reads the user: the run result keeps it as `requested_by`, and an MCO
  protocol passes it to its Pareto set, its navigation state and its deliverable plan. A cached run keeps its first
  requester; the user is not part of the run's key.
- Tests: `tests/test_trusted_proxy.py` (four routes that never read the user refuse the header without the secret,
  or with a wrong one, and answer with it); `tests/test_r11_protocol.py` (a protocol run under a user keeps it on the
  run, the Pareto set, the state and the deliverable plan). Checked by hand: a worker from the venv beside a Redis
  container answers the ping and runs the cleanup task.
- Docs: `README.md` (the two settings), `PRODUCTION.md` (the five queues and the worker that must consume them).

## R4: leaf transmission, rounded leaf ends and tongue-and-groove in aperture doses (2026-11-04)

Design: `docs/reports/mlc-leaf-model.md`, agreed with the project lead on 2026-11-04, rounded leaf ends included.

- **Model.** `LeafModel` (`models/photon_plan.py`): leaf and jaw transmission, dosimetric leaf gap, tongue-and-groove
  width. `MLCSpec` gains the gap and the width; `PhotonMachineSpec.leaf_model()` gives the four values. Both synthetic
  machines get a 1.5 mm gap and 0.5 mm tongue-and-groove (LoSasso, Chui and Ling 1998), their transmissions as before.
- **One aperture model.** `PhotonSegment.fluence_rectangles(model)`: the openings with each tip moved back by half the
  gap, at full fluence inside the jaws and at the jaw transmission outside them; the leaves inside the jaws at the leaf
  transmission; in a strip on each boundary between adjacent pairs, the overlap of the two openings. Without a model,
  or for a jaws-only field, the ideal aperture as before.
- **The three paths.** `sequencing.coverage_matrix` builds each aperture's segment (`aperture_segment`) and covers the
  open field's beamlets with its rectangles; `pb.aperture_rectangles` and the pencil beam's aperture fluence (plan dose
  and segment dose matrix) take the plan's model; `PhotonSegment.coverage_beamlets` and
  `ccc_driver.delivered_beamlet_geometry` take it for CCC's delivered dose.
- **Plans.** `PhotonPlan.leaf_model`: set from the machine by sequencing and VMAT, kept by a normalised plan and the
  plan of the day, set from the import's machine on an imported photon plan. Plans pickled before it read as ideal
  leaves (`getattr`).
- **Caches.** `LEAF_MODEL_VERSION` in the keys of sequences, arcs, MCO deliverable plans and protocol runs.
- Tests: `tests/test_r4_mlc_leaf_model.py` (a closed pair passes the transmission and its tips' gap; a narrow gap acts
  wider by the gap; complementary segments dip in the tongue-and-groove strip; pairs open alike have no stripe; the
  three paths integrate to the same fluence; a sequenced plan carries the machine's model; the pencil beam passes
  1.5 % under closed leaves; the keys change with the version). `tests/test_dose_command.py`: an imported sweep arc
  recomputed through its apertures now gets the default machine's leaves, so its band (13/10 of the beamlet columns'
  dose) is scaled by the leaves' fluence gain, 1.8 on that arc (its 3 mm slits, and eight closed pairs inside 8 cm
  jaws).
- Docs: the design note's "As built", ADR 0010's consequences, `architecture.md` §9, the R4 plan row.
- **Next.** The records with aperture doses are rerun on the compute server: R8 (VMAT, SBRT, CCC recomputation of
  delivered plans), R10 (the protocol plans) and R11 (the lung case's deliverable plans).

## The records rerun with the MLC leaf model (2026-11-05)

- **Runs.** On the compute server, one case per process, in the radiarch image built from `55ab566` with a clean
  checkout mounted over its code: from `412a105`, R8's `lung_sbrt_vmat`, `lung_vmat_lctsc` and `hn_sib_vmat`, R9's
  `lung_4d_itv`, R10's `protocol_batch_lctsc`, R11's `mco_front_tg119` and `mco_protocol_lung`; from `890a575`, R10's
  `protocol_lung_vmat`, which compares itself with the R8 rerun. A release upgrade of the server cut the first runs
  of five cases; they were rerun.
- **Baselines.** The first comparison, against the old records, mixed the leaf model with every commit since them
  (R9 to R11.9). So the six cases also ran from `55ab566`, the commit before the leaf model. For R11's lung case the
  correction's run from `8102454` is the baseline: no planning code changed after it.
- **Result.** Every graded check passes, in each baseline and with the leaf model. The low doses around the targets
  rise through the closed leaves and the wider tips: SBRT R50 by 8 to 10 %, lung V20 by about 1 percentage point in
  the conventional lung case and up to 2 in the 4D case, the MCO arcs plan's heart and oesophagus means by 2.6 and
  2.4 Gy. Organ maxima move both ways, by up to 2 Gy. The second engine agrees as before. `protocol_lung_vmat`
  reproduces the R8 rerun exactly.
- **Finding.** R11.9 changed the TG-119 case's deliverable plan, which the R11 correction called unaffected: its core
  D5 went from 6.16 Gy in the record to 17.65 Gy at `55ab566`, and is 22.40 Gy with the leaf model, inside the
  institutional limit (22.44 Gy) but not TG-119's goal (10 Gy). Every meterset round misses the core's and the outer
  target's goals. R11.11 (B1) is the follow-up, as for the lung case's arcs.
- **Records.** Dated rerun folders, each with its baseline: `docs/validation/2026-10-23-r8/`, `2026-10-25-r9/`,
  `2026-10-26-r10/` and `2026-10-31-r11/`, under `2026-11-05-leaf-model-412a105/`, and a notice in each record's guide.
  `protocol_lung_vmat` now names the R8 rerun as its record. The R4 plan row is updated.

## R4: the leaf model against Monte Carlo through the Agility MLC (2026-11-06)

- **Scope.** The project lead chose this before B1. The 4 × 4 and 20 × 20 cm references and their graded check had
  existed since 2026-10-23; only their plan row was open, and it is now ticked. New: 1 × 1 and 2 × 2 cm open fields at
  1.25 mm, and four fields set leaf by leaf through the Versa's Agility MLC (open, every pair closed on the axis, a
  10 mm gap on every pair, an irregular field), between Y jaws and two tungsten blocks standing in for X jaws.
- **Code.** `mc_reference.py`: the small and MLC cases, `mlc_leaf_positions` (refuses interdigitating pairs, which
  overlap in the Versa model), `set_mlc_field`, `per_thread`, the dose per simulated primary, `--merge`.
  `cases_r7._mc_reference` scales the older references. `cases_r8`: the small fields' dose and width graded;
  `_mlc_checks` fits the transmission and leaf gap to the closed and gap fields and grades the irregular field.
  `pb_vs_mc.yaml`: tolerances. `tests/test_r4_mlc_monte_carlo.py` (17 tests).
- **Two faults found in the Monte Carlo runs.**
  - OpenGATE 10 runs a source's `n` on every thread, so the R7 and R8 references ran 18 times the primaries they
    state. Their comparisons stand; the harness scales them.
  - One process stops gaining speed beyond about a dozen threads, so the long references ran as 62 chunks,
    16 processes at a time, about 2.5 hours in all, instead of the 26 hours one process would have needed.
- **Results.** The Agility fits a leaf transmission of 0.196 % and a dosimetric leaf gap of 1.01 mm. On the
  irregular field the pencil beam's gamma (3 %/2 mm) passes at 100 % (ideal leaves 99.1 %), and the closed pairs
  and the 10 mm gap pass. The 2 × 2 cm checks pass.
- **Two checks fail:** the 1 × 1 cm field's dose at 10 cm (−5.9 % of 5 %) and the irregular field's 5 mm gap (+3.2
  points of 3). One leaf gap cannot serve the 5 and 10 mm gaps together (0.6 and about 1.6 mm). Both are the pencil
  beam on openings of a centimetre and less.
- **A change after the first results.** The leaf gap is fitted to the gap field's dose integrated across the gap,
  as a sweeping gap measures it, not to its centre dose. The centre-dose fit gave 1.30 mm and failed the 5 mm gap by
  5.2 points. The project lead chose the integral; no tolerance changed. The design note
  (`docs/reports/mlc-leaf-model.md`, "Against Monte Carlo") has the table and the reasons.
- **References in the repository.** The six references (about 18 MB) are in `validation/references/mc/` with the
  project lead's approval, beside the earlier ones; the harness reads them from there.
- **The record.** Run `20261106-163934-727654c`, from a clean checkout of `727654c` on the compute server: 50
  checks, 33 pass, 2 fail (the two above), 15 informative, the same values as the working tree. The 34 checks of
  R8's `pb_vs_mc` repeat R8's values. Folder `docs/validation/2026-10-23-r8/2026-11-06-mc-leaf-model-727654c/`,
  with a notice in the R8 guide. The pencil kernel's note still states 3.0 × 10⁷ primaries; that run also used 18
  threads (5.4 × 10⁸), which the record states. The calibration cancels its scale.

## The reference files checked; one removed (2026-11-06)

- **Scope.** The project lead asked for the reference files to be checked and those not needed removed.
- **Kept, each read by a case or a tool:** the Monte Carlo references in `validation/references/mc/` (the water
  fields, the slabs and the MLC fields: `pb_vs_mc` and `photon_vs_mc`);
  `pencil_6mv.npz`, the pencil Monte Carlo that `pb_kernel --mc` turns into `engines/pb/pb_6mv_kernel.npz`; the
  pyRadPlan doses (`photon_vs_pyradplan`); `photon_6mv.json`, `proton_water.json` and `tg119_goals.json`; the
  Mohan spectrum.
- **Removed:** `validation/references/tolerances.json`. No code read it; the cases state their tolerances, and
  `docs/reports/validation-data-and-test-plan.md` cites the guidance it quoted (MPPG 5, TG-218, TG-119, TECDOC-1583,
  TG-185 and TG-224).

## The pencil kernel states the primaries its Monte Carlo simulated (2026-11-06)

- **Scope.** The project lead asked for the kernel's metadata to state what the pencil Monte Carlo ran.
- **Fault.** The pencil reference was made before the per-thread fix: OpenGATE ran its 3 × 10⁷ primaries on each of 18
  threads, 5.4 × 10⁸ in all. The kernel's metadata copied the stated number, and the `pb_vs_mc` note printed it.
- **Code.** `pb_kernel.source_primaries` scales the primaries of references made before the fix by their threads and
  states the table's unit (the dose per primary of one thread). `engines/pb/pb_6mv_kernel.json` states 5.4 × 10⁸ and
  18 threads. The table is unchanged, and so are its fingerprint (`f046d6a503757f17`) and every dose: the output
  calibration removes the scale. One test in `tests/test_r4_mlc_monte_carlo.py`.

## The R7 guide's primaries; CI's apt step (2026-11-06)

- **R7 guide.** A dated notice: the record's Monte Carlo references ran 18 times the 5×10⁷ primaries they state, and
  every comparison normalises the Monte Carlo dose, so no value changes (as in the R8 guide).
- **CI.** On 2026-11-05 a runner's package mirror hung `apt-get update` for 13 minutes and the full-tests job ran out of
  time. The dicom3tools step now retries a slow mirror (three retries, 30-second timeouts) and stops at its own
  4-minute limit, so a hang fails under that step's name. The step stays required: it guards the RT objects' check.

## The viewer follows a job until it ends (2026-11-06)

- **Fault.** The viewer's client stopped waiting for a job after 5 minutes. A deliverable arc plan takes hours, so the
  MCO panel showed a timeout while the job ran on and then succeeded.
- **Fix** (radiarch-ohif `eddc99c`, `viewer.ref` moved to it). The client follows a job until it ends: polls slow from
  0.5 s to 5 s, a gateway restart or dropped connection while polling is retried up to five times in a row, and a
  host may still set a limit. `makeDeliverable` and `evaluateExport` report the job's status at each poll and take a
  signal that stops the wait, not the job. The MCO panel shows the job's progress and stage, and stops waiting when it
  closes or another dose comes on screen. Six offline tests (a fake API and a fake clock) in radiarch-ohif's CI.
- **Open.** A second request for a deliverable whose job is still running starts another job; the API could let it
  join the running one.

## R11.11: a second Pareto set on the deliverable plan's apertures; closed leaf pairs under an X jaw (2026-11-06)

- **Scope.** The project lead started R11.11 (option B1 of `docs/reports/mco-deliverable-options.md`) together with
  parking closed leaf pairs under an X jaw, so that one rerun round covers both.
- **The second set** (`services/mco_apertures.py`, design note "B1 as built"). `POST /mco/deliverables/{id}/pareto`
  (200 cached, 202 job on the MCO job table, task `radiarch.mco.apertures`) builds a small Pareto set over a
  deliverable photon plan's metersets: the segment MU of static fields or the interval MU of arcs, with the first
  set's trade-offs and a budget of 2N + 1.
  - It is stored as a Pareto set, with `source_deliverable_id` and `elements`. Navigation, automatic navigation and
    `POST /mco/{id}/deliverable` work on it unchanged.
  - Making a state the plan changes only the metersets. For static fields its dose is the navigated dose exactly;
    for arcs the full kernel's, against the pencil beam's interval doses that navigation used.
  - Limits: the first set's hard constraints; with `hard_coverage`, the target's gEUD no lower than the deliverable
    plan's and its maximum at `max_dose_factor` times the prescription, each within 1 % of its level; every meterset
    at or above the machine's minimum. A limit the feasibility run cannot meet is relaxed to what it reaches, with a
    note.
  - A proton plan, and a plan of a second set, get 422.
- **Shared code.** `MCOService.run` is split into the problem's assembly and `generate`, which the second set reuses;
  the first set's cache keys and results are unchanged. The sequencer's coverage of a segment is
  `sequencing.segment_coverage` and a whole plan's `plan_coverage`. Lineage reads the second set's beam models
  (`metersets:`).
- **SDK, command line, protocols.** `MCOPlan.pareto()` returns the second set as a `ParetoSet`. A protocol's `mco`
  section has `second_set` (default on): the second set is navigated automatically by the same goals and that state
  is the plan. The run's `mco_id`, `state_id` and `deliverable_id` are the second set's; `radiarch plan` prints both
  sets. The digest of an `mco` protocol changes; a protocol without the section keeps its digest.
- **The R11 correction's two follow-ups.**
  - A meterset round within the normalisation band whose target maximum, once normalised, passes its limit is not
    accepted. The next round keeps the coverage level and divides the maximum's limit by the normalisation; the
    kept round prefers one whose normalised maximum holds.
  - Each round records its coverage and maximum limits, the gEUD and maximum reached, the maximum once normalised, and
    each constraint's excess. The R11 cases print them.
- **Closed leaf pairs.** `sequencing.park_position`: 10 mm behind the X1 jaw, behind X2 when the leaves cannot reach
  X1, else the deeper of the two. Static segments park every closed pair there; an arc parks a pair that no control
  point opens, for the whole arc. A pair open in some sectors still waits where its sweep leaves it. A machine without
  interdigitation keeps its closed pairs where the sequencer closed them. `LEAF_MODEL_VERSION` is 2, so cached
  sequences, arcs, deliverable plans and protocol runs are made again.
- **Validation cases.** `mco_front` and `mco_protocol` follow each plan back to its first set and deliverable plan,
  keep those checks under their names, and add the second set's checks, the plan on it (graded against TG-119's goals
  in `mco_front`), and a row per trade-off and goal from the first navigation to the plan.
- **Tests.** `tests/test_r11_apertures.py` (new); parking in `test_r4_sequencing.py` and `test_r8_vmat.py`; the
  second set on arcs in `test_r11_deliverable_vmat.py`; the limit divided by the normalisation in
  `test_r11_deliverable.py`; the protocol's second set in `test_r11_protocol.py`.
- **Viewer** (radiarch-ohif). The client's `apertureSet` builds the second set and follows its job. The MCO panel's
  "Navigate again on its apertures" moves the panel to it after a plan is made, and the panel names a second set as
  such. One offline job test, and the live client test (`tests/test_r11_viewer_client.py`) builds a second set and
  makes its balance plan the plan; radiarch's browser test clicks the button. `viewer.ref` moves to radiarch-ohif
  `150b05a`.
- **Open.** The 4 mm lung and TG-119 reruns on the compute server are next, with the R8–R10 cases the parking changes.

## R11.11: two fixes from the rerun (2026-11-06)

- **What the rerun found.** On the compute server, `mco_front_tg119` failed one new check: the plan made on the
  second set was not deliverable. The run's work files were not kept, so the plan's notes are gone. The likely cause:
  - a segment that every plan of the second set holds at the 2 MU minimum;
  - a blend of plans whose weights sum to 1 only to rounding, which puts that segment just below 2 MU (weights 0.7,
    0.2 and 0.1 give 1.9999999999999998);
  - the static deliverability check, which has no tolerance, while the arc check has one.
  In the same run, none of the second set's five plans converged at the case's 200 iterations, and the set's error
  bound stayed at 0.80. Every other check passed. The plan on the second set kept the navigated dose exactly
  (normalisation 1.002) and lowered the core's D5 from 22.40 Gy to 19.23 Gy at the same coverage.
- **The blend's metersets.** `mco_apertures.blend_metersets` puts a meterset below the machine's minimum by rounding
  back at the minimum, within the arc check's tolerance (1e-6 of the minimum). A meterset below it by more stays, and
  the deliverability check flags it.
- **The second set's own budget.** `ApertureSetRequest.solver` defaults to L-BFGS-B with 2000 iterations. `mco_front`
  and a protocol's second set use it rather than the first set's budget. The second set's solves have one variable
  per meterset (70 for TG-119), so the larger budget costs seconds.
- `APERTURE_SET_VERSION` is 2, so cached second sets and the plans made on them are made again.
- **Tests.** `tests/test_r11_apertures.py`: three plans hold a segment at a 2 MU minimum, and the blend 0.7, 0.2, 0.1
  is flagged without the fix and deliverable with it.
- **Open.** TG-119's rerun on the compute server.

## R11.11: a second set's plans at their lower limits (2026-11-07)

- **What the reruns found.** From `e03cd6d`, `mco_front_tg119` passes all 18 checks: its second set converged (5 of
  5, error bound 0.031), and the plan made on it is deliverable. `mco_protocol_lung` (4 mm) fails one check in each
  second set, as it did from `b11713b`: "each converged plan is the best of the set in its own weighted sum" reads
  0.0538 for the seven static fields and 0.2033 for the two arcs (limit 0.01). In the static set, the anchor for
  UniformRMS(PTV) is beaten by the balance plan on all five objectives. Every other graded check passes.
- **The diagnosis.** The case was run again from `e03cd6d` on the compute server with its work files kept. The run
  reproduced both values exactly. Each second set was then rebuilt from the kept files and generated again:
  - a stricter stall rule (1e-7, 1e-10), the metersets scaled by their dose per MU, and a re-solve of each beaten plan
    from the plan that beats it: the static check reads 0.017 at best;
  - each plan's use of each hard constraint's tolerance: only the target's coverage limit, gEUD (a = -10) at least
    the deliverable plan's 64.36 Gy within 1 % (0.64 Gy), is used much. The UniformRMS anchor uses 13 % of it, the
    balance plan 91 %.
- **The cause.** A solve may stop anywhere inside a limit's tolerance. Inside a lower limit, a plan gives less dose,
  and less dose scores better on every objective. The second set's spans are narrow (static UniformRMS 1.33 Gy, arcs
  0.16 Gy), so a plan deeper in the coverage limit's tolerance beats the others in their own weighted sums.
- **The fix.** `mco_apertures.at_lower_limits` scales each solved plan's metersets up until every lower limit (Dmin,
  gEUD >=) is met exactly. The scaling stops where an upper limit reaches its tolerance. The dose is linear in the
  metersets, and every limit's value scales with it, so the scaling is exact. It never lowers a meterset, so every
  meterset stays above the machine's minimum. `MCOService.generate` takes it as `finish`, applied to each solve
  before its values are taken; only the second set passes one, so the first sets are unchanged. On the kept run's
  plans, the scaling was at most 0.9 %, the target's maximum used at most 0.95 of its tolerance, and both checks
  read 0.0. Cutting every tolerance to a tenth also passed the static set (0.0, 189 s instead of 230 s), but it
  changes the tolerances, so it was not taken.
- `APERTURE_SET_VERSION` is 3, so cached second sets and the plans made on them are made again.
- **Tests.** `tests/test_r11_apertures.py`:
  - a plan 0.5 % below its gEUD limit is scaled to it exactly, a plan that meets it is kept, and an upper limit caps
    the scale at its tolerance;
  - on the stub patient, every plan of the second set meets its lower limits exactly (or has an upper limit at its
    tolerance), and those are the metersets stored. Without the fix, one of its five plans is 0.22 % below the
    coverage limit and the test fails. The stub's set passes the best-of-set check with or without the fix.
- **Open.** The reruns of `mco_front_tg119` and `mco_protocol_lung` on the compute server.

## R11.11 done: the records of the rerun round (2026-11-08)

- **R11.** From `a36fc4f` on the compute server, `mco_front_tg119` passes all 19 graded checks and
  `mco_protocol_lung` all 38. Both second sets' best-of-set checks read 0.0. Record:
  `docs/validation/2026-10-31-r11/2026-11-08-second-set-a36fc4f/`, with the failed rounds from `b11713b` and
  `e03cd6d` kept beside it.
  - TG-119: the second set converged (5 of 5, error bound 0.031). On it, the core's D5 is 19.32 Gy, against 22.40 Gy
    on the deliverable plan, at OuterTarget D95 50.1 Gy. The scaling to the lower limits stopped at the target's
    maximum (60.1 Gy), with the gEUD inside its tolerance.
  - Lung, seven fields: 11 of 11 converged (error bound 0.337). Every plan meets the coverage limit exactly. The plan
    on the second set lowers the cord's maximum (5.56 → 4.56 Gy) and the oesophagus mean (1.59 → 1.14 Gy).
  - Lung, two arcs: 1 of 11 converged (error bound 0.910). The plan on the second set lowers the cord's maximum from
    32.3 to 27.2 Gy and the oesophagus mean from 11.8 to 10.7 Gy at the same coverage.
- **R8–R10.** The cases the parked leaf pairs touch ran from `b11713b`. Every graded check passes. Only
  `lung_vmat_lctsc` and `protocol_lung_vmat` move, on one patient, by at most 0.19. Records:
  `2026-11-07-parked-leaf-pairs-b11713b/` under R8, R9 and R10.
- **Open.** The arcs' second set converges poorly. In the diagnosis, from `e03cd6d` and before the scaling, its
  metersets scaled by their dose per MU converged 11 of 11 (error bound 0.285, against 0.845). The two together have
  not been run. Two TG-119 checks share the name "OuterTarget Dmax <= 60.0 Gy in every plan" (the first set's limit
  and the second set's maximum, both 60 Gy there).

## R11.11: the arcs' second set, a diagnosis (2026-11-08)

The diagnosis ran on the work directory kept from the 4 mm lung run, with the code at `a36fc4f`. Its scripts are not
in the repository. No code changed.

- **The two fixes together.** The metersets were scaled by their dose per MU, and each plan was scaled to its lower
  limits. The arcs' set then converges 11 of 11 (error bound 0.403, against 0.910) in 15 minutes (against 34). Every
  plan meets its lower limits exactly, and no plan is dominated. But over all 11 plans the best-of-set check reads
  0.0168, above its 0.01 limit: the oesophagus anchor beats the balance plan in the balance plan's own weighted sum.
  The seven-field set is unchanged (11 of 11, error bound 0.336, check 0.0).
- **Why.** The plans use different shares of the PTV Dmax tolerance (72 Gy, tolerance 0.72 Gy): from 0.55 to 0.93.
  The anchor that beats the balance plan uses 0.93; the balance plan uses 0.61. Re-solving the balance plan from the
  anchor, or with three times the budget, leaves it beaten.
- **Solving to a tenth of each tolerance.** Each plan's solve stopped only when every violation was within a tenth
  of its tolerance; the penalty's start, the limits and the checks stayed as they are. On the arcs, no solve reached
  it. In every solve, and in both feasibility runs, the worst violation fell to 0.25 Gy and no lower; the stored
  plans put it on PTV Dmax, with the gEUD limit met exactly. Every solve ran all 12 rounds, the penalty rose to between 1e5 and 1e8, and the 11 plans came out nearly the same:
  4 dominated, the check at 0.676, the balance plan's weighted sum 31.9 Gy worse, 58 minutes. The seven-field set
  passed (11 of 11, error bound 0.345, check 0.0, 205 s).
- **What it means.** On the arcs' apertures, with every meterset at or above the machine's minimum, no plan meets
  PTV Dmax within 0.25 Gy while the gEUD limit holds. Every plan uses at least a third of the Dmax tolerance, and the
  set's trade-offs lie inside the rest of it. How deep each plan sits there is what fails the check.
- **Decision.** The project lead kept the arcs' convergence open (`impl-plan.md`). The lung record from `a36fc4f`
  stands as graded.

## Arcs: leaf pairs closed for part of an arc, measured (2026-11-08)

Since R11.11, an arc parks a leaf pair under an X jaw only when no control point opens it. A pair closed in some
sectors waits inside the field: at the field's centre where it has no fluence, or where its sweep ended. This was
measured on the four arcs of the 4 mm lung run (two plans, two arcs each; machine `synthetic-120`, leaf gap 1.5 mm,
25 mm/s). The script is not in the repository. No code changed.

- **How much.** Closed pairs sit inside the field for 20 to 35 % of the pair metersets: 4 to 8 of the 22 pairs in
  each interval, meterset-weighted. Their tips pass 2.2 to 5.8 % of the arc's open fluence, a geometric estimate
  (each leaking pair's 1.5 mm gap against the whole open area). The leaf model includes it in the dose, so the
  metersets are optimized with it.
- **Parking that lengthens no interval.** An interval's aperture is the mean of its two control points, so a closed
  run keeps its end points. Each inner point moves toward the jaw as far as the leaf speed allows in the intervals'
  present times. This removes about a quarter of the leak (2.2 to 1.6 %, 3.9 to 3.0 %, 5.0 to 4.2 %, 5.8 to 4.5 %).
  Most runs are too short for a 90 mm trip to the jaw and back.
- **Parking every run of three or more points.** This removes about half the leak, since the runs' ends still leak.
  Delivery lengthens from about 220 to 375 s per arc, and 20 to 34 intervals per arc fall below the new minimum
  meterset.
- **Decision.** The project lead chose to record the measurement and leave the pairs as they are. The parking that
  lengthens no interval is to be built with the next change that reruns the arcs (`impl-plan.md`, R8).

## The push's own credential only to its configured URL; ADR 0020 (2026-11-08)

- **Fix.** `POST /rt/exports/{id}/push` takes a `url`. A request that named one without a username was pushed with
  radiarch's own credential: its client-credentials token, or its HTTP-basic username and password. Any caller of
  the route could have that credential sent to a server of its choosing. Now `DICOMwebNotifier` uses radiarch's
  credential only when the target is `RADIARCH_DICOMWEB_URL` (scheme and host compared without case, the path
  without a final slash). Another URL gets only the username and password the request gives, or nothing.
- **Tests.** `tests/test_dicomweb_push_auth.py`: another URL receives no `Authorization` header and no token is
  fetched, directly and through the export service's push; a credential the request gives does reach it; the
  configured URL, named again with a final slash, still gets radiarch's credential; `_same_url` on hosts, ports,
  schemes and paths. The two tests that pushed with the settings' token to an unconfigured URL now configure it.
  The new test fails on the code before the fix.
- **ADR 0020** (accepted): an upload token per export, carried unchanged in `X-Upload-Authorization` for one push
  and never kept; a setting that requires it, off by default; the viewer's `getUploadToken` hook. The project lead
  decided its three open points. Only decision 6, this fix, is built; the rest is R13.4.
- **Documents.** `docs/PRODUCTION.md` states the rule in the push section.

## R13.4: an upload token per export (2026-11-08)

ADR 0020 built; decision 6 was built first (8d0bffc).

- **Radiarch.**
  - Two settings: `RADIARCH_UPLOAD_TOKEN_HEADER` (default `X-Upload-Authorization`) and
    `RADIARCH_UPLOAD_TOKEN_REQUIRED` (default off).
  - The RT routes read the header, never the body. They pass the token to `RTExportService.export`, `records` and
    `push`, and those pass it to `DICOMwebNotifier(upload_token=…)`.
  - The notifier sends the value, as given, as the STOW-RS `Authorization` header. It uses no credential of its own
    with it, and its log line says `upload token auth`.
  - A token with a username or password is refused (422). So is a value a header cannot carry: a line break, NUL or
    leading space. The HTTP library would otherwise quote it in its error.
  - An archive's refusal that quotes the token keeps `[upload token]` in its place. The original error is not
    chained.
  - With the token required, a push without one is refused (422) before anything is written. This covers the export
    (new or stored), the push route and records with `push`. An export without `push` works as before.
  - A plan job (`/plans`) holds no token, so with the token required it pushes nothing and logs why.
- **Beyond the ADR, recorded in it.** Records with `push` take the token too, and the plan job's push follows
  decision 5. The hook's `objects` are the object kinds the export writes, because it is asked before their UIDs
  exist.
- **Viewer (passlab/radiarch-ohif).**
  - `createClient` takes `uploadTokenHeader`. `exportPlan` and the new `pushExport` take `{ uploadToken }`, and send
    the header only with a token.
  - `exportAndPush` holds the panel's rule:
    - no hook: pushed as before;
    - a token: pushed with it;
    - `null`: written, not sent, with `notSent` saying why;
    - an error: nothing exported.
  - The planning extension's configuration takes `getUploadToken` and `uploadTokenHeader`. The MCO panel's "Export
    and open" uses them.
  - `viewer.ref` moves to that commit, 8666cd4.
- **Tests.**
  - `tests/test_upload_token.py`:
    - the archive gets the token as `Authorization`, and radiarch's own token is not fetched;
    - an export and a stored export pushed again, the push route to another URL, and records each push with their
      token;
    - no file under the artifact directory, no response and no log line holds the token;
    - a token with a username is refused;
    - a refused token is reported as any refused push;
    - with the token required, pushes without one are refused and nothing is written or sent, while an export
      without `push` and records without `push` work;
    - a plan job pushes nothing when the token is required.
  - The fake archive of `tests/test_dicomweb_push_auth.py` can quote the header in a refusal.
  - radiarch-ohif: `libs/radiarch-client/test/upload.test.js`, six tests, in that repository's CI.
  - The browser tests set no hook and are unchanged.
- **Documents.**
  - `docs/PRODUCTION.md`, push section: the header, the two settings and the rules.
  - `docs/viewing.md`: the hook.
  - README: the settings table. `.env.example` also lists the settings.
  - ADR 0018: a pointer.
  - ADR 0020: built, with the additions above.
  - The viewer's README: the hook and the test.
- **Release.** It stays 0.2.0, because no object radiarch writes changes.

## Release 0.3.0 (2026-11-08)

- Release 0.2.0 was stamped at 09c3ebf (2026-10-27). Several features since then changed output, but the release
  was not raised. Among them:
  - the export's marked copies (737d2c5);
  - R11's Pareto sets and deliverable plans;
  - the user as Operators' Name (6a8c717);
  - imported photon plans recomputed through their apertures (72b16a1);
  - the leaf model in aperture doses (412a105);
  - R11.11's second set.
- The project lead decided to raise it now, to 0.3.0: a minor raise, because these are features (`docs/PRODUCTION.md`).
- Objects written by the commits between 09c3ebf and this one state 0.2.0. Their git commit in Software Versions
  tells them apart from 0.2.0's own objects.
- No code changes, only `src/pyproject.toml`. `radiarch.build.release()` reads the installed package's version.

## A repeated request joins the job in flight (2026-11-10)

- **The gap.** Every job route returned the stored result for the same inputs (200) or started a job (202). A second
  request while the first job was still queued or running started the same computation again. It showed on
  `POST /mco/{mco_id}/deliverable`: a viewer reloaded during a deliverable plan started a second one. The same held for
  the geometry, beam-model, dose, influence, optimization, beam-angle, evaluation, protocol, Pareto-set and second-set
  routes.
- **The change.**
  - The job store has `find_active_job(kind, cache_key, max_age_s)`, in memory and in SQL. It returns the newest
    queued or running job of that kind for that cache key. Dose and influence jobs share a table and are told apart by
    their kind. The query uses the indexed `cache_key` column, so the schema does not change.
  - `api/routes/_inflight.py`: `in_flight(kind, cache_key, task)` asks the store, with the task's hard time limit from
    the Celery annotations (the default limit for a task without one) as the maximum age.
  - All ten job routes ask it after the cache and before they create a job. A joined job is answered with `202`, its
    `job_id` and its state. The routes that write audit events write one with state `joined`.
- **Lost jobs.** A job older than its task's hard time limit cannot still be running, so a request starts a new one.
  A job lost sooner (a Redis restart without persistence drops queued tasks) keeps repeated requests waiting until
  that limit. `docs/PRODUCTION.md` says so and asks for Redis with persistence. A worker that dies mid-task needs
  nothing: the task is acknowledged late and rejected on a lost worker, so Redis delivers it again under the same job.
- **Not covered.** Two identical requests that reach two API processes within the same moment can still both start a
  job, because the check and the creation are two store calls. Within one API process they cannot: the routes are
  async and do not await between the check and the creation.
- **Tests.** `tests/test_inflight_jobs.py`, 35 tests:
  - on both stores, for every kind: a queued or running job is found, an ended one is not, and another key is not;
  - a job past the maximum age is not found; the newer of two jobs is; dose and influence jobs are told apart;
  - the deliverable route: a repeat joins the running job and dispatches nothing; another state dispatches; a repeat
    after a failure dispatches a new job;
  - every route module has as many `in_flight` checks as it has job creations.
- **Documents.** `docs/architecture.md` §4.2 (the three answers) and `docs/PRODUCTION.md` (the hard limit bounds a
  join).
- **Release.** It stays 0.3.0, because no object radiarch writes changes.

## Arcs: leaf pairs closed for part of an arc move toward the jaw (2026-11-10)

The parking measured on 2026-11-08 ("Arcs: leaf pairs closed for part of an arc, measured"), the variant that
lengthens no interval.

- **The change.** `services/vmat.py`, `park_closed_runs`, called by `build_arc` after the pairs no control point opens
  are parked:
  - In each run of control points at which a pair is closed, an end next to an open control point stays. An
    interval's aperture is the mean of its two control points, so that end shapes the open interval beside it. An
    end at the arc's first or last control point moves too.
  - Every other point of the run goes as near the park position (`park_position`, 10 mm behind an X jaw) as the
    reach from the fixed ends allows.
  - The reach of an interval is how far a leaf moves in the time the interval takes anyway: its gantry time at the
    top gantry speed, or its largest leaf move as it stands, whichever is longer. So no interval's minimum time
    changes, and no interval's minimum meterset does either.
  - A pair closed for the whole arc still waits under the jaw, unchanged. Without interdigitation there is no park
    position, and nothing moves.
- **Version.** `LEAF_MODEL_VERSION` is 3. Cached arcs, sequences, deliverable plans and protocol runs are made again.
- **Tests.** `tests/test_r8_vmat.py`:
  - The arc test now expects the pair closed in sector 1 under the jaw. It is back where its sweep closed it at the
    control point before the sweep opens it, and it returns to the jaw after its sweep. Every interval's minimum time
    equals the arc built without the move.
  - `park_closed_runs` on its own: the ends stay and the inside goes as far as the reach allows; a two-point run
    between open points and a zero reach move nothing; a run at the arc's start moves its free end; the reach can
    differ per interval.
- **Release 0.3.1.** The arcs' control points change, so the patch number rises (`docs/PRODUCTION.md`); the project
  lead agreed.

## `radiarch plan --objects`; protocol aliases on a 4D CT's phase structures (2026-11-10)

- **`--objects`** on `radiarch plan` and `radiarch batch`. It chooses which RT objects the export writes,
  comma-separated: `rtstruct`, `rtplan`, `rtdose`, `rtimage`. The default is still all four. The command refuses
  an unknown kind, an empty list, and `rtplan` without `rtstruct` (the plan names the structure set written with it),
  before it plans. The CWL tools for both commands take it as an optional input. A host that declares a plan's
  outputs (structure set, plan and dose, no DRRs) can ask for exactly those.
- **Aliases on phase structures.** A 4D CT's structures carry their breathing phase (`Tumor_c30`, the naming of the
  4D lung data). A protocol's aliases matched only whole names, so such a structure was not found.
  - Now, when neither the protocol's name nor any alias matches exactly, a structure named `<name>_c<NN>` (two digits,
    any case) for the name or one of its aliases is taken. The run's alias map records it.
  - When several phases' structures match, the run is refused with their names. A 30 % phase's tumour must not
    become the plan's GTV without anyone saying so. Naming the structure in `structure_aliases` chooses one.
  - `AUTOPLAN_VERSION` is 2, so stored runs are not reused for a geometry the new rule reads differently.
- **Tests.** `tests/test_r10_cli.py`: a plan exported with `--objects rtdose,rtstruct,rtplan` writes RS, RP and RD
  only, and its dose references its plan; the refusals, on both commands. `tests/test_r10_protocols.py`: one phase's
  structure is aliased and recorded; two are refused with their names; an exact name wins; the suffix is two digits.
- **Documents.** README (DICOM RT out); the protocol model's field description.
- **Release.** No object changes for inputs that planned before. Both changes ship in 0.3.1.

## ADR 0021 proposed: stored results scoped by study (2026-11-10)

- Every caller with the API key can read every stored result, and the listing routes and the lineage graph hand
  out ids. ADR 0020 left per-user scoping of results to its own note. This is that note.
- It proposes scoping by study, not by creator. A read is allowed when the host says the user may see every study
  the result traces to. The cache and the job join stay shared, since a result holds nothing its inputs do not
  determine.
- Three points are open for the project lead: how the host answers (an endpoint or a header), what a request
  without a user means, and who sees `requested_by`. No code changed. The plan has an open row in R12.

## The records with arcs rerun from `f3a83c7`; R11 closed (2026-11-10)

From `f3a83c7` (release 0.3.1), an arc moves a pair closed for part of the arc toward an X jaw. Every validation case
that plans arcs runs again from that commit, one case per process on the 96-core server. Each record has a folder
`2026-11-10-arc-pairs-toward-jaw-f3a83c7/`. R9's 4D case is still running and follows with its own entry.

- **R8.** `lung_sbrt_vmat`, `lung_vmat_lctsc` and `hn_sib_vmat` pass every graded check (32, 10 and 12). All three
  move, by at most 1.6. Both lung 60 Gy patients' coverage rises (PTV V60Gy 95.6 → 95.94 and 95.43 → 95.96 %), and
  one patient's cord maximum rises by 0.8 Gy (limit 50.5 Gy). One SBRT patient's D2cm moves from within RTOG 0915's
  limit to its minor deviation (51.65 % against 51.39 %).
- **How much leak the move removes.** The four arcs of the R11 lung case were built again from their sector fluence,
  with the move and without it. The build with it equals the stored arcs. With the same stored metersets, the
  closed pairs' leak falls from 2.4, 5.1, 7.2 and 8.1 % of the arc's open fluence to 1.6, 3.7, 5.5 and 5.9 %, by 23 to
  32 %. Delivery time is unchanged, and no interval falls below its minimum meterset. The script is not in the
  repository.
- **R10.** `protocol_batch_lctsc` passes every graded check (79). `protocol_lung_vmat` fails 6 of its 44: the
  comparisons with the harness case's run that the case's `record` names, from 2026-11-05 (`412a105`). The move
  shifted the harness case itself by more than the 1 % tolerance. The protocol's 18 goal values equal the harness
  case's rerun from the same commit. The fix, which the project lead agreed: `cases/protocol_lung_vmat.yaml` names
  that rerun as its `record`, with the same 1 % tolerance. The case runs again from the commit that makes the change.
- **R11.** `mco_protocol_lung` passes every graded check (38). Only its arcs' deliverable plan, second set and plan on
  that set move. The protocol's arc plan gives the oesophagus 1.0 Gy less and the lungs 0.5 Gy less, at the same
  coverage. The arcs' second set converges in 3 of 11 plans (1 before; error bound 0.89).
- **R11 closed.** The arcs' second set's convergence is recorded as a known limitation (the diagnosis of 2026-11-08
  gives the cause). Every plan of the set meets its limits, none is dominated, the plan made on it is deliverable, and
  the error bound is reported with every set. A second set that converges stays in R11's "Later" row.

## The lung protocol's rerun; R9's 4D case from `f3a83c7` (2026-11-10)

- **The lung protocol.** `protocol_lung_vmat` ran again from `48c0cc4`, whose case names the R8 record's rerun from
  `f3a83c7` as its record. It passes all 44 graded checks. All 18 comparisons with the harness case read a
  difference of 0, and every other value equals the run from `f3a83c7`. The R10 folder
  `2026-11-10-arc-pairs-toward-jaw-f3a83c7/` holds it with the batch, and keeps the first round beside them
  (`results-f3a83c7.json`, `run-summary-f3a83c7.md`).
- **R9's 4D case.** `lung_4d_itv` ran from `f3a83c7` in 8107.6 s, and all 22 graded checks pass. The tumour's D95
  moves by at most 0.07 Gy on any phase, and its accumulated D95 stays above 60.9 Gy. As in the R8 lung case, the
  lungs' V20Gy falls by up to 0.3 percentage points and the cord maximum rises by up to 0.5 Gy. The R9 folder
  `2026-11-10-arc-pairs-toward-jaw-f3a83c7/` holds it, and the R9 README points to it.
- Every record with arcs now has a run from 0.3.1.

## A protocol names every structure the geometry lacks, before planning (2026-11-11)

A user planned the multi-criteria lung protocol on one breathing phase of a 4D CT whose structure set had no lungs. The
run failed at the derivation of `Lungs` with "structure 'Lung_L' not in the geometry". The refusal was right, but
it named one structure, and only after the run had started deriving.

- **The check.** After the aliases, `missing_structures` lists every structure the protocol needs that neither the
  geometry nor an alias gives: a derivation's sources, the main target, an extra objective's structure, and an
  `mco` section's trade-offs, hard constraints and navigation structures. Each of these would fail the run later.
  A goal's structure is not needed: a goal on a structure the patient lacks is reported, not failed.
- **The refusal** names each missing structure once, with what needs it and the aliases tried, then the geometry's
  structures. Example: "'Lung_L' (for the union that makes 'Lungs'; no structure matches it or its aliases LLung,
  Lung_Left, Left_Lung, Lung-Left)".
- Names match without case, as the derivations do. A structure that a derivation makes counts as present for later
  derivations, so one gap is named once.
- No plan changes, and `AUTOPLAN_VERSION` stays 2. The only difference: a run that would have failed now fails
  sooner, with a clearer message.
- **Tests.** In `test_r10_protocols.py`:
  - every gap is named, with nothing derived first;
  - names match without case;
  - a missing target is caught after the derivations;
  - the shipped `demo-lung-imrt-mco` protocol on a phase CT without lungs or cord names both lungs, and the cord as a
    trade-off and a hard constraint.

## Release 0.3.2 (2026-11-11)

- 0.3.2 contains one change since 0.3.1 (`48c0cc4`): `0a00d06`. A protocol run is now refused before planning when the
  geometry lacks a structure the protocol needs, and the refusal names each one. No output changes for inputs that
  planned before.
- **Why raise it.** A deployment that pins radiarch pins a release. Without the raise, two different versions of the
  code (`48c0cc4` and `0a00d06`) would both state 0.3.1.
- **The rule.** `docs/PRODUCTION.md` now says the release is also raised before a deployment takes a change that
  changes no output. It is a patch raise, because the change fixes how a refusal is reported.
- No code changes, only `src/pyproject.toml`.

## Stored results scoped by the studies a user may see (ADR 0021, 2026-11-11)

The project lead decided ADR 0021's three open points as recommended:
- A: the host serves an access endpoint;
- B: a request without a user is refused;
- C: `requested_by` is shown to every user who may see the study.

The ADR is built.

- **The check** (`api/access.py`). It is one dependency on every protected router, so a new route is checked by
  default. Only routes listed in `OPEN_ROUTES` stay open: machines, protocols, goal templates, models, engines,
  workflow templates, the capability statement and job status. With `RADIARCH_ACCESS_URL` set, a request to any
  other route:
  - must name a user (otherwise `401`);
  - may name, in its path or JSON body, only results and studies the host lets that user see. A refused id and an
    unknown one both answer `404 not found`;
  - may name no file on the server (otherwise `422`).
- **A result's studies** (`services/access.py`). The walk follows the lineage graph's parents up to the geometries,
  and takes each geometry's CT study. Arcs, deliverable plans, protocol runs, replanning assessments, uploads and
  legacy artifacts are mapped to their sources by hand. An upload's studies are those its DICOM files name.
  - A result that traces to no study, or to a version that is gone, is read by nobody.
  - Studies are kept once found, since results never change.
- **The host** is asked `GET {url}?user=&study=` with the proxy's secret.
  - Each answer is kept for `RADIARCH_ACCESS_CACHE_S` (60 s).
  - `403` or `404` means no.
  - Any other answer, or none, refuses the request with `503`.
- **Listings** drop what the user may not see: exports by UID, deliverable plans by dose or beam model, legacy plans,
  and the list of what derives from a version. A version's lineage graph holds only what it derives from, whose
  studies are among its own.
- **Unchanged.** The cache and the job join stay shared, and `requested_by` is a record that grants nothing. Without
  the setting, every route behaves as before. No output changes, so the release is not raised now. A deployment
  that takes the change gets a release first (`docs/PRODUCTION.md`).
- **Tests** (`tests/test_access_scope.py`):
  - reads by id, refused and unknown alike;
  - a result that joins two studies;
  - the listings;
  - writes on a refused result or study;
  - the shared cache;
  - no user, a server path, and the open routes;
  - one host call per user and study, and a host that does not answer;
  - every route and request field covered. A new id field must be listed, or the test fails.
- **An independent review** of the first build found ways round it, each reproduced by a test. All are closed:
  - **A body sent without a JSON content type was not checked.** FastAPI parses it as JSON anyway. The check now
    reads the body of every route that takes one, as JSON, whatever the content type says.
  - **Ids were not checked to be ids.** A stored id is joined onto a store's folder, so `../uploads/<id>/g` could
    name a forged record. An id that is not a plain token now names nothing. A state name in a body is held to the
    same rule.
  - **File fields ending in `_uri` were not refused** (a dose, a gamma reference, weights). Every field ending in
    `_uri` or `_path` is now refused. The data root, read by series UID whatever the study, is not read while access
    is checked.
  - **Two kinds of result joined a second study unseen.** An imported RT Plan now adds the study it was written in.
    A gamma comparison now adds its reference dose, which `GammaResult.reference_dose_id` records from now on. An
    evaluation whose dose or gamma reference came from a file, or one made before the reference was recorded, is
    read by nobody.
  - **The host was asked about the user's name cleaned for DICOM**, so `al=ice` had alice's access. It is now asked
    about the header exactly, up to 256 characters.
  - **An outage told known ids from unknown ones.** A host that failed is now taken as down for the cache time, and
    every checked request answers 503.
  - **A body nested 1,500 deep raised a server error.** The body walk is now iterative and stops at 64 levels, and
    the lineage walk fails closed.
  - **The open `POST /sessions` wrote a client's `../` file name outside its folder.** This bug predates the change.
    Sessions now need a user, and the file name is kept to its last part.
  - Smaller fixes: a cycle in the lineage fails closed, the export listing checks every match rather than the
    newest 500, and the host's HTTP client is reused.
- **A second independent review**, of the fixed build, found two more ways round and smaller gaps. All are closed:
  - **An arc plan and its dose traced to their geometry only.** An optimization may use another study's beam
    model, and the arcs' outputs did not trace back to the arcs. Their studies now include the arcs' sources.
  - **One malformed study UID took the check down for every user.** The host answered 400, and that counted as an
    outage for a minute. A study UID that is not one is now refused without asking the host. A host's `4xx`, other
    than `401`, `407`, `408` and `429`, now refuses only the request that asked.
  - **A geometry build's cache hit was returned without a check.** Its study comes from the CT it read, and a build
    from before the check could hold another study's CT. A cache hit is now checked like a read.
  - **Engine and machine names could be paths.** `mcsquare_dir` is now refused, and `bdl`, `scanner` and machine,
    model, template, protocol and workflow ids must be plain names.
  - **Known limits, recorded in the ADR:**
    - an id's existence shows to a caller who already holds it, at a host's first failure or by timing;
    - lineage states name other versions;
    - deletes check only their target;
    - an import's registration is not recorded as a parent;
    - malformed JSON gets `422` before `401`.
- **Tests:** three more in `tests/test_access_scope.py`, for the ways round, the joins and the second review. The coverage test also
  checks query parameters and fields that look like files, URIs or URLs.
- **Docs:** ADR 0021 (decided, as built, with the review), ADR 0020's pointer, README settings, `docs/PRODUCTION.md`
  (section and checklist).

## The reviewing physicist's way in; the plan's stale rows (2026-11-11)

- **`docs/validation/README.md`**, a new page for the physicist who reviews R7 to R11. It gives:
  - an order of reading;
  - per record, the documents to sign at their commit, and the later run that holds each superseded case's current
    numbers;
  - every graded check that fails in those runs, with its reading and where it is explained;
  - the limitations the records state;
  - a table for checking the eight goal templates against their sources;
  - the answers that would change the next work most;
  - how a signature names each run it covers.
- **`docs/impl-plan.md`:**
  - Two rows R9 did were still open: "Recalculate across frames of reference" (R9.6) and "4D robust scenarios"
    (R9.7). They are now ticked.
  - R9.7 moved robust optimization over the breathing phases to a later item, which had no row. It now has an open
    row under R3.
  - The R7 review row points to the new page.

## Four small open items: engine digest, asymmetric margins, relative-seriality NTCP and LQ-L, an import's registration (2026-11-11)

Group A of `docs/reports/open-items-plan.md`. None changes an existing output. Existing requests keep their cache keys:
each new field enters a key only when it is set.

- **The engine build's digest (R12):**
  - `services/dose_engines/digest.py`: SHA-256 over the files a run reads, named and in name order, cached per
    process by path, inode, size, and modification and change times. `engine_digest(name, params)` never fails a
    computation; it gives `null` for an engine without build files, such as the test engine.
  - Each engine has a `digest(params)` method:
    - CCC: the binary and the kernels.
    - MCsquare: the launcher, the binaries, the material database, and the run's beam data library and scanner.
    - `pb`: the kernel table and its description, as the process loaded them (the table is cached per path).
  - Results record it as `engine_digest`: doses, influence matrices, optimizations, beam-angle searches, arc plans,
    Pareto sets, MCO deliverable plans and 4D phase doses.
  - A result computed from cached matrices names the build that made them (`common_digest`), `null` when they differ
    or predate the digest:
    - an optimization, a Pareto set and an MCO deliverable plan: their influence matrices';
    - a beam-angle search: its scoring optimizations';
    - a sequence's segment dose: the open-field matrix it came from;
    - a second Pareto set and its delivered dose: the open-field matrix for static fields, the run's build for arcs.
  - The lineage's attribution, the derivation record and the export manifest carry it. ADR 0013 is updated.
- **Asymmetric margins (R4):**
  - `StructureOperation.directional_mm` gives expand and erode one margin per patient direction: right, left,
    anterior, posterior, superior, inferior. Each is 0 or more; an unknown direction is refused.
  - `structure_ops.expand_directional` and `erode_directional` dilate by the ellipsoid whose half-axis on each side
    is that side's margin, by FFT convolution on the structure's box.
  - With the sides equal in pairs, both give the per-axis result voxel for voxel. The grid's edge is not outside, as
    in `erode`.
  - The SDK's `ops.expand` and `ops.erode` take the directions as keywords. ADR 0010 is updated.
- **Relative-seriality NTCP and LQ-L (R5):**
  - `radiobiology.relative_seriality_ntcp` follows Källman, Ågren and Brahme 1992. The equation is as Adamus-Górka et
    al. (Acta Oncol 2008) print it, checked against an explicit product in the test.
  - It works in logs (ln Pˢ = −s eˣ), so a steep, low-dose voxel whose P is below the float range still counts. It
    also gives the uniform dose over the reference volume with the same NTCP, or `null` when the NTCP is 0 or 1 to
    machine precision.
  - `RelativeSerialityParameters` have an optional `reference_volume_cc`, the volume D50 refers to.
  - One set ships: heart, long-term cardiac mortality. The values are D50 52.3 Gy, γ 1.28 and s 1, from Gagliardi et
    al. 1996 as cited by Schneider et al. 2017, with the whole heart as reference.
  - The spinal-cord sets of Adamus-Górka et al. refer to a length of cord, not the whole structure, so they do not
    ship.
  - `NTCPSpec.relative_seriality` takes explicit parameters. `NTCPResult` gains `model` and `effective_dose_gy`, and
    its `geud_gy` is LKB's only.
  - `EvaluationRequest.lql_transition_gy` applies LQ-L to every EQD2 of the request: above the transition dose per
    fraction, each EQD2 follows the LQ curve's tangent there (Astrahan 2008). It needs the plan's fractions. `eqd2`
    and `bed` take `transition_gy`.
  - `GET /evaluate/models` lists the relative-seriality sets. ADR 0011 is updated.
- **An import's registration (ADR 0021's known limit):**
  - A plan imported through a radiarch registration keeps it as `frame_registration_id`.
  - The lineage names the registration as a parent, so the access check sees its studies.
  - The import's cache key includes the registration only when there is one. A replanned day plan does not inherit
    it.
- **An independent review** of the build found four defects and some smaller points. All are fixed and tested:
  - **Every shipped protocol's digest changed.** A structure step dumped `directional_mm: null`, so repeated protocol
    runs would have planned again instead of reusing their results. The digest now drops an unset one, and the seven
    protocols' digests equal those before the change.
  - **Results named the build running now, not the one that made their cached matrices**: optimizations, Pareto sets,
    MCO deliverable plans and beam-angle searches. A segment dose took the optimization's digest though its matrix
    was built with the default parameters. Each now names the matrices it read.
  - **A proton optimization's export carried no digest.** The export source now carries it.
  - **Smaller points:**
    - the `pb` digest re-read a file that the process had cached;
    - the digest cache missed a same-size replacement that kept the modification time;
    - two files of one name outside the engine folder counted once;
    - relative seriality lost accuracy where P underflows, and could give −0.0 or a meaningless effective dose;
    - LQ-L without fractions changed the key and nothing else;
    - a replanned day plan inherited the import's registration.
  - **Kept as it is:** the FFT of a directional margin needs memory that grows with the margin. It is about as much as
    the distance transform for 5 mm, and about twice for 50 mm.
- **Tests:**
  - `tests/test_engine_digest.py` (new);
  - `test_r12_lineage.py`: a digest from the engine to the export, and from cached matrices;
  - `test_r10_protocols.py`: the protocols' digests; `test_r11_protocol.py`'s reference digest drops the unset field,
    as the digest does;
  - `test_r4_machine_structures.py`: equality with the symmetric margins, the moved sides, a derived geometry's
    direction and the validation;
  - `test_r5_evaluation.py`: LQ-L, relative seriality, the two in an evaluation;
  - `test_r9_registration.py`: the parent.

## The digest cache hashes a recently changed file afresh (2026-11-11)

`tests/test_engine_digest.py::test_files_digest_depends_on_names_and_bytes` failed about two runs in five on the
workstation. It rewrites a file in place with the same size and its old modification time. Within one tick of the
file system's clock, a few milliseconds, the change time does not move either, so the cache returned the old digest.
CI had passed it by chance.

- `files_digest` no longer takes from the cache a file changed in the last two seconds; it hashes it afresh, as git
  does with racily clean entries. Engine files change rarely, so the cache still serves every later run.
- The test now passes every time (eight runs in a row).
