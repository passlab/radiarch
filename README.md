# Radiarch TPS Service

Radiarch is a FastAPI-based service that exposes treatment-planning workflows to OHIF using the same ergonomics as MONAILabel. Under the hood it orchestrates OpenTPS (proton/photon planning) and communicates with PACS providers such as Orthanc over DICOMweb.

## Layout

```
radiarch/
  docs/
    architecture.md   # evolving design document
  service/
    pyproject.toml
    radiarch/
      app.py          # FastAPI factory mirroring MONAILabel structure
      config.py       # Pydantic settings modeled after MONAILabel settings
      api/routes/     # `/info`, `/plans`, `/jobs`, `/artifacts` routers
      core/           # Stores, adapters, planners (in progress)
      models/         # Pydantic request/response models
      tasks/          # Async workers (placeholder)
```

## Getting Started

```bash
cd service
python3.12 -m venv .venv   # OpenTPS requires Python 3.12.x
source .venv/bin/activate
pip install -e .
uvicorn radiarch.app:create_app --factory --reload
```

Open <http://localhost:8000/api/v1/docs> to inspect the OpenAPI schema.

## Next Steps

- Flesh out Orthanc datastore + DICOMweb interactions
- Integrate Celery for asynchronous plan runs
- Wrap OpenTPS planners as reusable tasks
- Persist plans/jobs in Postgres (Alembic migrations)
- Expose DVH, RT Plan/Dose artifacts and push results back to Orthanc
- Align API contracts with MONAILabel clients so OHIF can reuse its plugin patterns
