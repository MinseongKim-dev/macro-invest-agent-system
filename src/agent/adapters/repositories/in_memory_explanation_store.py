"""In-memory explanation store — development and test implementation.

This is the default :class:`~storage.repositories.explanation_repository.ExplanationRepositoryInterface`
implementation.  It stores explanations in a plain dict keyed by
``explanation_id``.  All state is lost on process restart.

Used
----
* Default dependency-injected repository in dev and test environments.
* The module-level ``_store`` dict in ``apps/api/routers/explanations.py``
  has been replaced by this implementation.

Not suitable for
----------------
* Production deployments that require auditability across restarts.
* Multi-process deployments (each process has its own isolated store).

See also
--------
:class:`~storage.repositories.explanation_repository.ExplanationRepositoryInterface`
"""

from __future__ import annotations

from apps.api.dto.explanations import ExplanationResponse
from storage.repositories.explanation_repository import ExplanationRepositoryInterface


class InMemoryExplanationStore(ExplanationRepositoryInterface):
    """In-memory implementation of :class:`ExplanationRepositoryInterface`.

    Thread safety
    -------------
    Not thread-safe.  The GIL provides basic protection in CPython for
    single-process asyncio applications, but this should not be used in
    multi-threaded contexts without additional synchronisation.
    """

    def __init__(self) -> None:
        self._store: dict[str, ExplanationResponse] = {}

    # ------------------------------------------------------------------
    # ExplanationRepositoryInterface
    # ------------------------------------------------------------------

    def save(self, explanation: ExplanationResponse) -> None:
        """Persist *explanation* in the in-memory store.

        Idempotent — replaces any existing entry with the same ``explanation_id``.
        """
        self._store[explanation.explanation_id] = explanation

    def get_by_id(self, explanation_id: str) -> ExplanationResponse | None:
        """Return the explanation for *explanation_id*, or ``None`` if not found."""
        return self._store.get(explanation_id)

    def list_by_run_id(self, run_id: str) -> list[ExplanationResponse]:
        """Return all explanations for *run_id*, ordered by ``generated_at``."""
        matches = [e for e in self._store.values() if e.run_id == run_id]
        return sorted(matches, key=lambda e: e.generated_at)

    def clear(self) -> None:
        """Remove all stored explanations."""
        self._store.clear()

    # ------------------------------------------------------------------
    # Inspection helpers (not part of the public interface)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, explanation_id: object) -> bool:
        return explanation_id in self._store
