"""Tests for external event normalization helpers (Chunk 1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.domain.events.enums import (
    ExternalEventFreshness,
    ExternalEventStatus,
    ExternalEventType,
    SourceReliabilityTier,
)
from src.domain.events.models import NormalizedExternalEvent
from src.domain.events.normalizer import (
    assess_event_quality,
    infer_reliability_tier,
    normalize_external_event,
)

# ---------------------------------------------------------------------------
# infer_reliability_tier
# ---------------------------------------------------------------------------


class TestInferReliabilityTier:
    def test_known_tier1_source(self) -> None:
        assert infer_reliability_tier("Federal_Reserve") == SourceReliabilityTier.TIER_1

    def test_known_tier1_fred(self) -> None:
        assert infer_reliability_tier("fred") == SourceReliabilityTier.TIER_1

    def test_known_tier2_reuters(self) -> None:
        assert infer_reliability_tier("reuters") == SourceReliabilityTier.TIER_2

    def test_manual_entry_tier3(self) -> None:
        assert infer_reliability_tier("manual_entry") == SourceReliabilityTier.TIER_3

    def test_unknown_source_returns_unknown(self) -> None:
        assert infer_reliability_tier("some_random_source") == SourceReliabilityTier.UNKNOWN

    def test_case_insensitive(self) -> None:
        assert infer_reliability_tier("REUTERS") == SourceReliabilityTier.TIER_2


# ---------------------------------------------------------------------------
# normalize_external_event
# ---------------------------------------------------------------------------


class TestNormalizeExternalEvent:
    def _fresh_occurred_at(self) -> datetime:
        return datetime.now(UTC) - timedelta(hours=1)

    def test_basic_normalization(self) -> None:
        event = normalize_external_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            title="US CPI Released",
            occurred_at=self._fresh_occurred_at(),
            source="BLS",
            provenance="bls_release_v1",
            summary="CPI rose 3.1% YoY.",
        )
        assert isinstance(event, NormalizedExternalEvent)
        assert event.event_type == ExternalEventType.MACRO_RELEASE
        assert event.title == "US CPI Released"
        assert event.freshness == ExternalEventFreshness.FRESH
        assert event.reliability_tier == SourceReliabilityTier.TIER_1

    def test_title_stripped(self) -> None:
        event = normalize_external_event(
            event_type=ExternalEventType.OTHER,
            title="  Padded Title  ",
            occurred_at=self._fresh_occurred_at(),
            source="manual_entry",
            provenance="test",
        )
        assert event.title == "Padded Title"

    def test_partial_status_when_summary_missing(self) -> None:
        event = normalize_external_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            title="GDP Released",
            occurred_at=self._fresh_occurred_at(),
            source="BEA",
            provenance="bea_v1",
            summary=None,
        )
        assert event.status == ExternalEventStatus.PARTIAL

    def test_stale_status_when_freshness_stale(self) -> None:
        stale_occurred = datetime.now(UTC) - timedelta(days=30)
        event = normalize_external_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            title="Old CPI Data",
            occurred_at=stale_occurred,
            source="BLS",
            provenance="test",
            summary="Old CPI data.",
        )
        assert event.freshness == ExternalEventFreshness.STALE
        assert event.status == ExternalEventStatus.STALE

    def test_explicit_reliability_tier_used(self) -> None:
        event = normalize_external_event(
            event_type=ExternalEventType.OTHER,
            title="Some Event",
            occurred_at=self._fresh_occurred_at(),
            source="unknown_source",
            provenance="test",
            reliability_tier=SourceReliabilityTier.TIER_2,
        )
        assert event.reliability_tier == SourceReliabilityTier.TIER_2

    def test_inferred_reliability_when_not_provided(self) -> None:
        event = normalize_external_event(
            event_type=ExternalEventType.CENTRAL_BANK_DECISION,
            title="Fed Rate Decision",
            occurred_at=self._fresh_occurred_at(),
            source="Federal_Reserve",
            provenance="fed_calendar_v1",
            summary="Fed raised rates by 25 bps.",
        )
        assert event.reliability_tier == SourceReliabilityTier.TIER_1

    def test_affected_domains_stored(self) -> None:
        event = normalize_external_event(
            event_type=ExternalEventType.CENTRAL_BANK_DECISION,
            title="Rate Hike",
            occurred_at=self._fresh_occurred_at(),
            source="fed",
            provenance="test",
            summary="Rate hike.",
            affected_domains=["policy", "inflation", "credit"],
        )
        assert "policy" in event.affected_domains
        assert "inflation" in event.affected_domains

    def test_tags_stored(self) -> None:
        event = normalize_external_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            title="Jobs Report",
            occurred_at=self._fresh_occurred_at(),
            source="BLS",
            provenance="bls_v1",
            tags=["employment", "nonfarm_payrolls"],
        )
        assert "employment" in event.tags

    def test_reference_time_controls_freshness(self) -> None:
        occurred = datetime(2023, 1, 1, tzinfo=UTC)
        ref = datetime(2023, 1, 2, tzinfo=UTC)  # 1 day later → fresh for macro_release
        event = normalize_external_event(
            event_type=ExternalEventType.MACRO_RELEASE,
            title="Old event, fresh relative to ref",
            occurred_at=occurred,
            source="BLS",
            provenance="test",
            summary="Data.",
            reference_time=ref,
        )
        assert event.freshness == ExternalEventFreshness.FRESH


# ---------------------------------------------------------------------------
# assess_event_quality
# ---------------------------------------------------------------------------


class TestAssessEventQuality:
    def _make(self, **kwargs: object) -> NormalizedExternalEvent:
        defaults: dict[str, object] = {
            "event_type": ExternalEventType.MACRO_RELEASE,
            "title": "CPI",
            "occurred_at": datetime.now(UTC) - timedelta(hours=1),
            "source": "BLS",
            "provenance": "test",
            "summary": "CPI data.",
            "reliability_tier": SourceReliabilityTier.TIER_1,
        }
        defaults.update(kwargs)
        return NormalizedExternalEvent(**defaults)  # type: ignore[arg-type]

    def test_no_issues_returns_empty(self) -> None:
        event = self._make()
        notes = assess_event_quality(event)
        assert notes == []

    def test_stale_note_when_stale(self) -> None:
        event = self._make(freshness=ExternalEventFreshness.STALE)
        notes = assess_event_quality(event)
        assert any("stale" in n.lower() for n in notes)

    def test_partial_note_when_partial(self) -> None:
        event = self._make(status=ExternalEventStatus.PARTIAL)
        notes = assess_event_quality(event)
        assert any("partial" in n.lower() for n in notes)

    def test_tier3_source_note(self) -> None:
        event = self._make(
            source="manual_entry",
            reliability_tier=SourceReliabilityTier.TIER_3,
        )
        notes = assess_event_quality(event)
        assert any("lower-reliability" in n.lower() for n in notes)

    def test_unknown_tier_note(self) -> None:
        event = self._make(
            source="mystery_source",
            reliability_tier=SourceReliabilityTier.UNKNOWN,
        )
        notes = assess_event_quality(event)
        assert any("reliability is unknown" in n.lower() for n in notes)

    def test_duplicate_note(self) -> None:
        event = self._make(status=ExternalEventStatus.DUPLICATE)
        notes = assess_event_quality(event)
        assert any("duplicate" in n.lower() for n in notes)

    def test_degraded_note(self) -> None:
        event = self._make(status=ExternalEventStatus.DEGRADED)
        notes = assess_event_quality(event)
        assert any("quality issues" in n.lower() for n in notes)
