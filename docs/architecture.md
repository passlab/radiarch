# Radiarch design and architecture

State: 2026-10-22 (roadmap items R0–R7 and R14, R15, R2–R6, R12 complete; R8 in
progress). The plan and task status are in [`impl-plan.md`](impl-plan.md), the decisions
in [`adr/`](adr/), the history of each item in [`impl-log.md`](impl-log.md).

**Radiarch is research software and not for clinical use.** Every result, every DICOM
object it writes and `/info` say so.

## 1. What radiarch is

Radiarch is a treatment-planning service for research: a REST API that takes a CT with
its structure set and returns dose, optimized plans, deliverable apertures and arcs,
plan evaluations and the DICOM RT objects a commercial planning system would write. It
aims at **standards fidelity, not vendor fidelity**: the same workflow and objects as a
commercial TPS (patient model → machine → beams → optimization → dose → clinical goals →
DICOM RT), credible physics with a written validation, deliverable-shaped plans on a
stated machine model, and evaluation the way a physicist reads it.

What radiarch does not do: it has no GUI and no viewer (its objects go to Orthanc and are
viewed in OHIF or 3D Slicer); it never approves a plan (approval is recorded through its
state route by the record system, an oncology information system); it is not
commissioned against a real linac, and no plan from it reaches a treatment machine.

## 2. Design principles

1. **Own the core, run the engines as tools.** The data model, DICOM in and out, the plan
   models, the optimizer, evaluation and the writers are radiarch's code. Dose engines sit
   behind one protocol: MCsquare (protons) and the WiscPlan collapsed cone (photons) run as
   separate programs over files; the pencil-beam engine is radiarch's own and runs in process.
   No third-party planning library is imported at run time (ADR 0005, 0008).
