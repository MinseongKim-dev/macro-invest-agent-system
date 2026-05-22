"""Tests for the trust metadata DTOs and trust metadata builder functions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.api.dto.builders import (
    build_trust_from_comparison,
    build_trust_from_signal_result,
    build_trust_from_snapshot,
    delta_to_dto,
    feature_to_dto,
    signal_output_to_dto,
)
from apps.api.dto.trust import DataAvailability, FreshnessStatus, TrustMetadata
from src.domain.macro.comparison import FeatureDelta, PriorFeatureInput, SnapshotComparison
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.signals.enums import SignalStrength, SignalType, TrendDirection
from src.domain.signals.models import SignalOutput, SignalResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _snapshot(country: str = "US") -> MacroSnapshot:
    return MacroSnapshot(
        features=[
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=3.2,
                timestamp=_NOW,
                frequency=DataFrequency.QUARTERLY,
                country=country,
            ),
            MacroFeature(
                indicator_type=MacroIndicatorType.INFLATION,
                source=MacroSourceType.FRED,
                value=2.8,
                timestamp=_NOW,
                frequency=DataFrequency.MONTHLY,
                country=country,
            ),
        ],
        snapshot_time=_NOW,
        version=1,
    )


def _signal_output(score: float = 0.85) -> SignalOutput:
    return SignalOutput(
        signal_id="bull_market",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        score=score,
        triggered_at=_NOW,
        trend=TrendDirection.UP,
        rationale="GDP up, inflation contained.",
        rule_results={"gdp_growth_positive": True, "inflation_contained": False},
    )


def _signal_result(success: bool = True) -> SignalResult:
    return SignalResult(
        run_id="run-001",
        timestamp=_NOW,
        macro_snapshot=_snapshot(),
        signals=[_signal_output()],
        success=success,
        error_message=None if success else "engine error",
    )


# ---------------------------------------------------------------------------
# TrustMetadata model tests
# ---------------------------------------------------------------------------


class TestTrustMetadata:
    def test_default_freshness_is_unknown(self) -> None:
        trust = TrustMetadata()
        assert trust.freshness_status == FreshnessStatus.UNKNOWN

    def test_default_availability_is_full(self) -> None:
        trust = TrustMetadata()
        assert trust.availability == DataAvailability.FULL

    def test_is_degraded_default_false(self) -> None:
        trust = TrustMetadata()
        assert trust.is_degraded is False

    def test_sources_default_empty(self) -> None:
        trust = TrustMetadata()
        assert trust.sources == []

    def test_changed_indicators_count_default_none(self) -> None:
        trust = TrustMetadata()
        assert trust.changed_indicators_count is None

    def test_freshness_status_enum_values(self) -> None:
        assert FreshnessStatus.FRESH.value == "fresh"
        assert FreshnessStatus.STALE.value == "stale"
        assert FreshnessStatus.UNKNOWN.value == "unknown"

    def test_data_availability_enum_values(self) -> None:
        assert DataAvailability.FULL.value == "full"
        assert DataAvailability.PARTIAL.value == "partial"
        assert DataAvailability.DEGRADED.value == "degraded"
        assert DataAvailability.UNAVAILABLE.value == "unavailable"


# ---------------------------------------------------------------------------
# build_trust_from_snapshot
# ---------------------------------------------------------------------------


class TestBuildTrustFromSnapshot:
    def test_freshness_is_fresh(self) -> None:
        trust = build_trust_from_snapshot(_snapshot())
        assert trust.freshness_status == FreshnessStatus.FRESH

    def test_availability_is_full(self) -> None:
        trust = build_trust_from_snapshot(_snapshot())
        assert trust.availability == DataAvailability.FULL

    def test_snapshot_timestamp_set(self) -> None:
        trust = build_trust_from_snapshot(_snapshot())
        assert trust.snapshot_timestamp == _NOW

    def test_sources_populated(self) -> None:
        trust = build_trust_from_snapshot(_snapshot())
        assert len(trust.sources) >= 1
        source_ids = [s.source_id for s in trust.sources]
        assert "fred" in source_ids

    def test_is_degraded_false(self) -> None:
        trust = build_trust_from_snapshot(_snapshot())
        assert trust.is_degraded is False


# ---------------------------------------------------------------------------
# build_trust_from_comparison
# ---------------------------------------------------------------------------


class TestBuildTrustFromComparison:
    def _comparison(self, no_prior_count: int = 0) -> SnapshotComparison:
        deltas: list[FeatureDelta] = []
        if no_prior_count == 0:
            deltas = [
                FeatureDelta(
                    indicator_type="gdp",
                    current_value=3.2,
                    prior_value=3.0,
                    delta=0.2,
                    direction="increased",
                )
            ]
        else:
            for _ in range(no_prior_count):
                deltas.append(
                    FeatureDelta(
                        indicator_type="gdp",
                        current_value=3.2,
                        prior_value=None,
                        delta=None,
                        direction="no_prior",
                    )
                )
        return SnapshotComparison(
            country="US",
            prior_snapshot_label="Q1",
            current_snapshot_timestamp=_NOW,
            deltas=deltas,
            changed_count=1 if no_prior_count == 0 else 0,
            unchanged_count=0,
            no_prior_count=no_prior_count,
        )

    def test_changed_indicators_count_set(self) -> None:
        comp = self._comparison(no_prior_count=0)
        trust = build_trust_from_comparison(comp, _snapshot())
        assert trust.changed_indicators_count == 1

    def test_availability_partial_when_some_no_prior(self) -> None:
        snap = MacroSnapshot(
            features=[
                MacroFeature(
                    indicator_type=MacroIndicatorType.GDP,
                    source=MacroSourceType.FRED,
                    value=3.2,
                    timestamp=_NOW,
                    frequency=DataFrequency.QUARTERLY,
                    country="US",
                ),
                MacroFeature(
                    indicator_type=MacroIndicatorType.INFLATION,
                    source=MacroSourceType.FRED,
                    value=2.8,
                    timestamp=_NOW,
                    frequency=DataFrequency.MONTHLY,
                    country="US",
                ),
            ],
            snapshot_time=_NOW,
            version=1,
        )
        # One indicator matched, one no_prior
        from src.domain.macro.comparison import compare_snapshots

        comp = compare_snapshots(
            current=snap,
            prior_features=[PriorFeatureInput(indicator_type="gdp", value=3.0)],
            prior_snapshot_label="prior",
            country="US",
        )
        trust = build_trust_from_comparison(comp, snap)
        assert trust.availability == DataAvailability.PARTIAL

    def test_availability_unavailable_when_all_no_prior(self) -> None:
        comp = self._comparison(no_prior_count=1)
        trust = build_trust_from_comparison(comp, _snapshot())
        assert trust.availability == DataAvailability.UNAVAILABLE

    def test_previous_snapshot_timestamp_set_from_param(self) -> None:
        comp = self._comparison()
        prior_ts = datetime(2025, 10, 1, tzinfo=UTC)
        trust = build_trust_from_comparison(comp, _snapshot(), prior_snapshot_timestamp=prior_ts)
        assert trust.previous_snapshot_timestamp == prior_ts


# ---------------------------------------------------------------------------
# build_trust_from_signal_result
# ---------------------------------------------------------------------------


class TestBuildTrustFromSignalResult:
    def test_full_availability_on_success_with_signals(self) -> None:
        trust = build_trust_from_signal_result(_signal_result(success=True))
        assert trust.availability == DataAvailability.FULL

    def test_partial_availability_on_no_signals(self) -> None:
        result = SignalResult(
            run_id="run-empty",
            timestamp=_NOW,
            macro_snapshot=_snapshot(),
            signals=[],
            success=True,
        )
        trust = build_trust_from_signal_result(result)
        assert trust.availability == DataAvailability.PARTIAL

    def test_unavailable_on_failure(self) -> None:
        result = SignalResult(
            run_id="run-fail",
            timestamp=_NOW,
            macro_snapshot=_snapshot(),
            signals=[],
            success=False,
            error_message="engine error",
        )
        trust = build_trust_from_signal_result(result)
        assert trust.availability == DataAvailability.UNAVAILABLE

    def test_is_degraded_on_failure(self) -> None:
        result = SignalResult(
            run_id="run-fail",
            timestamp=_NOW,
            macro_snapshot=_snapshot(),
            signals=[],
            success=False,
            error_message="engine error",
        )
        trust = build_trust_from_signal_result(result)
        assert trust.is_degraded is True


# ---------------------------------------------------------------------------
# DTO converter tests
# ---------------------------------------------------------------------------


class TestFeatureToDTO:
    def test_fields_mapped(self) -> None:
        feature = MacroFeature(
            indicator_type=MacroIndicatorType.GDP,
            source=MacroSourceType.FRED,
            value=3.2,
            timestamp=_NOW,
            frequency=DataFrequency.QUARTERLY,
            country="US",
        )
        dto = feature_to_dto(feature)
        assert dto.indicator_type == "gdp"
        assert dto.indicator_label == "GDP Growth"
        assert dto.value == 3.2
        assert dto.source_id == "fred"
        assert dto.frequency == "quarterly"
        assert dto.country == "US"
        assert dto.observed_at == _NOW


class TestDeltaToDTO:
    def test_increased_direction(self) -> None:
        delta = FeatureDelta(
            indicator_type="gdp",
            current_value=3.2,
            prior_value=3.0,
            delta=0.2,
            direction="increased",
        )
        dto = delta_to_dto(delta)
        assert dto.direction == "increased"
        assert dto.delta == pytest.approx(0.2)
        assert dto.current_value == 3.2
        assert dto.prior_value == 3.0
        assert dto.indicator_label == "GDP Growth"

    def test_no_prior_direction(self) -> None:
        delta = FeatureDelta(
            indicator_type="gdp",
            current_value=3.2,
            prior_value=None,
            delta=None,
            direction="no_prior",
        )
        dto = delta_to_dto(delta)
        assert dto.direction == "no_prior"
        assert dto.prior_value is None
        assert dto.delta is None

    def test_is_significant_defaults_false(self) -> None:
        delta = FeatureDelta(
            indicator_type="inflation",
            current_value=2.8,
            prior_value=2.5,
            delta=0.3,
            direction="increased",
        )
        dto = delta_to_dto(delta)
        assert dto.is_significant is False


class TestSignalOutputToDTO:
    def test_fields_mapped(self) -> None:
        signal = _signal_output()
        dto = signal_output_to_dto(signal)
        assert dto.signal_id == "bull_market"
        assert dto.signal_type == "buy"
        assert dto.strength == "strong"
        assert dto.score == pytest.approx(0.85)
        assert dto.trend == "up"
        assert dto.rationale == "GDP up, inflation contained."

    def test_rules_counts(self) -> None:
        signal = _signal_output()
        dto = signal_output_to_dto(signal)
        assert dto.rules_total == 2
        assert dto.rules_passed == 1  # one True, one False
