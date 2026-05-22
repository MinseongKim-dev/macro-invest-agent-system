"""Tests for domain/macro/history.py — historical read models."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.domain.macro.history import (
    RegimeHistoryBundle,
    build_regime_history_bundle,
    regime_to_historical_record,
)
from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
from src.domain.macro.snapshot import DegradedStatus
from src.pipelines.ingestion.models import FreshnessStatus


def _make_regime(
    *,
    as_of_date: date = date(2026, 1, 1),
    label: RegimeLabel = RegimeLabel.GOLDILOCKS,
    family: RegimeFamily = RegimeFamily.EXPANSION,
    confidence: RegimeConfidence = RegimeConfidence.HIGH,
    transition_type: RegimeTransitionType = RegimeTransitionType.INITIAL,
    transition_from_prior: str | None = None,
    changed: bool = False,
    is_seeded: bool = False,
) -> MacroRegime:
    meta = {"seeded": "true", "source": "synthetic_seed"} if is_seeded else {}
    return MacroRegime(
        as_of_date=as_of_date,
        regime_timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        regime_label=label,
        regime_family=family,
        supporting_snapshot_id="snap-1",
        confidence=confidence,
        freshness_status=FreshnessStatus.FRESH,
        degraded_status=DegradedStatus.NONE,
        transition=RegimeTransition(
            transition_from_prior=transition_from_prior,
            transition_type=transition_type,
            changed=changed,
        ),
        metadata=meta,
    )


class TestRegimeToHistoricalRecord:
    def test_basic_fields_mapped(self) -> None:
        regime = _make_regime()
        record = regime_to_historical_record(regime)
        assert record.regime_id == regime.regime_id
        assert record.as_of_date == date(2026, 1, 1)
        assert record.regime_label == "goldilocks"
        assert record.regime_family == "expansion"
        assert record.confidence == "high"
        assert record.freshness_status == "fresh"
        assert record.degraded_status == "none"
        assert record.transition_type == "initial"
        assert record.transition_from_prior is None
        assert record.changed is False
        assert record.is_seeded is False

    def test_seeded_regime_sets_is_seeded(self) -> None:
        regime = _make_regime(is_seeded=True)
        record = regime_to_historical_record(regime)
        assert record.is_seeded is True

    def test_shift_transition_mapped(self) -> None:
        regime = _make_regime(
            transition_type=RegimeTransitionType.SHIFT,
            transition_from_prior="slowdown",
            changed=True,
        )
        record = regime_to_historical_record(regime)
        assert record.transition_type == "shift"
        assert record.transition_from_prior == "slowdown"
        assert record.changed is True

    def test_missing_inputs_propagated(self) -> None:
        regime = _make_regime()
        regime = regime.model_copy(update={"missing_inputs": ["gdp", "pmi"]})
        record = regime_to_historical_record(regime)
        assert record.missing_inputs == ["gdp", "pmi"]

    def test_supporting_snapshot_id_mapped(self) -> None:
        regime = _make_regime()
        record = regime_to_historical_record(regime)
        assert record.supporting_snapshot_id == "snap-1"


class TestBuildRegimeHistoryBundle:
    def test_empty_list_produces_empty_bundle(self) -> None:
        bundle = build_regime_history_bundle(regimes=[], as_of_date=date(2026, 3, 1))
        assert bundle.total == 0
        assert bundle.records == []
        assert bundle.latest is None
        assert bundle.previous is None

    def test_single_regime_populates_latest_only(self) -> None:
        regime = _make_regime(as_of_date=date(2026, 3, 1))
        bundle = build_regime_history_bundle(regimes=[regime], as_of_date=date(2026, 3, 1))
        assert bundle.total == 1
        assert bundle.latest is not None
        assert bundle.latest.as_of_date == date(2026, 3, 1)
        assert bundle.previous is None

    def test_two_regimes_populates_latest_and_previous(self) -> None:
        r1 = _make_regime(as_of_date=date(2026, 3, 1))  # most recent
        r2 = _make_regime(as_of_date=date(2026, 2, 1))  # prior
        bundle = build_regime_history_bundle(regimes=[r1, r2], as_of_date=date(2026, 3, 1))
        assert bundle.total == 2
        assert bundle.latest is not None
        assert bundle.latest.as_of_date == date(2026, 3, 1)
        assert bundle.previous is not None
        assert bundle.previous.as_of_date == date(2026, 2, 1)

    def test_records_ordered_most_recent_first(self) -> None:
        dates = [date(2026, 1, d) for d in [5, 1, 3]]
        regimes = [_make_regime(as_of_date=d) for d in dates]
        bundle = build_regime_history_bundle(regimes=regimes, as_of_date=date(2026, 1, 5))
        # Input is already ordered as the caller provides; bundle does NOT re-sort
        assert bundle.records[0].as_of_date == date(2026, 1, 5)

    def test_as_of_date_set_correctly(self) -> None:
        bundle = build_regime_history_bundle(regimes=[], as_of_date=date(2026, 6, 15))
        assert bundle.as_of_date == date(2026, 6, 15)


class TestRegimeHistoryBundleModel:
    def test_model_extra_forbid(self) -> None:
        with pytest.raises(ValueError):
            RegimeHistoryBundle(
                as_of_date=date(2026, 1, 1),
                total=0,
                unknown_field="should_fail",  # type: ignore[call-arg]
            )
