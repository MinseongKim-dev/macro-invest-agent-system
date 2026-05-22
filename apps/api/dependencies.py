"""FastAPI dependency providers for the analyst-facing product API.

These callables are injected into route handlers via ``Depends()`` so that
service construction is centralised, testable, and overridable in tests.

All provided services are read-only.  No write-capable services or
mutable state should be added here.

Usage::

    from apps.api.dependencies import get_macro_service, get_signal_service

    @router.get("/api/snapshots/latest")
    async def latest_snapshot(
        macro_service: MacroServiceInterface = Depends(get_macro_service),
    ) -> SnapshotLatestResponse:
        ...
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from src.agent.adapters.repositories.in_memory_alert_store import InMemoryAlertStore
from src.agent.adapters.repositories.in_memory_event_store import InMemoryEventStore
from src.agent.adapters.repositories.in_memory_explanation_store import InMemoryExplanationStore
from src.agent.adapters.repositories.in_memory_macro_regime_store import InMemoryMacroRegimeStore
from src.agent.adapters.repositories.in_memory_macro_snapshot_store import (
    InMemoryMacroSnapshotStore,
)
from src.core.storage.repositories.alert_repository import AlertRepositoryInterface
from src.core.storage.repositories.event_repository import EventRepositoryInterface
from src.core.storage.repositories.explanation_repository import ExplanationRepositoryInterface
from src.services.interfaces import (
    MacroServiceInterface,
    RegimeServiceInterface,
    SignalServiceInterface,
)
from src.services.macro_regime_service import MacroRegimeService
from src.services.macro_service import MacroService
from src.services.signal_service import SignalService


@lru_cache(maxsize=1)
def _macro_service_singleton() -> MacroService:
    """Return a cached :class:`~services.macro_service.MacroService` instance."""
    return MacroService()


@lru_cache(maxsize=1)
def _signal_service_singleton() -> SignalService:
    """Return a cached :class:`~services.signal_service.SignalService` instance."""
    return SignalService()


@lru_cache(maxsize=1)
def _snapshot_store_singleton() -> InMemoryMacroSnapshotStore:
    """Return the shared in-memory snapshot store.

    Exposed so the startup seeder can write into the same instance that
    :func:`_regime_service_singleton` reads from.
    """
    return InMemoryMacroSnapshotStore()


@lru_cache(maxsize=1)
def _regime_store_singleton() -> InMemoryMacroRegimeStore:
    """Return the shared in-memory regime store."""
    return InMemoryMacroRegimeStore()


@lru_cache(maxsize=1)
def _regime_service_singleton() -> MacroRegimeService:
    """Return a cached phase-3 regime service with in-memory repositories."""
    return MacroRegimeService(
        snapshot_repository=_snapshot_store_singleton(),
        regime_repository=_regime_store_singleton(),
    )


@lru_cache(maxsize=1)
def _alert_store_singleton() -> InMemoryAlertStore:
    """Return the shared in-memory alert store."""
    return InMemoryAlertStore()


@lru_cache(maxsize=1)
def _event_store_singleton() -> InMemoryEventStore:
    """Return the shared in-memory external event store."""
    return InMemoryEventStore()


@lru_cache(maxsize=1)
def _explanation_store_singleton() -> InMemoryExplanationStore:
    """Return the shared in-memory explanation store.

    This singleton is shared between the explanations router and the signals
    router so that explanations registered during a signal run can be
    retrieved via ``GET /api/explanations/{id}``.
    """
    return InMemoryExplanationStore()


def get_macro_service() -> MacroServiceInterface:
    """FastAPI dependency: provide the macro data service.

    Returns a shared :class:`~services.macro_service.MacroService` instance.
    Override in tests with ``app.dependency_overrides[get_macro_service]``.
    """
    return _macro_service_singleton()


def get_signal_service() -> SignalServiceInterface:
    """FastAPI dependency: provide the signal evaluation service.

    Returns a shared :class:`~services.signal_service.SignalService` instance.
    Override in tests with ``app.dependency_overrides[get_signal_service]``.
    """
    return _signal_service_singleton()


def get_regime_service() -> RegimeServiceInterface:
    """FastAPI dependency: provide the regime service."""
    return _regime_service_singleton()


def get_alert_repository() -> AlertRepositoryInterface:
    """FastAPI dependency: provide the shared alert repository.

    Returns the :class:`~adapters.repositories.in_memory_alert_store.InMemoryAlertStore`
    singleton.  Override in tests with::

        app.dependency_overrides[get_alert_repository] = lambda: my_test_store
    """
    return _alert_store_singleton()


def get_event_repository() -> EventRepositoryInterface:
    """FastAPI dependency: provide the shared external event repository.

    Returns the :class:`~adapters.repositories.in_memory_event_store.InMemoryEventStore`
    singleton.  Override in tests with::

        app.dependency_overrides[get_event_repository] = lambda: my_test_store
    """
    return _event_store_singleton()


def get_explanation_repository() -> ExplanationRepositoryInterface:
    """FastAPI dependency: provide the shared explanation repository.

    Returns the :class:`~adapters.repositories.in_memory_explanation_store.InMemoryExplanationStore`
    singleton.  Override in tests with::

        app.dependency_overrides[get_explanation_repository] = lambda: my_test_store

    The same store instance is used by both the explanations router and the
    signals router, ensuring that explanations registered during a signal run
    are immediately retrievable via the explanations API.
    """
    return _explanation_store_singleton()


# Re-export for convenience
__all__ = [
    "get_alert_repository",
    "get_event_repository",
    "get_macro_service",
    "get_signal_service",
    "get_regime_service",
    "get_explanation_repository",
    "get_snapshot_store",
    "Depends",
]


def get_snapshot_store() -> InMemoryMacroSnapshotStore:
    """FastAPI dependency: provide the shared snapshot store.

    Used by the startup seeder to populate the same store that the regime
    service reads from.
    """
    return _snapshot_store_singleton()
