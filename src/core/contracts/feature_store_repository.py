"""Contract (abstract base class) for feature-store repository adapters.

All concrete adapters — whether in-memory, SQLAlchemy-backed, or cloud-native
— must implement this contract.

Design notes
------------
* The contract is defined as an ABC to enable isinstance checks and to make
  missing-implementation errors explicit at construction time.
* All methods are **async** to support both synchronous stub adapters and
  future I/O-bound repository implementations without requiring callers to
  change.
* The repository is **append-friendly**: ``save_snapshot`` stores a new entry;
  ``get_latest_snapshot`` retrieves the most recent one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class FeatureStoreRepositoryContract(ABC):
    """Abstract contract for feature-store repository adapters.

    Concrete subclasses must implement :meth:`save_snapshot`,
    :meth:`get_latest_snapshot`, and :meth:`list_snapshots`.
    """

    @abstractmethod
    async def save_snapshot(self, snapshot: object) -> None:
        """Persist a feature snapshot.

        Args:
            snapshot: A :class:`~pipelines.ingestion.models.FeatureSnapshot`
                instance to persist.  Typed as ``object`` to avoid a circular
                import; concrete implementations should narrow the type in
                their own signatures.

        Raises:
            RuntimeError: If the persistence operation fails.
        """

    @abstractmethod
    async def get_latest_snapshot(self, country: str) -> object | None:
        """Retrieve the most recently stored snapshot for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code.

        Returns:
            The most recently persisted
            :class:`~pipelines.ingestion.models.FeatureSnapshot` for
            ``country``, or ``None`` if no snapshot has been stored yet.
        """

    @abstractmethod
    async def list_snapshots(self, country: str, limit: int = 10) -> Sequence[object]:
        """List the most recently stored snapshots for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code.
            limit: Maximum number of snapshots to return (most recent first).
                Must be >= 1.

        Returns:
            List of :class:`~pipelines.ingestion.models.FeatureSnapshot`
            instances ordered newest-first.  May be empty.
        """
