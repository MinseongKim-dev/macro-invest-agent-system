"""Storage repository interface for normalized external events (Chapter 7).

Defines the abstract contract that all event repository implementations must
satisfy.  The primary implementation is the in-memory store in
:mod:`adapters.repositories.in_memory_event_store`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.events.enums import ExternalEventStatus, ExternalEventType
from domain.events.models import NormalizedExternalEvent


class EventRepositoryInterface(ABC):
    """Abstract repository for persisting and querying normalized external events."""

    @abstractmethod
    def save(self, event: NormalizedExternalEvent) -> None:
        """Persist *event*.  Idempotent on ``event_id``."""

    @abstractmethod
    def get_by_id(self, event_id: str) -> NormalizedExternalEvent | None:
        """Return the event for *event_id*, or ``None`` if not found."""

    @abstractmethod
    def list_recent(
        self,
        *,
        limit: int = 50,
        event_type: ExternalEventType | None = None,
        status: ExternalEventStatus | None = None,
        region: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[NormalizedExternalEvent]:
        """Return recent events matching filters, ordered by ``occurred_at`` descending.

        Args:
            limit: Maximum number of results (default 50).
            event_type: Filter by event category.
            status: Filter by lifecycle status.
            region: Filter by region string (exact match).
            since: Include events at or after this UTC datetime.
            until: Include events at or before this UTC datetime.

        Returns:
            List of matching events, most recent first.
        """

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored events (used in tests)."""