2. **Content-addressed, immutable results.** Every service result has a cache key computed
   from its inputs (including the engine's resolved version); identical requests return the
   stored result without recomputation. Results are written atomically and never modified.
3. **Lineage and states.** Every result names its parents (a dose its geometry and beam model,
   a sequence its optimization, an export what it wrote); any version can be traced, attributed
   and given a state (draft, approved, superseded, retired). An approved version and its
   ancestors cannot be deleted (ADR 0013).
4. **No invented numbers.** A missing engine or a failed run fails the job with its error;
   there is no synthetic fallback. The analytic engine exists for tests only and is refused
   outside development.
5. **Standard objects.** Plans and doses go out as DICOM RT Structure Set, RT Plan / RT Ion
   Plan, RT Dose, RT Image (DRR) and treatment records, validated against the DICOM standard
   in CI (ADR 0012).
6. **Evidence for every engine.** A validation harness compares each engine with independent
   references and the commissioning literature and writes one document per engine version
   for review (ADR 0014).

## 3. System context

```
 clients: REST, radiarch.client SDK, demo/ scripts
        |
        v
 +------------------------- radiarch API (FastAPI) --------------------------+
 | /geometry  /beam-model  /dose  /optimize  /bao  /evaluate  /rt  /lineage   |
 | /uploads  /jobs  /artifacts  /sessions  /plans  /workflows  /info          |
 +----------+-------------------------------------------+--------------------+
            | jobs (Celery over Redis)                  | synchronous calls
            v                                           v
 +--------- workers -----------+        +------------ services -------------+
 | queues: dose, optimize,     | -----> | geometry, beam model, dose,       |
 | evaluate, maintenance       |        | optimization, BAO, evaluation,    |
 +-----------------------------+        | apertures, VMAT, RT export,       |
                                        | plan import, lineage              |
                                        +--------+------------------+-------+
                                                 |                  |
                    +----------------------------+                  |
                    v                                               v
 +---------- dose engines (one protocol) ----------+   +---- persistence ----+
 | mcsquare: MCsquare binary (protons)              |   | artifact directory  |
 | ccc: WiscPlan collapsed cone binary (photons)    |   | (content-addressed  |
 | pb: radiarch pencil beam, NumPy/CuPy (photons)   |   | stores), Postgres   |
 | analytic: test only                              |   | (plans, jobs),      |
 +--------------------------------------------------+   | audit log (JSONL)   |
                                                         +---------------------+
 DICOM: Orthanc / any DICOMweb server (QIDO, WADO, STOW) for CT, RTSTRUCT in and RT objects out
```

## 4. Components

### 4.1 API

FastAPI app (`app.py`) with one router per service under `api/routes/` and the prefix
`/api/v1`. A static API key (`X-API-Key`, `RADIARCH_API_KEY`) guards every router except
`/info`; long operations return a job (`202`) that `/…/jobs/{id}` reports; results are read
by id. OpenAPI at `/api/v1/docs`.

| Prefix | What it offers |
|---|---|
| `/geometry` | build a voxel model from a CT and structure set (disk, upload or PACS); derive margins, rings, booleans, density overrides and a couch; read density and masks |
| `/beam-model` | machines (photon and proton); build a beam model (proton spots or photon beamlets from a beam set); import a DICOM RT plan; the craniospinal template |
| `/dose` | engines and their health; compute a dose; build an influence matrix (Dij); recalculate an imported plan |
| `/optimize` | fluence optimization (objectives, constraints, solvers, robust aggregation, warm start, checkpoints); sequence into step-and-shoot apertures; turn sector fluence into VMAT arcs |
| `/bao` | beam-angle search (greedy, top-k) |
| `/evaluate` | DVH, indices, clinical goals with pass/fail, NTCP/TCP, EQD2/BED, gamma, robustness bands; goal templates; comparison of two evaluations (dose impact) |
| `/rt` | export RT objects for a plan, add treatment records, push to a DICOMweb server |
| `/lineage` | a version's graph, descendants, attribution, dataset-manifest derivation record, state and transitions; the capability declaration |
| `/uploads`, `/sessions`, `/artifacts`, `/jobs` | DICOM upload, session scratch space, artifact download, job status |
| `/plans`, `/workflows` | the original one-call workflows (proton basic, optimized, robust; photon open fields), now running on the services |

### 4.2 Jobs

Celery with Redis as broker; queues `dose`, `optimize` (optimization and BAO), `evaluate`
and `maintenance` (store cleanup). Each queue has soft and hard time limits and a rate limit;
workers recycle after a memory or task count (`RADIARCH_*` settings, `docs/PRODUCTION.md`).
Job records live in the job store: Postgres through SQLAlchemy and Alembic when
`RADIARCH_DATABASE_URL` is set, in memory otherwise (tests, local runs). Sequencing,
arcs and RT export run synchronously in the API process.

### 4.3 Services

Each service has one public entry point, a content-addressed store under the artifact
directory and its own result model.

| Service | Module | Store | Does |
|---|---|---|---|
| Geometry | `services/geometry.py`, `geometry_derive.py` | `geometry/` | CT + RTSTRUCT → density (HU model: Schneider, linear, stoichiometric) and structure masks (a bitmask: structures may overlap) on a dose grid; derived geometries |
| Beam model | `services/beam_model.py`, `spot_placement.py`, `photon_beamlets.py`, `plan_import.py`, `plan_templates.py` | `beam_models/` | proton spots per energy layer, photon open fields cut into beamlets; per-beam isocenters and target slabs; imported RT plans with their metersets |
| Dose | `services/dose.py`, `dose_engines/` | `doses/`, `influence/` | dose and Dij through the engine registry; scenarios (setup shifts, range and density scaling, engine-native robust sets); RBE |
| Optimization | `services/optimization.py`, `objectives.py`, `optimization_solvers.py` | `optimization/` | min/max/uniform, DVH and gEUD objectives, constraints, smoothness and total-variation regularizers; L-BFGS-B, Adam, projected gradient; worst-case, expected and CVaR robust aggregation |
| Beam-angle search | `services/bao.py`, `bao_search.py` | `bao/` | greedy and top-k selection on short optimizations |
| Evaluation | `services/evaluation.py`, `dvh.py`, `indices.py`, `clinical_goals.py`, `radiobiology.py`, `gamma.py`, `dose_compare.py`, `sbrt.py` | `evaluation/` | DVH, D/V metrics, CI/HI, clinical goals against templates, NTCP (LKB), TCP (Poisson), EQD2/BED, gEUD, interpolated gamma, dose-impact comparison, SBRT indices (R100, R50, D2cm) |
| Apertures | `services/apertures.py`, `sequencing.py` | `apertures/` | fluence → step-and-shoot segments on a machine (sliding-window decomposition, machine limits, segment metersets re-optimized), deliverability report |
| VMAT | `services/vmat.py` | `vmat/` | sector fluence → arcs (leaf sweeps per sector, control points every 2–4°, gantry/leaf/dose-rate timing per fraction, control-point doses recomputed, metersets re-optimized) |
| RT export | `services/rt_export.py`, `dicom/writers/` | `rt_exports/` | RT Structure Set, RT Plan (static and DYNAMIC arcs) or RT Ion Plan, RT Dose (plan and per beam), DRRs, treatment records; STOW-RS push |
| Lineage | `services/lineage.py` | `lineage/` | graph over every store, attribution, states and their transitions, delete guard |
| Audit | `services/audit.py` | JSONL file | one record per dose or influence build: who, what, how long, cache hit |

### 4.4 Dose engines

Every engine implements the `DoseEnginePlugin` protocol (`dose_engines/protocol.py`):
`validate`, `compute_dose`, `build_influence`, `apply_influence`, `compute_grad`. The
service hands engines loaded bundles (density, masks, plan), never storage ids, and the
registry (`registry.py`) resolves them by name.

| Engine | Modality | How it runs | Data | Notes |
|---|---|---|---|---|
| `mcsquare` (0.3.0) | protons, PBS | MCsquare binary over files, radiarch driver (`mcsquare_driver.py`) | `engines/mcsquare/` (binaries, materials, beam data library, scanner tables) | Monte Carlo dose and sparse Dij; engine-native robust scenario sets (81 / 21 / random); seedable |
| `ccc` (1.1.0) | photons | WiscPlan collapsed-cone binary (GPLv2, separate program) over files (`ccc_driver.py`) | `engines/ccc/` (source, binary rebuilt with scatter parameters, generic 6 MV kernels) | reference-field calibration; shipped scatter truncation (~2 cm) by default, full scatter as an option |
| `pb` (1.1.1) | photons | in process, NumPy or CuPy (`pb.py`) | `engines/pb/` (OpenGATE pencil kernel table) | SVD pencil beam with radiological depth and density-scaled lateral kernels; full-kernel dose, cut-off sampled Dij, per-segment doses for VMAT; the second engine |
| `analytic` | test only | in process | none | toy depth fall-off; refused outside development |

Engines follow IEC 61217 (gantry 90 enters from the patient's left). Absolute photon dose
is 1 cGy per MU at d_max of a 10 × 10 cm field at SSD 100 cm for both photon engines.

### 4.5 Data model

Pydantic models under `models/`; every request computes its cache key, every result carries
the research-use statement.

- **Geometry**: grid (spacing, origin), density and masks on disk, structure index, CT
  provenance (UIDs, patient position), parent geometry and operations for derived ones.
- **Photon plan** (`photon_plan.py`): beams (gantry, couch, isocenter, SAD) with segments
  (jaws, MLC rows, collimator, meterset); beamlets derived from each segment's aperture on a
  regular grid; an arc (`PhotonArc`) is control points (gantry angle, cumulative meterset, jaws,
  leaves) whose segments are its sectors at their mid-angles.
- **Proton plan** (`proton_plan.py`): beams with energy layers, spots and range shifters.
- **Machines** (`machine.py`, `radiarch/machines/*.json`): energies, dose rates, MLC leaf
  boundaries, travel and speed limits, jaws, gantry speed, deliverability thresholds; two
  synthetic linacs (120 and 160 leaves); proton machines from the beam data library.
- **Dose, influence, optimization, evaluation, apertures, VMAT, RT export, lineage**: request
  and result models per service.
- **Goal templates** (`radiarch/goals/*.json`): RTOG 0617, QUANTEC, TG-101 SBRT (3 and 5
  fractions), lung SBRT planning templates (54 Gy / 3, 50 Gy / 5), NCCN head and neck,
  PENTEC pediatric (provisional).

### 4.6 DICOM

`dicom/` reads CT series, RT Structure Sets, RT Plans (static, step-and-shoot, arcs), RT Ion
Plans, RT Dose and spatial registrations; `dicom/writers/` writes every RT object radiarch
produces with stable UIDs, research labelling (RT Plan label suffix `RESEARCH`, approval
status `UNAPPROVED`, a private block naming the engine and machine) and references between
them; `dicom/drr.py` ray-marches DRRs in the IEC beam frame. Adapters connect to Orthanc and
any DICOMweb server and ingest NRRD.

### 4.7 Persistence

```
{RADIARCH_ARTIFACT_DIR}/
  geometry/{id}/            density.nii.gz, masks.nii.gz, meta.json      + _index.json (cache key -> id)
  beam_models/{id}/         plan, fluence elements, meta
  doses/{id}/               dose.nii.gz (+ scenario doses), meta
  influence/{id}/           sparse Dij (CSR), meta
  optimization/{id}/        weights, checkpoints, convergence, meta
  bao/, evaluation/, apertures/, vmat/, rt_exports/   one folder per result
  lineage/                  states and their transitions
  ccc/, mcsquare/           engine calibrations and work files
  uploads/                  DICOM uploads
```

Writes go to a temporary folder and are renamed into place, so a crash never leaves a
half-written result under a valid key. Doses, influence matrices, optimizations, beam-angle
searches and evaluations have size caps: a periodic cleanup evicts the least recently read
entries above the cap and keeps entries younger than a minimum age. The cleanup does not yet
consult the lineage locks, so an approved version can be evicted (an open task of R12; the
delete routes do refuse). Postgres holds plans, jobs and artifact rows.

### 4.8 Validation harness

`validation/` (separate from `tests/` because its runs take minutes to hours and read public
data) holds phantoms, reference tables with citations, case files, Monte Carlo references
(OpenGATE, step-converged), the runner (`python -m radiarch.validation.run`) and the report
(`python -m radiarch.validation.report`), which writes one document per engine version for a
physicist's review. Records live in `docs/validation/`.

## 5. The planning pipeline

```
CT + RTSTRUCT --geometry/build--> geometry --geometry/{id}/derive--> PTV, rings, ...
geometry + beam set --beam-model/build--> beam model (spots or beamlets)
geometry + beam model + engine --dose/influence--> Dij --optimize/run--> weights + dose
   photons, static fields:  --optimize/{id}/sequence--> apertures (step and shoot) + segment dose
   photons, arcs:           --optimize/{id}/arcs--> arcs (control points) + recomputed dose
   protons:                 the spot weights are the plan
dose --evaluate/run--> DVH, goals, NTCP/TCP, indices    --evaluate/compare--> dose impact
plan + dose --rt/export--> RT Structure Set, RT Plan, RT Dose, DRRs (+ records) --push--> DICOMweb
every step --lineage--> graph, attribution, states
existing RT Plan --beam-model/import--> beam model --dose/recalculate--> dose
```

## 6. Conventions

- **Frames.** Patient coordinates are DICOM LPS in millimetres (head-first supine: +x patient
  left, +y posterior, +z superior). Volumes are NumPy arrays in `(z, y, x)` C order; a grid is
  `spacing_mm = (sx, sy, sz)` and `origin_mm` = the centre of voxel `[0, 0, 0]` as `(x, y, z)`.
- **Beams.** IEC 61217: at gantry 0 the beam travels +y with the beam's-eye-view x along +x
  and y along +z; the gantry turns about +z (gantry 90 enters from the patient's left), the
  collimator turns BEV x toward BEV y, the couch turns the beam about +y. Arcs turn CW
  (increasing angles) or CC.
- **Units.** mm, Gy, MU, degrees; proton doses in Gy(RBE) with RBE 1.1 by default.
- **Plans and doses.** Photon beamlet weights are metersets; plan doses are for the whole
  course; delivery limits apply per fraction.
- **Cache keys** include the engine's resolved version, so an engine fix never reuses old doses.

## 7. Deployment

`docker-compose.yml` runs `api`, `worker`, `redis`, `postgres` and `orthanc`; the image
carries the engines under `/app/engines`. All settings are `RADIARCH_*` environment variables
(`config.py`, `.env.example`). `docs/PRODUCTION.md` covers worker sizing, limits, the API key,
the audit log and storage hygiene. The pencil-beam engine uses a GPU through CuPy when
`RADIARCH_PB_DEVICE` is `gpu` or `auto`.

## 8. Quality

- **Tests** (`tests/`, about 880): every service, engine driver and route, goldens frozen from
  the engines' outputs, DICOM conformance of the written objects, the cross-engine gamma.
- **CI**: fast API tests, the full suite with the engine binaries, `dciodvfy` on the written
  objects, a nightly MCsquare consistency check and a nightly fast run of the validation harness.
- **Validation records**: `docs/validation/` (R7 and R8 for review).

## 9. Known limits

- No linac head model: generic 6 MV beams, no output factors from head scatter, no leaf
  transmission or tongue-and-groove in segment doses.
- CCC's shipped scatter truncation: central dose nearly independent of field size, depth dose
  dependent on beamlet size, no dose beyond ~2 cm of the beamlets (ADR 0015).
- The pencil beam's lateral kernel scaling in lung is fitted to two Monte Carlo slabs (2 x 2 and
  10 x 10 cm, within 2 %); photon scatter is not scaled and interface build-up is not modelled.
- VMAT leaf trajectories come from sliding-window sweeps of sector fluence, not from direct
  leaf optimization.
- Store cleanup can evict an approved version (it does not consult the lineage locks yet).
- Not yet built: registration, 4D and replanning (R9); the scripting SDK and planning protocols
  (R10); viewer integration (R13); multi-criteria optimization (R11).

## 10. Repository map

```
src/radiarch/
  app.py, config.py, client.py      the FastAPI app, settings, the Python client
  api/routes/                       one router per service
  services/                         the services; dose_engines/ (protocol, registry, mcsquare, ccc, pb)
  models/                           request and result models, plan models, machines
  dicom/                            readers; writers/ (RT objects); drr.py
  adapters/                         Orthanc, DICOMweb, NRRD
  core/                             job store (SQL / in memory), the /plans workflows
  tasks/                            Celery app and tasks
  validation/                       the validation harness
  goals/, machines/                 goal templates, machine definitions
engines/                            mcsquare/, ccc/, pb/ (engine programs and data)
tests/                              the test suite, goldens, test data
docs/                               this document, the plan and log, ADRs, reports, validation records
demo/                               scripts that exercise each service
```

## 11. Development conventions

**Templates to copy** when adding a service: the request model with `compute_cache_key`
(`models/dose.py`), the store with atomic writes and a cache index (`services/dose_persistence.py`),
the orchestrator (cache lookup → compute → persist, with progress stages; `services/dose.py`), the
routes (API key at router level, 200/202/422/401, audit; `api/routes/dose.py`), the Celery task
(state mirroring, time-limit handling, audit; `tasks/dose_tasks.py`), the tests (model, service,
API, end to end, production: `tests/test_dose_*.py`, `tests/test_api_dose.py`) and a demo
(`demo/show_dose.py`). A new engine implements `dose_engines/protocol.py` (the analytic engine is a
complete small example), registers itself, and gets a harness case and a report document.

**Rules the code follows:**
- Type hints everywhere; Pydantic v2 for API models, dataclasses for engine I/O.
- Docstrings say why, not what.
- Typed engine errors (`EngineParamError`, `EngineRuntimeError`, `EngineUnavailableError`); no
  silent fallbacks.
- `RADIARCH_*` settings in `config.py`; loguru for logs; audit emission never on the critical path.
- Atomic writes: a temporary folder renamed into place, the index updated last.
- Cache keys: SHA-256 of normalized JSON, with the engine's resolved version, without transient fields.
- A change to an engine's physics bumps its `version`.
- Every result and every written object says "not for clinical use".
- Arrays in `(z, y, x)`, positions in patient LPS mm, beams in IEC 61217 (§6).

**A roadmap item is done when** its code and tests are in and the full suite passes; its
physics, where it has any, has a harness case and a report document; an ADR records its decisions;
[`impl-plan.md`](impl-plan.md) checks its tasks and [`impl-log.md`](impl-log.md)
records what it did; README and this document describe what changed.
