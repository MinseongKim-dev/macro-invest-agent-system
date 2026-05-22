"""In-memory external event store — development and test implementation.

This is the default
:class:`~storage.repositories.event_repository.EventRepositoryInterface`
implementation.  All state is lost on process restart.

Used
----
* Default dependency-injected repository in dev and test environments.

Not suitable for
----------------
* Production deployments requiring audit trails across restarts.
* Multi-process deployments (each process has its own isolated store).
"""

from __future__ import annotations

from datetime import UTC, datetime

from domain.events.enums import ExternalEventStatus, ExternalEventType
from domain.events.models import NormalizedExternalEvent
from storage.repositories.event_repository import EventRepositoryInterface


class InMemoryEventStore(EventRepositoryInterface):
    """In-memory implementation of :class:`EventRepositoryInterface`.

    Thread safety
    -------------
    Not thread-safe.  The GIL provides basic protection in CPython for
    single-process asyncio applications.
    """

    def __init__(self) -> None:
        self._store: dict[str, NormalizedExternalEvent] = {}

    # ------------------------------------------------------------------
    # EventRepositoryInterface
    # ------------------------------------------------------------------

    def save(self, event: NormalizedExternalEvent) -> None:
        """Persist *event* in the in-memory store (idempotent on ``event_id``)."""
        self._store[event.event_id] = event

    def get_by_id(self, event_id: str) -> NormalizedExternalEvent | None:
        """Return the event for *event_id*, or ``None`` if not found."""
        return self._store.get(event_id)

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
        """Return matching events ordered by ``occurred_at`` descending."""
        results: list[NormalizedExternalEvent] = list(self._store.values())
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        if status is not None:
            results = [e for e in results if e.status == status]
        if region is not None:
            results = [e for e in results if e.region == region]
        if since is not None:
            # Normalise naive datetimes to UTC-aware for comparison.
            since_utc = since.replace(tzinfo=UTC) if since.tzinfo is None else since
            results = [e for e in results if e.occurred_at >= since_utc]
        if until is not None:
            until_utc = until.replace(tzinfo=UTC) if until.tzinfo is None else until
            results = [e for e in results if e.occurred_at <= until_utc]
        results.sort(key=lambda e: e.occurred_at, reverse=True)
        return results[:limit]

    def clear(self) -> None:
        """Remove all stored events."""
        self._store.clear()

    # ------------------------------------------------------------------
    # Inspection helpers (not part of the public interface)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, event_id: object) -> bool:
        return event_id in self._store
