# Radiarch TPS Service

[![CI](https://github.com/passlab/radiarch/actions/workflows/ci.yml/badge.svg)](https://github.com/passlab/radiarch/actions/workflows/ci.yml)

Radiarch is a FastAPI-based research treatment-planning service modeled after the MONAILabel server pattern. Its core (DICOM in, contour rasterization, calibration, spot and beamlet placement, optimization, evaluation) is its own; dose comes from two engines run as separate programs over files, [MCsquare](https://gitlab.com/openmcsquare/MCsquare) for protons and the WiscPlan collapsed-cone engine for photons (`engines/`). It communicates with PACS providers such as Orthanc over DICOMweb and ships no viewer: SMIS's own OHIF deployment does the viewing against this API.

## Intended use

**Research use only. Not for clinical use.** Radiarch is a research treatment-planning
system: its plans, doses and evaluations must never be used to treat patients. Every
result the API returns carries a `disclaimer` field with that statement, `/api/v1/info`
reports it as `intended_use`, and every DICOM object radiarch writes carries
`NOT FOR CLINICAL USE` in its description, comment and a private `RADIARCH` block.
The dose engines are research engines with no site commissioning; see
`docs/REAL_DATA_VALIDATION.md` for what has and has not been checked.

## Layout

```
radiarch/
  Dockerfile            # Multi-stage container build
  docker-compose.yml    # Full stack: API + Worker + Redis + Postgres + Orthanc
  .env.example          # Documented env var template
  demo/                 # CLI demos per service (show_*.py) + compare_engines.py; walkthrough in docs/demo.md
  engines/              # Dose engine assets run as subprocesses (engines/README.md)
    mcsquare/           # MCsquare launcher + Linux binaries, Materials/, BDL/, Scanners/ (Apache 2.0)
    ccc/                # WiscPlan collapsed-cone engine + kernels (GPLv2, subprocess only)
  tests/data/           # SimpleFantomWithStruct: the bundled CT + structure set
  src/
    pyproject.toml
    radiarch/
      dicom/            # CT, RT Structure Set, RT Plan, RT Dose, registration readers (pydicom)
      app.py            # FastAPI factory
      client.py         # RadiarchClient Python library
      config.py         # Pydantic settings
      api/routes/       # /info, /workflows, /plans, /jobs, /artifacts, /sessions, /uploads,
                        # /geometry, /beam-model, /dose, /optimize, /bao, /evaluate
      core/
        planner.py      # Orchestrator — dispatches to workflow modules (no fallback)
        store.py        # InMemoryStore + SQLAlchemy persistence
        workflows/      # proton_basic, proton_robust, proton_optimized, photon_ccc
      models/           # Pydantic request/response models
      services/         # Services 1–6: geometry, beam_model, dose (+ dose_engines/),
                        # optimization, bao, evaluation
      tasks/            # Celery workers (plan execution + per-service tasks)
```

## Quick Start — Docker Compose

The fastest way to run the entire stack:

```bash
cp .env.example .env        # Edit as needed
docker compose up -d        # Starts all 5 services
curl http://localhost:8000/api/v1/info
```

### Smoke test (recommended)

After the stack is up, run an end-to-end API smoke test (plan → job → artifacts):

```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh
```

To target a different API base URL:

```bash
API_BASE_URL="http://127.0.0.1:8000/api/v1" ./scripts/smoke_test.sh
```

| Service | Port | Description |
|---|---|---|
| `api` | 8000 | Radiarch FastAPI server |
| `worker` | — | Celery worker (plan execution) |
| `redis` | 6379 | Celery broker + result backend |
| `postgres` | 5432 | Persistent data store |
| `orthanc` | 8042 | DICOM server (Web UI + DICOMweb) |

Stop everything: `docker compose down` (add `-v` to remove volumes).

## Quick Start — Local Development

```bash
python3 -m venv src/.venv
source src/.venv/bin/activate
./scripts/install-dev.sh         # editable install + sanity check
uvicorn radiarch.app:create_app --factory --reload
```

The `install-dev.sh` helper purges stale build artifacts before
calling `pip install -e ./src`. Use it instead of a bare `pip install
-e` whenever `src/radiarch` gains a new subpackage — modern setuptools'
*strict* editable install snapshots the package list at install time,
so old finders can mask freshly added `__init__.py` files. The test
suite's `tests/conftest.py` also prepends `src/` to `sys.path` as a
belt-and-suspenders guard so `pytest` works even if the install is
stale.

Open <http://localhost:8000/api/v1/docs> to inspect the OpenAPI schema.

### Engines

The dose engines are data, not Python: `engines/mcsquare` (launcher, Linux binaries
for SSE4/AVX/AVX2/AVX-512, material database, beam data library, scanner
calibrations) and `engines/ccc` (the WiscPlan collapsed-cone engine, its kernels and
LINAC data). `scripts/fetch-engines.sh <tag>` refreshes them from the OpenTPS
repository, which packages both; see `engines/README.md`.

There is no synthetic fallback. If an engine is missing, or a workflow runner fails, the plan job is recorded as `failed` with the error in its message — Radiarch never returns invented QA numbers. The API-contract tests inject a test-only fake runner (`tests/conftest.py`) instead of running an engine.

## Configuration

All settings use `RADIARCH_` prefix. Place them in `.env` or export as env vars.

| Template | Use case |
|---|---|
| [`.env.example`](.env.example) | Docker Compose / production |
| [`.env.dev`](.env.dev) | Local development / demo (no Docker needed) |

| Variable | Default | Description |
|---|---|---|
| `RADIARCH_ENVIRONMENT` | `dev` | `dev` = Celery eager mode; `production` = async workers |
| `RADIARCH_DATABASE_URL` | `""` | Empty = InMemoryStore; `postgresql+psycopg://...` for persistence |
| `RADIARCH_ORTHANC_USE_MOCK` | `true` | `true` = in-memory fake; `false` = real Orthanc |
| `RADIARCH_ORTHANC_BASE_URL` | `http://localhost:8042` | Orthanc REST/DICOMweb URL |
| `RADIARCH_BROKER_URL` | `redis://localhost:6379/0` | Celery broker (Redis) |
| `RADIARCH_DICOMWEB_URL` | `""` | DICOMweb STOW-RS URL for artifact push; empty = disabled |
| `RADIARCH_API_KEY` | `""` | `X-API-Key` required on every `/api/v1` route except `/info`; empty disables auth (dev only) |
| `RADIARCH_ALLOW_TEST_ENGINES` | unset | Permit the test-only `analytic` engine (wrong physics by design). Unset = only when `RADIARCH_ENVIRONMENT=dev` |
| `RADIARCH_DATA_ROOT` | `""` | DICOM (CT + RTSTRUCT) directory read when no upload or PACS study is given; empty = the bundled `tests/data/SimpleFantomWithStruct` |
| `RADIARCH_MCSQUARE_DIR`, `RADIARCH_CCC_ENGINE_DIR` | `engines/…` | Engine asset directories |

## Dose engines

Proton dose comes from **MCsquare** (Apache-2.0) and photon dose from the **WiscPlan collapsed-cone**
binary (GPLv2), both run as separate processes on files radiarch writes through its own drivers
(`services/dose_engines/mcsquare_driver.py`, `services/dose_engines/ccc_driver.py`; ADR 0005,
0006). Engine assets are read from `RADIARCH_MCSQUARE_DIR` / `RADIARCH_CCC_ENGINE_DIR`,
defaulting to `engines/`. `RADIARCH_MCSQUARE_SEED` with `RADIARCH_MCSQUARE_N_THREADS=1` makes a proton run
reproducible bit for bit. Doses and influence matrices are in radiarch's `(z, y, x)` C-order frame.

## Robust protons, Gy(RBE), craniospinal fields

Scenario sets can be explicit (one engine run per scenario) or **engine-native**
(`engine_native` on a scenario set or on the optimizer's robustness spec): MCsquare then
samples the set itself in one run — `ALL` (81), `REDUCED_SET` (21) or `RANDOM` (n) scenarios
of systematic setup, per-fraction random setup and range errors — and every scenario comes
back labelled with the errors applied. Proton doses, influence matrices and optimized doses
are in **Gy(RBE)** with RBE 1.1 unless `rbe` is set (results carry `rbe_factor` and
`dose_units`). An evaluation of a dose with scenarios reports DVH bands, per-scenario DVH
metrics with their envelope, and worst-case target goals. Beams may carry their own
isocenter and a target z slab; `POST /beam-model/templates/craniospinal` builds the
posterior fields of a craniospinal plan with overlapping junctions, optionally a
posterior-oblique pair for the brain (ADR 0009).

## Machines, structures, apertures

Photon machines are data (`radiarch/machines/`, `GET /beam-model/machines`): leaf boundaries,
travel limits, speeds, dose rates and deliverability thresholds; two synthetic linacs ship,
custom ones live in `RADIARCH_BEAM_LIBRARY_DIR/<id>/machine.json`. Structures overlap freely
(a bitmask volume). `POST /geometry/{id}/derive` makes PTVs, rings, booleans, density
overrides and a couch slab from an existing geometry. `POST /optimize/{id}/sequence` turns a
photon optimization into step-and-shoot MLC apertures with re-optimized segment MU and a
deliverability report (ADR 0010).

## DICOM RT in

`radiarch.dicom` reads RT Plan and RT Ion Plan objects into the plan models, RT Dose objects onto
the `(z, y, x)` grid, and registration objects (ADR 0007). A plan becomes a beam model with its own
metersets, and its dose is recomputed with the ordinary pipeline:

```bash
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"geometry_id": "<id>", "path": "/data/plans/RTPLAN.dcm"}' $API/beam-model/import
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"geometry_id": "<id>", "beam_model_id": "<imported id>", "engine": {"name": "mcsquare"}}' $API/dose/recalculate
```

The plan's frame of reference must be the geometry's (a plan from another CT needs a registration,
roadmap R9). Arcs are discretized per control-point interval at the mid-angle.

## Validation harness

`src/radiarch/validation/` holds the physics and cross-check cases that go beyond unit
tests (roadmap R7a; see the SMIS report *Radiarch validation data and test plan*):

```bash
python -m radiarch.validation.run --list                  # the cases
python -m radiarch.validation.run --all --fast            # smoke run: coarser grids, fewer primaries
python -m radiarch.validation.run --cases photon_pdd_10x10 photon_profile_10x10
python -m radiarch.validation.goldens --capture           # refreeze tests/golden (only when a change is intended)
```

Cases compare radiarch against reference tables with citations (`validation/references/`:
6 MV representative beam data, proton ranges, TG-119 goals, the MPPG 5.a/5.b, TG-218 and
TECDOC-1583 tolerance sets) and against independent tools (dicompyler-core for DVHs;
pymedphys for gamma, run through `uv run --python 3.12` because it needs Python < 3.13).
Cases on public data expect `../data/public/{lctsc,pancreatic-ct-cbct-seg,tg119}` from the
SMIS repo (`make public-lctsc-validation public-pancreatic-validation public-tg119` there) or
`RADIARCH_VALIDATION_DATA`. A run writes `validation/results/<stamp>-<commit>/summary.md`.
Statuses are research targets; nothing here is a clinical commissioning.

`tests/golden/` freezes the outputs captured from the vendored OpenTPS code before it was
replaced (CCC beamlet matrix, SimpleFantom geometry, proton spots, the MCsquare input files);
radiarch's own loaders, rasterizer, spot placement and drivers reproduce them on every push
(`tests/test_goldens.py`; ADR 0008).

## Testing

The suite covers the API, client SDK, the DICOM readers, Services 1–6, the engine drivers,
the legacy workflows and the regression goldens. Two are opt-in real-MCsquare legs that skip
unless `RADIARCH_RUN_MCSQUARE_VALIDATION=1` is set.

### Test Suite Overview

| Test File | What It Covers |
|-----------|----------------|
| `tests/test_api_backend.py` | InMemoryStore CRUD, workflow registry, session helpers, Pydantic models |
| `tests/test_api_e2e.py` | End-to-end API (plans, jobs, artifacts, sessions, workflows) on the fake runner; runner failure → job failed |
| `tests/test_client.py` | RadiarchClient Python SDK |
| `tests/test_dicom_readers.py`, `tests/test_plan_import.py` | RT Plan / Ion Plan / Dose / registration readers, plan import and recalculation |
| `tests/test_goldens.py`, `tests/test_engine_assets.py` | Regression goldens; the engine asset layout |
| `tests/test_mcsquare_driver.py`, `tests/test_ccc_engine.py` | The two engine drivers against the real binaries |
| `tests/services/`, `tests/test_*_{service,d1,e2e,…}.py` | Services 1–6 (geometry, beam model, spot placement, dose engines, optimization, BAO, evaluation), persistence |

### Running Tests

```bash
source .venv/bin/activate

# Full suite
python -m pytest tests/ -v

# Fast tests only (API + client, no engine) — ~2 seconds
python -m pytest tests/test_api_e2e.py tests/test_client.py tests/test_api_backend.py -v

# Engine drivers and goldens only
python -m pytest tests/test_mcsquare_driver.py tests/test_ccc_engine.py tests/test_goldens.py -v
```

## Python Client Library

```python
from radiarch.client import RadiarchClient

client = RadiarchClient("http://localhost:8000/api/v1")
info = client.info()
plan = client.create_plan(
    study_instance_uid="1.2.3.4",
    prescription_gy=2.0,
    beam_count=3,
)
job = client.poll_job(plan["job_id"], timeout=300)
```

## Optimization Service (`/api/v1/optimize`)

Service 4 solves the inverse-planning problem: given a built geometry, beam
model, and dose engine, find the fluence-element weights `w*` minimizing a
composite objective. It is engine-agnostic — the only engine interaction during
the solver loop is the `Dij·w` matvec — and content-addressable, so identical
requests reuse the cached result.

| Method & path | Purpose |
|---|---|
| `POST /api/v1/optimize/run` | Run (200 cache hit / 202 async dispatch / 422 / 401). |
| `GET /api/v1/optimize/jobs/{job_id}` | Poll an async run. |
| `GET /api/v1/optimize/{opt_id}` | Retrieve the `OptimizationResult`. |
| `GET /api/v1/optimize/{opt_id}/weights` | Stream the optimal weights (`.npy`). |
| `GET /api/v1/optimize/{opt_id}/checkpoints` | List checkpoint snapshots. |
| `DELETE /api/v1/optimize/{opt_id}` | Drop from cache. |

**Objectives:** `DMin`, `DMax`, `DUniform`, `DVHMin`, `DVHMax`, `EUD`, plus hard
constraints and fluence-smoothness / total-variation regularizers.
**Solvers:** `L-BFGS-B` (default), `Adam`, `ProjectedGradient` — see
[`docs/adr/0002-optimization-solver-choice.md`](docs/adr/0002-optimization-solver-choice.md).
**Robust optimization:** scenario aggregation `WORST_CASE` / `EXPECTED` / `CVaR`.

```bash
# End-to-end demo on the bundled SimpleFantom (analytic engine, no MCsquare):
python demo/show_optimization.py
python demo/show_optimization.py --objectives ptv_dmin=60,oar_dmax=20
python demo/show_optimization.py --robust 9 --aggregation WORST_CASE
python demo/show_optimization.py --solver Adam --max-iters 500 --show
```

See `docs/PRODUCTION.md` → "Optimization Service" for worker sizing and settings.

## BAO Service (`/api/v1/bao`)

Service 5 (Beam Angle Optimization) selects which beam directions a plan should
use, *before* fluence optimization. It sits on top of Service 4: each candidate
angle set is scored by building a beam model for it and running a short fluence
optimization — the achieved composite cost is the score (lower is better) — then
a search strategy selects the best `n_beams`.

| Method & path | Purpose |
|---|---|
| `POST /api/v1/bao/run` | Run (200 cache hit / 202 async / 422 / 401). |
| `GET /api/v1/bao/jobs/{job_id}` | Poll an async run. |
| `GET /api/v1/bao/{bao_id}` | Retrieve the `BAOResult` (selected angles + scores). |
| `DELETE /api/v1/bao/{bao_id}` | Drop from cache. |

**Search strategies:** `greedy` (forward selection, captures beam interplay) and
`top_k` (rank candidates individually) — see
[`docs/adr/0003-bao-search-strategy.md`](docs/adr/0003-bao-search-strategy.md).

```bash
python demo/show_bao.py --n-beams 3 --angle-step 45 --search greedy
```

## Evaluation Service (`/api/v1/evaluate`)

Service 6 is the read-only end of the pipeline: it turns a computed dose volume
(from Service 3 or the final dose of Service 4) plus the geometry's structure
masks into a clinician report — per-structure DVHs, target plan-quality indices
(Paddick conformity, ICRU-83 homogeneity, coverage), and an optional gamma
comparison against a reference dose.

| Method & path | Purpose |
|---|---|
| `POST /api/v1/evaluate/run` | Run (200 cache hit / 202 async / 422 / 401). |
| `GET /api/v1/evaluate/jobs/{job_id}` | Poll an async run. |
| `GET /api/v1/evaluate/{evaluation_id}` | Retrieve the report. |
| `DELETE /api/v1/evaluate/{evaluation_id}` | Drop from cache. |

Metrics and their definitions are documented in
[`docs/adr/0004-evaluation-metrics.md`](docs/adr/0004-evaluation-metrics.md).

```bash
python demo/show_evaluation.py --prescription 20 --gamma --show
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the detailed design document and [`docs/radiarch_project_report.md`](docs/radiarch_project_report.md) for the full project report including phase roadmap, testing strategy, and comparison with MONAILabel.

## License & Attribution

Radiarch is licensed under the Apache License 2.0 (`LICENSE`); `NOTICE` lists the third-party
components. MCsquare is Apache 2.0. The WiscPlan collapsed-cone photon engine is GPLv2 and is
only ever run as a separate program over files. Parts of radiarch's core (the contour
rasterizer, the CT calibration, the spot placement, the engine file protocols) are ports of
OpenTPS core (© UCLouvain, Apache 2.0) and say so in their module docstrings. The direction
for the engines and the core is recorded in `docs/adr/0005-own-core-engines-as-tools.md` and
its completion in `docs/adr/0008-own-core-complete.md`.
