# Radiarch TPS Service

[![CI](https://github.com/passlab/radiarch/actions/workflows/ci.yml/badge.svg)](https://github.com/passlab/radiarch/actions/workflows/ci.yml)

Radiarch is a FastAPI-based treatment planning service modeled after the MONAILabel server pattern. It vendors [OpenTPS Core](https://gitlab.com/openmcsquare/opentps) directly for proton/photon dose calculation (MCsquare, CCC) and communicates with PACS providers such as Orthanc over DICOMweb. It ships no viewer: SMIS's own OHIF deployment does the viewing against this API.

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
  demo/                 # CLI demos per service (show_*.py) + compare_engines.py
  src/
    pyproject.toml
    opentps/                # Vendored opentps_core (Apache 2.0)
      ATTRIBUTION.md
      LICENSE
      core/                 # 174 Python files — data, IO, processing, utils
        processing/
          doseCalculation/
            protons/MCsquare/   # MCsquare binaries (Linux SSE4/AVX only)
            photons/            # CCC dose engine
          planOptimization/     # BFGS, FISTA, gradient descent solvers
    radiarch/
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
-e` whenever the vendored OpenTPS tree gains a new subpackage —
modern setuptools' *strict* editable install snapshots the package
list at install time, so old finders can mask freshly added
`__init__.py` files and break imports like
`opentps.core.processing.doseCalculation.protons.MCsquare`. The test
suite's `tests/conftest.py` also prepends `src/` to `sys.path` as a
belt-and-suspenders guard so `pytest` works even if the install is
stale.

Open <http://localhost:8000/api/v1/docs> to inspect the OpenAPI schema.

### About OpenTPS (Vendored)

OpenTPS Core is vendored directly in `src/opentps/` — no separate installation needed. The vendored copy:
- Includes all 174 Python source files from `opentps_core`
- Ships with Linux MCsquare binaries (SSE4 + AVX variants, ~7MB)
- Strips Windows/Mac binaries and pre-compiled `.dll`/`.dylib` files
- Resolves the upstream `numpy>=2.3.2` incompatibility by using the project's own numpy/scipy versions

There is no synthetic fallback. If OpenTPS cannot be imported, or a workflow runner fails, the plan job is recorded as `failed` with the error in its message — Radiarch never returns invented QA numbers. The API-contract tests inject a test-only fake runner (`tests/conftest.py`) instead of running MCsquare.

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

## Testing

The suite has **668 tests** covering the API, client SDK, Services 1–6, OpenTPS core, MCsquare dose calculation, and end-to-end integration. Two are opt-in real-MCsquare legs that skip unless `RADIARCH_RUN_MCSQUARE_VALIDATION=1` is set.

### Test Suite Overview

| Test File | Tests | What It Covers |
|-----------|-------|----------------|
| `tests/opentps/core/test_api_backend.py` | 41 | InMemoryStore CRUD, workflow registry, session helpers, Pydantic models |
| `tests/opentps/core/test_mcsquare_interface.py` | 10 | Patient data loading, contour extraction, DICE, DVH, MCsquare simulation, SPR/WET |
| `tests/opentps/core/test_opentps_core.py` | 10 | CT/RTStruct loading, plan design, MCsquare dose calculation, DVH computation |
| `tests/test_api_e2e.py` | 20 | End-to-end API (plans, jobs, artifacts, sessions, workflows) on the fake runner; runner failure → job failed |
| `tests/test_client.py` | 5 | RadiarchClient Python SDK |
| `tests/test_opentps_integration.py` | 1 | Full OpenTPS pipeline with real MCsquare Monte Carlo |
| `tests/services/`, `tests/test_*_{service,d1,e2e,…}.py` | 581 | Services 1–6 (geometry, beam model, dose engines, optimization, BAO, evaluation), persistence, package layout |

### Running Tests

```bash
source .venv/bin/activate

# Full suite (API + Services 1–6 + MCsquare + OpenTPS core)
python -m pytest tests/ -v

# Fast tests only (API + client, no MCsquare) — ~2 seconds
python -m pytest tests/test_api_e2e.py tests/test_client.py tests/opentps/core/test_api_backend.py -v

# OpenTPS core + MCsquare dose calculation tests
python -m pytest tests/opentps/core/ -v

# Full OpenTPS integration only
python -m pytest tests/test_opentps_integration.py -v
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
components. The vendored OpenTPS Core is © UCLouvain, Apache 2.0, with radiarch's patches and the
vendoring procedure in `src/opentps/ATTRIBUTION.md`. MCsquare is Apache 2.0. The WiscPlan
collapsed-cone photon engine is GPLv2 and is only ever run as a separate program over files.
The direction for the engines and the core is recorded in `docs/adr/0005-own-core-engines-as-tools.md`.
