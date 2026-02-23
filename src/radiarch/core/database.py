"""SQLAlchemy database engine and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from ..config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def _build_engine():
    settings = get_settings()
    url = settings.database_url
    if not url:
        return None
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, echo=False)


_engine = None
SessionLocal = None


def get_engine():
    global _engine, SessionLocal
    if _engine is None:
        _engine = _build_engine()
        if _engine is not None:
            SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_db():
    """Yield a SQLAlchemy session (for use as a FastAPI dependency)."""
    engine = get_engine()
    if engine is None or SessionLocal is None:
        raise RuntimeError("Database not configured")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """Create all tables from ORM metadata. Called during app lifespan startup."""
    engine = get_engine()
    if engine is not None:
        from . import db_models  # noqa: F401 — ensure models are registered
        Base.metadata.create_all(bind=engine)
