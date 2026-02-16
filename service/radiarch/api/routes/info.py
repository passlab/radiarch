from fastapi import APIRouter

from ...config import get_settings

router = APIRouter(tags=["info"])
settings = get_settings()


@router.get("/info")
async def service_info():
    return {
        "name": settings.project_name,
        "version": "0.1.0",
        "environment": settings.environment,
        "workflows": [
            {
                "id": "proton-impt-basic",
                "name": "Proton IMPT (3-beam)",
                "description": "Proton plan using OpenTPS ProtonPlanDesign with MCsquare dose",
            },
            {
                "id": "photon-ccc",
                "name": "Photon 9-field",
                "description": "Photon plan using CCC dose engine",
            },
        ],
    }
