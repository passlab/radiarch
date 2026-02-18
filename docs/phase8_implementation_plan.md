# Phase 8 — OpenTPS Feature Integration

Extend the Radiarch API and planner to expose OpenTPS's full treatment planning capabilities: **plan optimization**, **photon dose computation**, **dose delivery simulation**, and enhanced **dose constraints**.

## Background

Currently Radiarch supports one narrow path:
```
CT + RTStruct → Build proton plan (fixed geometry) → MCsquare dose → RTDOSE + DVH
```

OpenTPS provides much richer capabilities (see [Example Gallery](https://opentps.github.io/examples/auto_examples/index.html)) that are not yet exposed through the API.

---

## Proposed Changes

### Phase 8A — API Model Extensions & Plan Optimization

The highest-value feature: enables clinically meaningful plans with dose objectives.

#### [MODIFY] [plan.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/models/plan.py)

Extend `PlanRequest` with optimization parameters:

```python
class ObjectiveType(str, Enum):
    d_min = "DMin"        # Minimum dose to structure
    d_max = "DMax"        # Maximum dose to structure
    d_uniform = "DUniform" # Uniform dose
    dvh_min = "DVHMin"    # DVH-based minimum
    dvh_max = "DVHMax"    # DVH-based maximum

class DoseObjective(BaseModel):
    structure_name: str          # ROI name (e.g. "PTV", "SpinalCord")
    objective_type: ObjectiveType
    dose_gy: float               # Dose value
    weight: float = 1.0          # Optimization weight
    volume_fraction: Optional[float] = None  # For DVH objectives (0-1)

class PlanRequest(BaseModel):
    # ... existing fields ...
    objectives: Optional[List[DoseObjective]] = None  # If set → run optimizer
    optimization_method: str = "Scipy_L-BFGS-B"
    max_iterations: int = 50
    spot_spacing_mm: float = 5.0
    layer_spacing_mm: float = 5.0
    scoring_spacing_mm: List[float] = [2, 2, 2]
    nb_primaries: float = 1e4    # For beamlet calc (1e6 for final)
    nb_primaries_final: float = 1e6
```

Also add `PlanWorkflow` entries:
```python
class PlanWorkflow(str, Enum):
    proton_impt_basic = "proton-impt-basic"
    proton_impt_optimized = "proton-impt-optimized"  # NEW
    proton_robust = "proton-robust"                  # NEW
    photon_ccc = "photon-ccc"                        # NEW (implement)
```

#### [MODIFY] [planner.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/core/planner.py)

Add `_run_optimized_proton()` method using OpenTPS's optimization pipeline:

```
1. Load patient data (CT + RTStruct) from Orthanc
2. Configure MCsquareDoseCalculator (calibration, BDL, scoring grid)
3. Build ProtonPlanDesign (gantry angles, spot/layer spacing, target margin)
4. Compute beamlets: mc2.computeBeamlets(ct, plan, roi=[target, body])
5. Map API objectives → OpenTPS objectives (DMin, DMax, DUniform, DVHMin, DVHMax)
6. Run IntensityModulationOptimizer.optimize()
7. Final dose computation with high primaries (1e6)
8. Export RTDOSE, compute DVH
```

Key OpenTPS imports:
```python
from opentps.core.processing.planOptimization.planOptimization import IntensityModulationOptimizer
import opentps.core.processing.planOptimization.objectives.dosimetricObjectives as doseObj
from opentps.core.data.plan import ObjectivesList
```

#### [MODIFY] [plan_tasks.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/tasks/plan_tasks.py)

Update progress reporting stages for optimization:
- `loading_data` → `building_plan` → `computing_beamlets` → `optimizing` → `final_dose` → `exporting`

---

### Phase 8B — Photon CCC Dose Computation

Activate the `photon-ccc` workflow that is currently stub-only.

#### [MODIFY] [planner.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/core/planner.py)

Add `_run_photon_ccc()` method:

```
1. Load CT from Orthanc
2. Create PhotonPlan with PlanPhotonBeam + PlanPhotonSegment (MLC shapes)
3. Configure CCCDoseCalculator (CT calibration, batch size)
4. Compute dose: ccc.computeDose(ct, plan)
5. Export RTDOSE + DVH
```

Key OpenTPS imports:
```python
from opentps.core.processing.doseCalculation.photons.cccDoseCalculator import CCCDoseCalculator
from opentps.core.data.plan._photonPlan import PhotonPlan
from opentps.core.data.plan._planPhotonBeam import PlanPhotonBeam
from opentps.core.data.plan._planPhotonSegment import PlanPhotonSegment
```

Extend `PlanRequest` for MLC/photon-specific fields:
```python
class PlanRequest(BaseModel):
    # ... existing ...
    mlc_leaf_width_mm: float = 10.0   # For photon plans
    jaw_opening_mm: List[float] = [-50, 50]
    mu_per_beam: float = 5000
```

---

### Phase 8C — Robust Proton Optimization

Extends 8A with robustness scenarios for uncertainty analysis.

#### [MODIFY] [plan.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/models/plan.py)

Add robustness parameters:
```python
class RobustnessConfig(BaseModel):
    setup_systematic_error_mm: List[float] = [1.6, 1.6, 1.6]
    setup_random_error_mm: List[float] = [0.0, 0.0, 0.0]
    range_systematic_error_pct: float = 5.0
    selection_strategy: str = "REDUCED_SET"  # REDUCED_SET | ALL | RANDOM
    num_scenarios: int = 5
```

#### [MODIFY] [planner.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/core/planner.py)

Add `_run_robust_proton()`:
```
1. Same as 8A but configure planDesign.robustness = RobustnessProton()
2. Use mc2.computeRobustScenarioBeamlets() instead of computeBeamlets()
3. Optimize with robust scenarios included
4. Return worst-case DVH bands in QA summary
```

Key OpenTPS imports:
```python
from opentps.core.data.plan import RobustnessProton
```

---

### Phase 8D — Dose Delivery Simulation

PBS delivery timing and 4D dose simulation for motion management.

#### [NEW] [simulation.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/models/simulation.py)

New request/response models:
```python
class SimulationRequest(BaseModel):
    plan_id: str                          # Reference to completed plan
    simulation_type: str = "4d_dose"      # "4d_dose" | "4d_dynamic" | "fractionation"
    num_fractions: int = 5
    num_starting_phases: int = 3
    num_fractionation_scenarios: int = 7

class SimulationResult(BaseModel):
    id: str
    plan_id: str
    type: str
    status: str
    dvh_bands: Optional[dict] = None      # Min/max/nominal DVH per structure
    timing_data: Optional[dict] = None    # PBS spot delivery times
```

#### [NEW] [simulations.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/api/routes/simulations.py)

New API endpoints:
- `POST /api/v1/simulations` — submit a delivery simulation job
- `GET /api/v1/simulations/{sim_id}` — get simulation status/results

#### [NEW] [simulator.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/core/simulator.py)

Wrapper around OpenTPS's `PlanDeliverySimulation`:
```python
from opentps.core.processing.planDeliverySimulation.planDeliverySimulation import PlanDeliverySimulation
```

---

### Phase 8E — Enhanced API & Workflow Registry

#### [MODIFY] [workflows.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/api/routes/workflows.py)

Update workflow registry with new workflows and their parameter schemas.

#### [MODIFY] [info.py](file:///home/yyan7/work/SMIS/radiarch/service/radiarch/api/routes/info.py)

Update `/info` models to reflect new capabilities.

---

## Phasing Summary

| Phase | Feature | Effort | Priority |
|-------|---------|--------|----------|
| **8A** | Proton IMPT optimization | 3–4 days | 🔴 Critical — makes plans clinically meaningful |
| **8B** | Photon CCC dose | 2 days | 🟡 Medium — second modality |
| **8C** | Robust optimization | 2 days | 🟡 Medium — builds on 8A |
| **8D** | Delivery simulation | 2–3 days | 🟢 Low — research/QA feature |
| **8E** | API cleanup & workflow registry | 1 day | 🟢 Low — polish |

> [!IMPORTANT]
> All of 8A–8D require a working OpenTPS + MCsquare installation inside the Docker image (or volume-mounted). The current Docker setup uses `RADIARCH_FORCE_SYNTHETIC=true` because MCsquare is not bundled. You'll need to either:
> 1. Volume-mount the OpenTPS venv into the container
> 2. Build a Docker image that includes OpenTPS + MCsquare

## Verification Plan

### Automated Tests
- Extend `test_api_e2e.py` with optimization parameter tests (synthetic mode)
- Add integration tests that run against real OpenTPS (marked `@pytest.mark.opentps`)
- Test new `photon-ccc` workflow endpoint

### Manual Verification
- Submit an optimized plan via `curl` and verify the optimizer runs to convergence
- Compare DVH before/after optimization
- Verify RTDOSE is uploadable to Orthanc and viewable in OHIF
