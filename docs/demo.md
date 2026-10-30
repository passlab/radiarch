# Radiarch demo guide

A walk through what radiarch can do today, on the bundled test phantom, in about
fifteen minutes. Every command below was run on 2026-10-21 on a 20-core Linux
workstation; the timings are from those runs.

**Research use only. Not for clinical use.** Nothing here is a commissioned
system: the plans, doses and evaluations are research artifacts, every result
carries that statement, and the machine models are generic (an IBA-style proton
nozzle and a generic 6 MV photon beam).

## 1. What you need

- Linux x86-64 (the MCsquare and CCC engine binaries ship for Linux only; a CPU
  with AVX2 is used automatically, SSE4 as a fallback).
- Python 3.12 or newer, `git`, and about 2 GB of free disk for the artifact cache.
- The repository with its bundled test data: `tests/data/SimpleFantomWithStruct`
  (200 CT slices of a water phantom with one contoured target, `TargetVolume`).
  No download, no Orthanc, no Docker, no GPU.

```bash
git clone https://github.com/passlab/radiarch.git && cd radiarch
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -e "./src[dev]"
./scripts/install-dev.sh          # regenerates the editable install cleanly, checks the MCsquare import
cp .env.dev .env                  # dev mode: in-process jobs, in-memory stores, no API key
```

`.env.dev` sets `RADIARCH_ENVIRONMENT=dev`, which runs jobs in-process (no Redis,
no Celery worker) and permits the test-only `analytic` engine. Everything the demos
write goes under `data/artifacts/` (`rm -rf data/artifacts` resets every cache).

## 2. One flag to remember: `--spacing 5`

The phantom's native grid is 200 × 200 × 200 voxels at 1 mm (8 million voxels).
The proton Monte Carlo engine is fine on it, but the collapsed-cone photon engine
and the gamma analysis take twenty minutes or more at that resolution. Passing
`--spacing 5` to any demo resamples the geometry to a 5 mm grid covering the same
200 mm extent (40 × 40 × 40 voxels), which turns every step below into seconds to
a minute and changes nothing about what the demo shows. The geometry, beam model, dose, influence
matrix and optimization results are content-addressed, so a second run of the
same command is a cache hit (each demo proves this by running its last step twice).

## 3. The demo ladder

Run them in order; each step reuses what the previous one cached. `--show` writes a
`preview.png` next to the result it renders (matplotlib) and opens a window when a
display is available.

### 3.1 Geometry — DICOM in, density grid and structure masks out

```bash
python demo/show_geometry.py --show
python demo/show_geometry.py --spacing 5 --show     # the 5 mm grid the later steps use
```

Reads the CT series and the RTSTRUCT, converts HU to mass density with the
stoichiometric (MCsquare) calibration, rasterizes every contour into a label
volume and writes three NIfTI files. Shows the grid, the structure index and an
axial slice with the masks overlaid.

### 3.2 Proton dose — MCsquare Monte Carlo (about 10 s)

```bash
python demo/show_dose.py --engine mcsquare --spacing 5
python demo/show_dose.py --engine mcsquare --spacing 5 --scenarios 5     # + setup/range error scenarios
python demo/show_dose.py --engine mcsquare --spacing 5 --influence       # + the sparse Dij matrix
```

Places pencil-beam-scanning spots on energy layers covering the target from one
gantry angle, writes the MCsquare input files, runs the Monte Carlo binary as a
subprocess and reads the dose back. With `--scenarios` it also computes the dose
under setup shifts and range scaling (the inputs for robust optimization); with
`--influence` it computes one dose column per spot, which is what the optimizer
needs. Weights are all ones here, so the dose is an unweighted "every spot at
1 MU" field, not a plan.

### 3.3 Photon dose — collapsed-cone engine (about 40 s)

```bash
python demo/show_dose.py --engine ccc --modality photon --spacing 5
```

Builds a one-field open photon plan (20 × 20 cm jaws, 10 mm leaves, 5 mm beamlets:
1,600 beamlets; the proton plan above has 784 spots), writes the geometry and beamlet list for the WiscPlan
collapsed-cone binary, runs it as four parallel subprocesses and reads the dose
back, normalized so that 1 MU gives 1 cGy at d_max for a 10 × 10 cm field. Again
every beamlet carries 1 MU, so the maximum is 0.01 Gy; the plan comes in the next step.

### 3.4 Inverse planning — the actual plan (under a minute each)

