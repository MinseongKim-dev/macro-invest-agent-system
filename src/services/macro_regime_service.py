"""Phase 3 service for building macro regimes from stored snapshots."""

from __future__ import annotations

from datetime import date, timedelta

from core.contracts.macro_regime_repository import MacroRegimeRepositoryContract
from core.contracts.macro_snapshot_repository import MacroSnapshotRepositoryContract
from domain.macro.regime import MacroRegime
from domain.macro.regime_mapping import (
    build_regime_rationale,
    derive_regime_confidence,
    derive_regime_missing_inputs,
    derive_regime_warnings,
    map_snapshot_to_regime,
)
from domain.macro.regime_transition import derive_regime_transition
from domain.quant.scoring import score_snapshot
from services.interfaces import RegimeServiceInterface


class MacroRegimeService(RegimeServiceInterface):
    """Build deterministic macro regimes for a selected as-of date."""

    def __init__(
        self,
        snapshot_repository: MacroSnapshotRepositoryContract,
        regime_repository: MacroRegimeRepositoryContract | None = None,
    ) -> None:
        self._snapshot_repository = snapshot_repository
        self._regime_repository = regime_repository

    async def build_regime(self, as_of_date: date) -> MacroRegime:
        snapshot = await self._snapshot_repository.get_latest_on_or_before(as_of_date)
        if snapshot is None:
            raise ValueError(f"No snapshot available on or before {as_of_date.isoformat()}")

        label, family = map_snapshot_to_regime(snapshot)
        quant_scores = score_snapshot(snapshot)
        confidence = derive_regime_confidence(
            snapshot=snapshot, label=label, quant_scores=quant_scores
        )
        missing_inputs = derive_regime_missing_inputs(snapshot)
        return MacroRegime(
            as_of_date=snapshot.as_of_date,
            regime_label=label,
            regime_family=family,
            supporting_snapshot_id=snapshot.snapshot_id,
            supporting_states={
                "growth_state": snapshot.growth_state.value,
                "inflation_state": snapshot.inflation_state.value,
                "labor_state": snapshot.labor_state.value,
                "policy_state": snapshot.policy_state.value,
                "financial_conditions_state": snapshot.financial_conditions_state.value,
            },
            confidence=confidence,
            freshness_status=snapshot.freshness_status,
            degraded_status=snapshot.degraded_status,
            missing_inputs=missing_inputs,
            quant_scores=quant_scores,
            rationale_summary=build_regime_rationale(snapshot=snapshot, label=label),
            warnings=derive_regime_warnings(
                snapshot=snapshot,
                label=label,
                confidence=confidence,
                missing_inputs=missing_inputs,
                is_seeded=False,
            ),
        )

    async def build_and_save_regime(self, as_of_date: date) -> MacroRegime:
        if self._regime_repository is None:
            raise ValueError("Regime repository is not configured")
        regime = await self.build_regime(as_of_date=as_of_date)
        previous = await self._regime_repository.get_latest_on_or_before(
            as_of_date - timedelta(days=1)
        )
        regime.transition = derive_regime_transition(current=regime, previous=previous)
        await self._regime_repository.save_regime(regime)
        return regime

    async def get_latest_regime(self, as_of_date: date) -> MacroRegime | None:
        if self._regime_repository is None:
            raise ValueError("Regime repository is not configured")
        return await self._regime_repository.get_latest_on_or_before(as_of_date)

    async def compare_latest_with_prior(
        self,
        as_of_date: date,
    ) -> tuple[MacroRegime, MacroRegime | None]:
        if self._regime_repository is None:
            raise ValueError("Regime repository is not configured")
        current = await self._regime_repository.get_latest_on_or_before(as_of_date)
        if current is None:
            raise ValueError(f"No regime available on or before {as_of_date.isoformat()}")
        previous = await self._regime_repository.get_latest_on_or_before(
            current.as_of_date - timedelta(days=1)
        )
        return current, previous

    async def list_recent_regimes(
        self,
        as_of_date: date,
        limit: int = 10,
    ) -> list[MacroRegime]:
        if self._regime_repository is None:
            raise ValueError("Regime repository is not configured")
        return await self._regime_repository.list_recent(as_of_date=as_of_date, limit=limit)

