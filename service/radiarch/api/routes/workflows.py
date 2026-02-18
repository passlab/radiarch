from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional


router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowParameter(BaseModel):
    name: str
    label: str
    type: str = "number"
    default: float | int | str | None = None
    description: str = ""


class Workflow(BaseModel):
    id: str
    name: str
    description: str
    modality: str
    engine: str
    default_parameters: List[WorkflowParameter] = []


AVAILABLE_WORKFLOWS: List[Workflow] = [
    Workflow(
        id="proton-impt-basic",
        name="Proton IMPT (single beam)",
        description="Single-beam proton plan using OpenTPS ProtonPlanDesign with MCsquare dose engine",
        modality="proton",
        engine="mcsquare",
        default_parameters=[
            WorkflowParameter(name="gantry_angle", label="Gantry Angle (deg)", default=0.0),
            WorkflowParameter(name="couch_angle", label="Couch Angle (deg)", default=0.0),
            WorkflowParameter(name="spot_spacing", label="Spot Spacing (mm)", default=5.0),
            WorkflowParameter(name="nb_primaries", label="MC Primaries", type="integer", default=10000,
                              description="Number of Monte Carlo primaries for dose calculation"),
        ],
    ),
    Workflow(
        id="photon-ccc",
        name="Photon 9-field",
        description="Photon plan using collapsed cone convolution dose engine (not yet implemented)",
        modality="photon",
        engine="ccc",
        default_parameters=[],
    ),
]


@router.get("", response_model=List[Workflow])
async def list_workflows():
    """List available planning workflow templates."""
    return AVAILABLE_WORKFLOWS


@router.get("/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str):
    for wf in AVAILABLE_WORKFLOWS:
        if wf.id == workflow_id:
            return wf
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
