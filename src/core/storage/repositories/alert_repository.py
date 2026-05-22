"""Abstract repository interface for alert event persistence.

Implementations
---------------
* :class:`~adapters.repositories.in_memory_alert_store.InMemoryAlertStore`
  — used in development and tests.

Deferred
--------
* A SQL-backed implementation is planned for a future phase once durable
  persistence is required for audit trails and cross-restart history.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.alerts.models import (
    AlertAcknowledgementState,
    AlertEvent,
    AlertSeverity,
    AlertTriggerType,
)


class AlertRepositoryInterface(ABC):
    """Abstract repository for storing and retrieving alert events.

    All write operations must be durable within the scope of a single
    application process (or truly persistent for SQL implementations).
    """

    @abstractmethod
    def save(self, alert: AlertEvent) -> None:
        """Persist *alert*.

        Idempotent — saving the same ``alert_id`` twice replaces the
        previous entry.
        """

    @abstractmethod
    def get_by_id(self, alert_id: str) -> AlertEvent | None:
        """Return the alert for *alert_id*, or ``None`` if not found."""

    @abstractmethod
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
        """Return alerts matching the supplied filters, ordered most-recent first.

        Args:
            limit: Maximum number of records to return.
            trigger_type: Filter by alert trigger type.
            severity: Filter by alert severity.
            country: Filter by country code.
            since: Return alerts triggered at or after this UTC datetime.
            until: Return alerts triggered at or before this UTC datetime.

        Returns:
            List of :class:`~domain.alerts.models.AlertEvent`, newest first.
        """

    @abstractmethod
    def update_acknowledgement(
        self,
        alert_id: str,
        state: AlertAcknowledgementState,
        *,
        acknowledged_at: datetime | None = None,
        snoozed_until: datetime | None = None,
    ) -> AlertEvent | None:
        """Update the acknowledgement state of an alert.

        Args:
            alert_id: The alert to update.
            state: The new acknowledgement state.
            acknowledged_at: Set when transitioning to ``acknowledged``.
            snoozed_until: Set when transitioning to ``snoozed``.

        Returns:
            The updated :class:`~domain.alerts.models.AlertEvent`, or ``None``
            if the alert was not found.
        """

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored alerts.  Primarily used in test teardown."""
