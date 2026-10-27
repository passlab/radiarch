from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .api.routes import info, plans, jobs, artifacts, workflows, sessions, geometry, beam_model, uploads, dose, optimization, bao, evaluation, rt, lineage, registration, four_d, replan, protocols
from .adapters import build_orthanc_adapter
from .api.security import api_key_auth
from .core.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.orthanc_adapter = build_orthanc_adapter(settings)
    init_db()
    yield


def create_app() -> FastAPI:
    from .build import release

    app = FastAPI(
        title=settings.project_name,
        version=release(),
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # /info stays open: service identity and the intended-use statement.
    # Everything else needs the API key once RADIARCH_API_KEY is set.
    app.include_router(info.router, prefix=settings.api_prefix)
    protected = [Depends(api_key_auth)]
    for router in (
        workflows.router,
        plans.router,
        jobs.router,
        artifacts.router,
        sessions.router,
        geometry.router,
        beam_model.router,
        uploads.router,
        dose.router,
        optimization.router,
        bao.router,
        evaluation.router,
        rt.router,
        lineage.router,
        registration.router,
        four_d.router,
        replan.router,
        protocols.router,
    ):
        app.include_router(router, prefix=settings.api_prefix, dependencies=protected)

    @app.get("/")
    async def root():
        return {"service": settings.project_name, "status": "ok"}

    return app
