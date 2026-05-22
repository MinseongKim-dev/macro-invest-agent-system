"""Signal evaluation service implementation."""

import uuid
from datetime import UTC, datetime

from core.logging.logger import get_logger
from core.metrics import SIGNAL_GENERATION_DURATION
from core.tracing import get_tracer
from core.tracing.span_attributes import SIGNAL_COUNT
from domain.macro.models import MacroSnapshot
from domain.macro.regime import MacroRegime, RegimeConfidence
from domain.signals.conflict import derive_conflict
from domain.signals.engine import SignalEngine
from domain.signals.models import SignalDefinition, SignalOutput, SignalResult
from domain.signals.regime_signal_rules import get_regime_signal_rules
from services.interfaces import SignalServiceInterface

_log = get_logger(__name__)
_tracer = get_tracer(__name__)


def _adjust_signal_score(
    base_score: float,
    regime_confidence: RegimeConfidence,
    quant_overall_support: float | None,
) -> float:
    """Adjust a rule-level signal score using regime confidence and quant support.

    Adjustment rules
    ----------------
    1. Apply a regime-confidence multiplier first:
       - HIGH   → 1.00 (unchanged)
       - MEDIUM → 0.85 (mild reduction)
       - LOW    → 0.65 (significant reduction)
    2. If quant overall_support is available and very weak (<0.35), apply an
       additional 0.85 multiplier to reflect poor quantitative backing.
    3. Result is clamped to [0.0, 1.0].

    Note: this function never raises the base_score above its rule-level value.
    Score inflation is not the goal; calibrated reduction is.
    """
    confidence_multipliers: dict[RegimeConfidence, float] = {
        RegimeConfidence.HIGH: 1.00,
        RegimeConfidence.MEDIUM: 0.85,
        RegimeConfidence.LOW: 0.65,
    }
    score = base_score * confidence_multipliers.get(regime_confidence, 1.0)

    if quant_overall_support is not None and quant_overall_support < 0.35:
        score *= 0.85

    return max(0.0, min(1.0, score))

