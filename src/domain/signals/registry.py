"""In-memory registry of built-in signal definitions.

Provides a simple lookup mechanism so MCP tools can resolve signal IDs to
:class:`~domain.signals.models.SignalDefinition` objects without a database.
A small set of built-in definitions is shipped with the package; callers can
also inject a custom registry for testing.
"""

from __future__ import annotations

from domain.signals.enums import SignalType
from domain.signals.models import SignalDefinition, SignalRule

# ---------------------------------------------------------------------------
# Built-in signal definitions
# ---------------------------------------------------------------------------

_BUILT_IN_SIGNALS: dict[str, SignalDefinition] = {
    "bull_market": SignalDefinition(
        signal_id="bull_market",
        name="Bull Market Signal",
        signal_type=SignalType.BUY,
        description=(
            "Triggers when GDP growth is positive and inflation is contained. "
            "Indicates a risk-on environment favourable for equity exposure."
        ),
        rules=[
            SignalRule(
                name="gdp_growth_positive",
                description="GDP growth should be above 2%",
                condition="gdp > 2.0",
                weight=1.5,
            ),
            SignalRule(
                name="inflation_contained",
                description="Inflation should be below 4%",
                condition="inflation < 4.0",
                weight=1.0,
            ),
        ],
        required_indicators=["gdp", "inflation"],
    ),
    "recession_warning": SignalDefinition(
        signal_id="recession_warning",
        name="Recession Warning Signal",
        signal_type=SignalType.SELL,
        description=(
            "Triggers when unemployment is elevated and GDP is contracting. "
            "Indicates a risk-off environment; reduce equity exposure."
        ),
        rules=[
            SignalRule(
                name="unemployment_elevated",
                description="Unemployment rate exceeds 7%",
                condition="unemployment > 7.0",
                weight=1.0,
            ),
            SignalRule(
                name="gdp_contracting",
                description="GDP growth is negative",
                condition="gdp < 0",
                weight=2.0,
            ),
        ],
        required_indicators=["unemployment", "gdp"],
    ),
    "hold_neutral": SignalDefinition(
        signal_id="hold_neutral",
        name="Neutral Hold Signal",
        signal_type=SignalType.HOLD,
        description=(
            "Neutral signal when PMI is in the expansion-borderline range. "
            "Indicates mixed macro conditions; maintain current allocation."
        ),
        rules=[
            SignalRule(
                name="pmi_borderline",
                description="PMI is in the 45–55 range (neutral zone)",
                condition="pmi > 45 AND pmi < 55",
                weight=1.0,
            ),
        ],
        required_indicators=["pmi"],
    ),
}


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------


class SignalRegistry:
    """In-memory registry of :class:`~domain.signals.models.SignalDefinition` objects.

    Provides look-up by ``signal_id``.  A default instance pre-populated with
    the built-in definitions is available as :data:`default_registry`.

    The registry is intentionally *read-only* from the MCP layer's perspective:
    MCP tools consume definitions; they never mutate them.
    """

    def __init__(
        self,
        definitions: dict[str, SignalDefinition] | None = None,
    ) -> None:
        """Initialise with *definitions* or fall back to the built-in set.

        Args:
            definitions: Optional mapping of signal_id → SignalDefinition.
                         Pass ``None`` to use :data:`_BUILT_IN_SIGNALS`.
        """
        source = definitions if definitions is not None else _BUILT_IN_SIGNALS
        self._definitions: dict[str, SignalDefinition] = {
            sid: defn.model_copy(deep=True) for sid, defn in source.items()
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, signal_id: str) -> SignalDefinition:
        """Return the :class:`~domain.signals.models.SignalDefinition` for *signal_id*.

        Args:
            signal_id: ID of the signal to look up.

        Returns:
            The matching :class:`~domain.signals.models.SignalDefinition`.

        Raises:
            KeyError: If *signal_id* is not present in the registry.
        """
        definition = self._definitions.get(signal_id)
        if definition is None:
            raise KeyError(signal_id)
        return definition

    def list_ids(self) -> list[str]:
        """Return all registered signal IDs."""
        return list(self._definitions.keys())

    def register(self, definition: SignalDefinition) -> None:
        """Add or replace a signal definition.

        Args:
            definition: :class:`~domain.signals.models.SignalDefinition` to register.
        """
        self._definitions[definition.signal_id] = definition


# ---------------------------------------------------------------------------
# Module-level default instance
# ---------------------------------------------------------------------------

default_registry: SignalRegistry = SignalRegistry()
