"""Abstract repository interface for explanation persistence.

Implementations
---------------
* :class:`~adapters.repositories.in_memory_explanation_store.InMemoryExplanationStore`
  — used in development, tests, and the current Phase 3 bridge surface.

Deferred
--------
* A SQL-backed implementation (``SqlExplanationRepository``) is planned for
  Phase 5 once durable persistence is required for auditability.  The interface
  below defines the contract that implementation must satisfy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from apps.api.dto.explanations import ExplanationResponse


class ExplanationRepositoryInterface(ABC):
    """Abstract repository for storing and retrieving explanation objects.

    All write operations must be durable within the scope of a single
    application process (or truly persistent for SQL implementations).
    No fake-success returns are permitted.
    """

    @abstractmethod
    def save(self, explanation: ExplanationResponse) -> None:
        """Persist *explanation*.

        Idempotent — saving the same ``explanation_id`` twice replaces the
        previous entry.

        Args:
            explanation: The :class:`~apps.api.dto.explanations.ExplanationResponse`
                to persist.
        """

    @abstractmethod
    def get_by_id(self, explanation_id: str) -> ExplanationResponse | None:
        """Return the explanation for *explanation_id*, or ``None`` if not found.

        Args:
            explanation_id: The unique explanation identifier.

        Returns:
            :class:`~apps.api.dto.explanations.ExplanationResponse` when found;
            ``None`` otherwise.
        """

    @abstractmethod
    def list_by_run_id(self, run_id: str) -> list[ExplanationResponse]:
        """Return all explanations associated with *run_id*, ordered by
        ``generated_at`` (ascending).

        Args:
            run_id: The signal engine run or regime identifier.

        Returns:
            List of :class:`~apps.api.dto.explanations.ExplanationResponse` objects.
            Empty list when none are found.
        """

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored explanations.

        Primarily used in test teardown.  Production implementations may
        choose to make this a no-op or restrict it behind a feature flag.
        """
