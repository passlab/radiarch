# Radiarch TPS Service — Architecture Draft

## 1. Purpose
Radiarch provides treatment-planning-as-a-service for OHIF. It mirrors the ergonomics of MONAILabel's server while replacing MONAI inference tasks with proton/photon planning workflows powered by a vendored copy of [OpenTPS Core](https://gitlab.com/openmcsquare/opentps). Radiarch exposes a REST API that OHIF (and other clients) can call to:

- Discover available workflows/beam templates
- Submit planning jobs using studies pulled from a PACS (Orthanc via DICOMweb)
- Poll for job status and retrieve resulting RT Plan/Dose artifacts
- Stream QA metrics (DVH, beam stats) back into the viewer

## 2. Reference: MONAILabel Server

See [docs/monailabel_architecture.md](monailabel_architecture.md) for a comprehensive analysis.

Key takeaways from MONAILabel v0.8.5 (`monailabel/app.py`, 13 routers, 781-line `MONAILabelApp` base class):

| Concept | MONAILabel | Radiarch analogue |
|---|---|---|
| App instance | `MONAILabelApp` singleton (5 init hooks) | `RadiarchPlanner` → per-workflow modules |
| Datastore | `Datastore` ABC → 5 impls (local, DICOM, DSA, XNAT, CVAT) | `OrthancAdapterBase` → 2 impls (real + mock) |
| Tasks | `InferTask`, `TrainTask`, `Strategy`, `ScoringMethod` | `PlanTask` orchestrating OpenTPS pipelines |
| Routers | 13 routers: `/info`, `/infer`, `/train`, `/activelearning`, etc. | `/info`, `/plans`, `/jobs`, `/artifacts`, `/workflows` |
| Background workers | Internal `AsyncTask` (threading) | Celery with Redis broker |
| Config | Pydantic `BaseSettings` (~50 `MONAI_LABEL_*` vars) | Pydantic `BaseSettings` (`RADIARCH_*` vars) |
| Client lib | `MONAILabelClient` HTTP wrapper | `RadiarchClient` ✅ |
| Auth | Keycloak RBAC (4 roles) | Keycloak RBAC (2 roles, Phase 7) |
| OHIF plugin | `plugins/ohifv3/` (panels, commands, toolbar) | Custom OHIF extension (Phase 6) |

**Design principle:** We reuse MONAILabel's structural patterns (thin routers → central app → pluggable datastore) while replacing ML inference/training with physics-based dose computation. We do *not* adopt dynamic app loading, active learning, or training endpoints since they are annotation-specific.

## 3. High-Level Architecture

```
          +-----------------+
          |   OHIF Client   |
          | (4 panels, 8    |
          |  commands)       |
          +-----------------+
                  | REST (JSON)
                  v
        +-----------------------+
        |   Radiarch FastAPI    |
        |-----------------------|
        | Routers               |
        |   plans, workflows,   |
        |   sessions, sims      |
        | RadiarchPlanner        |
        |   → workflow modules  |
        | RadiarchSimulator      |
        | Adapters (Orthanc)    |
        | Workers (Celery)      |
        +-----------------------+
             ^            |
   DICOMweb  |            |  Async tasks
             |            v
      +-------------+  +---------------------------+
      |   Orthanc   |  | Vendored OpenTPS Core     |
      +-------------+  | MCsquare (proton MC)      |
                       | CCC (photon convolution)  |
                       | Plan optimization (BFGS,  |
                       |   FISTA, gradient descent) |
                       +---------------------------+
```

- **Routers**: implement MONAILabel-style endpoints (`/info`, `/workflows`, `/plans`, `/jobs`, `/artifacts`).
- **Services/core**: orchestrate DICOM import, plan orchestration, job persistence, eventing.
- **Adapters**: talk to Orthanc (DICOMweb QIDO/WADO/STOW) and optionally other PACS.
- **Workers**: execute OpenTPS plans asynchronously to avoid blocking HTTP threads.

