# Radiarch TPS Service — Architecture Draft

## 1. Purpose
Radiarch provides treatment-planning-as-a-service for OHIF. It mirrors the ergonomics of MONAILabel’s server while replacing MONAI inference tasks with proton/photon planning workflows from OpenTPS. Radiarch exposes a REST API that OHIF (and other clients) can call to:

- Discover available workflows/beam templates
- Submit planning jobs using studies pulled from a PACS (Orthanc via DICOMweb)
- Poll for job status and retrieve resulting RT Plan/Dose artifacts
- Stream QA metrics (DVH, beam stats) back into the viewer

## 2. Reference: MONAILabel Server

See [docs/monailabel_architecture.md](monailabel_architecture.md) for a comprehensive analysis.

Key takeaways from MONAILabel v0.8.5 (`monailabel/app.py`, 13 routers, 781-line `MONAILabelApp` base class):

| Concept | MONAILabel | Radiarch analogue |
|---|---|---|
| App instance | `MONAILabelApp` singleton (5 init hooks) | `RadiarchPlanner` (static, single engine) |
| Datastore | `Datastore` ABC → 5 impls (local, DICOM, DSA, XNAT, CVAT) | `OrthancAdapterBase` → 2 impls (real + mock) |
| Tasks | `InferTask`, `TrainTask`, `Strategy`, `ScoringMethod` | `PlanTask` orchestrating OpenTPS pipelines |
| Routers | 13 routers: `/info`, `/infer`, `/train`, `/activelearning`, etc. | `/info`, `/plans`, `/jobs`, `/artifacts`, `/workflows` |
| Background workers | Internal `AsyncTask` (threading) | Celery with Redis broker |
| Config | Pydantic `BaseSettings` (~50 `MONAI_LABEL_*` vars) | Pydantic `BaseSettings` (`RADIARCH_*` vars) |
| Client lib | `MONAILabelClient` HTTP wrapper | `RadiarchClient` (planned, Phase 6) |
| Auth | Keycloak RBAC (4 roles) | Keycloak RBAC (2 roles, Phase 7) |
| OHIF plugin | `plugins/ohifv3/` (panels, commands, toolbar) | Custom OHIF extension (Phase 6) |

**Design principle:** We reuse MONAILabel's structural patterns (thin routers → central app → pluggable datastore) while replacing ML inference/training with physics-based dose computation. We do *not* adopt dynamic app loading, active learning, or training endpoints since they are annotation-specific.

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

## 5. API Surface