```bash
python demo/show_optimization.py --engine mcsquare --spacing 5 --show
python demo/show_optimization.py --engine ccc --modality photon --spacing 5 --show
python demo/show_optimization.py --engine mcsquare --spacing 5 --robust 9 --aggregation WORST_CASE
python demo/show_optimization.py --engine mcsquare --spacing 5 --solver Adam --max-iters 500
python demo/show_optimization.py --engine mcsquare --spacing 5 --objectives ptv_dmin=60,oar_dmax=20
```

Builds the influence matrix, then minimizes the dose objectives over the spot or
beamlet weights with L-BFGS-B (default; Adam and projected gradient are selectable),
checkpointing along the way. The default objective is a uniform 10 Gy on the target;
`--robust N` optimizes the worst case (or the expectation, or CVaR) over N error
scenarios. The preview shows the DVH, a dose slice and the convergence curve; the
weights (`weights.npy`) and the optimized dose (`dose.nii.gz`) are saved.

### 3.5 Evaluation — DVH, indices, gamma (a few seconds)

```bash
python demo/show_evaluation.py --engine mcsquare --spacing 5 --prescription 20 --gamma --show
python demo/show_evaluation.py --engine ccc --modality photon --spacing 5 --prescription 2 --gamma
```

Cumulative DVH per structure (mean, max, D95, V_prescription), the ICRU-83
homogeneity index, the Paddick conformity index, coverage and hotspot, and a
3 %/3 mm gamma comparison. The gamma here compares the dose with itself (a 100 %
sanity check of the pipeline); comparing two doses is the same request with a
different `reference_dose_id`. The dose evaluated is the unweighted field of
step 3.2 or 3.3, so coverage reads 0 %; evaluate an optimized dose to see a
plan-quality report.

### 3.6 Beam-angle search (about 4 min)

```bash
python demo/show_bao.py --engine mcsquare --spacing 5 --n-beams 2 --angle-step 90 --search greedy
```

Scores candidate gantry angles (four here: 0, 90, 180, 270) by a short
optimization each, including a Monte Carlo influence matrix per angle, and picks
the best set greedily (or `top_k`). On the phantom it selects the two lateral
fields (90 and 270). `--scoring-iters` trades accuracy for time.

### 3.7 Physics checks

```bash
python -m radiarch.validation.run --list
python -m radiarch.validation.run --all --fast
```

The validation harness: 6 MV depth dose, profiles and output factors against
representative beam data, lung and bone slabs, proton range in water, and
cross-checks of the DVH and gamma code against independent tools. `--fast`
coarsens the grids. A run writes `src/radiarch/validation/results/<stamp>-<commit>/summary.md`.
These are research targets, not a clinical commissioning.

## 4. The service: the same pipeline over HTTP

What a client calls is the API, not the scripts. Locally:

```bash
uvicorn radiarch.app:create_app --factory --reload      # http://localhost:8000/api/v1/docs
```

With the full stack (API, Celery worker, Redis, Postgres, Orthanc):

```bash
cp .env.example .env            # set RADIARCH_API_KEY (openssl rand -hex 32)
docker compose build && docker compose up -d
X_API_KEY=<the key> ./scripts/smoke_test.sh        # /info → /plans → /jobs → /artifacts
curl -H "X-API-Key: <the key>" http://localhost:8000/api/v1/dose/engines
```

Once `RADIARCH_API_KEY` is set, every route except `/api/v1/info` requires the
`X-API-Key` header. `/info` is open and reports the intended-use statement and
the engines. The service endpoints mirror the demo steps: `/geometry/build`,
`/beam-model/build`, `/dose/compute` and `/dose/influence`, `/optimize/run`,
`/bao/run`, `/evaluate/run`; each returns a job id to poll and a result that
carries the `disclaimer` field. `src/radiarch/client.py` wraps them for Python.

## 5. Seeing the dose in a viewer

The RT objects radiarch writes (structure set, plan, dose with its DVHs, images; `POST /api/v1/rt/export`) go to
a DICOMweb server, and the viewer shows them. With the Docker Compose stack and its viewer profile:

```bash
docker compose --profile viewer up -d --build
./scripts/demo-lung.sh            # a public lung-cancer patient into Orthanc, a plan with demo-lung-imrt, pushed
```

and open the link it prints (`http://localhost:3000/plan-review?StudyInstanceUIDs=...`). The plan review mode shows
the dose as isodose bands over the CT with the plan's contours (GTV, CTV, PTV, organs), the DVHs, and the radiarch
plan with its goals. `docs/viewing.md` covers the viewer, and 3D Slicer with SlicerRT for the same objects. The
service results are also NIfTI volumes, which Slicer and ITK-SNAP open directly.

### 5.1 The lung patient

