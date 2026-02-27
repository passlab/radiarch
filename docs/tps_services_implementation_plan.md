# Implementation Plan: 6 Cloud-Native TPS Services

> Based on the SMIS Cloud TPS SDD v0.1 and the existing Radiarch codebase (`src/radiarch/`).

---

## Executive Summary

The current Radiarch prototype implements all 6 TPS tasks **inline** within 4 monolithic workflow modules ([proton_basic](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/proton_basic.py), [proton_optimized](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/proton_optimized.py), [proton_robust](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/proton_robust.py), [photon_ccc](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/photon_ccc.py)). Shared logic lives in [_helpers.py](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py). This plan decomposes those monoliths into **6 independent, async-capable service modules** with well-defined I/O contracts, while preserving backward compatibility with the existing API and demo UI.

### Existing Assets to Reuse

| SDD Service | Existing Code | Status |
|---|---|---|
| Geometry | `load_ct_and_patient()`, `setup_calibration()` in `_helpers.py` | Partial — needs CT→density, contour rasterization, grid spec |
| Beam Model | `ProtonPlanDesign.buildPlan()`, `build_gantry_angles()` | Partial — tightly coupled to OpenTPS objects |
| Dose | `build_mc_calculator()`, `mc_calc.computeDose()`, `CCCDoseCalculator` | Partial — no influence matrix caching, no scenario support |
| Optimization | `IntensityModulationOptimizer`, `build_objectives()` | Partial — no robust wrapper, no async checkpointing |
| BAO | *None* | New |
| Evaluation | `compute_dvh()`, `export_rtdose()` | Partial — no constraint checks, no reporting |

---

## Service 1 — Geometry Service

### Purpose
Convert raw clinical DICOM imaging into a computation-ready voxel model.

### Inputs

```
GeometryBuildRequest:
  patient_ref:
    dicom_study_uid: str            # DICOM Study Instance UID
    ct_series_uid: str | None       # Specific CT series (auto-detect if null)
    rtstruct_uid: str | None        # RTSTRUCT Series Instance UID
  grid_spec:                        # Desired output grid (null = match CT)
    spacing_mm: [float, float, float]
    origin_mm: [float, float, float] | null
    size: [int, int, int] | null
  hu_to_density_model: str          # "SCHNEIDER" | "STOICHIOMETRIC" | "LINEAR"
  structure_name_map: dict | null   # {"PTV": ["PTV_60", "PTV60"], ...}
  data_root_override: str | null    # Override opentps_data_root
```

### Outputs

```
GeometryResult:
  geometry_id: str (uuid)
  density_grid_uri: str             # Path/URI to density volume (NIfTI or .npy)
  structure_masks_uri: str          # Multi-label mask volume
  structure_index: dict             # {"PTV": 1, "SpinalCord": 2, ...}
  grid_spec:                        # Actual grid used
    spacing_mm: [float, float, float]
    origin_mm: [float, float, float]
    size: [int, int, int]
    affine: [[float]*4]*4
  frame_of_reference_uid: str
  ct_metadata:
    patient_name: str
    modality: str
    num_slices: int
  cache_key: str                    # Hash of (ct_uid + rtstruct_uid + grid_spec)
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/geometry/build` | Submit geometry build job |
| `GET` | `/api/v1/geometry/jobs/{job_id}` | Poll job status |
| `GET` | `/api/v1/geometry/{geometry_id}` | Retrieve completed geometry metadata |

