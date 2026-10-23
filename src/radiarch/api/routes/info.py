from fastapi import APIRouter

from ...config import get_settings
from ...models.common import RESEARCH_USE_ONLY
from ...services.dose_engines.registry import engine_health

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
                "description": "Photon dose via the WiscPlan collapsed-cone engine, run as a subprocess",
                "status": "available" if engine_health("ccc").get("available") else "unavailable",
                "type": "dose_calculation",
            },
            "photon-pb": {
                "description": "Photon dose via radiarch's own pencil-beam engine (SVD kernels, NumPy/CuPy); VMAT control-point doses",
                "status": "available" if engine_health("pb").get("available") else "unavailable",
                "type": "dose_calculation",
            },
        },
        "workflows": [
            {
                "id": "proton-impt-basic",
                "name": "Proton IMPT (3-beam)",
                "description": "Proton plan with spots on the target and MCsquare dose",
            },
            {
                "id": "photon-ccc",
                "name": "Photon 9-field",
                "description": "Photon plan of open fields with dose from the CCC engine",
            },
        ],
    }