## 4. Modules

| Module | Responsibility |
|---|---|
| `radiarch.config` | Pydantic-based configuration (`RADIARCH_*` env vars). |
| `radiarch.app` | FastAPI instantiation, router wiring, lifespan hooks. |
| `radiarch.api.routes.*` | Routers: `/info`, `/plans`, `/workflows`, `/sessions`, `/simulations`, `/artifacts`. |
| `radiarch.core.planner` | Orchestrator — dispatches to per-workflow modules, manages synthetic fallback. |
| `radiarch.core.simulator` | 4D delivery simulation engine for plan delivery analysis. |
| `radiarch.core.store` | `InMemoryStore` + SQLAlchemy-backed `DBStore` for plan/job persistence. |
| `radiarch.core.db_models` | SQLAlchemy ORM models for plans and jobs. |
| `radiarch.core.workflows.*` | Per-workflow modules: `proton_basic`, `proton_robust`, `proton_optimized`, `photon_ccc`, shared `_helpers`. |
| `radiarch.models.*` | Pydantic request/response models (`PlanDetail`, `SimulationDetail`, `JobState`). |
| `radiarch.tasks.plan_tasks` | Celery task registration and async job execution. |
| `radiarch.client` | `RadiarchClient` Python SDK (mirrors `MONAILabelClient`). |
| `service/opentps/` | Vendored OpenTPS Core — 174 Python files for DICOM I/O, dose calculation (MCsquare, CCC), plan optimization, image processing. |

## 5. API Surface

### Implemented

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/info` | GET | ✅ Capabilities, version, available workflows, models |
| `/api/v1/workflows` | GET | ✅ Planning templates (Proton IMPT, Photon CCC, etc.) |
| `/api/v1/workflows/{id}` | GET | ✅ Workflow detail with default parameters |
| `/api/v1/plans` | POST | ✅ Submit plan — returns job ID + status |
| `/api/v1/plans` | GET | ✅ List all plans |
| `/api/v1/plans/{id}` | GET | ✅ Plan metadata + job pointer + artifacts |
| `/api/v1/plans/{id}` | DELETE | ✅ Cancel plan, update status |
| `/api/v1/jobs/{id}` | GET | ✅ Status, progress %, stage, messages |
| `/api/v1/artifacts/{id}` | GET | ✅ Download RTPLAN/RTDOSE/DVH |
| `/api/v1/sessions` | POST | ✅ Upload temp image data for plan preview |
| `/api/v1/sessions/{id}` | GET / DELETE | ✅ Retrieve or expire session |
| `/api/v1/simulations` | POST / GET | ✅ Create and list delivery simulations |
| `/api/v1/simulations/{id}` | GET | ✅ Simulation detail with 4D dose results |

### Planned

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/hooks/orthanc` | POST | Webhook for Orthanc event-driven study ingestion |

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

### Phase 4 — Persistence & Data Layer ✅
- SQLAlchemy + Alembic migrations for plans and jobs (`DBStore`, `db_models.py`)
- Session endpoints (`POST /sessions`, `GET/DELETE /sessions/{id}`)
- `models` field in `/info` listing available engines

### Phase 5 — Production Readiness ✅
- Celery with Redis broker, structured job progress polling with stage tracking
- `RadiarchPlanner` refactored to dispatch to per-workflow modules
- 4 workflow modules: `proton_basic`, `proton_robust`, `proton_optimized`, `photon_ccc`
- `RadiarchSimulator` for 4D delivery simulation

### Phase 6 — OHIF Integration & Client SDK ✅
- `RadiarchClient` Python SDK with `create_plan()`, `poll_job()`, `get_artifact()` methods
- OHIF v3 extension with 4 panels: Plan Submission, DVH, Dose Overlay, Simulation
- 8 commands bridging OHIF UI → Radiarch API
- Standalone browser demo (`demo/index.html`)

