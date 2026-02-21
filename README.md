# Radiarch TPS Service

Radiarch is a FastAPI-based treatment planning service for OHIF, modeled after the MONAILabel server pattern. It vendors [OpenTPS Core](https://gitlab.com/openmcsquare/opentps) directly for proton/photon dose calculation (MCsquare, CCC) and communicates with PACS providers such as Orthanc over DICOMweb.

## Layout

```
radiarch/
  Dockerfile            # Multi-stage container build
  docker-compose.yml    # Full stack: API + Worker + Redis + Postgres + Orthanc
  .env.example          # Documented env var template
  demo/
    index.html          # Standalone browser demo (all 4 panels vs. live API)
  ohif-extension/       # OHIF v3 extension (8 commands, 4 panels)
    src/
      index.ts          # Extension entry point
      commandsModule.js # 8 commands bridging UI → API
      services/
        RadiarchClient.js   # HTTP client (axios)
      panels/
        PlanSubmissionPanel.js  # Workflow selection, Rx, objectives
        DVHPanel.js             # Dose-volume histogram (SVG)
        DoseOverlayPanel.js     # Opacity, colormap, isodose lines
        SimulationPanel.js      # Delivery simulation (4D dose)
  service/
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
      api/routes/       # /info, /plans, /jobs, /artifacts, /workflows, /sessions, /simulations
      core/
        planner.py      # Orchestrator — dispatches to workflow modules
        simulator.py    # 4D delivery simulation engine
        store.py        # InMemoryStore + SQLAlchemy persistence
        workflows/      # proton_basic, proton_robust, proton_optimized, photon_ccc
      models/           # Pydantic request/response models
      tasks/            # Celery workers (plan execution)
```

## Quick Start — Docker Compose

The fastest way to run the entire stack:

```bash
cp .env.example .env        # Edit as needed
docker compose up -d        # Starts all 5 services
curl http://localhost:8000/api/v1/info
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
cd service
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn radiarch.app:create_app --factory --reload
```

Open <http://localhost:8000/api/v1/docs> to inspect the OpenAPI schema.

### About OpenTPS (Vendored)

OpenTPS Core is vendored directly in `service/opentps/` — no separate installation needed. The vendored copy:
- Includes all 174 Python source files from `opentps_core`
- Ships with Linux MCsquare binaries (SSE4 + AVX variants, ~7MB)
- Strips Windows/Mac binaries and pre-compiled `.dll`/`.dylib` files
- Resolves the upstream `numpy>=2.3.2` incompatibility by using the project's own numpy/scipy versions

When `RADIARCH_FORCE_SYNTHETIC=true`, the planner uses fast synthetic outputs (instant, no MCsquare needed). Set it to `false` (default) to run real Monte Carlo dose calculations.

## Configuration

All settings use `RADIARCH_` prefix. Place them in `.env` or export as env vars. See [`.env.example`](.env.example) for the full list.

| Variable | Default | Description |
|---|---|---|
| `RADIARCH_ENVIRONMENT` | `dev` | `dev` = Celery eager mode; `production` = async workers |
| `RADIARCH_FORCE_SYNTHETIC` | `false` | `true` bypasses MCsquare, uses fast synthetic planner |
| `RADIARCH_DATABASE_URL` | `""` | Empty = InMemoryStore; `postgresql+psycopg://...` for persistence |
| `RADIARCH_ORTHANC_USE_MOCK` | `true` | `true` = in-memory fake; `false` = real Orthanc |
| `RADIARCH_ORTHANC_BASE_URL` | `http://localhost:8042` | Orthanc REST/DICOMweb URL |
| `RADIARCH_BROKER_URL` | `redis://localhost:6379/0` | Celery broker (Redis) |
| `RADIARCH_DICOMWEB_URL` | `""` | DICOMweb STOW-RS URL for artifact push; empty = disabled |

## OHIF v3 Extension

The `ohif-extension/` directory contains a complete OHIF Viewer v3 extension that connects to the Radiarch API. It provides:

| Panel | Description |
|---|---|
| **Plan Submission** | Dynamic workflow selection, prescription dose, beam/fraction config, dose objectives editor, robustness settings |
| **DVH** | Interactive dose-volume histogram rendered as inline SVG with dose statistics cards |
| **Dose Overlay** | Controls for dose visibility, opacity, colormap selection, and isodose line toggles |
| **Simulation** | 4D delivery simulation with motion amplitude, period, and fractionation parameters |

### Standalone Demo

A self-contained browser demo (`demo/index.html`) exercises all 4 panels against the live API without needing OHIF:

```bash
# 1. Start the API in synthetic mode (no OpenTPS needed)
cd service && source .venv/bin/activate
RADIARCH_FORCE_SYNTHETIC=true RADIARCH_DATABASE_URL="" RADIARCH_BROKER_URL="" \
  python3 -m uvicorn radiarch.app:create_app --factory --port 8000

# 2. Open the demo page in your browser
open demo/index.html
# Click "Connect", then "Submit Plan" → observe QA summary + DVH chart
# Enter the plan ID into the Simulation panel → "Run Simulation"
```

### Installing in OHIF

```bash
cd ohif-extension
npm install
# Then register in your OHIF config — see ohif-extension/README.md for details
```

## Testing

The project includes **92 tests** covering the API, client SDK, OpenTPS core, MCsquare dose calculation, and end-to-end integration.

### Test Suite Overview

| Test File | Tests | What It Covers |
|-----------|-------|----------------|
| `tests/opentps/core/test_api_backend.py` | 48 | InMemoryStore CRUD, workflow registry, delivery simulator, session helpers, Pydantic models |
| `tests/opentps/core/test_mcsquare_interface.py` | 8 | Patient data loading, contour extraction, DICE, DVH, MCsquare simulation, SPR/WET |
| `tests/opentps/core/test_opentps_core.py` | 9 | CT/RTStruct loading, plan design, MCsquare dose calculation, DVH computation |
| `tests/test_api_e2e.py` | 21 | End-to-end API (plans, jobs, artifacts, sessions, workflows, simulations) |
| `tests/test_client.py` | 5 | RadiarchClient Python SDK |
| `tests/test_opentps_integration.py` | 1 | Full OpenTPS pipeline with real MCsquare Monte Carlo |

### Running Tests

```bash
source .venv/bin/activate

# All 92 tests (API + MCsquare + OpenTPS core)
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

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the detailed design document and [`docs/radiarch_project_report.md`](docs/radiarch_project_report.md) for the full project report including phase roadmap, testing strategy, and comparison with MONAILabel.

## License & Attribution

Radiarch is developed by the Radiarch Team. The vendored OpenTPS Core is © UCLouvain, licensed under Apache 2.0. See `service/opentps/ATTRIBUTION.md` for full citation and modification details.
