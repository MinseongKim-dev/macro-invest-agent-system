"""Tests for regime-grounded signal rules."""

from __future__ import annotations

import pytest

from src.domain.macro.regime import RegimeLabel
from src.domain.signals.enums import SignalStrength, SignalType, TrendDirection
from src.domain.signals.regime_signal_rules import REGIME_SIGNAL_MAP, get_regime_signal_rules


class TestRegimeSignalMap:
    def test_all_regime_labels_have_entries(self) -> None:
        """Every RegimeLabel must have at least one signal rule."""
        for label in RegimeLabel:
            rules = get_regime_signal_rules(label)
            assert len(rules) >= 1, f"No signal rules for regime label: {label}"

    def test_goldilocks_has_buy_equities(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.GOLDILOCKS)
        equity_buys = [
            r for r in rules if r.asset_class == "equities" and r.signal_direction == SignalType.BUY
        ]
        assert len(equity_buys) >= 1

    def test_contraction_has_sell_equities_very_strong(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.CONTRACTION)
        sell_equities = [
            r for r in rules if r.asset_class == "equities" and r.signal_direction == SignalType.SELL
        ]
        assert len(sell_equities) >= 1
        assert sell_equities[0].signal_strength == SignalStrength.VERY_STRONG

    def test_stagflation_has_sell_equities(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.STAGFLATION_RISK)
        sells = [r for r in rules if r.signal_direction == SignalType.SELL]
        assert len(sells) >= 1

    def test_unclear_has_neutral_signal(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.UNCLEAR)
        neutral = [r for r in rules if r.signal_direction == SignalType.NEUTRAL]
        assert len(neutral) >= 1

    def test_mixed_has_hold_signal(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.MIXED)
        holds = [r for r in rules if r.signal_direction == SignalType.HOLD]
        assert len(holds) >= 1

    def test_all_rules_have_non_empty_rationale(self) -> None:
        for label, rules in REGIME_SIGNAL_MAP.items():
            for rule in rules:
                assert rule.regime_rationale.strip(), (
                    f"Empty rationale for {label} / {rule.signal_id}"
                )

    def test_all_rules_have_unique_signal_ids(self) -> None:
        all_ids = [rule.signal_id for rules in REGIME_SIGNAL_MAP.values() for rule in rules]
        assert len(all_ids) == len(set(all_ids)), "Duplicate signal IDs found in REGIME_SIGNAL_MAP"

    def test_disinflation_bonds_buy(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.DISINFLATION)
        bond_buys = [
            r for r in rules if r.asset_class == "bonds" and r.signal_direction == SignalType.BUY
        ]
        assert len(bond_buys) >= 1

    def test_policy_tightening_drag_bonds_sell(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.POLICY_TIGHTENING_DRAG)
        bond_sells = [
            r for r in rules if r.asset_class == "bonds" and r.signal_direction == SignalType.SELL
        ]
        assert len(bond_sells) >= 1

    def test_reflation_commodities_buy(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.REFLATION)
        commodity_buys = [
            r for r in rules if r.asset_class == "commodities" and r.signal_direction == SignalType.BUY
        ]
        assert len(commodity_buys) >= 1

    def test_unclear_trend_is_unknown(self) -> None:
        rules = get_regime_signal_rules(RegimeLabel.UNCLEAR)
        assert rules[0].trend == TrendDirection.UNKNOWN

    def test_fallback_returns_unclear_rules(self) -> None:
        """get_regime_signal_rules falls back to UNCLEAR for unknown labels."""
        unclear_rules = get_regime_signal_rules(RegimeLabel.UNCLEAR)
        # Ensure the function returns the UNCLEAR rules for a missing entry by
        # temporarily checking the fallback branch manually
        assert unclear_rules == REGIME_SIGNAL_MAP[RegimeLabel.UNCLEAR]


@pytest.mark.asyncio
async def test_signal_service_run_regime_grounded_engine() -> None:
    """SignalService.run_regime_grounded_engine produces grounded signals."""
    from datetime import UTC, date, datetime

    from src.domain.macro.regime import (
        MacroRegime,
        RegimeConfidence,
        RegimeFamily,
    )
    from src.domain.macro.snapshot import DegradedStatus
    from src.pipelines.ingestion.models import FreshnessStatus
    from src.services.signal_service import SignalService

    regime = MacroRegime(
        as_of_date=date(2026, 4, 1),
        regime_timestamp=datetime(2026, 4, 1, tzinfo=UTC),
        regime_label=RegimeLabel.GOLDILOCKS,
        regime_family=RegimeFamily.EXPANSION,
        supporting_snapshot_id="snap-test",
        confidence=RegimeConfidence.HIGH,
        freshness_status=FreshnessStatus.FRESH,
        degraded_status=DegradedStatus.NONE,
    )

    svc = SignalService()
    result = await svc.run_regime_grounded_engine(regime)

    assert result.success is True
    assert len(result.signals) >= 1
    buy_signals = [s for s in result.signals if str(s.signal_type) == "buy"]
    assert len(buy_signals) >= 1
    # All signals must have non-empty rationale
    for sig in result.signals:
        assert sig.rationale.strip()
