"""Tests for signal domain models."""

from datetime import datetime

import pytest

from src.domain.macro.enums import MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.signals.enums import SignalStrength, SignalType
from src.domain.signals.models import SignalDefinition, SignalOutput, SignalResult, SignalRule


class TestSignalRule:
    """Tests for SignalRule model."""

    def test_create_valid_rule(self) -> None:
        """Test creating a valid signal rule."""
        rule = SignalRule(
            name="high_gdp_growth",
            description="GDP growth above 2%",
            condition="gdp_growth > 2.0",
        )
        assert rule.name == "high_gdp_growth"
        assert rule.weight == 1.0

    def test_rule_with_custom_weight(self) -> None:
        """Test creating rule with custom weight."""
        rule = SignalRule(
            name="inflation_moderate",
            description="Inflation between 2-4%",
            condition="inflation > 2.0 AND inflation < 4.0",
            weight=2.5,
        )
        assert rule.weight == 2.5

    def test_rule_negative_weight_invalid(self) -> None:
        """Test that negative weights are rejected."""
        with pytest.raises(ValueError):
            SignalRule(
                name="invalid",
                description="Invalid",
                condition="test",
                weight=-1.0,
            )


class TestSignalDefinition:
    """Tests for SignalDefinition model."""

    def test_create_valid_signal(self) -> None:
        """Test creating a valid signal definition."""
        rules = [
            SignalRule(
                name="gdp_rule",
                description="GDP check",
                condition="gdp_growth > 2.0",
            )
        ]
        signal = SignalDefinition(
            signal_id="buy_signal_1",
            name="Buy Signal 1",
            signal_type=SignalType.BUY,
            description="Buy when GDP grows",
            rules=rules,
        )
        assert signal.signal_id == "buy_signal_1"
        assert signal.version == 1
        assert len(signal.rules) == 1

    def test_signal_empty_rules_invalid(self) -> None:
        """Test that signals require at least one rule."""
        with pytest.raises(ValueError, match="at least one rule"):
            SignalDefinition(
                signal_id="invalid",
                name="Invalid",
                signal_type=SignalType.BUY,
                description="No rules",
                rules=[],
            )

    def test_signal_with_required_indicators(self) -> None:
        """Test signal with required indicators list."""
        rules = [
            SignalRule(
                name="inflation_check",
                description="Check inflation",
                condition="inflation < 4.0",
            )
        ]
        signal = SignalDefinition(
            signal_id="inflation_signal",
            name="Inflation Signal",
            signal_type=SignalType.HOLD,
            description="Based on inflation",
            rules=rules,
            required_indicators=["inflation", "gdp"],
        )
        assert signal.required_indicators == ["inflation", "gdp"]


class TestSignalOutput:
    """Tests for SignalOutput model."""

    def test_create_valid_output(self) -> None:
        """Test creating a valid signal output."""
        output = SignalOutput(
            signal_id="sig1",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            score=0.85,
            triggered_at=datetime.utcnow(),
        )
        assert output.signal_id == "sig1"
        assert output.score == 0.85

    def test_signal_output_score_bounds(self) -> None:
        """Test that scores are bounded 0.0-1.0."""
        with pytest.raises(ValueError):
            SignalOutput(
                signal_id="sig1",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                score=1.5,  # > 1.0
                triggered_at=datetime.utcnow(),
            )

    def test_signal_output_with_rationale(self) -> None:
        """Test signal output with custom rationale."""
        rationale = "GDP growth accelerating with falling unemployment"
        output = SignalOutput(
            signal_id="sig1",
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            score=0.65,
            triggered_at=datetime.utcnow(),
            rationale=rationale,
        )
        assert output.rationale == rationale

    def test_signal_output_with_rule_results(self) -> None:
        """Test signal output captures rule evaluation results."""
        rule_results = {
            "inflation_check": True,
            "gdp_check": False,
            "employment_check": True,
        }
        output = SignalOutput(
            signal_id="sig1",
            signal_type=SignalType.SELL,
            strength=SignalStrength.WEAK,
            score=0.35,
            triggered_at=datetime.utcnow(),
            rule_results=rule_results,
        )
        assert output.rule_results == rule_results


