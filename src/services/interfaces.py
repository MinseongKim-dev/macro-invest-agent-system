"""Service layer interface contracts."""

from abc import ABC, abstractmethod
from datetime import date

from domain.macro.models import MacroFeature, MacroSnapshot
from domain.macro.regime import MacroRegime
from domain.signals.models import SignalDefinition, SignalResult


class MacroServiceInterface(ABC):
    """Interface for macro data retrieval and management.

    Defines the contract for services that provide macroeconomic data
    to the signal evaluation layer.
    """

    @abstractmethod
    async def fetch_features(
        self, indicator_types: list[str], country: str = "US"
    ) -> list[MacroFeature]:
        """Fetch macro features for given indicators.

        Args:
            indicator_types: List of indicator types to fetch
            country: Country code (default: "US")

        Returns:
            List of MacroFeature objects

        Raises:
            ValueError: If indicator_types is empty.
            ProviderTimeoutError: If the upstream provider times out.
            ProviderHTTPError: If the upstream provider returns a non-2xx HTTP
                status.
            ProviderNetworkError: On network I/O failure.
            PartialDataError: If fewer indicators are returned than requested
                (degraded but not a hard failure).
        """

    @abstractmethod
    async def get_snapshot(self, country: str = "US") -> MacroSnapshot:
        """Get a complete macro snapshot at current time.

        Args:
            country: Country code (default: "US")

        Returns:
            MacroSnapshot containing all available features

        Raises:
            ProviderTimeoutError: If the upstream provider times out.
            ProviderHTTPError: If the upstream provider returns a non-2xx HTTP
                status.
            ProviderNetworkError: On network I/O failure.
            StaleDataError: If the snapshot is beyond the freshness threshold.
            RuntimeError: If snapshot cannot be created for other reasons.
        """


class SignalServiceInterface(ABC):
    """Interface for signal evaluation and engine execution.

    Defines the contract for services that manage signal evaluation
    against macro data.
    """

    @abstractmethod
    async def evaluate_signal(
        self, signal_def: SignalDefinition, snapshot: MacroSnapshot
    ) -> dict[str, bool]:
        """Evaluate a signal against macro data.

        Args:
            signal_def: Signal definition with rules
            snapshot: Macro data snapshot

        Returns:
            Dictionary mapping rule names to boolean results

        Raises:
            ValueError: If signal definition is invalid
            RuntimeError: If evaluation fails
        """

    @abstractmethod
    async def run_engine(
        self,
        signal_definitions: list[SignalDefinition],
        snapshot: MacroSnapshot,
    ) -> SignalResult:
        """Run the signal engine against macro data.

        Evaluates all signals and returns comprehensive result.

        Args:
            signal_definitions: List of signals to evaluate
            snapshot: Macro data snapshot

        Returns:
            SignalResult containing all generated signals

        Raises:
            ValueError: If signal definitions are invalid
            RuntimeError: If engine execution fails
        """


class RegimeServiceInterface(ABC):
    """Interface for macro regime build/query flows."""

    @abstractmethod
    async def build_regime(self, as_of_date: date) -> MacroRegime:
        """Build a regime from latest snapshot on/before the as-of date."""

    @abstractmethod
    async def build_and_save_regime(self, as_of_date: date) -> MacroRegime:
        """Build and persist regime for the as-of date."""

    @abstractmethod
    async def get_latest_regime(self, as_of_date: date) -> MacroRegime | None:
        """Load latest persisted regime on/before as-of date."""

    @abstractmethod
    async def compare_latest_with_prior(
        self, as_of_date: date
    ) -> tuple[MacroRegime, MacroRegime | None]:
        """Load current regime plus previous baseline regime."""

    @abstractmethod
    async def list_recent_regimes(
        self, as_of_date: date, limit: int = 10
    ) -> list[MacroRegime]:
        """Return up to *limit* regimes on or before *as_of_date*, most recent first.

        Args:
            as_of_date: Upper bound date (inclusive).
            limit: Maximum number of regimes to return.  Must be ≥ 1.

        Returns:
            List of regimes ordered by ``as_of_date`` descending.
            Empty list when the store is empty.
        """
