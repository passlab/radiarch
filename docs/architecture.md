# Radiarch TPS Service — Architecture Draft

## 1. Purpose
Radiarch provides treatment-planning-as-a-service for OHIF. It mirrors the ergonomics of MONAILabel’s server while replacing MONAI inference tasks with proton/photon planning workflows from OpenTPS. Radiarch exposes a REST API that OHIF (and other clients) can call to:

- Discover available workflows/beam templates
- Submit planning jobs using studies pulled from a PACS (Orthanc via DICOMweb)
- Poll for job status and retrieve resulting RT Plan/Dose artifacts
- Stream QA metrics (DVH, beam stats) back into the viewer

## 2. Reference: MONAILabel Server
Key takeaways from the MONAILabel FastAPI app (`monailabel/app.py` and routers):

| Concept              | MONAILabel                           | Radiarch analogue                           |
|----------------------|--------------------------------------|---------------------------------------------|
| App instance         | `MONAILabelApp` managing infer/train | `RadiarchTPSApp` managing plan/dose ops     |
| Datastore            | Local/DSA/XNAT/DICOMweb adapters     | Orthanc DICOMweb adapter (read/write RT")  |
| Tasks                | `InferTask`, `TrainTask`, etc.       | `PlanTask` orchestrating OpenTPS pipelines  |
| Routers              | `/infer`, `/train`, `/logs`, etc.    | `/plans`, `/jobs`, `/artifacts`, `/info`    |
| Background workers   | ThreadPool/Celery optional           | Celery/RQ for MCsquare/CCC                   |

We reuse the same structural ideas: a central app instance that knows about the datastore, workflows, and job runners, while routers stay thin.

## 3. High-Level Architecture

```
          +-----------------+
          |   OHIF Client   |
          +-----------------+
                  | REST (JSON)
                  v
        +-----------------------+
        |   Radiarch FastAPI    |
        |-----------------------|
        | Routers (plans/jobs)  |
        | Services (PlanMgr)    |
        | Adapters (Orthanc)    |
        | Workers (Celery/RQ)   |
        +-----------------------+
             ^            |
   DICOMweb  |            |  Async tasks
             |            v
      +-------------+  +-------------------+
      |   Orthanc   |  | OpenTPS Executors |
      +-------------+  +-------------------+
```

- **Routers**: implement MONAILabel-style endpoints (`/info`, `/workflows`, `/plans`, `/jobs`, `/artifacts`).
- **Services/core**: orchestrate DICOM import, plan orchestration, job persistence, eventing.
- **Adapters**: talk to Orthanc (DICOMweb QIDO/WADO/STOW) and optionally other PACS.
- **Workers**: execute OpenTPS plans asynchronously to avoid blocking HTTP threads.

## 4. Modules

| Module                        | Responsibility |
|------------------------------|----------------|
| `radiarch.config.settings`   | Pydantic-based configuration (Orthanc URL, DB DSN, worker broker, OpenTPS paths). |
| `radiarch.app`               | FastAPI instantiation, router wiring, lifespan hooks (similar to MONAILabel `app.py`). |
| `radiarch.api.info`          | Health/data about available workflows, beam libraries, environment. |
| `radiarch.api.plans`         | CRUD + submission of plan jobs (POST create, GET list, GET detail, DELETE cancel). |
| `radiarch.api.jobs`          | Job status, logs, progress streaming. |
| `radiarch.api.artifacts`     | Download RTPLAN/RTDOSE/DVH JSON. |
| `radiarch.core.datastore`    | Interface describing `fetch_study`, `fetch_segmentation`, `store_artifact`. First implementation: Orthanc DICOMweb. |
| `radiarch.core.planner`      | Wraps OpenTPS to build CT/ROI objects, configure `ProtonPlanDesign`, run MCsquare/CCC, emit DICOM + QA data. |
| `radiarch.core.tasks`        | Definition of async jobs + Celery task registration. |
| `radiarch.core.models`       | Shared Pydantic models for requests/responses. |
| `radiarch.core.persistence`  | Postgres/SQLite repository for job metadata. |

## 5. API Surface (initial draft)

- `GET /api/v1/info` — capabilities, version, available workflows.
- `GET /api/v1/workflows` — list of supported planning templates (e.g., Proton 3-beam, IMPT). Mirrors MONAILabel `/info` payload but custom schema.
- `POST /api/v1/plans` — submit plan computation. Body includes: study UID, segmentation UID, prescription, workflow id, optional overrides. Returns job id + status.
- `GET /api/v1/plans/{plan_id}` — metadata + job pointer + artifacts produced.
- `GET /api/v1/jobs/{job_id}` — status/progress/log excerpts.
- `GET /api/v1/artifacts/{artifact_id}` — signed download or direct DICOM STOW reference.
- `POST /api/v1/hooks/orthanc` — optional webhook for Orthanc event ingestion (future).

All endpoints return JSON by default; binary DICOM is either proxied via `/artifacts/...` or saved back into Orthanc (so OHIF simply re-queries DICOMweb).

## 6. Data Flow

1. OHIF selects study + segmentation and POSTs to `/plans`.
2. FastAPI validates request, persists a job record, and enqueues Celery task.
3. Celery worker pulls CT/SEG via Orthanc adapter, converts to OpenTPS objects.
4. Worker configures plan (beams, prescription) and runs dose calc via OpenTPS (MCsquare/CCC).
5. Worker exports RTPLAN + RTDOSE (and optional DVH CSV/JSON), stores them (Orthanc STOW + artifact registry).
6. Worker updates job status; OHIF polls `/jobs/{id}` or receives WebSocket push (future).
7. OHIF overlays RTDOSE via DICOMweb fetch or direct artifact download.

## 7. Implementation Priorities

1. Bootstrapped FastAPI app + configuration (#service scaffolding).
2. Pydantic models + routers for `/info`, `/plans`, `/jobs` (mock responses).
3. Orthanc adapter stub + fake data layer to unblock OHIF.
4. Celery wiring + in-process mock job runner.
5. Real OpenTPS integration (CT import, plan builder, RTDOSE export).
6. QA outputs (DVH JSON, plan summary) + artifact storage.

## 8. Open Questions

- Do we keep artifacts only in Orthanc or also expose S3/minio storage? (Default: STOW into Orthanc.)
- Auth: rely on reverse proxy (Keycloak) or embed JWT validation? (Align with OHIF deployment.)
- Multi-tenant: single Orthanc or per-site connectors? (Start with single connector; abstract once needed.)

---
This document will evolve as we flesh out requirements and start implementing.