### Phase 7 — Vendoring OpenTPS Core ✅
- Vendored `opentps_core` (174 Python files) into `service/opentps/`
- Stripped Windows/Mac MCsquare binaries, keep Linux SSE4/AVX only
- Added `scipy`, `pandas`, `SimpleITK` as hard dependencies
- All 27 tests pass including real MCsquare proton dose calculation
- Added attribution (`ATTRIBUTION.md`) and Apache 2.0 license

### Phase 8 — Operations (Next)
- **Auth** — Keycloak RBAC with 2 roles: `radiarch-admin` and `radiarch-user`
- **Docker Compose** — FastAPI + Celery worker + Redis + Orthanc + Postgres
- **Artifact storage** — Optional S3/MinIO backend alongside Orthanc STOW-RS
- **Orthanc webhook** — `POST /hooks/orthanc` for event-driven study ingestion

### Phase 10 — Testing of MCsquare and TPS Cores
- Add more testing based on OpenTPS test data which can be found from [OpenTPS Test Data](https://gitlab.com/openmcsquare/opentps/-/tree/master/testData), and the MCsquare python interface which can be found from https://gitlab.com/openmcsquare/python_interface


### Future Phases - Enhancements of TPS Algorithms and Features, and GUI
- E.g. incorporate development from [gitlab.com/flash-tps/flash-tps](https://gitlab.com/flash-tps/flash-tps) and [Eliot-P/PRBIO](https://github.com/Eliot-P/PRBIO) that is based on OpenTPS Core. 
- Enhancing the UI according to OpenTPS GUI, which can be found from its [OpenTPS User Guide](https://opentps.org/docs/OpenTPS_user_guide_FINAL.pdf)
-

## 8. Design Decisions (Resolved)

| Question | Decision | Rationale |
|---|---|---|
| OpenTPS: dependency or vendored? | **Vendored** `opentps_core` in `service/opentps/` | Avoids `numpy>=2.3.2` blocker, strips GUI deps, full control over fixes |
| MCsquare binaries: all platforms? | **Linux-only** (SSE4/AVX), strip Win/Mac | Server-only deployment; saves ~150MB |
| Artifacts: Orthanc-only or also S3? | **Orthanc primary**, S3/MinIO optional (Phase 8) | Keeps DICOM in PACS; S3 for large non-DICOM artifacts |
| Auth: reverse proxy or embedded JWT? | **Keycloak RBAC** (embedded JWT validation) | Same approach as MONAILabel; 2 roles sufficient |
| Multi-tenant? | **Single Orthanc** connector, abstract later | Start simple; `OrthancAdapterBase` ABC allows future expansion |
| Job progress: WebSocket or polling? | **Polling** (`GET /jobs/{id}`) | MONAILabel uses polling; OHIF clients already support it |
| Planner architecture? | **Dispatch to per-workflow modules** | Each workflow (`proton_basic`, etc.) is a standalone module; `_helpers.py` shares common logic |
| GPU dose calculation? | **Evaluating MOQUI** (open-source CUDA MC) | MCsquare is CPU-only (SSE/AVX); MOQUI from MGH offers GPU acceleration with validated accuracy |

## 9. MONAILabel Alignment Principles

1. **`/info` discovery** — Clients should discover available engines/workflows from `/info` the same way MONAILabel clients discover models.
2. **Thin routers** — All logic lives in `RadiarchPlanner` and the store; routers are pure HTTP translation.
3. **Session-based preview** — Adopt MONAILabel's `/session` pattern for plan preview before commit.
4. **Client library** — Ship `RadiarchClient` so OHIF plugin code stays clean (like `MONAILabelClient`).
5. **Do NOT adopt** — Dynamic app loading, active learning, scoring, training endpoints. These are annotation-specific.

---
*Last updated: 2026-02-19. OpenTPS Core vendored, all 27 tests passing. See [monailabel_architecture.md](monailabel_architecture.md) for the MONAILabel reference.*
