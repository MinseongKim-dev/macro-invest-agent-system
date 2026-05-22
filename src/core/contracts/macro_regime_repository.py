"""Contract for macro regime persistence adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from domain.macro.regime import MacroRegime


class MacroRegimeRepositoryContract(ABC):
    @abstractmethod
    async def save_regime(self, regime: MacroRegime) -> None:
        """Persist a macro regime."""

    @abstractmethod
    async def get_regime_by_id(self, regime_id: str) -> MacroRegime | None:
        """Retrieve a regime by ID."""

    @abstractmethod
    async def get_latest_on_or_before(self, as_of_date: date) -> MacroRegime | None:
        """Retrieve latest regime on or before as_of_date."""

    @abstractmethod
    async def list_recent(self, as_of_date: date, limit: int = 10) -> list[MacroRegime]:
        """Return up to *limit* regimes on or before *as_of_date*, most recent first.

        Args:
            as_of_date: Upper bound date (inclusive).
            limit: Maximum number of regimes to return.  Must be ≥ 1.

        Returns:
            Ordered list of regimes (most recent ``as_of_date`` first).
            Empty list when no regimes exist on or before ``as_of_date``.
        """
