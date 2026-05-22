"""Tests for NormalizedExternalEvent domain model (Chunk 1 — normalization)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.events.enums import (
    ExternalEventFreshness,
    ExternalEventStatus,
    ExternalEventType,
    SourceReliabilityTier,
)
from src.domain.events.models import NormalizedExternalEvent, compute_event_freshness

# ---------------------------------------------------------------------------
# compute_event_freshness
# ---------------------------------------------------------------------------


class TestComputeEventFreshness:
    def test_fresh_within_threshold(self) -> None:
        ref = datetime.now(UTC)
        occurred = ref - timedelta(hours=1)
        result = compute_event_freshness(
            ExternalEventType.MACRO_RELEASE, occurred, reference_time=ref
        )
        assert result == ExternalEventFreshness.FRESH

    def test_recent_between_thresholds(self) -> None:
        ref = datetime.now(UTC)
        occurred = ref - timedelta(hours=30)  # > 24h but < 3 days
        result = compute_event_freshness(
            ExternalEventType.MACRO_RELEASE, occurred, reference_time=ref
        )
        assert result == ExternalEventFreshness.RECENT

    def test_stale_beyond_threshold(self) -> None:
        ref = datetime.now(UTC)
        occurred = ref - timedelta(days=10)
        result = compute_event_freshness(
            ExternalEventType.MACRO_RELEASE, occurred, reference_time=ref
        )
        assert result == ExternalEventFreshness.STALE

    def test_central_bank_has_wider_threshold(self) -> None:
        ref = datetime.now(UTC)
        occurred = ref - timedelta(hours=36)
        result = compute_event_freshness(
            ExternalEventType.CENTRAL_BANK_DECISION, occurred, reference_time=ref
        )
        assert result == ExternalEventFreshness.FRESH

    def test_defaults_reference_time_to_now(self) -> None:
        occurred = datetime.now(UTC) - timedelta(hours=1)
        result = compute_event_freshness(ExternalEventType.MACRO_RELEASE, occurred)
        assert result == ExternalEventFreshness.FRESH


# ---------------------------------------------------------------------------
# NormalizedExternalEvent construction
# ---------------------------------------------------------------------------


class TestNormalizedExternalEvent:
    def _make(self, **kwargs: object) -> NormalizedExternalEvent:
        defaults: dict[str, object] = {
            "event_type": ExternalEventType.MACRO_RELEASE,
            "title": "US CPI Released",
            "occurred_at": datetime.now(UTC) - timedelta(hours=1),
            "source": "BLS",
            "provenance": "fred_release_calendar_v1",
            "summary": "CPI rose 3.1% YoY in January 2024.",
            "reliability_tier": SourceReliabilityTier.TIER_1,
        }
        defaults.update(kwargs)
        return NormalizedExternalEvent(**defaults)  # type: ignore[arg-type]

    def test_basic_construction(self) -> None:
        event = self._make()
        assert event.event_type == ExternalEventType.MACRO_RELEASE
        assert event.title == "US CPI Released"
        assert event.source == "BLS"
        assert isinstance(event.event_id, str)
        assert len(event.event_id) == 36  # UUID format

    def test_freshness_derived_from_occurred_at(self) -> None:
        event = self._make(
            occurred_at=datetime.now(UTC) - timedelta(hours=1),
            freshness=ExternalEventFreshness.UNKNOWN,
        )
        assert event.freshness == ExternalEventFreshness.FRESH

    def test_explicit_freshness_preserved(self) -> None:
        event = self._make(freshness=ExternalEventFreshness.STALE)
        assert event.freshness == ExternalEventFreshness.STALE

    def test_defaults(self) -> None:
        event = self._make()
        assert event.market_scope == []
        assert event.tags == []
        assert event.affected_domains == []
        assert event.metadata == {}
        assert event.status == ExternalEventStatus.ACTIVE
        assert event.region is None
        assert event.entity is None

    def test_is_stale_true_when_stale(self) -> None:
        event = self._make(freshness=ExternalEventFreshness.STALE)
        assert event.is_stale() is True

    def test_is_stale_false_when_fresh(self) -> None:
        event = self._make(freshness=ExternalEventFreshness.FRESH)
        assert event.is_stale() is False

    def test_is_partial_true_when_partial(self) -> None:
        event = self._make(status=ExternalEventStatus.PARTIAL)
        assert event.is_partial() is True

    def test_is_duplicate_true(self) -> None:
        event = self._make(status=ExternalEventStatus.DUPLICATE)
        assert event.is_duplicate() is True

    def test_is_usable_false_for_duplicate(self) -> None:
        event = self._make(status=ExternalEventStatus.DUPLICATE)
        assert event.is_usable() is False

    def test_is_usable_false_for_degraded_stale(self) -> None:
        event = self._make(
            status=ExternalEventStatus.DEGRADED,
            freshness=ExternalEventFreshness.STALE,
        )
        assert event.is_usable() is False

    def test_is_usable_true_for_active_fresh(self) -> None:
        event = self._make()
        assert event.is_usable() is True

    def test_required_fields_enforced(self) -> None:
        with pytest.raises(ValidationError):
            NormalizedExternalEvent(  # type: ignore[call-arg]
                event_type=ExternalEventType.MACRO_RELEASE,
                occurred_at=datetime.now(UTC),
                source="BLS",
                # missing title and provenance
            )

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            NormalizedExternalEvent(
                event_type=ExternalEventType.MACRO_RELEASE,
                title="Test",
                occurred_at=datetime.now(UTC),
                source="BLS",
                provenance="test",
                unknown_field="bad",  # type: ignore[call-arg]
            )

    def test_ingested_at_defaults_to_now(self) -> None:
        before = datetime.now(UTC)
        event = self._make()
        after = datetime.now(UTC)
        assert before <= event.ingested_at <= after
