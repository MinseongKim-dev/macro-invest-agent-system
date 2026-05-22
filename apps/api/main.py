"""FastAPI application entry point for the macro-invest-agent-platform.

Exposes:
- ``GET /health``                          — liveness probe.
- ``GET /readiness``                       — readiness probe.
- ``GET /metrics``                         — Prometheus metrics scrape endpoint.
- ``GET /api/snapshots/latest``            — latest macro snapshot (analyst read).
- ``POST /api/snapshots/compare``          — snapshot comparison (analyst read).
- ``GET /api/signals/latest``              — latest regime-grounded signal evaluations.
- ``GET /api/regimes/latest``              — latest persisted macro regime (analyst read).
- ``GET /api/regimes/compare``             — current-vs-prior regime transition + change delta.
- ``GET /api/regimes/history``             — recent regime history list (analyst read).
- ``GET /api/explanations/regime/latest``  — analyst narrative for current regime.
- ``GET /api/explanations/run/{run_id}``   — all explanations for a run.
- ``GET /api/explanations/{id}``           — explanation by ID.
- ``GET /api/alerts/recent``                — recent alert events (queryable by type/severity/country/time).
- ``GET /api/alerts/{id}``                  — alert event by ID.
- ``PATCH /api/alerts/{id}/acknowledge``    — mark alert as acknowledged (analyst-facing).
- ``PATCH /api/alerts/{id}/snooze``         — snooze alert until a datetime (analyst-facing).
- ``GET /api/events/recent``               — recent normalized external events (queryable by type/status/region/time).
- ``GET /api/events/{id}``                 — external event by ID.
- ``GET /api/sessions/{id}``               — session context by ID (analyst read).

Usage::

    uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

Environment variables are read from ``.env`` via :mod:`core.config.settings`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from apps.api.dependencies import (
    _regime_service_singleton,
    _snapshot_store_singleton,
)
from apps.api.routers import alerts as alerts_router
from apps.api.routers import events as events_router
from apps.api.routers import explanations as explanations_router
from apps.api.routers import regimes as regimes_router
from apps.api.routers import sessions as sessions_router
from apps.api.routers import signals as signals_router
from apps.api.routers import snapshots as snapshots_router
from apps.api.routers import stream as stream_router
from apps.api.startup_seeder import SeedStatus, seed_regime_from_synthetic_observations
from core.config.settings import get_settings
from core.logging.logger import get_logger
from core.tracing.tracer import configure_tracing
from services.macro_snapshot_service import MacroSnapshotService

_log = get_logger(__name__)
_settings = get_settings()

# ---------------------------------------------------------------------------
# Application-level mutable state (set once during lifespan startup)
# ---------------------------------------------------------------------------

_seed_status: SeedStatus | None = None

# ---------------------------------------------------------------------------
# Lifespan: seed in-memory stores on startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """Seed the in-memory regime store on application startup.

    The in-memory snapshot/regime stores are empty at boot.  This hook
    seeds them with a synthetic macro snapshot and a derived regime so
    that ``GET /api/regimes/latest`` returns a real response from the
    first request onwards.

    The seeder is controlled by the ``SEED_ON_STARTUP`` environment variable
    (default: ``True``).  Set ``SEED_ON_STARTUP=false`` in production
    environments that rely on a real ingestion pipeline.

    Failure contract
    ----------------
    If seeding fails the application continues running but ``_seed_status``
    records the failure.  ``GET /readiness`` surfaces this as a warning
    so operators can observe the degraded bootstrap state.
    """
    global _seed_status  # noqa: PLW0603
    if not _settings.seed_on_startup:
        _log.info("startup_seeder_disabled", reason="SEED_ON_STARTUP=false")
        yield
        return
    snapshot_store = _snapshot_store_singleton()
    regime_service = _regime_service_singleton()
    snapshot_service = MacroSnapshotService(repository=snapshot_store)
    status = await seed_regime_from_synthetic_observations(
        snapshot_service=snapshot_service,
        regime_service=regime_service,
    )
    _seed_status = status
    if status.success:
        if status.skipped:
            _log.info("startup_seeder_skipped_already_populated")
        else:
            _log.info("startup_seeder_complete", regime_id=status.regime_id)
    else:
        _log.warning("startup_seeder_failed", error=status.error)
    yield


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

configure_tracing(_settings)

app = FastAPI(
    title="macro-invest-agent-platform",
    version="0.1.0",
    description=(
        "Macroeconomic investment agent platform — analyst-facing read API. "
        "Provides read-only access to macro observations/snapshots and regime outputs. "
        "Signals are regime-grounded; explanations are analyst-facing narratives."
    ),
    docs_url="/docs",
    redoc_url=None,
    lifespan=_lifespan,
)

# ---------------------------------------------------------------------------
# Register analyst-facing routers
# ---------------------------------------------------------------------------

app.include_router(snapshots_router.router)
app.include_router(signals_router.router)
app.include_router(explanations_router.router)
app.include_router(sessions_router.router)
app.include_router(regimes_router.router)
app.include_router(alerts_router.router)
app.include_router(events_router.router)
app.include_router(stream_router.router)


# ---------------------------------------------------------------------------
# Health and readiness probes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return ``{"status": "ok"}`` to confirm the process is alive.

    Kubernetes liveness probes should call this endpoint.  It performs no
    dependency checks — it only verifies that the application process and
    event loop are running.
    """
    return {"status": "ok"}


@app.get("/readiness", tags=["ops"], summary="Readiness probe")
async def readiness() -> dict[str, str]:
    """Return readiness status, confirming configuration is valid.

    Includes bootstrap seeder status so operators can observe whether the
    startup seeder succeeded, was skipped (store already populated), or
    failed (degraded state — regime data may be unavailable).
    """
    seed_state = "not_run"
    if _seed_status is not None:
        if _seed_status.skipped:
            seed_state = "skipped_already_populated"
        elif _seed_status.success:
            seed_state = "ok"
        else:
            seed_state = f"degraded:{_seed_status.error or 'unknown'}"
    return {"status": "ready", "env": _settings.app_env.value, "seed_status": seed_state}


@app.get("/metrics", tags=["ops"], summary="Prometheus metrics scrape endpoint")
async def metrics() -> Response:
    """Expose all registered Prometheus metrics in Prometheus text format.

    Configure your Prometheus scrape job to call ``GET /metrics``.

    When ``METRICS_ENABLED=false`` the endpoint returns an empty 200 response
    so scrape jobs do not fail while metrics are disabled.
    """
    if not _settings.metrics_enabled:
        return Response(content="", media_type="text/plain")

    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
