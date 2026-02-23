"""Workflow registry: typed definitions, parameter schema, and lookup utilities.

Phase 8E refactoring: replaces the flat AVAILABLE_WORKFLOWS list with a structured
WorkflowRegistry class that supports lookup, validation, and schema export.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# Typed parameter schema
# ---------------------------------------------------------------------------

class ParameterType(str, Enum):
    number = "number"
    integer = "integer"
    string = "string"
    boolean = "boolean"


class WorkflowParameter(BaseModel):
    """Typed parameter definition with metadata for UI rendering."""
    name: str
    label: str
    type: ParameterType = ParameterType.number
    default: Union[float, int, str, bool, None] = None
    description: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    units: Optional[str] = None


class Workflow(BaseModel):
    """Workflow definition with typed metadata."""
    id: str
    name: str
    description: str
    modality: str           # "proton" | "photon"
    engine: str             # "mcsquare" | "ccc"
    category: str = "dose"  # "dose" | "optimization" | "robust" | "simulation"
    default_parameters: List[WorkflowParameter] = []


# ---------------------------------------------------------------------------
# Registry: single source of truth for all workflows
# ---------------------------------------------------------------------------

class WorkflowRegistry:
    """Central registry for workflow definitions.

    Usage:
        registry = WorkflowRegistry()
        registry.register(workflow)
        wf = registry.get("proton-impt-basic")
        all_wfs = registry.list()
    """

    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}

    def register(self, workflow: Workflow) -> None:
        """Register a workflow (overwrites existing with the same id)."""
        self._workflows[workflow.id] = workflow

    def get(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    def list(self) -> List[Workflow]:
        return list(self._workflows.values())

    def ids(self) -> List[str]:
        return list(self._workflows.keys())

    def __len__(self) -> int:
        return len(self._workflows)

    def __contains__(self, workflow_id: str) -> bool:
        return workflow_id in self._workflows


# Singleton registry instance
registry = WorkflowRegistry()


# ---------------------------------------------------------------------------
# Built-in workflow definitions
# ---------------------------------------------------------------------------

# Common parameters
_SPOT_SPACING = WorkflowParameter(
    name="spot_spacing", label="Spot Spacing (mm)", default=5.0, units="mm",
)
_LAYER_SPACING = WorkflowParameter(
    name="layer_spacing", label="Layer Spacing (mm)", default=5.0, units="mm",
)
_OPTIMIZER = WorkflowParameter(
    name="optimization_method", label="Optimizer",
    type=ParameterType.string, default="Scipy_L-BFGS-B",
    description="Optimization algorithm",
)
_MAX_ITER = WorkflowParameter(
    name="max_iterations", label="Max Iterations",
    type=ParameterType.integer, default=50, min_value=1, max_value=500,
)

# Register workflows
registry.register(Workflow(
    id="proton-impt-basic",
    name="Proton IMPT (basic)",
    description="Single/multi-beam proton plan using MCsquare dose engine — no optimization",
    modality="proton",
    engine="mcsquare",
    category="dose",
    default_parameters=[
        WorkflowParameter(name="gantry_angle", label="Gantry Angle (°)", default=0.0, units="deg"),
        WorkflowParameter(name="couch_angle", label="Couch Angle (°)", default=0.0, units="deg"),
        _SPOT_SPACING,
        WorkflowParameter(
            name="nb_primaries", label="MC Primaries",
            type=ParameterType.integer, default=10000,
            description="Number of Monte Carlo primaries for dose calculation",
        ),
    ],
))

registry.register(Workflow(
    id="proton-impt-optimized",
    name="Proton IMPT Optimized",
    description="Multi-beam proton plan with IMPT optimization using beamlet interaction matrix and L-BFGS-B solver",
    modality="proton",
    engine="mcsquare",
    category="optimization",
    default_parameters=[
        _SPOT_SPACING,
        _LAYER_SPACING,
        _OPTIMIZER,
        _MAX_ITER,
        WorkflowParameter(
            name="nb_primaries_beamlets", label="Beamlet Primaries",
            type=ParameterType.integer, default=10000,
        ),
        WorkflowParameter(
            name="nb_primaries_final", label="Final Primaries",
            type=ParameterType.integer, default=1000000,
        ),
    ],
))

registry.register(Workflow(
    id="proton-robust",
    name="Proton Robust Optimization",
    description="Robust proton optimization with setup/range error scenarios for uncertainty management",
    modality="proton",
    engine="mcsquare",
    category="robust",
    default_parameters=[
        _SPOT_SPACING,
        _OPTIMIZER,
        _MAX_ITER,
        WorkflowParameter(
            name="range_systematic_error_pct", label="Range Error (%)",
            default=5.0, min_value=0.0, max_value=20.0, units="%",
        ),
        WorkflowParameter(
            name="num_scenarios", label="Robustness Scenarios",
            type=ParameterType.integer, default=5, min_value=1, max_value=21,
        ),
    ],
))

registry.register(Workflow(
    id="photon-ccc",
    name="Photon CCC Dose",
    description="Photon plan using collapsed-cone convolution (CCC) dose engine for conformal therapy",
    modality="photon",
    engine="ccc",
    category="dose",
    default_parameters=[
        WorkflowParameter(
            name="mlc_leaf_width_mm", label="MLC Leaf Width (mm)",
            default=10.0, units="mm",
        ),
        WorkflowParameter(
            name="mu_per_beam", label="MU per Beam",
            default=5000.0, min_value=100.0,
        ),
    ],
))


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[Workflow])
async def list_workflows():
    """List available planning workflow templates."""
    return registry.list()


@router.get("/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str):
    wf = registry.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return wf
