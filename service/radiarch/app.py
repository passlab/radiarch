from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .api.routes import info, plans, jobs, artifacts
from .adapters import build_orthanc_adapter

settings = get_settings()


@asynccontextmanager
def lifespan(app: FastAPI):
    app.state.orthanc_adapter = build_orthanc_adapter(settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
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

    app.include_router(info.router, prefix=settings.api_prefix)
    app.include_router(plans.router, prefix=settings.api_prefix)
    app.include_router(jobs.router, prefix=settings.api_prefix)
    app.include_router(artifacts.router, prefix=settings.api_prefix)

    @app.get("/")
    async def root():
        return {"service": settings.project_name, "status": "ok"}

    return app
