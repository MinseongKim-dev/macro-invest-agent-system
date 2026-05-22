"""In-memory repository for Phase 2 macro snapshots."""

from __future__ import annotations

from datetime import date

from core.contracts.macro_snapshot_repository import MacroSnapshotRepositoryContract
from domain.macro.snapshot import MacroSnapshotState


class InMemoryMacroSnapshotStore(MacroSnapshotRepositoryContract):
    def __init__(self) -> None:
        self._snapshots: list[MacroSnapshotState] = []

    async def save_snapshot(self, snapshot: MacroSnapshotState) -> None:
        self._snapshots.append(snapshot)

    async def get_snapshot_by_id(self, snapshot_id: str) -> MacroSnapshotState | None:
        for snapshot in self._snapshots:
            if snapshot.snapshot_id == snapshot_id:
                return snapshot
        return None

    async def get_latest_on_or_before(self, as_of_date: date) -> MacroSnapshotState | None:
        candidates = [s for s in self._snapshots if s.as_of_date <= as_of_date]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.as_of_date)

    async def list_recent(self, as_of_date: date, limit: int = 10) -> list[MacroSnapshotState]:
        """Return up to *limit* snapshots on or before *as_of_date*, most recent first.

        When multiple snapshots share the same ``as_of_date``, ties are broken
        by ``snapshot_timestamp`` (most recent first).
        """
        candidates = [s for s in self._snapshots if s.as_of_date <= as_of_date]
        candidates.sort(key=lambda s: (s.as_of_date, s.snapshot_timestamp), reverse=True)
        return candidates[:limit]

    def all_snapshots(self) -> list[MacroSnapshotState]:
        return list(self._snapshots)
