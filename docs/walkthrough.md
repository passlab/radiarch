# Phase 7 Walkthrough — Docker Compose Operations

## What Changed

### 1. Docker Stack

#### [Dockerfile](file:///home/yyan7/work/SMIS/radiarch/Dockerfile)
Multi-stage build (builder → runtime). Defaults to synthetic mode. Health check via `curl /api/v1/info`.

#### [docker-compose.yml](file:///home/yyan7/work/SMIS/radiarch/docker-compose.yml)

| Service | Image | Port |
|---|---|---|
| `api` | local build | 8000 |
| `worker` | same, celery entrypoint | — |
| `redis` | `redis:7-alpine` | 6379 |
| `postgres` | `postgres:16-alpine` | 5432 |
| `orthanc` | `orthancteam/orthanc:24.6.2` | 8042 |

Postgres has health check, API/worker depend on it.

---

### 2. Config Cleanup

#### [config.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/config.py)

```diff
-opentps_data_root = "/home/yyan7/work/SMIS/radiarch/opentps/testData"  # hardcoded
+opentps_data_root = "/data/opentps"  # parameterized via env var
+force_synthetic: bool = False        # proper config field
+session_ttl: int = 3600              # was missing from config
+opentps_venv: str = ""               # replaces hardcoded venv path
```

---

### 3. New Files
- [.env.example](file:///home/yyan7/work/SMIS/radiarch/.env.example) — all `RADIARCH_*` vars documented
- [.dockerignore](file:///home/yyan7/work/SMIS/radiarch/.dockerignore) — keeps build context small

### 4. README Rewrite
[README.md](file:///home/yyan7/work/SMIS/radiarch/README.md) — Docker quickstart, updated config table, Python client usage section.

---

## Test Results

```
19 passed in 1.13s ✅
```
