"""Tests for signal service."""

from datetime import datetime

import pytest

from src.domain.macro.enums import MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.signals.enums import SignalType
from src.domain.signals.models import SignalDefinition, SignalRule
from src.services.signal_service import SignalService


@pytest.mark.asyncio
class TestSignalService:
    """Tests for SignalService."""

    async def test_service_initialization(self) -> None:
        """Test signal service initializes."""
        service = SignalService()
        assert service.engine is not None

    async def test_evaluate_signal(self) -> None:
        """Test evaluating a signal."""
        service = SignalService()

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

        results = await service.evaluate_signal(signal_def, snapshot)
        assert isinstance(results, dict)
        assert len(results) > 0

    async def test_evaluate_signal_no_rules_invalid(self) -> None:
        """Test that signal with no rules is rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SignalDefinition(
                signal_id="invalid",
                name="Invalid Signal",
                signal_type=SignalType.BUY,
                description="No rules",
                rules=[],
            )

    async def test_run_engine(self) -> None:
        """Test running the signal engine."""
        service = SignalService()

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

        result = await service.run_engine([signal_def], snapshot)
        assert result.success is True

    async def test_run_engine_empty_signals_invalid(self) -> None:
        """Test that engine rejects empty signal list."""
        service = SignalService()

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

        with pytest.raises(ValueError, match="At least one"):
            await service.run_engine([], snapshot)
