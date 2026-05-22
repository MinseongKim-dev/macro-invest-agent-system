"""In-memory alert store — development and test implementation.

This is the default
:class:`~storage.repositories.alert_repository.AlertRepositoryInterface`
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

from datetime import datetime

from domain.alerts.models import (
    AlertAcknowledgementState,
    AlertEvent,
    AlertSeverity,
    AlertTriggerType,
)
from storage.repositories.alert_repository import AlertRepositoryInterface


class InMemoryAlertStore(AlertRepositoryInterface):
    """In-memory implementation of :class:`AlertRepositoryInterface`.

    Thread safety
    -------------
    Not thread-safe.  The GIL provides basic protection in CPython for
    single-process asyncio applications.
    """

    def __init__(self) -> None:
        self._store: dict[str, AlertEvent] = {}

    # ------------------------------------------------------------------
    # AlertRepositoryInterface
    # ------------------------------------------------------------------

    def save(self, alert: AlertEvent) -> None:
        """Persist *alert* in the in-memory store (idempotent)."""
        self._store[alert.alert_id] = alert

    def get_by_id(self, alert_id: str) -> AlertEvent | None:
        """Return the alert for *alert_id*, or ``None`` if not found."""
        return self._store.get(alert_id)

    def list_recent(
        self,
        *,
        limit: int = 50,
        trigger_type: AlertTriggerType | None = None,
        severity: AlertSeverity | None = None,
        country: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[AlertEvent]:
        """Return alerts matching filters, ordered most-recent first."""
        results: list[AlertEvent] = list(self._store.values())
        if trigger_type is not None:
            results = [a for a in results if a.trigger_type == trigger_type]
        if severity is not None:
            results = [a for a in results if a.severity == severity]
        if country is not None:
            results = [a for a in results if a.country == country]
        if since is not None:
            results = [a for a in results if a.triggered_at >= since]
        if until is not None:
            results = [a for a in results if a.triggered_at <= until]
        results.sort(key=lambda a: a.triggered_at, reverse=True)
        return results[:limit]

    def update_acknowledgement(
        self,
        alert_id: str,
        state: AlertAcknowledgementState,
        *,
        acknowledged_at: datetime | None = None,
        snoozed_until: datetime | None = None,
    ) -> AlertEvent | None:
        """Update acknowledgement state; return updated alert or ``None``."""
        existing = self._store.get(alert_id)
        if existing is None:
            return None
        updated = existing.model_copy(
            update={
                "acknowledgement_state": state,
                "acknowledged_at": acknowledged_at,
                "snoozed_until": snoozed_until,
            }
        )
        self._store[alert_id] = updated
        return updated

    def clear(self) -> None:
        """Remove all stored alerts."""
        self._store.clear()

    # ------------------------------------------------------------------
    # Inspection helpers (not part of the public interface)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, alert_id: object) -> bool:
        return alert_id in self._store
