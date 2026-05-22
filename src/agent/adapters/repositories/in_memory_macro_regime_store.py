"""In-memory repository for Phase 3 macro regimes."""

from __future__ import annotations

from datetime import date

from core.contracts.macro_regime_repository import MacroRegimeRepositoryContract
from domain.macro.regime import MacroRegime


class InMemoryMacroRegimeStore(MacroRegimeRepositoryContract):
    def __init__(self) -> None:
        self._regimes: list[MacroRegime] = []

    async def save_regime(self, regime: MacroRegime) -> None:
        self._regimes.append(regime)

    async def get_regime_by_id(self, regime_id: str) -> MacroRegime | None:
        for regime in self._regimes:
            if regime.regime_id == regime_id:
                return regime
        return None

    async def get_latest_on_or_before(self, as_of_date: date) -> MacroRegime | None:
        candidates = [r for r in self._regimes if r.as_of_date <= as_of_date]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.as_of_date)

    async def list_recent(self, as_of_date: date, limit: int = 10) -> list[MacroRegime]:
        """Return up to *limit* regimes on or before *as_of_date*, most recent first.

        When multiple regimes share the same ``as_of_date`` (e.g. re-runs),
        ties are broken by ``regime_timestamp`` (most recent first).
        """
        candidates = [r for r in self._regimes if r.as_of_date <= as_of_date]
        candidates.sort(key=lambda r: (r.as_of_date, r.regime_timestamp), reverse=True)
        return candidates[:limit]

    def all_regimes(self) -> list[MacroRegime]:
        return list(self._regimes)