class TestSignalResult:
    """Tests for SignalResult model."""

    def test_create_valid_result(self) -> None:
        """Test creating a valid signal result."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
            )
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        result = SignalResult(
            run_id="run1",
            timestamp=datetime.utcnow(),
            macro_snapshot=snapshot,
        )
        assert result.run_id == "run1"
        assert result.success is True

    def test_result_with_signals(self) -> None:
        """Test result with generated signals."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
            )
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        signals = [
            SignalOutput(
                signal_id="sig1",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                score=0.9,
                triggered_at=datetime.utcnow(),
            ),
            SignalOutput(
                signal_id="sig2",
                signal_type=SignalType.SELL,
                strength=SignalStrength.WEAK,
                score=0.3,
                triggered_at=datetime.utcnow(),
            ),
        ]
        result = SignalResult(
            run_id="run1",
            timestamp=datetime.utcnow(),
            macro_snapshot=snapshot,
            signals=signals,
        )
        assert len(result.signals) == 2

    def test_get_signals_by_type(self) -> None:
        """Test filtering signals by type."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
            )
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        signals = [
            SignalOutput(
                signal_id="sig1",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                score=0.9,
                triggered_at=datetime.utcnow(),
            ),
            SignalOutput(
                signal_id="sig2",
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                score=0.6,
                triggered_at=datetime.utcnow(),
            ),
            SignalOutput(
                signal_id="sig3",
                signal_type=SignalType.SELL,
                strength=SignalStrength.WEAK,
                score=0.3,
                triggered_at=datetime.utcnow(),
            ),
        ]
        result = SignalResult(
            run_id="run1",
            timestamp=datetime.utcnow(),
            macro_snapshot=snapshot,
            signals=signals,
        )
        buy_signals = result.get_signals_by_type(SignalType.BUY)
        assert len(buy_signals) == 2

    def test_get_buy_and_sell_signals(self) -> None:
        """Test convenience methods for buy/sell signals."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
            )
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        signals = [
            SignalOutput(
                signal_id="sig1",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                score=0.9,
                triggered_at=datetime.utcnow(),
            ),
            SignalOutput(
                signal_id="sig2",
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG,
                score=0.9,
                triggered_at=datetime.utcnow(),
            ),
        ]
        result = SignalResult(
            run_id="run1",
            timestamp=datetime.utcnow(),
            macro_snapshot=snapshot,
            signals=signals,
        )
        assert len(result.get_buy_signals()) == 1
        assert len(result.get_sell_signals()) == 1

    def test_strongest_signal(self) -> None:
        """Test finding strongest signal by score."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
            )
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        signals = [
            SignalOutput(
                signal_id="sig1",
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                score=0.6,
                triggered_at=datetime.utcnow(),
            ),
            SignalOutput(
                signal_id="sig2",
                signal_type=SignalType.BUY,
                strength=SignalStrength.VERY_STRONG,
                score=0.95,
                triggered_at=datetime.utcnow(),
            ),
        ]
        result = SignalResult(
            run_id="run1",
            timestamp=datetime.utcnow(),
            macro_snapshot=snapshot,
            signals=signals,
        )
        strongest = result.strongest_signal()
        assert strongest is not None
        assert strongest.signal_id == "sig2"

    def test_strongest_signal_empty(self) -> None:
        """Test strongest_signal returns None for empty signals."""
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=5.2,
                timestamp=datetime.utcnow(),
            )
        ]
        snapshot = MacroSnapshot(
            features=features,
            snapshot_time=datetime.utcnow(),
        )
        result = SignalResult(
            run_id="run1",
            timestamp=datetime.utcnow(),
            macro_snapshot=snapshot,
            signals=[],
        )
        assert result.strongest_signal() is None
