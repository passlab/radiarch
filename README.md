# Radiarch TPS Service

Radiarch is a FastAPI-based service that exposes treatment-planning workflows to OHIF using the same ergonomics as MONAILabel. Under the hood it orchestrates OpenTPS (proton/photon planning) and communicates with PACS providers such as Orthanc over DICOMweb.

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
    radiarch/
      app.py            # FastAPI factory
      client.py         # RadiarchClient Python library
      config.py         # Pydantic settings
      api/routes/       # /info, /plans, /jobs, /artifacts, /workflows, /sessions, /simulations
      core/             # Stores, adapters, planner, workflow modules
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
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn radiarch.app:create_app --factory --reload
```

Open <http://localhost:8000/api/v1/docs> to inspect the OpenAPI schema.

### About OpenTPS

OpenTPS 3.0 currently declares a dependency on `numpy>=2.3.2`, which has not been released yet. The planner falls back to synthetic outputs until OpenTPS is installed:

1. Clone <https://gitlab.com/openmcsquare/opentps> and use Python 3.12.
2. Install with `pip install --no-deps /path/to/opentps`.
3. Optionally: `pip install -e .[opentps]`.

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

```bash
cd service

# All tests (synthetic planner, no external deps) — 26 tests
RADIARCH_FORCE_SYNTHETIC=true pytest tests/test_api_e2e.py tests/test_client.py -v

# Full OpenTPS integration (requires MCsquare binary)
pytest tests/test_opentps_integration.py -v
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
