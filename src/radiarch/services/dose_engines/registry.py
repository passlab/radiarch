"""Engine registry — name → :class:`DoseEnginePlugin` instance.

Tiny and module-global on purpose. Engines self-register at import time
by calling :func:`register_engine`. Tests can reset the registry via
:func:`reset_registry`.

A registered engine is *the* engine for that name; we don't support
multiple versions side-by-side (versioning lives inside the engine and
is folded into cache keys via ``DoseEnginePlugin.version``).
"""

from __future__ import annotations

from typing import Dict, List

from .protocol import DoseEnginePlugin


class EngineRegistryError(KeyError):
    """Raised when a requested engine isn't registered."""


class TestOnlyEngineError(ValueError):
    """Raised when a test-only engine is requested outside development."""


_REGISTRY: Dict[str, DoseEnginePlugin] = {}


def register_engine(engine: DoseEnginePlugin) -> None:
    """Register an engine. Overwrites any existing entry with the same name."""
    if not engine.name:
        raise ValueError("engine.name must be non-empty")
    _REGISTRY[engine.name] = engine


def get_engine(name: str) -> DoseEnginePlugin:
    """Look up a registered engine by name."""
    if name not in _REGISTRY:
        raise EngineRegistryError(
            f"Engine {name!r} is not registered. "
            f"Available: {sorted(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]


def ensure_engine_allowed(engine: DoseEnginePlugin) -> None:
    """Refuse engines flagged ``test_only`` unless the deployment allows them.

    The analytic engine has the right shape and the wrong physics by design;
    it exists for the test suite. ``RADIARCH_ALLOW_TEST_ENGINES`` defaults to
    true only when ``RADIARCH_ENVIRONMENT=dev``.
    """
    if not getattr(engine, "test_only", False):
        return
    from ...config import get_settings  # lazy — the registry imports without settings

    settings = get_settings()
    if settings.allow_test_engines:
        return
    raise TestOnlyEngineError(
        f"Engine {engine.name!r} is a test-only engine (wrong physics by design) "
        f"and is refused when RADIARCH_ENVIRONMENT={settings.environment!r}. "
        "Set RADIARCH_ALLOW_TEST_ENGINES=1 only for development."
    )


def list_engines() -> List[str]:
    """Return registered engine names, sorted."""
    return sorted(_REGISTRY.keys())


def get_all_engines() -> Dict[str, DoseEnginePlugin]:
    """Return a snapshot of the registry. Safe for serialization."""
    return dict(_REGISTRY)


def engine_health(name: str) -> dict:
    """Return a health-check payload for one engine.

    Calls ``engine.health()`` if the engine implements it; otherwise
    synthesizes a minimal payload from the public fields (name,
    version, modalities). Used by :func:`/dose/engines` (D6.7).

    Always returns a dict — never raises — because health-check
    endpoints are called when *things might be broken* and the worst
    thing they can do is also break.
    """
    try:
        engine = get_engine(name)
    except EngineRegistryError:
        return {"name": name, "registered": False, "available": False}

    health_fn = getattr(engine, "health", None)
    if callable(health_fn):
        try:
            payload = dict(health_fn())
        except Exception as exc:  # never trust an engine's health method
            payload = {
                "name": engine.name,
                "version": getattr(engine, "version", "unknown"),
                "available": False,
                "health_error": f"{type(exc).__name__}: {exc}",
            }
    else:
        payload = {
            "name": engine.name,
            "version": getattr(engine, "version", "unknown"),
            "modalities": list(getattr(engine, "modalities", [])),
            "available": True,
        }
    payload["registered"] = True
    payload.setdefault("test_only", bool(getattr(engine, "test_only", False)))
    return payload


def reset_registry() -> None:
    """Drop all registered engines. Tests only."""
    _REGISTRY.clear()


__all__ = [
    "EngineRegistryError",
    "TestOnlyEngineError",
    "ensure_engine_allowed",
    "register_engine",
    "get_engine",
    "get_all_engines",
    "engine_health",
    "list_engines",
    "reset_registry",
]