class SignalService(SignalServiceInterface):
    """Skeleton implementation of signal service.

    This service coordinates signal evaluation using the SignalEngine.
    Future enhancements will add caching, audit logging, and signal persistence.
    """

    def __init__(self) -> None:
        """Initialize the signal service."""
        self.engine = SignalEngine()

    async def evaluate_signal(
        self, signal_def: SignalDefinition, snapshot: MacroSnapshot
    ) -> dict[str, bool]:
        """Evaluate a signal against macro data.

        Placeholder: returns rule evaluation results.

        Args:
            signal_def: Signal definition with rules
            snapshot: Macro data snapshot

        Returns:
            Dictionary mapping rule names to boolean results

        Raises:
            ValueError: If signal definition is invalid
        """
        if not signal_def.rules:
            raise ValueError("Signal must have at least one rule")

        rule_results: dict[str, bool] = {}
        for rule in signal_def.rules:
            # Placeholder: all rules evaluate to true
            rule_results[rule.name] = True

        return rule_results

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
        """
        if not signal_definitions:
            raise ValueError("At least one signal definition is required")

        _log.debug(
            "service_fetch_started",
            operation="run_engine",
            signal_count=len(signal_definitions),
        )
        with _tracer.start_as_current_span("service.run_signal_engine") as span:
            span.set_attribute("signal.definitions_count", len(signal_definitions))
            with SIGNAL_GENERATION_DURATION.time():
                result = await self.engine.run(signal_definitions, snapshot)
            span.set_attribute(SIGNAL_COUNT, len(result.signals))
        _log.debug(
            "service_fetch_complete",
            operation="run_engine",
            signals_generated=len(result.signals),
        )
        return result

    async def run_regime_grounded_engine(self, regime: MacroRegime) -> SignalResult:
        """Run the regime-grounded signal engine.

        Derives investment signals deterministically from the current macro
        regime label.  Each signal is grounded in the regime with an
        analyst-facing rationale and structured driver lists.

        Degraded propagation
        --------------------
        When the grounding regime is degraded, stale, or low-confidence, each
        generated signal receives ``is_degraded=True`` and a ``caveat`` string
        that explains the specific condition.  This lets the API and UI surface
        degraded badges without re-inspecting the regime directly.

        Args:
            regime: The current :class:`~domain.macro.regime.MacroRegime`.

        Returns:
            :class:`~domain.signals.models.SignalResult` with all regime-derived signals.
        """
        from domain.macro.regime import RegimeConfidence, RegimeLabel
        from domain.macro.snapshot import DegradedStatus
        from pipelines.ingestion.models import FreshnessStatus

        run_id = str(uuid.uuid4())
        rules = get_regime_signal_rules(regime.regime_label)
        now = datetime.now(UTC)

        # --- Derive regime-level degraded state and caveat -------------------
        is_seeded = regime.metadata.get("seeded") == "true"
        regime_is_degraded = (
            is_seeded
            or regime.freshness_status in {FreshnessStatus.STALE, FreshnessStatus.UNKNOWN}
            or regime.degraded_status
            in {
                DegradedStatus.PARTIAL,
                DegradedStatus.MISSING,
                DegradedStatus.SOURCE_UNAVAILABLE,
            }
            or regime.confidence == RegimeConfidence.LOW
            or regime.regime_label in {RegimeLabel.MIXED, RegimeLabel.UNCLEAR}
        )

        caveat: str | None = None
        if is_seeded:
            caveat = (
                "Signal derived from bootstrap/synthetic regime data. "
                "This is not a production signal."
            )
        elif regime.regime_label in {RegimeLabel.MIXED, RegimeLabel.UNCLEAR}:
            caveat = (
                f"Grounding regime is non-directional ({regime.regime_label.value}). "
                "No asset-level signal can be derived with meaningful confidence."
            )
        elif regime.freshness_status == FreshnessStatus.STALE:
            caveat = (
                f"Grounding regime is stale (freshness={regime.freshness_status.value}). "
                "Signal may not reflect current market conditions."
            )
        elif regime.freshness_status == FreshnessStatus.UNKNOWN:
            caveat = (
                "Regime data freshness is unknown. "
                "Signal confidence is reduced."
            )
        elif regime.degraded_status in {
            DegradedStatus.MISSING,
            DegradedStatus.SOURCE_UNAVAILABLE,
        }:
            caveat = (
                f"Grounding regime has degraded inputs "
                f"(status={regime.degraded_status.value}). "
                "Signal derived from incomplete macro evidence."
            )
        elif regime.degraded_status == DegradedStatus.PARTIAL:
            caveat = (
                "Grounding regime was built from partial indicator data. "
                "Signal confidence may be lower than stated."
            )
        elif regime.confidence == RegimeConfidence.LOW:
            caveat = (
                "Grounding regime confidence is LOW. "
                "Signal direction is indicative only — do not act with high conviction."
            )

        # --- Build signals ---------------------------------------------------
        quant_overall_support = (
            regime.quant_scores.overall_support if regime.quant_scores is not None else None
        )

        signals: list[SignalOutput] = []
        for rule in rules:
            adjusted_score = _adjust_signal_score(
                base_score=rule.signal_confidence,
                regime_confidence=regime.confidence,
                quant_overall_support=quant_overall_support,
            )
            conflict_surface = derive_conflict(
                supporting_drivers=list(rule.supporting_drivers),
                conflicting_drivers=list(rule.conflicting_drivers),
                quant_overall_support=quant_overall_support,
                is_degraded=regime_is_degraded,
            )
            signal_out = SignalOutput(
                signal_id=rule.signal_id,
                signal_type=rule.signal_direction,
                strength=rule.signal_strength,
                score=adjusted_score,
                triggered_at=now,
                trend=rule.trend,
                rationale=rule.regime_rationale,
                rule_results={"regime_rule": True},
                asset_class=rule.asset_class,
                supporting_regime=rule.supporting_regime,
                supporting_drivers=list(rule.supporting_drivers),
                conflicting_drivers=list(rule.conflicting_drivers),
                is_degraded=regime_is_degraded,
                caveat=caveat,
                conflict=conflict_surface,
            )
            signals.append(signal_out)

        _log.debug(
            "regime_grounded_engine_complete",
            regime_label=regime.regime_label.value,
            signals_generated=len(signals),
            is_degraded=regime_is_degraded,
        )
        from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
        from domain.macro.models import MacroFeature, MacroSnapshot

        placeholder_feature = MacroFeature(
            indicator_type=MacroIndicatorType.PMI,
            source=MacroSourceType.MARKET_DATA,
            value=0.0,
            timestamp=datetime(regime.as_of_date.year, regime.as_of_date.month, 1, tzinfo=UTC),
            frequency=DataFrequency.MONTHLY,
            country="US",
            metadata={"regime_label": regime.regime_label.value},
        )
        placeholder_snapshot = MacroSnapshot(
            features=[placeholder_feature],
            snapshot_time=now,
            version=1,
        )

        return SignalResult(
            run_id=run_id,
            timestamp=now,
            macro_snapshot=placeholder_snapshot,
            signals=signals,
            success=True,
        )
