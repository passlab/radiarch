from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from .config import get_settings
from .api.routes import info, plans, jobs, artifacts, workflows, sessions, geometry, beam_model, uploads, dose, optimization, bao, evaluation, rt, lineage, registration, four_d, replan, protocols, mco
from .adapters import build_orthanc_adapter
from .api.access import access_guard
from .api.security import api_key_auth, user_header_untrusted
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

    # A user header without the trusted proxy's secret is refused on every route, not only where the user is read.
    # Registered before CORS, so CORS stays the outer layer and the refusal carries its headers.
    @app.middleware("http")
    async def refuse_untrusted_user(request: Request, call_next):
        if user_header_untrusted(request):
            logger.warning(f"untrusted user header refused: path={request.url.path} method={request.method}")
            return JSONResponse(status_code=401, content={"detail": "untrusted user header"})
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # /info stays open: service identity and the intended-use statement.
    # Everything else needs the API key once RADIARCH_API_KEY is set, and, once RADIARCH_ACCESS_URL is set, a user the
    # host lets see every study the request's results trace to (ADR 0021).
    app.include_router(info.router, prefix=settings.api_prefix)
    if settings.access_url and not (settings.trusted_user_header and settings.trusted_proxy_secret):
        logger.warning("RADIARCH_ACCESS_URL is set without the trusted proxy's user header and secret: every request is refused")
    protected = [Depends(api_key_auth), Depends(access_guard)]
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
        mco.router,
    ):
        app.include_router(router, prefix=settings.api_prefix, dependencies=protected)

    @app.get("/")
    async def root():
        return {"service": settings.project_name, "status": "ok"}

    return app
