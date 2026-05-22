"""Tests for external event routes — GET /api/events/recent, GET /api/events/{id}."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from apps.api.dependencies import get_event_repository
from apps.api.main import app
from src.agent.adapters.repositories.in_memory_event_store import InMemoryEventStore
from src.domain.events.enums import (
    ExternalEventFreshness,
    ExternalEventStatus,
    ExternalEventType,
    SourceReliabilityTier,
)
from src.domain.events.models import NormalizedExternalEvent


def _make_event(
    *,
    event_type: ExternalEventType = ExternalEventType.MACRO_RELEASE,
    status: ExternalEventStatus = ExternalEventStatus.ACTIVE,
    region: str | None = "US",
    occurred_at: datetime | None = None,
    title: str = "CPI report",
) -> NormalizedExternalEvent:
    return NormalizedExternalEvent(
        event_type=event_type,
        title=title,
        source="BLS",
        provenance="test",
        occurred_at=occurred_at or datetime.now(UTC),
        status=status,
        region=region,
        freshness=ExternalEventFreshness.FRESH,
        reliability_tier=SourceReliabilityTier.TIER_1,
    )


def _store_with(*events: NormalizedExternalEvent) -> InMemoryEventStore:
    store = InMemoryEventStore()
    for e in events:
        store.save(e)
    return store


class TestEventsRecentRoute:
    def test_empty_store_returns_empty_list(self) -> None:
        store = InMemoryEventStore()
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["events"] == []
            assert payload["total"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_returns_stored_events(self) -> None:
        store = _store_with(_make_event(), _make_event(title="Fed meeting"))
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent")
            assert resp.status_code == 200
            assert resp.json()["total"] == 2
        finally:
            app.dependency_overrides.clear()

    def test_event_type_filter(self) -> None:
        store = _store_with(
            _make_event(event_type=ExternalEventType.MACRO_RELEASE),
            _make_event(event_type=ExternalEventType.CENTRAL_BANK_DECISION),
        )
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent?event_type=central_bank_decision")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["total"] == 1
            assert payload["events"][0]["event_type"] == "central_bank_decision"
        finally:
            app.dependency_overrides.clear()

    def test_status_filter(self) -> None:
        store = _store_with(
            _make_event(status=ExternalEventStatus.ACTIVE),
            _make_event(status=ExternalEventStatus.STALE),
        )
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent?status=stale")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_region_filter(self) -> None:
        store = _store_with(
            _make_event(region="US"),
            _make_event(region="EU"),
        )
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent?region=EU")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
            assert resp.json()["events"][0]["region"] == "EU"
        finally:
            app.dependency_overrides.clear()

    def test_since_filter(self) -> None:
        now = datetime.now(UTC)
        old_event = _make_event(occurred_at=now - timedelta(days=10))
        new_event = _make_event(occurred_at=now - timedelta(days=1))
        store = _store_with(old_event, new_event)
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            since = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
            resp = tc.get(f"/api/events/recent?since={since}")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_until_filter(self) -> None:
        now = datetime.now(UTC)
        old_event = _make_event(occurred_at=now - timedelta(days=10))
        new_event = _make_event(occurred_at=now - timedelta(days=1))
        store = _store_with(old_event, new_event)
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            until = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
            resp = tc.get(f"/api/events/recent?until={until}")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_limit_applied(self) -> None:
        store = _store_with(_make_event(), _make_event(title="B"), _make_event(title="C"))
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent?limit=2")
            assert resp.status_code == 200
            payload = resp.json()
            assert len(payload["events"]) == 2
            assert payload["limit_applied"] == 2
        finally:
            app.dependency_overrides.clear()

    def test_invalid_event_type_returns_422(self) -> None:
        store = InMemoryEventStore()
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent?event_type=invalid_type")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_invalid_status_returns_422(self) -> None:
        store = InMemoryEventStore()
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent?status=not_a_status")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_response_fields_shape(self) -> None:
        event = _make_event()
        store = _store_with(event)
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/recent")
            assert resp.status_code == 200
            dto = resp.json()["events"][0]
            assert "event_id" in dto
            assert "event_type" in dto
            assert "title" in dto
            assert "freshness" in dto
            assert "reliability_tier" in dto
            assert "status" in dto
        finally:
            app.dependency_overrides.clear()


class TestEventsGetByIdRoute:
    def test_returns_event_by_id(self) -> None:
        event = _make_event()
        store = _store_with(event)
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get(f"/api/events/{event.event_id}")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["event_id"] == event.event_id
            assert payload["title"] == event.title
        finally:
            app.dependency_overrides.clear()

    def test_not_found_returns_404(self) -> None:
        store = InMemoryEventStore()
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/events/nonexistent-id")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_event_fields_complete(self) -> None:
        event = NormalizedExternalEvent(
            event_type=ExternalEventType.CENTRAL_BANK_DECISION,
            title="Fed raises rates by 25bps",
            summary="The Federal Reserve raised its target rate.",
            entity="Federal Reserve",
            region="US",
            market_scope=["bonds", "equities"],
            occurred_at=datetime.now(UTC),
            source="Federal Reserve",
            source_url="https://www.federalreserve.gov/",
            provider="fred_release_calendar",
            freshness=ExternalEventFreshness.FRESH,
            provenance="fred_release_calendar_v1",
            reliability_tier=SourceReliabilityTier.TIER_1,
            tags=["monetary_policy", "rate_decision"],
            affected_domains=["policy", "growth"],
            status=ExternalEventStatus.ACTIVE,
        )
        store = _store_with(event)
        app.dependency_overrides[get_event_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get(f"/api/events/{event.event_id}")
            assert resp.status_code == 200
            dto = resp.json()
            assert dto["entity"] == "Federal Reserve"
            assert dto["region"] == "US"
            assert "bonds" in dto["market_scope"]
            assert dto["source_url"] == "https://www.federalreserve.gov/"
            assert dto["provider"] == "fred_release_calendar"
            assert "monetary_policy" in dto["tags"]
            assert "policy" in dto["affected_domains"]
        finally:
            app.dependency_overrides.clear()
