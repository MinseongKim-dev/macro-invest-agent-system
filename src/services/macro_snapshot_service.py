"""Phase 2 service for building and comparing macro snapshots."""

from __future__ import annotations

from datetime import date, timedelta

from core.contracts.macro_snapshot_repository import MacroSnapshotRepositoryContract
from domain.macro.snapshot import (
    MacroSnapshotState,
    compare_snapshot_states,
    derive_degraded_status,
    derive_financial_conditions_state,
    derive_freshness_status,
    derive_growth_state,
    derive_inflation_state,
    derive_labor_state,
    derive_policy_state,
    select_latest_observations,
)
from pipelines.ingestion.indicator_catalog import PRIORITY_INDICATORS
from pipelines.ingestion.models import NormalizedMacroObservation


class MacroSnapshotService:
    """Build and persist deterministic macro snapshots for an as-of date."""

    def __init__(self, repository: MacroSnapshotRepositoryContract) -> None:
        self._repository = repository

    async def build_snapshot(
        self,
        observations: list[NormalizedMacroObservation],
        as_of_date: date,
    ) -> MacroSnapshotState:
        selected = select_latest_observations(observations, as_of_date)
        freshness = derive_freshness_status(selected)
        degraded, missing = derive_degraded_status(
            selected=selected,
            required_indicators=list(PRIORITY_INDICATORS),
        )

        source_summary: dict[str, int] = {}
        for obs in selected.values():
            source_key = str(obs.source)
            source_summary[source_key] = source_summary.get(source_key, 0) + 1

        snapshot = MacroSnapshotState(
            as_of_date=as_of_date,
            freshness_status=freshness,
            degraded_status=degraded,
            growth_state=derive_growth_state(selected),
            inflation_state=derive_inflation_state(selected),
            labor_state=derive_labor_state(selected),
            policy_state=derive_policy_state(selected),
            financial_conditions_state=derive_financial_conditions_state(selected),
            missing_indicators=missing,
            source_summary=source_summary,
            indicator_values={k.value: v.value for k, v in selected.items() if v.value is not None},
        )
        return snapshot

    async def build_and_save_snapshot(
        self,
        observations: list[NormalizedMacroObservation],
        as_of_date: date,
    ) -> MacroSnapshotState:
        snapshot = await self.build_snapshot(observations=observations, as_of_date=as_of_date)
        previous = await self._repository.get_latest_on_or_before(as_of_date - timedelta(days=1))
        snapshot.comparison = compare_snapshot_states(snapshot, previous)
        snapshot.key_indicator_changes = list(snapshot.comparison.changed_indicators)
        await self._repository.save_snapshot(snapshot)
        return snapshot
