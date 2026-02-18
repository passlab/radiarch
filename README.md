# Radiarch TPS Service

Radiarch is a FastAPI-based service that exposes treatment-planning workflows to OHIF using the same ergonomics as MONAILabel. Under the hood it orchestrates OpenTPS (proton/photon planning) and communicates with PACS providers such as Orthanc over DICOMweb.

## Layout

```
radiarch/
  Dockerfile            # Multi-stage container build
  docker-compose.yml    # Full stack: API + Worker + Redis + Postgres + Orthanc
  .env.example          # Documented env var template
  ohif-extension/       # OHIF v3 extension scaffold
  service/
    pyproject.toml
    radiarch/
      app.py            # FastAPI factory
      client.py         # RadiarchClient Python library
      config.py         # Pydantic settings
      api/routes/       # /info, /plans, /jobs, /artifacts, /workflows, /sessions
      core/             # Stores, adapters, planners
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

## Testing

```bash
cd service

# All tests (synthetic planner, no external deps)
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

See [`docs/architecture.md`](docs/architecture.md) for the detailed design document including phase roadmap and comparison with MONAILabel.
