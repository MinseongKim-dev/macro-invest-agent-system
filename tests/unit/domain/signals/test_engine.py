"""Tests for signal engine."""

from datetime import datetime

import pytest

from src.domain.macro.enums import MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.signals.engine import SignalEngine
from src.domain.signals.enums import SignalStrength, SignalType
from src.domain.signals.models import SignalDefinition, SignalRule


@pytest.mark.asyncio
class TestSignalEngine:
    """Tests for SignalEngine."""

    async def test_engine_initialization(self) -> None:
        """Test engine initializes correctly."""
        engine = SignalEngine()
        assert engine.run_count == 0

    async def test_engine_run_with_signals(self) -> None:
        """Test running engine with valid signals."""
        engine = SignalEngine()

        rules = [
            SignalRule(
                name="test_rule",
                description="Test rule",
                condition="gdp > 0",
            )
        ]
        signal_def = SignalDefinition(
            signal_id="test_signal",
            name="Test Signal",
            signal_type=SignalType.BUY,
            description="Test signal",
            rules=rules,
        )

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

        result = await engine.run([signal_def], snapshot)

        assert result.success is True
        assert len(result.signals) > 0
        assert engine.run_count == 1

    async def test_engine_run_empty_signals_invalid(self) -> None:
        """Test that engine rejects empty signal list."""
        engine = SignalEngine()

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

        with pytest.raises(ValueError, match="empty"):
            await engine.run([], snapshot)

    async def test_engine_score_to_strength_mapping(self) -> None:
        """Test score to strength enum mapping."""
        engine = SignalEngine()

        assert engine._score_to_strength(0.95) == SignalStrength.VERY_STRONG
        assert engine._score_to_strength(0.75) == SignalStrength.STRONG
        assert engine._score_to_strength(0.55) == SignalStrength.MODERATE
        assert engine._score_to_strength(0.35) == SignalStrength.WEAK
        assert engine._score_to_strength(0.15) == SignalStrength.VERY_WEAK