`demo-lung.sh` uses `radiarch fetch-tcia`, which downloads a patient's planning CT and structure set from The Cancer
Imaging Archive's public NBIA API (no account needed) into the API container's artifact volume and pushes them to
Orthanc. The default patient is `LUNG1-002` of NSCLC-Radiomics: a non-small-cell lung cancer with the tumour
(`GTV-1`), both lungs, the heart, the oesophagus and the spinal cord contoured. Another patient of that collection
is `PATIENT=LUNG1-001 ./scripts/demo-lung.sh` (it has no heart or oesophagus contours, so those goals are reported
missing). `PROTOCOL=lung-60gy-30fx-vmat` plans two VMAT arcs instead, in about twenty minutes on a CPU.

Run again for the same patient, the script downloads, plans and exports nothing new: the cached series, the stored
plan and its stored export, pushed again with the same UIDs, so the study still holds one plan.
`NEW_EXPORT=1 ./scripts/demo-lung.sh` pushes a marked copy (`copy 2`, its plan referencing the first) instead
(README, "Exporting a plan again").

The `demo-lung-imrt` protocol grows the CTV (5 mm) and PTV (5 mm) from the GTV, plans 60 Gy in 30 fractions with
seven static fields, and judges the plan by the RTOG 0617 limits (cord, oesophagus, heart, lungs). It is a
demonstration, not a site protocol: the dose engine and machine are radiarch's research models.

`PROTOCOL=demo-lung-imrt-mco ./scripts/demo-lung.sh` makes the same plan by multi-criteria optimization: a Pareto set
of five trade-offs (PTV homogeneity, lungs, heart and oesophagus mean dose, a cord EUD), navigated automatically by
the protocol's goals and made deliverable. The viewer's MCO panel then moves along the set from the plan on screen
(`docs/viewing.md`). Validation record R11 compares the two plans on this patient.

NSCLC-Radiomics is distributed under CC BY-NC 3.0 (non-commercial use) with TCIA's data usage policy. Work that uses
it cites the data and the paper:

- Aerts, H. J. W. L. et al. (2019). Data from NSCLC-Radiomics (version 4). The Cancer Imaging Archive.
  https://doi.org/10.7937/K9/TCIA.2015.PF0M9REI
- Aerts, H. J. W. L. et al. (2014). Decoding tumour phenotype by noninvasive imaging using a quantitative radiomics
  approach. Nature Communications 5, 4006. https://doi.org/10.1038/ncomms5006

Without internet access, `./scripts/demo-viewer.sh` does the same with the bundled phantom (a water cylinder with one
contoured target and the `demo-phantom-imrt` protocol).

## 6. Your own data

```bash
python demo/show_geometry.py --upload /path/to/study.zip --show
python demo/show_dose.py --upload /path/to/study.zip --engine mcsquare --spacing 5
```

A ZIP of one CT series plus its RTSTRUCT goes through the same upload path the
service exposes (`POST /uploads/dicom`). Target detection looks for structures
named PTV, GTV or CTV (prefixes such as `PTV_60` count); map other names with the
geometry request's `structure_name_map`. Slicer `.seg.nrrd` label maps are accepted
too (`demo/README_DICOM.md` describes public datasets to try).

### 6.1 A plan you already have

An RT Plan or RT Ion Plan that belongs to the same CT (same frame of reference) can be imported as a
beam model and its dose recomputed with radiarch's engines, through `POST /api/v1/beam-model/import`
(an upload id or a server path) and `POST /api/v1/dose/recalculate`; see the README's "DICOM RT in".
Public collections rarely ship plans next to their CTs, so the demo stops at the phantom here.

## 7. If something looks wrong

| Symptom | Cause and fix |
|---|---|
| A photon or gamma step runs for many minutes | Native grid. Add `--spacing 5`. |
| `--engine analytic` reports hundreds of Gy | By design: the analytic engine is a test fixture with the right shape and the wrong physics. It is refused outside `RADIARCH_ENVIRONMENT=dev` and should not be shown. |
| `MCsquare engine is not available` | The engine assets are missing or not executable: `ls engines/mcsquare`, `./scripts/fetch-engines.sh`; on macOS or Windows there is no engine binary. |
| `ModuleNotFoundError: radiarch...` after a `git pull` | Stale editable install; `./scripts/install-dev.sh` again. |
| `401 Invalid or missing API key` | The server has `RADIARCH_API_KEY` set; send `X-API-Key` (the smoke test reads `X_API_KEY`). |
| Disk filling under `data/artifacts` | Caches of every dose and Dij; `rm -rf data/artifacts` resets them (the cleanup task evicts old entries in a deployment). |
| Coverage 0 % in the evaluation | You evaluated an unweighted field (steps 3.2–3.3). Optimize first (3.4). |