### What Exists Today
- [load_ct_and_patient()](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py#L36-L77): Loads CT + patient + RTStructs from `opentps_data_root` via `dataLoader.readData()`
- [setup_calibration()](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py#L84-L100): Loads MCsquare CT calibration (HU→stopping power)

### What Must Be Built
1. **[NEW] `src/radiarch/services/geometry.py`** — `GeometryService` class
   - Extract CT loading from `_helpers.py` → proper HU→density conversion with pluggable models
   - Contour rasterization to voxel masks (currently done implicitly by OpenTPS `Patient` object)
   - Grid resampling to user-specified `GridSpec`
   - Persist outputs to artifact storage with content-addressable caching
2. **[NEW] `src/radiarch/models/geometry.py`** — Pydantic I/O models
3. **[NEW] `src/radiarch/api/routes/geometry.py`** — FastAPI route
4. **[MODIFY] `src/radiarch/core/workflows/_helpers.py`** — Refactor `load_ct_and_patient` to delegate to `GeometryService`

---

## Service 2 — Beam Model Service

### Purpose
Create a modality-specific representation of deliverable radiation elements (beamlets for photons, spots for protons).

### Inputs

```
BeamModelBuildRequest:
  plan_id: str | null
  geometry_id: str                   # Reference to built geometry
  modality: "PHOTON_IMRT" | "PROTON_PBS"
  machine_model_id: str | null       # Machine config reference (null = default)
  beam_set:
    isocenter_mm: [float, float, float]
    beams: [
      { beam_id: str, gantry_deg: float, couch_deg: float, collimator_deg: float }
    ]
  delivery_params:
    # PHOTON_IMRT
    beamlet_size_mm: [float, float] | null   # Default [5, 5]
    mlc_leaf_width_mm: float | null
    jaw_opening_mm: [float, float] | null
    # PROTON_PBS
    spot_spacing_mm: float | null            # Default 5.0
    layer_spacing_mm: float | null           # Default 5.0
    energy_range: [float, float] | null      # MeV range
```

### Outputs

```
BeamModelResult:
  beam_model_id: str (uuid)
  modality: str
  fluence_elements:                  # Canonical abstraction
    total_count: int
    per_beam: [
      {
        beam_id: str,
        element_count: int,
        # PHOTON: beamlet grid dims
        # PROTON: spot positions + energy layers
      }
    ]
  beam_model_ref_uri: str            # Serialized beam model artifact
  cache_key: str
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/beam-model/build` | Submit beam model build job |
| `GET` | `/api/v1/beam-model/jobs/{job_id}` | Poll job status |
| `GET` | `/api/v1/beam-model/{beam_model_id}` | Retrieve completed beam model |

### What Exists Today
- `ProtonPlanDesign.buildPlan()` inside [proton_basic.py](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/proton_basic.py#L40-L55), [proton_optimized.py](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/proton_optimized.py#L43-L58): Creates proton spot maps with gantry angles, spot spacing, layer spacing
- Photon beam construction in [photon_ccc.py](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/photon_ccc.py#L38-L49): Creates `PhotonPlan` with beams/segments
- [build_gantry_angles()](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py#L167-L171): Generates evenly-spaced angles

### What Must Be Built
1. **[NEW] `src/radiarch/services/beam_model.py`** — `BeamModelService` class
   - Unified `FluenceElementSet` abstraction for both modalities
   - Proton: `ProtonPlanDesign` → spot map generation → serialize to artifact
   - Photon: `PhotonPlan` → beamlet grid generation → serialize to artifact
   - Machine model config loading (energy layers, nozzle params, BDL files)
2. **[NEW] `src/radiarch/models/beam_model.py`** — Pydantic I/O models
3. **[NEW] `src/radiarch/api/routes/beam_model.py`** — FastAPI route
4. **[MODIFY] `_helpers.py`** — Extract `load_bdl()` and calibration into `BeamModelService`

---

## Service 3 — Dose Service

### Purpose
Compute dose for a given plan and weights. Optionally build influence matrices and compute gradients for optimization.

### Inputs

```
DoseComputeRequest:
  plan_id: str
  geometry_id: str
  beam_model_id: str
  weights: WeightsSpec                # Inline array or URI reference
  dose_engine:
    name: str                         # "mcsquare" | "photon_ccc" | "pencil_beam" | "pyradplan"
    version: str | null
    params:                           # Engine-specific
      nb_primaries: float | null
      scoring_spacing_mm: [float, float, float] | null
  scenario: ScenarioSpec | null       # Setup shift / range uncertainty

InfluenceBuildRequest:
  plan_id: str
  geometry_id: str
  beam_model_id: str
  dose_engine: DoseEngineSpec
  scenario: ScenarioSpec | null
```

### Outputs

```
DoseResult:
  dose_id: str (uuid)
  dose_ref_uri: str                   # 3D dose grid artifact
  dose_metadata:
    max_gy: float
    mean_gy: float
    units: "Gy"
    grid_spec: GridSpec
    beam_contributions: [{ beam_id: str, max_gy: float }] | null
  compute_time_s: float
  engine_used: str

InfluenceResult:
  influence_id: str (uuid)
  influence_ref_uri: str              # Sparse matrix or kernel set artifact
  shape: [int, int]                   # (n_voxels, n_elements)
  storage_format: str                 # "csr" | "csc" | "dense" | "per_beam_chunks"
  size_bytes: int
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/dose/compute` | Submit dose computation job |
| `POST` | `/api/v1/dose/influence/build` | Submit influence matrix build job |
| `GET` | `/api/v1/dose/jobs/{job_id}` | Poll job status |
| `GET` | `/api/v1/dose/{dose_id}` | Retrieve dose metadata |

### Dose Engine Plugin Interface

Each engine must implement a Python protocol:

```python
class DoseEnginePlugin(Protocol):
    name: str
    modalities: list[str]

    def validate(self, geometry_ref, beam_model_ref, params) -> list[str]:
        """Return list of validation errors, empty if OK."""

    def compute_dose(self, geometry_ref, beam_model_ref, weights, scenario=None) -> DoseResult:
        """Forward dose calculation."""

    def build_influence(self, geometry_ref, beam_model_ref, scenario=None) -> InfluenceResult:
        """Build influence/beamlet matrix (optional)."""

    def apply_influence(self, influence_ref, weights) -> DoseResult:
        """Fast dose from cached influence (optional)."""

    def compute_grad(self, geometry_ref, beam_model_ref, weights, dL_dDose, scenario=None) -> np.ndarray:
        """Adjoint gradient dL/dWeights (optional, for optimization)."""
```

### What Exists Today
- [build_mc_calculator()](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py#L227-L236): Creates `MCsquareDoseCalculator` instance
- `mc_calc.computeDose(ct, plan)` called in all proton workflows
- `mc_calc.computeBeamlets(ct, plan, roi)` called in [proton_optimized.py:L71](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/proton_optimized.py#L71)
- `CCCDoseCalculator` used in [photon_ccc.py:L53-L55](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/photon_ccc.py#L53-L55)

### What Must Be Built
1. **[NEW] `src/radiarch/services/dose.py`** — `DoseService` class + plugin registry
2. **[NEW] `src/radiarch/services/engines/`** — Engine plugin directory
   - `mcsquare_engine.py` — Wraps existing `MCsquareDoseCalculator`
   - `photon_ccc_engine.py` — Wraps existing `CCCDoseCalculator`
   - `pyradplan_engine.py` — Future pyRadPlan integration slot
3. **[NEW] `src/radiarch/models/dose.py`** — Pydantic I/O models + `DoseEnginePlugin` protocol
4. **[NEW] `src/radiarch/api/routes/dose.py`** — FastAPI routes
5. **[MODIFY]** Workflows to delegate dose computation to `DoseService` instead of inline

---

## Service 4 — Optimization Service

### Purpose
Solve for optimal fluence weights `w*` given dose objectives/constraints and a dose engine.

### Inputs

```
OptimizationRunRequest:
  plan_id: str
  geometry_id: str
  beam_model_id: str
  dose_engine: DoseEngineSpec
  objectives: [
    {
      structure_name: str,
      type: "DMin" | "DMax" | "DUniform" | "DVHMin" | "DVHMax" | "EUD",
      dose_gy: float,
      weight: float,
      volume_fraction: float | null    # For DVH objectives
    }
  ]
  constraints: [                      # Hard constraints (penalty-based in v0.1)
    { structure_name: str, type: str, op: ">=" | "<=", value_gy: float, weight: float }
  ]
  solver:
    method: str                        # "L-BFGS-B" | "Adam" | "ProjectedGradient"
    max_iterations: int
    convergence_tol: float | null
    regularization:
      fluence_smoothness: float | null
      total_variation: float | null
  init_weights_uri: str | null         # Warm start
  robustness:
    enabled: bool
    scenarios: [ScenarioSpec]
    aggregation: "WORST_CASE" | "EXPECTED" | "CVAR"
  checkpoint_interval: int | null      # Save every N iterations
```

### Outputs

```
OptimizationResult:
  optimization_id: str (uuid)
  weights_ref_uri: str                # Final weights vector
  dose_ref_uri: str                   # Nominal dose from final weights
  convergence:
    success: bool
    iterations: int
    final_cost: float
    cost_history: [float]
    constraint_violations: [{ name: str, value: float, limit: float }]
  robust_stats:                       # Only if robustness enabled
    scenario_doses: [{ scenario_id: str, dose_ref_uri: str }]
    worst_case_metrics: dict
  compute_time_s: float
  checkpoints: [{ iteration: int, weights_uri: str, cost: float }]
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/optimize/run` | Submit optimization job |
| `GET` | `/api/v1/optimize/jobs/{job_id}` | Poll job status + progress |
| `GET` | `/api/v1/optimize/{opt_id}` | Retrieve final results |

### What Exists Today
- [build_objectives()](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py#L174-L220): Maps `PlanDetail.objectives` to OpenTPS `ObjectivesList`
- `IntensityModulationOptimizer` used in [proton_optimized.py:L79-L84](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/proton_optimized.py#L79-L84)
- `RobustnessConfig` Pydantic model in [plan.py:L32-L38](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/models/plan.py#L32-L38)
- Robustness evaluation in `proton_robust.py` (scenario generation via `scenarioHandler`)

### What Must Be Built
1. **[NEW] `src/radiarch/services/optimization.py`** — `OptimizationService` class
   - Modality-agnostic objective function library operating in dose space
   - Robust wrapper: scenario generation → per-scenario dose → aggregation
   - Solver abstraction (L-BFGS-B via scipy, Adam, projected gradient)
   - Async execution with checkpointing
2. **[NEW] `src/radiarch/services/objectives.py`** — Shared objective function library
   - `DMin`, `DMax`, `DUniform`, `DVHMin`, `DVHMax`, `EUD` — all take `(dose_grid, structure_mask) → loss`
3. **[NEW] `src/radiarch/models/optimization.py`** — Pydantic I/O models
4. **[NEW] `src/radiarch/api/routes/optimization.py`** — FastAPI route

---

## Service 5 — BAO Service (Beam Angle Optimization)

### Purpose
Search over beam geometries to find better beam angle configurations. BAO is an **outer loop** that repeatedly invokes Optimization + Dose services.

### Inputs

```
BAORunRequest:
  plan_id: str
  geometry_id: str
  dose_engine: DoseEngineSpec
  objectives: [ObjectiveSpec]
  search_space:
    modality: "PHOTON_IMRT" | "PROTON_PBS"
    # PHOTON
    candidate_gantry_angles: [float] | null   # Discrete set (null = 0-359 by 10°)
    num_beams: int
    couch_angles: [float] | null
    avoidance_sectors: [[float, float]] | null
    # PROTON
    candidate_field_angles: [float] | null
    field_count: int
  scoring:
    method: "FULL_OPTIMIZE" | "FAST_SURROGATE"
    surrogate_engine: str | null      # Faster engine for pruning
    full_engine: str | null           # Accurate engine for final candidates
  budget:
    max_candidates: int
    max_parallel: int
    time_limit_s: int | null
    strategy: "EXHAUSTIVE" | "RANDOM" | "BAYESIAN" | "GREEDY"
```

### Outputs

```
BAOResult:
  bao_id: str (uuid)
  ranked_candidates: [
    {
      rank: int,
      beam_set: BeamSetSpec,
      score: float,
      optimization_ref: str | null,   # Link to full optimization result
      metrics: dict
    }
  ]
  pareto_set: [...] | null           # Multi-objective Pareto front
  compute_time_s: float
  candidates_evaluated: int
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/bao/run` | Submit BAO search job |
| `GET` | `/api/v1/bao/jobs/{job_id}` | Poll job status |
| `GET` | `/api/v1/bao/{bao_id}` | Retrieve ranked results |

### What Exists Today
- **Nothing** — BAO is entirely new to the Radiarch codebase.

### What Must Be Built
1. **[NEW] `src/radiarch/services/bao.py`** — `BAOService` class
   - Search strategy implementations (exhaustive, random sampling, greedy beam addition, Bayesian)
   - Candidate evaluation: calls `OptimizationService.run()` or fast surrogate
   - Multi-candidate parallel execution via worker pool
   - Scoring and ranking
2. **[NEW] `src/radiarch/models/bao.py`** — Pydantic I/O models
3. **[NEW] `src/radiarch/api/routes/bao.py`** — FastAPI route

---

## Service 6 — Evaluation Service

### Purpose
Compute plan quality metrics (DVH, indices, constraint pass/fail) and generate review artifacts.

### Inputs

```
EvaluationRunRequest:
  plan_id: str
  dose_ref_uri: str                  # Primary dose to evaluate
  structure_masks_ref: str           # From geometry service
  structure_index: dict              # Structure name → label mapping
  prescription:
    targets: [{ structure: str, dose_gy: float, fractions: int }]
  constraints: [
    { structure: str, type: str, op: str, value_gy: float }
  ]
  scenarios: [                       # Robust evaluation (optional)
    { scenario_id: str, dose_ref_uri: str }
  ]
  reference_dose_uri: str | null     # Comparison dose (gamma analysis)
  gamma_criteria:
    dose_pct: float                  # Default 3.0
    distance_mm: float               # Default 3.0
  report_format: "JSON" | "PDF" | "HTML" | null
```

### Outputs

```
EvaluationResult:
  evaluation_id: str (uuid)
  dvh_curves: [
    {
      structure: str,
      dose_gy: [float],             # Dose axis
      volume_pct: [float],          # Volume axis
      d_min: float, d_max: float, d_mean: float,
      d95: float | null, d5: float | null, v20: float | null
    }
  ]
  constraint_table: [
    { structure: str, type: str, op: str, target: float, achieved: float, pass: bool }
  ]
  indices:
    homogeneity_index: float | null   # (D5-D95)/Dprescription
    conformity_index: float | null
  gamma_analysis:                    # Only if reference dose provided
    pass_rate_pct: float
    mean_gamma: float
    max_gamma: float
  robust_summary:                    # Only if scenarios provided
    per_scenario_dvh: [...]
    worst_case_constraints: [...]
    endpoint_bands: { structure: { metric: { min, max, mean } } }
  report_uri: str | null              # PDF/HTML report artifact
  dvh_ref_uri: str                    # Serialized DVH data
  metrics_ref_uri: str                # JSON summary
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/evaluate/run` | Submit evaluation job |
| `GET` | `/api/v1/evaluate/jobs/{job_id}` | Poll job status |
| `GET` | `/api/v1/evaluate/{eval_id}` | Retrieve metrics |
| `GET` | `/api/v1/evaluate/{eval_id}/dvh` | Retrieve DVH curves |

### What Exists Today
- [compute_dvh()](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py#L301-L342): Basic cumulative DVH for target ROI
- [export_rtdose()](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/workflows/_helpers.py#L243-L298): DICOM RTDOSE export
- DVH rendering in [demo/index.html](file:///home/yyan7/work/SMIS/radiarch/demo/index.html) (client-side SVG chart)

### What Must Be Built
1. **[NEW] `src/radiarch/services/evaluation.py`** — `EvaluationService` class
   - Per-structure DVH computation (extend existing `compute_dvh` to all structures)
   - Dose statistics: Dmin, Dmax, Dmean, D95, D5, Vxx
   - Constraint pass/fail checker against prescription
   - Homogeneity Index, Conformity Index
   - Gamma analysis (optional, via OpenTPS `gammaIndex`)
   - Robust evaluation: per-scenario DVHs, worst-case endpoint aggregation
   - Report generation (JSON always, PDF/HTML optional)
2. **[NEW] `src/radiarch/models/evaluation.py`** — Pydantic I/O models
3. **[NEW] `src/radiarch/api/routes/evaluation.py`** — FastAPI route
4. **[MODIFY] `_helpers.py`** — Refactor `compute_dvh` into `EvaluationService`

---

## Cross-Cutting: Scenario/Robustness Subsystem

### Shared Data Model

```python
class ScenarioSpec(BaseModel):
    scenario_id: str
    setup_shift_mm: list[float] = [0, 0, 0]   # [dx, dy, dz]
    range_scale_pct: float = 0.0                # ±% stopping power
    density_scale: float = 1.0                  # Multiplicative
    description: str = ""
```

### Scenario Generator

```python
def generate_scenarios(mode: str, params: RobustnessConfig) -> list[ScenarioSpec]:
    """
    Modes:
      - "PBS_DEFAULT": 9 scenarios (nominal + 6 setup shifts + 2 range)
      - "PBS_FULL": 21 scenarios (all combinations)
      - "IMRT_OPTIONAL": reduced set
    """
```

Used by both Dose Service (per-scenario computation) and Optimization Service (robust aggregation).

---

## Orchestrator Refactoring

### Current State
[RadiarchPlanner](file:///home/yyan7/work/SMIS/radiarch/src/radiarch/core/planner.py) dispatches to monolithic workflow `run()` functions.

### Target State
`RadiarchPlanner` becomes a **pipeline orchestrator** that chains service calls:

```
Pipeline("proton-impt-optimized"):
  1. GeometryService.build(patient_ref, grid_spec)  → geometry_id
  2. BeamModelService.build(geometry_id, beam_set)   → beam_model_id
  3. DoseService.build_influence(geometry_id, ...)   → influence_id
  4. OptimizationService.run(objectives, ...)        → weights, dose
  5. DoseService.compute(final weights)              → final_dose_id
  6. EvaluationService.run(dose, masks, constraints) → metrics, DVH
```

### Backward Compatibility
- The existing `POST /api/v1/plans` endpoint and demo UI remain functional
- Internally, `RadiarchPlanner.run()` calls the service pipeline instead of inline workflow code
- The old workflow modules become thin wrappers or gradually deprecate

---

## New Directory Structure

```
src/radiarch/
├── services/                    # [NEW] — The 6 TPS services
│   ├── __init__.py
│   ├── geometry.py              # Service 1
│   ├── beam_model.py            # Service 2
│   ├── dose.py                  # Service 3
│   ├── optimization.py          # Service 4
│   ├── bao.py                   # Service 5
│   ├── evaluation.py            # Service 6
│   ├── scenarios.py             # Cross-cutting robustness
│   └── engines/                 # Dose engine plugins
│       ├── __init__.py
│       ├── mcsquare_engine.py
│       ├── photon_ccc_engine.py
│       └── pyradplan_engine.py  # Future
├── models/
│   ├── geometry.py              # [NEW]
│   ├── beam_model.py            # [NEW]
│   ├── dose.py                  # [NEW]
│   ├── optimization.py          # [NEW]
│   ├── bao.py                   # [NEW]
│   ├── evaluation.py            # [NEW]
│   ├── scenario.py              # [NEW]
│   ├── plan.py                  # [MODIFY] — add references to service outputs
│   └── ...
├── api/routes/
│   ├── geometry.py              # [NEW]
│   ├── beam_model.py            # [NEW]
│   ├── dose.py                  # [NEW]
│   ├── optimization.py          # [NEW]
│   ├── bao.py                   # [NEW]
│   ├── evaluation.py            # [NEW]
│   └── ...
├── core/
│   ├── planner.py               # [MODIFY] — becomes pipeline orchestrator
│   ├── store.py                 # [MODIFY] — add artifact storage for new types
│   └── workflows/               # [DEPRECATE gradually] — keep for backward compat
└── tasks/
    ├── celery_app.py
    └── plan_tasks.py            # [MODIFY] — register new service tasks
```

---

## Phased Implementation Strategy

### Phase A — Foundation (Services 1 + 6)
Build Geometry and Evaluation first — they are the **input/output** bookends.

1. Create Pydantic models for `GeometryBuildRequest/Result` and `EvaluationRunRequest/Result`
2. Implement `GeometryService` by extracting from `_helpers.py`
3. Implement `EvaluationService` by extending `compute_dvh` with constraint checks
4. Add FastAPI routes and Celery task wrappers
5. Write unit tests for both services

### Phase B — Core Compute (Services 2 + 3)
Build Beam Model and Dose services — enables modular dose calculation.

1. Define `FluenceElementSet` abstraction and `DoseEnginePlugin` protocol
2. Implement `BeamModelService` for both proton and photon
3. Implement `DoseService` with MCsquare and CCC engine plugins
4. Add influence matrix caching
5. Wire into orchestrator pipeline

### Phase C — Optimization (Service 4)
Build the Optimization service — enables inverse planning.

1. Implement shared objective function library
2. Implement solver abstraction (L-BFGS-B, Adam)
3. Implement robust wrapper with scenario aggregation
4. Add async checkpointing
5. Wire into orchestrator for optimized workflows

### Phase D — BAO (Service 5)
Build Beam Angle Optimization — the outer-loop search.

1. Implement candidate generation strategies
2. Implement distributed evaluation via worker pool
3. Implement scoring and ranking
4. Add Pareto front tracking (optional)

---

## Verification Plan

### Existing Tests to Preserve
- [test_api_e2e.py](file:///home/yyan7/work/SMIS/radiarch/tests/test_api_e2e.py) — Full API integration tests (92 tests)
- [test_opentps_integration.py](file:///home/yyan7/work/SMIS/radiarch/tests/test_opentps_integration.py) — OpenTPS dose calculation tests
- [test_client.py](file:///home/yyan7/work/SMIS/radiarch/tests/test_client.py) — Client SDK tests

### New Tests Per Phase

| Phase | Test | Command |
|---|---|---|
| A | `tests/test_geometry_service.py` — unit tests for CT loading, density conversion, mask rasterization | `python -m pytest tests/test_geometry_service.py -v` |
| A | `tests/test_evaluation_service.py` — unit tests for DVH, constraint checks, indices | `python -m pytest tests/test_evaluation_service.py -v` |
| B | `tests/test_beam_model_service.py` — unit tests for spot/beamlet generation | `python -m pytest tests/test_beam_model_service.py -v` |
| B | `tests/test_dose_service.py` — unit tests for engine plugins, influence caching | `python -m pytest tests/test_dose_service.py -v` |
| C | `tests/test_optimization_service.py` — unit tests for objectives, solver, robustness | `python -m pytest tests/test_optimization_service.py -v` |
| D | `tests/test_bao_service.py` — unit tests for candidate search, scoring | `python -m pytest tests/test_bao_service.py -v` |
| All | Backward compatibility: `python -m pytest tests/test_api_e2e.py -v` must still pass | `python -m pytest tests/ -v` |

### Integration Verification
- Docker: `docker compose up --build -d` → submit plan via demo UI → verify DVH and dose overlay still work
- API: Each new service endpoint tested via `curl` or `httpie` commands

---

## Open Questions for User

> [!IMPORTANT]
> The following decisions affect implementation details and should be confirmed before starting Phase A.

1. **Storage backend for service artifacts**: Should we use local filesystem (`/data/artifacts/`) for v0.1, or set up MinIO/S3 now?
2. **Service deployment model**: Should all 6 services run in the same FastAPI process (monolith with logical separation), or as separate Docker containers from the start?
3. **pyRadPlan integration timeline**: Should we create the `pyradplan_engine.py` plugin slot in Phase B, or defer entirely?
4. **Database schema**: Should we extend the existing PostgreSQL schema with new tables (`geometry_builds`, `beam_models`, `dose_results`, `optimizations`, `evaluations`), or use a separate schema?
5. **Grid format**: NIfTI (`.nii.gz`) vs NumPy (`.npy`) vs HDF5 for density/dose grids?
