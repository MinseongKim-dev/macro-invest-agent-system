"""Unit tests for domain.macro.comparison.

Covers:
- PriorFeatureInput: construction, extra=forbid, round-trip
- FeatureDelta: construction, extra=forbid, round-trip
- SnapshotComparison: construction, extra=forbid, round-trip
- compare_snapshots: no-change path, change-detected path,
  prior-snapshot-missing (empty prior_features) path, partial prior,
  unchanged_threshold, first-match-wins, multiple indicator types
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domain.macro.comparison import (
    FeatureDelta,
    PriorFeatureInput,
    SnapshotComparison,
    compare_snapshots,
)
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _feature(
    indicator: MacroIndicatorType,
    value: float,
    country: str = "US",
) -> MacroFeature:
    return MacroFeature(
        indicator_type=indicator,
        source=MacroSourceType.MARKET_DATA,
        value=value,
        timestamp=datetime.now(UTC),
        frequency=DataFrequency.MONTHLY,
        country=country,
    )


def _snapshot(*features: tuple[MacroIndicatorType, float], country: str = "US") -> MacroSnapshot:
    return MacroSnapshot(
        features=[_feature(ind, val, country) for ind, val in features],
        snapshot_time=datetime.now(UTC),
    )


def _prior(*features: tuple[str, float]) -> list[PriorFeatureInput]:
    return [PriorFeatureInput(indicator_type=ind, value=val) for ind, val in features]


# ---------------------------------------------------------------------------
# PriorFeatureInput
# ---------------------------------------------------------------------------


class TestPriorFeatureInput:
    def test_valid_construction(self) -> None:
        p = PriorFeatureInput(indicator_type="gdp", value=3.2)
        assert p.indicator_type == "gdp"
        assert p.value == 3.2

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PriorFeatureInput(indicator_type="gdp", value=3.2, extra="bad")  # type: ignore[call-arg]

    def test_round_trip(self) -> None:
        p = PriorFeatureInput(indicator_type="inflation", value=4.1)
        reparsed = PriorFeatureInput.model_validate(p.model_dump())
        assert reparsed == p


# ---------------------------------------------------------------------------
# FeatureDelta
# ---------------------------------------------------------------------------


class TestFeatureDelta:
    def test_increased(self) -> None:
        d = FeatureDelta(
            indicator_type="gdp",
            current_value=3.7,
            prior_value=3.2,
            delta=0.5,
            direction="increased",
        )
        assert d.direction == "increased"

    def test_decreased(self) -> None:
        d = FeatureDelta(
            indicator_type="inflation",
            current_value=3.9,
            prior_value=4.1,
            delta=-0.2,
            direction="decreased",
        )
        assert d.direction == "decreased"

    def test_unchanged(self) -> None:
        d = FeatureDelta(
            indicator_type="unemployment",
            current_value=5.0,
            prior_value=5.0,
            delta=0.0,
            direction="unchanged",
        )
        assert d.direction == "unchanged"

    def test_no_prior(self) -> None:
        d = FeatureDelta(
            indicator_type="pmi",
            current_value=52.1,
            prior_value=None,
            delta=None,
            direction="no_prior",
        )
        assert d.prior_value is None
        assert d.delta is None

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            FeatureDelta(
                indicator_type="gdp",
                current_value=3.7,
                direction="increased",
                bad_field="x",  # type: ignore[call-arg]
            )

    def test_round_trip(self) -> None:
        d = FeatureDelta(
            indicator_type="gdp",
            current_value=3.7,
            prior_value=3.2,
            delta=0.5,
            direction="increased",
        )
        reparsed = FeatureDelta.model_validate(d.model_dump())
        assert reparsed == d


# ---------------------------------------------------------------------------
# SnapshotComparison
# ---------------------------------------------------------------------------


class TestSnapshotComparison:
    def test_construction(self) -> None:
        sc = SnapshotComparison(
            country="US",
            prior_snapshot_label="Q1-2026",
            changed_count=1,
            unchanged_count=1,
            no_prior_count=0,
        )
        assert sc.country == "US"
        assert sc.changed_count == 1

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotComparison(
                country="US",
                prior_snapshot_label="Q1",
                unknown="x",  # type: ignore[call-arg]
            )

    def test_round_trip(self) -> None:
        sc = SnapshotComparison(
            country="JP",
            prior_snapshot_label="Q4-2025",
            current_snapshot_timestamp=datetime.now(UTC),
            deltas=[
                FeatureDelta(
                    indicator_type="gdp",
                    current_value=2.5,
                    prior_value=2.3,
                    delta=0.2,
                    direction="increased",
                )
            ],
            changed_count=1,
            unchanged_count=0,
            no_prior_count=0,
        )
        reparsed = SnapshotComparison.model_validate(sc.model_dump())
        assert reparsed.country == "JP"
        assert reparsed.deltas[0].direction == "increased"


# ---------------------------------------------------------------------------
# compare_snapshots — no-change path
# ---------------------------------------------------------------------------


class TestCompareSnapshotsNoChange:
    def test_all_unchanged_returns_unchanged_count(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.2), (MacroIndicatorType.INFLATION, 4.1))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2), ("inflation", 4.1)),
            prior_snapshot_label="prior",
            country="US",
        )
        assert result.changed_count == 0
        assert result.unchanged_count == 2
        assert result.no_prior_count == 0

    def test_all_unchanged_directions(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.2))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2)),
            prior_snapshot_label="prior",
            country="US",
        )
        assert result.deltas[0].direction == "unchanged"

    def test_unchanged_threshold_respected(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.2000000001))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2)),
            prior_snapshot_label="prior",
            country="US",
            unchanged_threshold=1e-6,
        )
        assert result.deltas[0].direction == "unchanged"
        assert result.changed_count == 0

    def test_just_above_threshold_registers_as_change(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.2 + 1e-5))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2)),
            prior_snapshot_label="prior",
            country="US",
            unchanged_threshold=1e-6,
        )
        assert result.deltas[0].direction == "increased"
        assert result.changed_count == 1


# ---------------------------------------------------------------------------
# compare_snapshots — change-detected path
# ---------------------------------------------------------------------------


class TestCompareSnapshotsChangeDetected:
    def test_increased_direction(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.7))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2)),
            prior_snapshot_label="Q1-2026",
            country="US",
        )
        assert result.deltas[0].direction == "increased"
        assert result.changed_count == 1

    def test_decreased_direction(self) -> None:
        snap = _snapshot((MacroIndicatorType.INFLATION, 3.9))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("inflation", 4.1)),
            prior_snapshot_label="Q1-2026",
            country="US",
        )
        assert result.deltas[0].direction == "decreased"
        assert result.changed_count == 1

    def test_delta_is_correct(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.7))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2)),
            prior_snapshot_label="Q1",
            country="US",
        )
        assert abs(result.deltas[0].delta - 0.5) < 1e-9  # type: ignore[operator]

    def test_current_and_prior_values_preserved(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.7))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2)),
            prior_snapshot_label="Q1",
            country="US",
        )
        assert result.deltas[0].current_value == 3.7
        assert result.deltas[0].prior_value == 3.2

    def test_mixed_change_and_no_change(self) -> None:
        snap = _snapshot(
            (MacroIndicatorType.GDP, 3.7),
            (MacroIndicatorType.INFLATION, 4.1),
        )
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2), ("inflation", 4.1)),
            prior_snapshot_label="Q1",
            country="US",
        )
        assert result.changed_count == 1
        assert result.unchanged_count == 1

    def test_all_changed(self) -> None:
        snap = _snapshot(
            (MacroIndicatorType.GDP, 3.7),
            (MacroIndicatorType.INFLATION, 5.0),
            (MacroIndicatorType.UNEMPLOYMENT, 3.5),
        )
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(
                ("gdp", 3.2), ("inflation", 4.1), ("unemployment", 4.0)
            ),
            prior_snapshot_label="Q1",
            country="US",
        )
        assert result.changed_count == 3
        assert result.unchanged_count == 0


# ---------------------------------------------------------------------------
# compare_snapshots — prior-snapshot-missing path
# ---------------------------------------------------------------------------


class TestCompareSnapshotsPriorMissing:
    def test_empty_prior_all_no_prior(self) -> None:
        snap = _snapshot(
            (MacroIndicatorType.GDP, 3.2),
            (MacroIndicatorType.INFLATION, 4.1),
        )
        result = compare_snapshots(
            current=snap,
            prior_features=[],
            prior_snapshot_label="missing-prior",
            country="US",
        )
        assert result.no_prior_count == 2
        assert result.changed_count == 0
        assert result.unchanged_count == 0

    def test_empty_prior_directions_all_no_prior(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.2))
        result = compare_snapshots(
            current=snap,
            prior_features=[],
            prior_snapshot_label="missing",
            country="US",
        )
        assert result.deltas[0].direction == "no_prior"
        assert result.deltas[0].prior_value is None
        assert result.deltas[0].delta is None

    def test_partial_prior_some_no_prior(self) -> None:
        snap = _snapshot(
            (MacroIndicatorType.GDP, 3.2),
            (MacroIndicatorType.INFLATION, 4.1),
        )
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.2)),  # no inflation prior
            prior_snapshot_label="partial",
            country="US",
        )
        assert result.no_prior_count == 1
        assert result.unchanged_count == 1


# ---------------------------------------------------------------------------
# compare_snapshots — metadata fields
# ---------------------------------------------------------------------------


class TestCompareSnapshotsMetadata:
    def test_country_is_preserved(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 2.5), country="JP")
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 2.3)),
            prior_snapshot_label="Q4-2025",
            country="JP",
        )
        assert result.country == "JP"

    def test_prior_snapshot_label_is_preserved(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.2))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.0)),
            prior_snapshot_label="Q1-2026",
            country="US",
        )
        assert result.prior_snapshot_label == "Q1-2026"

    def test_current_snapshot_timestamp_is_preserved(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.2))
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.0)),
            prior_snapshot_label="Q1",
            country="US",
        )
        assert result.current_snapshot_timestamp == snap.snapshot_time

    def test_delta_order_matches_current_feature_order(self) -> None:
        snap = _snapshot(
            (MacroIndicatorType.GDP, 3.2),
            (MacroIndicatorType.INFLATION, 4.1),
            (MacroIndicatorType.UNEMPLOYMENT, 4.0),
        )
        result = compare_snapshots(
            current=snap,
            prior_features=_prior(("gdp", 3.0), ("inflation", 4.1), ("unemployment", 4.0)),
            prior_snapshot_label="Q1",
            country="US",
        )
        types = [d.indicator_type for d in result.deltas]
        assert types == ["gdp", "inflation", "unemployment"]

    def test_first_prior_match_wins(self) -> None:
        snap = _snapshot((MacroIndicatorType.GDP, 3.7))
        result = compare_snapshots(
            current=snap,
            prior_features=[
                PriorFeatureInput(indicator_type="gdp", value=3.2),
                PriorFeatureInput(indicator_type="gdp", value=9.9),  # duplicate — ignored
            ],
            prior_snapshot_label="Q1",
            country="US",
        )
        assert result.deltas[0].prior_value == 3.2
