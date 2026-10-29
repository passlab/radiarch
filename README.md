# Radiarch TPS Service

[![CI](https://github.com/passlab/radiarch/actions/workflows/ci.yml/badge.svg)](https://github.com/passlab/radiarch/actions/workflows/ci.yml)

Radiarch is a FastAPI-based research treatment-planning service modeled after the MONAILabel server pattern. Its core (DICOM in, contour rasterization, calibration, spot and beamlet placement, optimization, evaluation) is its own; dose comes from two engines run as separate programs over files, [MCsquare](https://gitlab.com/openmcsquare/MCsquare) for protons and the WiscPlan collapsed-cone engine for photons (`engines/`), and from radiarch's own photon pencil-beam engine. It communicates with PACS providers such as Orthanc over DICOMweb. Plans are viewed in OHIF through radiarch's viewer packages (`viewer/`): a dose extension, a plan panel and a plan review mode, standalone or in another OHIF build (`docs/viewing.md`).

## Intended use

**Research use only. Not for clinical use.** Radiarch is a research treatment-planning
system: its plans, doses and evaluations must never be used to treat patients. Every
result the API returns carries a `disclaimer` field with that statement, `/api/v1/info`
reports it as `intended_use`, and every DICOM object radiarch writes carries
`NOT FOR CLINICAL USE` in its description, comment and a private `RADIARCH` block.
The dose engines are research engines with no site commissioning; see the validation records in
`docs/validation/` and the study `docs/reports/validation-data-and-test-plan.md` for what has and has not been checked.

## Layout

```
radiarch/
  Dockerfile            # Multi-stage container build
  docker-compose.yml    # Full stack: API + Worker + Redis + Postgres + Orthanc (+ the viewer, profile "viewer")
  .env.example          # Documented env var template
  scripts/              # smoke_test.sh, demo-lung.sh and demo-viewer.sh (a plan into the viewer), install-dev.sh, fetch-engines.sh
  viewer/               # OHIF packages: rt-dose-core, the RT Dose and radiarch extensions, the plan review mode,
                        # standalone/ (the viewer image: OHIF + nginx proxy) (viewer/README.md)
  demo/                 # CLI demos per service (show_*.py) + compare_engines.py; walkthrough in docs/demo.md
  engines/              # Dose engine assets run as subprocesses (engines/README.md)
    mcsquare/           # MCsquare launcher + Linux binaries, Materials/, BDL/, Scanners/ (Apache 2.0)
    ccc/                # WiscPlan collapsed-cone engine + kernels (GPLv2, subprocess only)
    pb/                 # kernel table of radiarch's own pencil-beam engine (R8)
  docs/                 # architecture.md, impl-plan.md (plan and task status), impl-log.md,
                        # ADRs, reports, validation records (docs/README.md)
  tests/data/           # SimpleFantomWithStruct: the bundled CT + structure set
  src/
    pyproject.toml
    radiarch/
      dicom/            # CT, RT Structure Set, RT Plan, RT Dose, registration readers (pydicom);
                        # writers/ for every RT object radiarch writes; drr.py
      app.py            # FastAPI factory
      client.py         # RadiarchClient Python library (legacy /plans)
      sdk/              # the SDK: every service as Python objects (R10)
      cli.py            # the `radiarch` command: protocols, plan, batch; cwl/ for workflow engines
      protocols/        # shipped planning protocols (JSON)
      config.py         # Pydantic settings
      api/routes/       # /info, /workflows, /plans, /jobs, /artifacts, /sessions, /uploads,
                        # /geometry, /beam-model, /dose, /optimize, /bao, /evaluate, /rt, /lineage
      core/
        planner.py      # Orchestrator — dispatches to workflow modules (no fallback)
        store.py        # InMemoryStore + SQLAlchemy persistence
        workflows/      # proton_basic, proton_robust, proton_optimized, photon_ccc
      models/           # Pydantic request/response models
      services/         # geometry, beam_model, dose (+ dose_engines/: mcsquare, ccc, pb),
                        # optimization, bao, evaluation, apertures, vmat, rt_export, lineage
      validation/       # the validation harness (cases, references, runner, report)
      goals/, machines/ # clinical-goal templates; photon machine definitions
      tasks/            # Celery workers (plan execution + per-service tasks)
```

## Quick Start — Docker Compose

Needs a Linux x86-64 machine (Ubuntu 22.04 or 24.04 works) with `git` and Docker Engine with the compose
plugin (`docker compose version`; Docker's install guide for Ubuntu, then `sudo usermod -aG docker $USER`
and log in again). The first build downloads and builds about 10 GB of images and takes 10 to 20 minutes;
the stack then needs about 4 GB of memory. No GPU on the server; the viewer draws in your browser.

```bash
git clone https://github.com/passlab/radiarch.git && cd radiarch
cp .env.example .env                                   # as shipped: no API key, for a machine only you use
export RADIARCH_BUILD_COMMIT=$(git rev-parse --short=7 HEAD)   # stamped into every DICOM object radiarch writes
docker compose --profile viewer up -d --build          # api, worker, redis, postgres, orthanc and the viewer
curl http://localhost:8000/api/v1/info                 # the API answers once its container is up
```

Without `--profile viewer` the viewer is left out (and its OHIF build skipped). If the build stops with
`429 Too Many Requests` from Docker Hub, its anonymous pull limit was reached (shared networks hit it): `docker login`
with a free Docker Hub account and run the command again.

### A plan in the viewer

```bash
./scripts/demo-lung.sh
```

It downloads a public lung-cancer patient from The Cancer Imaging Archive (NSCLC-Radiomics `LUNG1-002`, about
60 MB: a planning CT with the tumour, `GTV-1`, and the lungs, heart, oesophagus and spinal cord contoured by the
clinic) into the stack's Orthanc. It then plans it with the shipped `demo-lung-imrt` protocol (CTV = GTV + 5 mm,
PTV = CTV + 5 mm, 60 Gy in 30 fractions, seven IMRT fields on radiarch's pencil-beam engine, RTOG 0617 dose limits)
through the `radiarch` command inside the API container, pushes the structure set, plan and dose to Orthanc, and
prints a link:

```
http://localhost:3000/plan-review?StudyInstanceUIDs=<the patient's study>
```

Planning takes about six minutes on a 10-core (20-thread) workstation and longer on a smaller machine; meanwhile the command
prints each planning round (`protocols: running planning 15% (imrt planning, round 1 of up to 2)`). Until it prints
`pushed ... RT objects` and the link, the study in the viewer holds only the CT and the clinic's structure set: no
plan, dose or DVH yet. `docker compose logs -f worker` shows the planning itself. Run again for the same patient,
the script reuses the stored geometry, plan and export (`done (computed before: the stored result)`, `the stored export
of this plan`) and pushes the same objects again, which Orthanc already holds: the study keeps one plan.
`NEW_EXPORT=1 ./scripts/demo-lung.sh` pushes a marked copy instead (see [Exporting a plan again](#exporting-a-plan-again)).

Open it in Firefox or Chrome on the same machine (or through `ssh -L 3000:localhost:3000 <machine>`). The plan
review mode opens on the slice through the dose maximum: the dose as isodose colour bands over the CT, and the
plan's structures (GTV, CTV, PTV and the organs) as contours. On the right are the DVHs, the radiarch plan (summary,
a goal template, Evaluate) and the structure list, where each contour can be hidden or shown. `docs/viewing.md`
explains the viewer and its configuration.

**Chrome on Linux:** its default graphics backend (ANGLE on OpenGL) draws the CT and the dose black, while the contours
and DVHs still show; OHIF's own MPR view is black too. Use Firefox, or in Chrome open `chrome://flags/#use-angle`, choose
**Vulkan** and relaunch. The viewer says so when its image stays black.

NSCLC-Radiomics is licensed CC BY-NC 3.0 (non-commercial use; cite it as `docs/demo.md` says). The download stays
in the stack's artifact volume, not in this repository. Without internet access, `./scripts/demo-viewer.sh` does
the same with the bundled phantom (`tests/data/SimpleFantomWithStruct`: a water cylinder with one contoured target).

### Smoke test

After the stack is up, an end-to-end API smoke test: the phantom into Orthanc (`scripts/load-phantom.sh`), a proton
plan through the legacy `/plans` route (MCsquare in the worker), its job and artifacts. It also pushes that plan's
dose, so the phantom's study then holds two doses; the plan review mode opens the latest.

```bash
./scripts/smoke_test.sh
API_BASE_URL="http://127.0.0.1:8000/api/v1" X_API_KEY=<key> ./scripts/smoke_test.sh   # another server, or with a key
```

| Service | Port | Description |
|---|---|---|
| `api` | 8000 | Radiarch FastAPI server (OpenAPI at `/api/v1/docs`) |
| `worker` | — | Celery worker (every service's jobs) |
| `redis` | 6379 | Celery broker + result backend |
| `postgres` | 5432 | Persistent data store |
| `orthanc` | 8042, 4242 | DICOM server: web UI, REST and DICOMweb on 8042 (user `radiarch`, password `radiarch`); DICOM on 4242 |
| `viewer` | 3000 (localhost) | OHIF with radiarch's extensions; Orthanc and the API behind it (profile `viewer`) |

Stop everything: `docker compose --profile viewer down` (add `-v` to remove the volumes: plans, Orthanc, database).

For a machine others can reach, set `RADIARCH_API_KEY` in `.env` (`openssl rand -hex 32`), change Orthanc's password
in `docker-compose.yml`, and read `docs/PRODUCTION.md`.

## Quick Start — Local Development

Python 3.12 or newer (Ubuntu: `sudo apt install python3-venv python3-pip`). No Docker needed: `.env.dev` runs jobs in
process with in-memory stores.

```bash
python3 -m venv .venv
source .venv/bin/activate
./scripts/install-dev.sh         # editable install with the dev extras + sanity check
cp .env.dev .env
uvicorn radiarch.app:create_app --factory --reload
```

The `install-dev.sh` helper purges stale build artifacts before
calling `pip install -e ./src`. Use it instead of a bare `pip install
-e` whenever `src/radiarch` gains a new subpackage — modern setuptools'
*strict* editable install snapshots the package list at install time,
so old finders can mask freshly added `__init__.py` files. The test
suite's `tests/conftest.py` also prepends `src/` to `sys.path` as a
belt-and-suspenders guard so `pytest` works even if the install is
stale.

Open <http://localhost:8000/api/v1/docs> to inspect the OpenAPI schema. `docs/demo.md` walks through the services on
the bundled phantom in about fifteen minutes.

### Engines

The dose engines are data, not Python: `engines/mcsquare` (launcher, Linux binaries
for SSE4/AVX/AVX2/AVX-512, material database, beam data library, scanner
calibrations) and `engines/ccc` (the WiscPlan collapsed-cone engine, its kernels and
LINAC data). `scripts/fetch-engines.sh <tag>` refreshes them from the OpenTPS
repository, which packages both; see `engines/README.md`.

There is no synthetic fallback. If an engine is missing, or a workflow runner fails, the plan job is recorded as `failed` with the error in its message — Radiarch never returns invented QA numbers. The API-contract tests inject a test-only fake runner (`tests/conftest.py`) instead of running an engine.

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
| `RADIARCH_VIEWER_URL` | `""` | OHIF base URL; a successful push returns a `viewer_url` that opens the study (`docs/viewing.md`) |
| `RADIARCH_VIEWER_ROUTE` | `viewer` | The OHIF route of that link: `viewer` for any OHIF, `plan-review` for radiarch's viewer (the compose file's) |
| `RADIARCH_ORTHANC_DICOMWEB_ROOT` | `/dicom-web` | Orthanc's DICOMweb path under `RADIARCH_ORTHANC_BASE_URL`, where studies are read from |
| `RADIARCH_BUILD_COMMIT` | `""` | The commit an image was built from (a build argument); else the git checkout's. Every DICOM object states `[release, "git <commit>"]` in Software Versions |
| `RADIARCH_API_KEY` | `""` | `X-API-Key` required on every `/api/v1` route except `/info`; empty disables auth (dev only) |
| `RADIARCH_ALLOW_TEST_ENGINES` | unset | Permit the test-only `analytic` engine (wrong physics by design). Unset = only when `RADIARCH_ENVIRONMENT=dev` |
| `RADIARCH_DATA_ROOT` | `""` | DICOM (CT + RTSTRUCT) directory read when no upload or PACS study is given; empty = the bundled `tests/data/SimpleFantomWithStruct` |
| `RADIARCH_MCSQUARE_DIR`, `RADIARCH_CCC_ENGINE_DIR` | `engines/…` | Engine asset directories |

## Dose engines

Proton dose comes from **MCsquare** (Apache-2.0) and photon dose from the **WiscPlan collapsed-cone**
binary (GPLv2), both run as separate processes on files radiarch writes through its own drivers
(`services/dose_engines/mcsquare_driver.py`, `services/dose_engines/ccc_driver.py`; ADR 0005,
0006). Engine assets are read from `RADIARCH_MCSQUARE_DIR` / `RADIARCH_CCC_ENGINE_DIR`,
defaulting to `engines/`. `RADIARCH_MCSQUARE_SEED` with `RADIARCH_MCSQUARE_N_THREADS=1` makes a proton run
reproducible bit for bit. Doses and influence matrices are in radiarch's `(z, y, x)` C-order frame.

The third engine, **`pb`**, is radiarch's own photon pencil beam (roadmap R8, ADR 0015): an
OpenGATE pencil kernel of the same 6 MV spectrum, decomposed into four depth-weighted components,
radiological depth by ray casting, NumPy with an optional CuPy path (`params["device"]`, `RADIARCH_PB_DEVICE`).
Its influence matrix stops 80 mm from each beamlet and thins small entries by an unbiased roulette;
its doses convolve the full kernel and can use the apertures as they are (`params["fluence"]="apertures"`),
which is how VMAT control points are recomputed. All photon engines turn the gantry as IEC 61217 does
(gantry 90 enters from the patient's left; CCC did not before version 1.1.0).

## Robust protons, Gy(RBE), craniospinal fields

Scenario sets can be explicit (one engine run per scenario) or **engine-native**
(`engine_native` on a scenario set or on the optimizer's robustness spec): MCsquare then
samples the set itself in one run — `ALL` (81), `REDUCED_SET` (21) or `RANDOM` (n) scenarios
of systematic setup, per-fraction random setup and range errors — and every scenario comes
back labelled with the errors applied. Proton doses, influence matrices and optimized doses
are in **Gy(RBE)** with RBE 1.1 unless `rbe` is set (results carry `rbe_factor` and
`dose_units`). An evaluation of a dose with scenarios reports DVH bands, per-scenario DVH
metrics with their envelope, and worst-case target goals. Beams may carry their own
isocenter and a target z slab; `POST /beam-model/templates/craniospinal` builds the
posterior fields of a craniospinal plan with overlapping junctions, optionally a
posterior-oblique pair for the brain (ADR 0009).

## Clinical goals, radiobiology, gamma, comparisons

An evaluation grades clinical goals (TG-263 DVH statements with priorities; templates for
RTOG 0617, QUANTEC, TG-101 SBRT, NCCN head and neck and a provisional PENTEC set under
`radiarch/goals/`, listed by `GET /evaluate/goal-templates`), reports LKB NTCP and Poisson TCP
with published parameter sets (`GET /evaluate/models`), converts to EQD2 when the fractions are
given, and computes a gamma with sub-voxel interpolation. `POST /evaluate/compare` gives the
dose impact between two evaluations: DVH metric and index differences and the goals that
changed state (ADR 0011).

## Machines, structures, apertures

Photon machines are data (`radiarch/machines/`, `GET /beam-model/machines`): leaf boundaries,
travel limits, speeds, dose rates and deliverability thresholds; two synthetic linacs ship,
custom ones live in `RADIARCH_BEAM_LIBRARY_DIR/<id>/machine.json`. Structures overlap freely
(a bitmask volume). `POST /geometry/{id}/derive` makes PTVs, rings, booleans, density
overrides and a couch slab from an existing geometry. `POST /optimize/{id}/sequence` turns a
photon optimization into step-and-shoot MLC apertures with re-optimized segment MU and a
deliverability report (ADR 0010). `POST /optimize/{id}/arcs` turns an optimization of an arc's sector
beams into VMAT arcs: each sector's fluence swept by the leaves, control points every 2–4°, their doses
recomputed by `pb`, the metersets re-optimized within the gantry-speed, leaf-speed and dose-rate limits,
and the delivery time reported per fraction (ADR 0015). Arcs are DYNAMIC beams in the RT Plan writer and
reader. `radiarch.services.sbrt` grades R100, R50, D2cm and lung V20 against the RTOG 0813/0915 table,
and the `sbrt-lung-54gy-3fx` and `sbrt-lung-50gy-5fx` goal templates add the prescription and target goals
to the TG-101 limits.

## DICOM RT in

`radiarch.dicom` reads RT Plan and RT Ion Plan objects into the plan models, RT Dose objects onto
the `(z, y, x)` grid, and registration objects (ADR 0007). A plan becomes a beam model with its own
metersets, and its dose is recomputed with the ordinary pipeline:

```bash
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"geometry_id": "<id>", "path": "/data/plans/RTPLAN.dcm"}' $API/beam-model/import
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"geometry_id": "<id>", "beam_model_id": "<imported id>", "engine": {"name": "mcsquare"}}' $API/dose/recalculate
```

The plan's frame of reference must be the geometry's (a plan from another CT needs a registration,
roadmap R9). Arcs are discretized per control-point interval at the mid-angle.

## DICOM RT out

`radiarch.dicom.writers` writes the RT objects of a case on one shared context, every one labelled
research use only (ADR 0012): the RT Structure Set of a geometry (masks → closed planar contours),
the RT Plan (photon step-and-shoot with MLC control points and MU) or RT Ion Plan (spots per energy
layer), the RT Dose (PLAN with each structure's DVH, and BEAM per beam on request), one DRR RT Image per beam
(`radiarch.dicom.drr`, ray marching), and the RT (Ion) Beams Treatment Record per session plus the
RT Treatment Summary Record. `POST /rt/export` assembles them from an aperture sequence, a proton
optimization or a beam model with its own metersets; `GET /rt/exports?sop_instance_uid=…` finds the export
that wrote an object (`docs/viewing.md`); `POST /rt/exports/{id}/records` adds sessions;
`push` or `POST /rt/exports/{id}/push` sends them with STOW-RS (`RADIARCH_DICOMWEB_URL`):

```bash
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"sequence_id": "<id>", "prescription": {"dose_gy": 60, "fractions": 30, "target_structure": "PTV"}, "per_beam_dose": true, "push": true}' \
  $API/rt/export
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"sessions": [{"fraction_number": 1, "treatment_date": "20261101"}]}' $API/rt/exports/<export id>/records
curl -H "X-API-Key: $KEY" -o RP.dcm $API/rt/exports/<export id>/files/RP.dcm
```

### Exporting a plan again

An export is identified by its plan and by every setting that shapes the objects, among them the label, description,
prescription, structures, object kinds, DVHs, per-beam doses, DRR size, and the referenced structure set and
plans (`RTExportRequest.compute_cache_key`; `push` is not part of it). Asked for an export again:

| Request | What radiarch does | In the archive |
|---|---|---|
| The same plan and settings (the default) | returns the stored export, `"reused": true`; with `push`, sends the same objects again | Orthanc keeps the copy it holds: one plan in the study |
| The same plan, `new_export` | writes a copy: new UIDs, `copy N` in the RT Plan and structure set labels and in every series description, the latest earlier plan referenced with RTPlanRelationship `PREDECESSOR` | a second, marked plan beside the first |
| Another setting (label, prescription, structures, ...) | a new export of its own (`copy_number` 1) | a separate plan |

Nothing is deleted or replaced, in radiarch or in the archive: as in commercial planning systems, a later plan
supersedes an earlier one by reference. Once a copy exists, the default returns the latest copy. An export whose
files are gone is written anew. The export's manifest records `cache_key`, `copy_number` (1 for the first export)
and `copy_of` (the export a copy follows).

```bash
radiarch plan --protocol demo-lung-imrt --study <uid> --push                  # again: the stored export, pushed again
radiarch plan --protocol demo-lung-imrt --study <uid> --push --new-export     # a marked copy, "copy 2"
NEW_EXPORT=1 ./scripts/demo-lung.sh                                           # the same from the demo scripts
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"sequence_id": "<id>", "push": true, "new_export": true}' $API/rt/export
```

```python
run = rx.run_protocol("demo-lung-imrt", geometry)
first = run.export(push=True)                    # first.result.reused is False on the first export
again = run.export(push=True)                    # again.id == first.id, again.result.reused is True
copy = run.export(push=True, new_export=True)    # copy.result.copy_number == 2, copy.result.copy_of == first.id
```

`radiarch plan` says which it was: `export <id>: the stored export of this plan, the same objects and UIDs`, or
`export <id>: copy 2, its plan follows export <id>'s`. In the viewer a copy's series read `RESEARCH - NOT FOR CLINICAL
USE (copy 2)`.

Exports written before this behaviour (radiarch before 737d2c5) carry no key and are never matched: the first export
after an upgrade is a new one. To clear duplicate series that older runs left in a study, delete them in Orthanc's
web interface (`http://localhost:8042`), or start the stack again empty with `docker compose --profile viewer down -v`.

A photon optimization is exported through its aperture sequence (a fluence is not a plan). Every
object type validates clean against the DICOM standard (`dicom-validator` in the test suite,
`dciodvfy` in CI); `RADIARCH_TEST_DICOMWEB_URL=http://host:8042/dicom-web` opts a test into a round
trip through a DICOMweb server.

## Versions, lineage and states

Every stored result is a version with parents, read from the stores by `services/lineage.py`
(ADR 0013): `GET /lineage/{kind}/{id}` walks a version back to the geometry it started from,
`/descendants` forward, `/attribution` names the capability (radiarch, engine and version, machine
model, HU model) and the dataset (patient, study, CT series, frame of reference), and
`/derivation?dataset_id=&version=` renders the version as a dataset manifest's `derivation` record.
Kinds: `geometry`, `beam_model`, `influence`, `dose`, `optimization`, `sequence`, `bao`,
`evaluation`, `rt_export`, `plan`. `GET /lineage/capability` is radiarch's declaration to a
capability registry.

States are recorded, not decided: `POST /lineage/{kind}/{id}/state` records `approved` (with the
deciding authority, actor and reference), `superseded` (with the successor) or `retired`; an
approval under the authority `radiarch` is refused. A version that was ever approved, and every
version it derives from, cannot be deleted (409):

```bash
curl -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"state": "approved", "actor": "physicist:ab", "authority": "ois", "reference": "Task/42"}' \
  $API/lineage/dose/<id>/state
```

## Validation harness

`src/radiarch/validation/` holds the physics and cross-check cases that go beyond unit
tests (roadmap R7a; see the study `docs/reports/validation-data-and-test-plan.md`):

```bash
python -m radiarch.validation.run --list                  # the cases
python -m radiarch.validation.run --all --fast            # smoke run: coarser grids, fewer primaries
python -m radiarch.validation.run --cases photon_pdd_10x10 photon_profile_10x10
python -m radiarch.validation.goldens --capture           # refreeze tests/golden (only when a change is intended)
```

Cases compare radiarch against reference tables with citations (`validation/references/`:
6 MV representative beam data, proton ranges, TG-119 goals, the MPPG 5.a/5.b, TG-218 and
TECDOC-1583 tolerance sets) and against independent tools (dicompyler-core for DVHs;
pymedphys for gamma, run through `uv run --python 3.12` because it needs Python < 3.13).
Cases on public data read `{lctsc,pancreatic-ct-cbct-seg,tg119,pddca}` from a data directory outside
the repository, `RADIARCH_VALIDATION_DATA` (default `../data/public`); without it they are skipped. A run writes `validation/results/<stamp>-<commit>/summary.md`.
Statuses are research targets; nothing here is a clinical commissioning.

R7 (ADR 0014) adds the Monte Carlo comparison, the planning cases and the signed documents:

```bash
# OpenGATE references (its own Python 3.12 environment; hours per phantom; written to validation/references/mc)
uv run --no-project --python 3.12 --with opengate==10.1.1 --with itk \
  python -m radiarch.validation.mc_reference --case water_10x10 --primaries 5e7
uv run --no-project --python 3.12 --with pyRadPlan==0.5.0 python -m radiarch.validation.pyradplan_crosscheck --case water_10x10
python -m radiarch.validation.run --cases photon_vs_mc photon_vs_pyradplan dij_consistency proton_bragg_peak tg119_planning lung_e2e_lctsc
python -m radiarch.validation.report                      # one document per engine from the newest run, validation/reports/
```

The record for review is `docs/validation/2026-10-22-r7/` (a guide for the reviewing physicist, the three
documents and the run they come from, commit `20fc3bf`). `photon_vs_mc` compares the CCC engine with the references (PDD, profile, heterogeneity ratios,
gamma 3 %/3 mm); `dij_consistency` repeats the Dij-versus-forward gate for every engine;
`proton_bragg_peak` checks the fall-off and spot size against Bortfeld and the beam data library;
`tg119_planning` plans the four TG-119 structure sets and scores the goals with the report's
institutional means as context; `lung_e2e_lctsc` runs contour → plan → dose → RTOG 0617 goals on
an LCTSC thorax. The CCC engine is radiarch's own build: `params["scatter"]` chooses `shipped`
(fast, truncated scatter, the default) or `full` (complete scatter, about 45x slower);
`RADIARCH_CCC_SCATTER` sets the installation default. The full setting overshoots the Monte Carlo
reference at depth (ADR 0014), so `shipped` stays the default.

R8 (ADR 0015) adds the pencil-beam engine's cases and the arc plans:

```bash
# the pencil kernel (OpenGATE, about two hours on 18 threads) and the engine's table from it
uv run --no-project --python 3.12 --with opengate==10.1.1 --with itk \
  python -m radiarch.validation.mc_reference --pencil --primaries 3e7 --threads 18
python -m radiarch.services.dose_engines.pb_kernel --mc src/radiarch/validation/references/mc/pencil_6mv.npz
python -m radiarch.validation.run --cases pb_vs_mc pb_vs_ccc photon_pdd_10x10_pb photon_profile_10x10_pb \
  photon_output_vs_field_pb lung_sbrt_vmat hn_sib_vmat
```

`pb_vs_mc` grades the pencil beam against the OpenGATE references (the lung checks are consistency
checks: the lateral kernel scaling was fitted to the two lung slabs); `pb_vs_ccc` is the cross-engine check (gamma 3 %/3 mm in absolute
dose, the beamlet-size and field-size dependence of each engine, and which side a lateral beam enters);
`lung_sbrt_vmat` plans 54 Gy in 3 fractions with one arc on LCTSC thoraces and grades the TG-101 limits,
R100, R50 and D2cm, with CCC recomputing the delivered arcs; `hn_sib_vmat` plans a 70/56 Gy simultaneous
integrated boost with two arcs on PDDCA head-and-neck CTs against the NCCN template.

`tests/golden/` freezes the outputs captured from the vendored OpenTPS code before it was
replaced (CCC beamlet matrix, SimpleFantom geometry, proton spots, the MCsquare input files);
radiarch's own loaders, rasterizer, spot placement and drivers reproduce them on every push
(`tests/test_goldens.py`; ADR 0008).

## Testing

The suite covers the API, client SDK, the DICOM readers, Services 1–6, the engine drivers,
the legacy workflows and the regression goldens. Two are opt-in real-MCsquare legs that skip
unless `RADIARCH_RUN_MCSQUARE_VALIDATION=1` is set.

### Test Suite Overview

| Test File | What It Covers |
|-----------|----------------|
| `tests/test_api_backend.py` | InMemoryStore CRUD, workflow registry, session helpers, Pydantic models |
| `tests/test_api_e2e.py` | End-to-end API (plans, jobs, artifacts, sessions, workflows) on the fake runner; runner failure → job failed |
| `tests/test_client.py` | RadiarchClient Python SDK |
| `tests/test_dicom_readers.py`, `tests/test_plan_import.py` | RT Plan / Ion Plan / Dose / registration readers, plan import and recalculation |
| `tests/test_goldens.py`, `tests/test_engine_assets.py` | Regression goldens; the engine asset layout |
| `tests/test_mcsquare_driver.py`, `tests/test_ccc_engine.py` | The two engine drivers against the real binaries |
| `tests/services/`, `tests/test_*_{service,d1,e2e,…}.py` | Services 1–6 (geometry, beam model, spot placement, dose engines, optimization, BAO, evaluation), persistence |

### Running Tests

```bash
source .venv/bin/activate

# Full suite
python -m pytest tests/ -v

# Fast tests only (API + client, no engine) — ~2 seconds
python -m pytest tests/test_api_e2e.py tests/test_client.py tests/test_api_backend.py -v

# Engine drivers and goldens only
python -m pytest tests/test_mcsquare_driver.py tests/test_ccc_engine.py tests/test_goldens.py -v
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

**Objectives:** `DMin`, `DMax`, `DUniform`, `DVHMin`, `DVHMax`, `EUD` (exponent `eud_a`, 10 when unset), weighted
penalty constraints (`constraints`), and fluence-smoothness / total-variation regularizers.

**Trade-off objectives** (R11, for multi-criteria planning; usable in any run): `MeanDose`, `EUDMax` (`eud_a >= 1`),
`EUDMin` (`eud_a <= 1`), `RMSOver`, `RMSUnder`, `UniformRMS`. Each is convex in the dose, reads in Gy above or below
its `dose_gy` level, and is zero when met (`dose_gy: 0` makes an organ's objective "as low as possible"); the result
lists every objective's value in `convergence.objective_values`.

**Hard constraints** (`hard_constraints`): `Dmax <=`, `Dmin >=`, `Dmean <=`, `gEUD <=` (`eud_a >= 1`) or `gEUD >=`
(`eud_a <= 1`), each met within its `tolerance_gy` (default 0.1 Gy). A feasibility run comes first and refuses a set
no plan on the beams can meet (the job fails with `InfeasibleConstraintsError` naming them); then the objectives are minimized under the limits by an
augmented Lagrangian, and `convergence.hard_constraints` reports each limit's achieved value. On the nominal scenario
in a single optimization (not with `robustness`); an MCO run holds them in every scenario. Design:
`docs/reports/mco-research-and-design.md` (D1, D2).

```json
"objectives": [{"type": "UniformRMS", "structure_name": "PTV", "dose_gy": 60, "weight": 1},
               {"type": "EUDMax", "structure_name": "Heart", "dose_gy": 0, "eud_a": 2, "weight": 0.2}],
"hard_constraints": [{"structure_name": "SpinalCord", "metric": "Dmax", "op": "<=", "value_gy": 45},
                     {"structure_name": "PTV", "metric": "Dmin", "op": ">=", "value_gy": 54}]
```
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

## Multi-criteria optimization (`/api/v1/mco`, R11, in progress)

A Pareto set: plans where no trade-off can improve without another getting worse, computed up front so a planner (or
a rule) can choose between them. Anchor plans (one per trade-off), a balance plan, then plans chosen by the sandwich
algorithm until its bound on the distance from any Pareto plan to the computed ones falls to `error_tolerance`
(default 0.05 of each trade-off's range) or the `plan_budget` (default 3N + 1) is spent. Trade-offs are the convex
objectives above (two to eight); hard constraints hold in every plan, and a coverage constraint on the target
(`PTV Dmin >=`) keeps organ anchors from switching every beamlet off (the run notes a plan that delivers no dose).
Navigation blends the stored plans, so a slider move needs no dose calculation. A navigation state is made deliverable
by projecting it onto the Pareto set and mimicking its dose: apertures for static fields, arcs when given, the spots
themselves for protons; a deviation table compares the deliverable plan with the navigated one and flags what got
worse. Design: `docs/reports/mco-research-and-design.md`.

**Robust MCO** (`robustness`: scenarios, as in robust optimization): each plan minimizes the worst scenario of its
weighted sum, hard constraints hold in every scenario, and every trade-off value is its worst case over the scenarios,
with its nominal value beside it (`nominal_gy`). Goals are graded on the nominal dose with their worst case
(`worst_case`, `robust_all_passed`), and automatic navigation works on the worst cases. `robust_gap` is the part of the
error bound that comes from protecting scenarios rather than each trade-off's own worst case; more plans do not remove
it. A robust set is made deliverable for protons only (422 for photons).

| Method & path | Purpose |
|---|---|
| `POST /api/v1/mco/run` | The Pareto set of a beam model (200 cached / 202 job / 422). |
| `GET /api/v1/mco/jobs/{job_id}` | Poll a run. |
| `GET /api/v1/mco/{mco_id}` | The set: each plan's weights and trade-off values in Gy, ideal and nadir, the error bound per plan. |
| `POST /api/v1/mco/{mco_id}/navigate` | A slider `move`, a `reference` point, `clamps` and `locks` from a state (the balance plan by default): the blend, exact trade-off values, DVHs and graded goals. |
| `POST /api/v1/mco/{mco_id}/auto-navigate` | The blend that best meets a goal set (template or inline), priority 1 first, then 2, then 3; met goals stay met. |
| `GET /api/v1/mco/{mco_id}/states` | The stored navigation states, the balance plan first; `/states/{state_id}` one of them. |
| `POST /api/v1/mco/{mco_id}/deliverable` | A state made deliverable (200 cached / 202 job): projection, apertures or `arcs` mimicking its dose, optional `normalise`, the deviation table. |
| `GET /api/v1/mco/deliverables/{id}` | The deliverable plan (beam model, dose, technique) and its deviation table; `/deliverables/jobs/{job_id}` its job. |

```python
from radiarch.sdk import Radiarch, ops
ps = beam_model.mco([ops.uniform_rms("PTV", 60), ops.mean_dose("Lungs-PTV"), ops.mean_dose("Heart"),
                     ops.eud_max("SpinalCord", 12)],
                    hard_constraints=[ops.hard("SpinalCord", "Dmax", "<=", 45), ops.hard("PTV", "Dmin", ">=", 54)])
ps.error_bound, ps.table()
st = ps.navigate(move={"MeanDose(Heart)": 8.0}, locks=["EUDMax(SpinalCord)"], goals="rtog-0617", prescription_gy=60)
st.values_gy, st.goals.all_priority1_passed
ps.navigate(from_state=st, clamps={"MeanDose(Lungs-PTV)": 12.0}, reference={"UniformRMS(PTV)": 1.5})
auto = ps.auto_navigate("rtog-0617", prescription_gy=60, fractions=30)
[(lv.priority, lv.passed, lv.goals) for lv in auto.levels]
plan = ps.deliverable(auto, goals="rtog-0617", prescription_gy=60, normalise={"structure": "PTV", "metric": "D95", "gy": 60})
plan.deviation_table()          # navigated, projected and deliverable value of every trade-off and goal, flagged ones
plan.export(label="MCO", prescription={"dose_gy": 60, "fractions": 30})

robust = proton_beam_model.mco([ops.uniform_rms("CTV", 60), ops.mean_dose("Parotid_L")], hard_constraints=[ops.hard("CTV", "Dmin", ">=", 57)],
                               robustness={"enabled": True, "scenarios": [{"name": "range+3%", "range_scale": 1.03},
                                                                          {"name": "range-3%", "range_scale": 0.97}]})
robust.table()                  # worst-case values, and "<name> nominal" columns
```

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

[`docs/architecture.md`](docs/architecture.md) is the design and architecture as built; [`docs/impl-plan.md`](docs/impl-plan.md) the implementation plan and the status of every task; [`docs/impl-log.md`](docs/impl-log.md) what each roadmap item did; [`docs/README.md`](docs/README.md) indexes the rest (decisions, reports, validation records).

## License & Attribution

Radiarch is licensed under the Apache License 2.0 (`LICENSE`); `NOTICE` lists the third-party
components. MCsquare is Apache 2.0. The WiscPlan collapsed-cone photon engine is GPLv2 and is
only ever run as a separate program over files. Parts of radiarch's core (the contour
rasterizer, the CT calibration, the spot placement, the engine file protocols) are ports of
OpenTPS core (© UCLouvain, Apache 2.0) and say so in their module docstrings. The direction
for the engines and the core is recorded in `docs/adr/0005-own-core-engines-as-tools.md` and
its completion in `docs/adr/0008-own-core-complete.md`.
