"""In-memory feature-store repository adapter.

Stores :class:`~pipelines.ingestion.models.FeatureSnapshot` objects in a
plain Python list so the ingestion service can be tested without a real
database.

Design notes
------------
* Snapshots are stored in insertion order.
* ``get_latest_snapshot`` returns the most recently inserted snapshot for a
  country (highest index), not the one with the latest ``ingested_at``
  timestamp.  This simplifies the implementation and is correct for the
  sequential ingestion pattern used by ``MacroIngestionService``.
* This adapter is intended for use in tests and local development.  It is
  **not** thread-safe.
"""

from __future__ import annotations

from core.contracts.feature_store_repository import FeatureStoreRepositoryContract
from pipelines.ingestion.models import (
    FeatureSnapshot,
    IngestionRunRecord,
    NormalizedMacroObservation,
    RawFeatureRecord,
)


class InMemoryFeatureStore(FeatureStoreRepositoryContract):
    """Mutable in-memory feature-store repository.

    Stores :class:`~pipelines.ingestion.models.FeatureSnapshot` objects in
    memory.  All stored data is lost when the object is garbage-collected.

    Example::

        store = InMemoryFeatureStore()
        await store.save_snapshot(snapshot)
        latest = await store.get_latest_snapshot("US")
    """

    def __init__(self) -> None:
        self._snapshots: list[FeatureSnapshot] = []
        self._raw_records: dict[str, list[RawFeatureRecord]] = {}
        self._normalized_records: dict[str, list[NormalizedMacroObservation]] = {}
        self._ingestion_runs: list[IngestionRunRecord] = []

    async def save_snapshot(self, snapshot: object) -> None:
        """Append a snapshot to the in-memory store.

        Args:
            snapshot: A :class:`~pipelines.ingestion.models.FeatureSnapshot`
                instance to persist.

        Raises:
            TypeError: If ``snapshot`` is not a
                :class:`~pipelines.ingestion.models.FeatureSnapshot`.
        """
        if not isinstance(snapshot, FeatureSnapshot):
            raise TypeError(
                f"Expected FeatureSnapshot, got {type(snapshot).__name__}"
            )
        self._snapshots.append(snapshot)

    async def get_latest_snapshot(self, country: str) -> FeatureSnapshot | None:
        """Return the most recently saved snapshot for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code.

        Returns:
            The most recently appended :class:`~pipelines.ingestion.models.FeatureSnapshot`
            whose ``country`` matches, or ``None`` if none exists.
        """
        for snapshot in reversed(self._snapshots):
            if snapshot.country == country:
                return snapshot
        return None

    async def list_snapshots(self, country: str, limit: int = 10) -> list[FeatureSnapshot]:
        """Return the ``limit`` most recently saved snapshots for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code.
            limit: Maximum number of snapshots to return (>= 1).

        Returns:
            List of :class:`~pipelines.ingestion.models.FeatureSnapshot`
            instances in newest-first order.  May be empty.

        Raises:
            ValueError: If ``limit`` is less than 1.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        matching = [s for s in self._snapshots if s.country == country]
        return list(reversed(matching))[:limit]

    def all_snapshots(self) -> list[FeatureSnapshot]:
        """Return all stored snapshots (for test introspection).

        Returns:
            All stored snapshots in insertion order.
        """
        return list(self._snapshots)

    # ------------------------------------------------------------------
    # Raw / normalized / run record persistence (optional protocol)
    # ------------------------------------------------------------------

    async def save_raw_records(
        self, snapshot_id: str, records: list[RawFeatureRecord]
    ) -> None:
        self._raw_records.setdefault(snapshot_id, []).extend(records)

    async def save_normalized_records(
        self, snapshot_id: str, records: list[NormalizedMacroObservation]
    ) -> None:
        self._normalized_records.setdefault(snapshot_id, []).extend(records)

    async def save_ingestion_run(self, run: IngestionRunRecord) -> None:
        self._ingestion_runs.append(run)

    def raw_records(self, snapshot_id: str) -> list[RawFeatureRecord]:
        return list(self._raw_records.get(snapshot_id, []))

    def normalized_records(self, snapshot_id: str) -> list[NormalizedMacroObservation]:
        return list(self._normalized_records.get(snapshot_id, []))

    def ingestion_runs(self) -> list[IngestionRunRecord]:
        return list(self._ingestion_runs)
