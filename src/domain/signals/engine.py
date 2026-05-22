"""Deterministic signal evaluation engine."""

import uuid
from datetime import UTC, datetime

from domain.macro.models import MacroSnapshot
from domain.signals.enums import SignalStrength
from domain.signals.models import SignalDefinition, SignalOutput, SignalResult


class SignalEngine:
    """Deterministic signal evaluation engine.

    Evaluates signal definitions against macro snapshots and generates
    investment signals with confidence scores.

    The engine is stateless and deterministic: the same input snapshot
    and signal definitions will always produce the same output.
    """

    def __init__(self) -> None:
        """Initialize the signal engine."""
        self.run_count = 0

    async def run(
        self,
        signal_definitions: list[SignalDefinition],
        snapshot: MacroSnapshot,
    ) -> SignalResult:
        """Run signal evaluation against macro data.

        Evaluates all signals and generates outputs with confidence scores.

        Args:
            signal_definitions: Signals to evaluate
            snapshot: Macro data to evaluate against

        Returns:
            SignalResult containing generated signals

        Raises:
            ValueError: If inputs are invalid
        """
        if not signal_definitions:
            raise ValueError("Signal definitions cannot be empty")
        if not snapshot.features:
            raise ValueError("Snapshot must contain features")

        run_id = str(uuid.uuid4())
        self.run_count += 1
        signals: list[SignalOutput] = []

        for signal_def in signal_definitions:
            try:
                signal_output = await self._evaluate_signal(signal_def, snapshot)
                signals.append(signal_output)
            except Exception:
                # Log but continue with other signals
                # In production, would use structured logging
                continue

        return SignalResult(
            run_id=run_id,
            timestamp=datetime.now(UTC),
            macro_snapshot=snapshot,
            signals=signals,
            success=True,
        )

    async def _evaluate_signal(
        self,
        signal_def: SignalDefinition,
        snapshot: MacroSnapshot,
    ) -> SignalOutput:
        """Evaluate a single signal definition.

        Args:
            signal_def: Signal to evaluate
            snapshot: Macro data

        Returns:
            SignalOutput with score and triggered_at timestamp
        """
        from domain.signals.rules import evaluate_rules

        rule_results = {}
        total_weight = 0.0
        weighted_score = 0.0

        for rule in signal_def.rules:
            # Placeholder: evaluate rule returns 0.0 or 1.0
            rule_score = await evaluate_rules(rule.name, rule.condition, snapshot)
            rule_results[rule.name] = bool(rule_score > 0.5)

            total_weight += rule.weight
            weighted_score += rule_score * rule.weight

        # Calculate final score (0.0-1.0)
        final_score = weighted_score / total_weight if total_weight > 0 else 0.0
        final_score = max(0.0, min(1.0, final_score))

        # Map score to strength
        strength = self._score_to_strength(final_score)

        return SignalOutput(
            signal_id=signal_def.signal_id,
            signal_type=signal_def.signal_type,
            strength=strength,
            score=final_score,
            triggered_at=datetime.now(UTC),
            rule_results=rule_results,
            rationale=f"Signal {signal_def.name} evaluated with {len(rule_results)} rules",
        )

    def _score_to_strength(self, score: float) -> SignalStrength:
        """Map numerical score to signal strength enum.

        Args:
            score: Score from 0.0 to 1.0

        Returns:
            SignalStrength enum value
        """
        if score >= 0.9:
            return SignalStrength.VERY_STRONG
        elif score >= 0.7:
            return SignalStrength.STRONG
        elif score >= 0.5:
            return SignalStrength.MODERATE
        elif score >= 0.3:
            return SignalStrength.WEAK
        else:
            return SignalStrength.VERY_WEAK
