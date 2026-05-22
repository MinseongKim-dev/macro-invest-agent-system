"""Domain models for investment signal definitions and evaluation results."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from domain.macro.models import MacroSnapshot
from domain.signals.conflict import ConflictSurface
from domain.signals.enums import SignalStrength, SignalType, TrendDirection


class SignalRule(BaseModel):
    """A single rule within a signal definition.

    Rules are conditions that contribute to signal generation, such as
    "inflation > 3%" or "unemployment trend is down".
    """

    name: str = Field(..., description="Name of the rule")
    description: str = Field(..., description="Human-readable description of the rule")
    condition: str = Field(
        ...,
        description="Rule condition expression (e.g., 'gdp_growth > 2.0 AND inflation < 4')",
    )
    weight: float = Field(
        default=1.0,
        description="Weight of this rule in final signal strength calculation",
        ge=0.0,
    )


class SignalDefinition(BaseModel):
    """Definition of a signal that can be evaluated against macro data.

    Contains rules and parameters needed to generate a signal from macro features.
    """

    signal_id: str = Field(..., description="Unique identifier for this signal")
    name: str = Field(..., description="Human-readable signal name")
    signal_type: SignalType = Field(..., description="Type of signal (buy/sell/hold)")
    description: str = Field(..., description="Detailed description of the signal logic")
    rules: list[SignalRule] = Field(..., description="Rules that compose this signal")
    required_indicators: list[str] = Field(
        default_factory=list,
        description="List of required macro indicator types",
    )
    version: int = Field(default=1, description="Signal definition version for evolution tracking")

    @field_validator("rules")
    @classmethod
    def validate_rules_not_empty(cls, v: list[SignalRule]) -> list[SignalRule]:
        """Ensure signal has at least one rule."""
        if not v:
            raise ValueError("Signal must contain at least one rule")
        return v


class SignalOutput(BaseModel):
    """Output of signal evaluation at a point in time.

    Represents the result of evaluating a signal against macro data, including
    the decision and confidence metrics.
    """

    signal_id: str = Field(..., description="ID of the evaluated signal")
    signal_type: SignalType = Field(..., description="Type of signal")
    strength: SignalStrength = Field(..., description="Confidence level of the signal")
    score: float = Field(
        ...,
        description="Numerical score (0.0-1.0) representing signal confidence",
        ge=0.0,
        le=1.0,
    )
    triggered_at: datetime = Field(..., description="Time when signal was generated")
    trend: TrendDirection = Field(
        default=TrendDirection.NEUTRAL, description="Underlying trend direction"
    )
    rationale: str = Field(
        default="",
        description="Human-readable explanation of why this signal was generated",
    )
    rule_results: dict[str, bool] = Field(
        default_factory=dict,
        description="Results of each rule evaluation (rule_name -> passed)",
    )
    asset_class: str = Field(
        default="",
        description=(
            "Target asset class for this signal (e.g. 'equities', 'bonds', 'commodities'). "
            "Empty for regime-level or multi-asset signals."
        ),
    )
    supporting_regime: str = Field(
        default="",
        description="Regime label that grounds this signal (e.g. 'goldilocks', 'contraction').",
    )
    supporting_drivers: list[str] = Field(
        default_factory=list,
        description=(
            "Macro factors that support this signal direction "
            "(e.g. 'growth_accelerating', 'inflation_cooling')."
        ),
    )
    conflicting_drivers: list[str] = Field(
        default_factory=list,
        description=(
            "Macro factors that partially contradict or reduce confidence in this signal "
            "(e.g. 'policy_restrictive', 'labor_weakening')."
        ),
    )
    is_degraded: bool = Field(
        default=False,
        description=(
            "True when this signal was derived from a degraded, stale, or low-confidence "
            "regime.  Downstream consumers should render a degraded badge and interpret "
            "the signal with increased caution."
        ),
    )
    caveat: str | None = Field(
        default=None,
        description=(
            "Analyst-facing caveat string explaining why this signal is degraded or should "
            "be interpreted with reduced confidence.  None when is_degraded=False."
        ),
    )
    conflict: ConflictSurface | None = Field(
        default=None,
        description=(
            "Conflict Surface v1: analytical conflict descriptor for this signal. "
            "Populated when signals are derived via the regime-grounded engine. "
            "Distinct from is_degraded (which reflects data/freshness problems). "
            "None in the legacy snapshot-based engine path."
        ),
    )


class SignalResult(BaseModel):
    """Complete result of signal engine execution.

    Contains all signals generated and metadata about the evaluation run.
    """

    run_id: str = Field(..., description="Unique ID for this evaluation run (UUID)")
    timestamp: datetime = Field(..., description="Time when evaluation was performed")
    macro_snapshot: MacroSnapshot = Field(..., description="Macro data that was evaluated")
    signals: list[SignalOutput] = Field(
        default_factory=list, description="All signals generated in this run"
    )
    success: bool = Field(default=True, description="Whether evaluation completed successfully")
    error_message: str | None = Field(
        default=None, description="Error message if evaluation failed"
    )

    def get_signals_by_type(self, signal_type: SignalType) -> list[SignalOutput]:
        """Get all signals of a given type."""
        return [s for s in self.signals if s.signal_type == signal_type]

    def get_buy_signals(self) -> list[SignalOutput]:
        """Get all buy signals."""
        return self.get_signals_by_type(SignalType.BUY)

    def get_sell_signals(self) -> list[SignalOutput]:
        """Get all sell signals."""
        return self.get_signals_by_type(SignalType.SELL)

    def strongest_signal(self) -> SignalOutput | None:
        """Get the strongest signal by confidence score."""
        if not self.signals:
            return None
        return max(self.signals, key=lambda s: s.score)
