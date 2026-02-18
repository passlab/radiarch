# Phase 7 — Operations (Docker Compose)

- [x] Dockerfile (multi-stage build)
- [x] docker-compose.yml (api + worker + redis + postgres + orthanc)
- [x] Config cleanup (parameterize OpenTPS paths, add force_synthetic, session_ttl)
- [x] .env.example (documented template)
- [x] .dockerignore
- [x] README.md update (Docker quickstart, config table, client usage)
- [x] Verify all tests pass (19/19)
- [x] Fix: `_StoreProxy` lazy delegation instead of hardcoded `InMemoryStore` singleton
- [x] Fix: `database.SessionLocal` import-by-value bug → use module attribute access
- [x] Fix: Orthanc auth credentials in docker-compose.yml
- [x] Fix: `DICOMwebClient` init (use `requests.Session` with auth)
- [x] Full Docker e2e verified: upload DICOM → submit plan → worker executes → job succeeds