### Implemented (Phases 1–3)

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/info` | GET | ✅ Capabilities, version, available workflows, **models** |
| `/api/v1/workflows` | GET | ✅ Planning templates (Proton IMPT, Photon CCC, etc.) |
| `/api/v1/workflows/{id}` | GET | ✅ Workflow detail with default parameters |
| `/api/v1/plans` | POST | ✅ Submit plan — returns job ID + status |
| `/api/v1/plans` | GET | ✅ List all plans |
| `/api/v1/plans/{id}` | GET | ✅ Plan metadata + job pointer + artifacts |
| `/api/v1/plans/{id}` | DELETE | ✅ Cancel plan, update status |
| `/api/v1/jobs/{id}` | GET | ✅ Status, progress %, messages |
| `/api/v1/artifacts/{id}` | GET | ✅ Download RTPLAN/RTDOSE/DVH |

### Planned (Phase 4+)

| Endpoint | Method | Phase | Purpose |
|---|---|---|---|
| `/api/v1/sessions` | POST | 4 | Upload temp image data for plan preview (mirrors MONAILabel `/session`) |
| `/api/v1/sessions/{id}` | GET / DELETE | 4 | Retrieve or expire session |
| `/api/v1/info` | GET | 4 | Add `models` field listing available engines (MONAILabel-style discovery) |
| `/api/v1/hooks/orthanc` | POST | 5 | Webhook for Orthanc event ingestion |

> **Note:** MONAILabel's `/info` returns `{"models": {...}, "trainers": {...}, "strategies": {...}}` to let clients discover capabilities dynamically. Radiarch's `/info` will adopt the same pattern with `models` listing planning engines.

All endpoints return JSON by default; binary DICOM is either proxied via `/artifacts/...` or saved back into Orthanc (so OHIF simply re-queries DICOMweb).

## 6. Data Flow

1. OHIF selects study + segmentation and POSTs to `/plans`.
2. FastAPI validates request, persists a job record, and enqueues Celery task.
3. Celery worker pulls CT/SEG via Orthanc adapter, converts to OpenTPS objects.
4. Worker configures plan (beams, prescription) and runs dose calc via OpenTPS (MCsquare/CCC).
5. Worker exports RTPLAN + RTDOSE (and optional DVH CSV/JSON), stores them (Orthanc STOW + artifact registry).
6. Worker updates job status; OHIF polls `GET /jobs/{id}` for progress (MONAILabel uses the same polling pattern — no WebSocket needed).
7. OHIF overlays RTDOSE via DICOMweb fetch or direct artifact download.

## 7. Implementation Roadmap

### Phase 1 — Service Scaffolding ✅
FastAPI app, Pydantic config, routers for `/info`, `/plans`, `/jobs`, mock Orthanc adapter, Celery wiring.

### Phase 2 — OpenTPS Integration & Artifacts ✅
Real OpenTPS pipeline (CT import → plan → MCsquare dose calc), RTDOSE DICOM export, DVH computation, artifact registry.

### Phase 3 — E2E Testing & Boot Verification ✅
`GET /workflows`, `DELETE /plans/{id}`, 9-test e2e suite, service boot smoke test, `RADIARCH_FORCE_SYNTHETIC` for fast testing.

---

### Phase 4 — Persistence & Data Layer
- **Postgres persistence** — Replace `InMemoryStore` with SQLAlchemy + Alembic migrations for plans, jobs, artifacts.
- **Real Orthanc adapter** — Wire `OrthancAdapter` with DICOMweb (QIDO-RS search, WADO-RS retrieval, STOW-RS artifact push).
- **Richer `/info` response** — Add `models` field listing available engines (e.g., `{"proton-mcsquare": {...}, "photon-ccc": {...}}`), mirroring MONAILabel's capability discovery pattern.
- **Session endpoint** — `POST /sessions` for temporary image upload + plan preview before commit (inspired by MONAILabel's `/session`).

### Phase 5 — Production Readiness
- **Celery with Redis broker** — Test with `RADIARCH_ENVIRONMENT=production` and real async workers.
- **Job progress polling** — Structured `GET /jobs/{id}` with progress %, stage, ETA. MONAILabel uses polling (not WebSocket), and OHIF clients already understand this pattern.
- **Error handling & retries** — Celery retry policies for transient failures.
- **Orthanc webhook** — `POST /hooks/orthanc` for event-driven study ingestion.

### Phase 6 — OHIF Integration
- **`RadiarchClient` Python library** — Ship a client class (mirrors `MONAILabelClient`) with `create_plan()`, `get_job()`, `get_artifact()` methods to simplify OHIF plugin dev.
- **OHIF v3 extension** — Based on MONAILabel's `plugins/ohifv3/` template. Custom panel for plan submission, dose overlay, DVH display.
- **Multi-beam workflows** — Extend `ProtonPlanDesign` beyond single-beam; implement `photon-ccc` engine.

### Phase 7 — Operations
- **Auth** — Keycloak RBAC with 2 roles: `radiarch-admin` (manage workflows, cancel jobs) and `radiarch-user` (submit plans, view results). Follows MONAILabel's RBAC pattern but simplified.
- **Docker Compose** — FastAPI + Celery worker + Redis + Orthanc + Postgres.
- **Artifact storage** — Optional S3/MinIO backend alongside Orthanc STOW-RS.

## 8. Design Decisions (Resolved)

| Question | Decision | Rationale |
|---|---|---|
| Artifacts: Orthanc-only or also S3? | **Orthanc primary**, S3/MinIO optional (Phase 7) | Keeps DICOM in PACS; S3 for large non-DICOM artifacts |
| Auth: reverse proxy or embedded JWT? | **Keycloak RBAC** (embedded JWT validation) | Same approach as MONAILabel; 2 roles sufficient |
| Multi-tenant? | **Single Orthanc** connector, abstract later | Start simple; `OrthancAdapterBase` ABC allows future expansion |
| Job progress: WebSocket or polling? | **Polling** (`GET /jobs/{id}`) | MONAILabel uses polling; OHIF clients already support it |
| Dynamic app loading? | **No** — static `RadiarchPlanner` | Radiarch has one fixed engine, not a plugin marketplace |

## 9. MONAILabel Alignment Principles

1. **`/info` discovery** — Clients should discover available engines/workflows from `/info` the same way MONAILabel clients discover models.
2. **Thin routers** — All logic lives in `RadiarchPlanner` and the store; routers are pure HTTP translation.
3. **Session-based preview** — Adopt MONAILabel's `/session` pattern for plan preview before commit.
4. **Client library** — Ship `RadiarchClient` so OHIF plugin code stays clean (like `MONAILabelClient`).
5. **Do NOT adopt** — Dynamic app loading, active learning, scoring, training endpoints. These are annotation-specific.

---
*Last updated: 2026-02-17 based on MONAILabel v0.8.5 analysis. See [monailabel_architecture.md](monailabel_architecture.md) for the full reference.*
