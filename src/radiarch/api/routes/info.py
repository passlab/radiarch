from fastapi import APIRouter

from ...config import get_settings
from ...models.common import RESEARCH_USE_ONLY

router = APIRouter(tags=["info"])
settings = get_settings()


@router.get("/info")
async def service_info():
    """Service identity. Open (no API key): it carries the intended-use statement."""
    return {
        "name": settings.project_name,
        "version": "0.1.0",
        "environment": settings.environment,
        "intended_use": RESEARCH_USE_ONLY,
        "models": {
            "proton-mcsquare": {
                "description": "Proton PBS dose via the MCsquare Monte Carlo engine",
                "status": "available",
                "type": "dose_calculation",
            },
            "photon-ccc": {
                "description": "Photon dose via the WiscPlan collapsed-cone engine (stub; wired in roadmap item R1)",
                "status": "unavailable",
                "type": "dose_calculation",
            },
        },
        "workflows": [
            {
                "id": "proton-impt-basic",
                "name": "Proton IMPT (3-beam)",
                "description": "Proton plan using OpenTPS ProtonPlanDesign with MCsquare dose",
            },
            {
                "id": "photon-ccc",
                "name": "Photon 9-field",
                "description": "Photon plan using the CCC dose engine (not yet producing dose)",
            },
        ],
    }
