"""Tests for alert routes — GET /api/alerts/recent, GET /api/alerts/{id},
PATCH /api/alerts/{id}/acknowledge, PATCH /api/alerts/{id}/snooze.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.agent.adapters.repositories.in_memory_alert_store import InMemoryAlertStore
from apps.api.dependencies import get_alert_repository
from apps.api.main import app
from src.domain.alerts.models import (
    AlertEvent,
    AlertSeverity,
    AlertTriggerType,
)


def _make_alert(
    *,
    trigger_type: AlertTriggerType = AlertTriggerType.REGIME_TRANSITION,
    severity: AlertSeverity = AlertSeverity.WARNING,
    country: str | None = None,
    triggered_at: datetime | None = None,
) -> AlertEvent:
    return AlertEvent(
        trigger_type=trigger_type,
        severity=severity,
        source_regime="goldilocks",
        target_regime="contraction",
        context_snapshot_id="snap-1",
        country=country,
        rule_id="rule-1",
        rule_name="Test Rule",
        message="Test regime transition alert",
        triggered_at=triggered_at or datetime.now(UTC),
    )


def _store_with(*alerts: AlertEvent) -> InMemoryAlertStore:
    store = InMemoryAlertStore()
    for a in alerts:
        store.save(a)
    return store


class TestAlertsRecentRoute:
    def test_empty_store_returns_empty_list(self) -> None:
        store = InMemoryAlertStore()
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["alerts"] == []
            assert payload["total"] == 0
        finally:
            app.dependency_overrides.clear()

    def test_returns_stored_alerts(self) -> None:
        store = _store_with(_make_alert(), _make_alert())
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent")
            assert resp.status_code == 200
            assert resp.json()["total"] == 2
        finally:
            app.dependency_overrides.clear()

    def test_trigger_type_filter(self) -> None:
        store = _store_with(
            _make_alert(trigger_type=AlertTriggerType.REGIME_TRANSITION),
            _make_alert(trigger_type=AlertTriggerType.STALENESS_WARNING),
        )
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?trigger_type=staleness_warning")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["total"] == 1
            assert payload["alerts"][0]["trigger_type"] == "staleness_warning"
        finally:
            app.dependency_overrides.clear()

    def test_severity_filter(self) -> None:
        store = _store_with(
            _make_alert(severity=AlertSeverity.CRITICAL),
            _make_alert(severity=AlertSeverity.INFO),
        )
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?severity=critical")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
            assert resp.json()["alerts"][0]["severity"] == "critical"
        finally:
            app.dependency_overrides.clear()

    def test_country_filter(self) -> None:
        store = _store_with(
            _make_alert(country="US"),
            _make_alert(country="DE"),
        )
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?country=US")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["total"] == 1
            assert payload["alerts"][0]["country"] == "US"
        finally:
            app.dependency_overrides.clear()

    def test_since_filter(self) -> None:
        now = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        old = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
        store = _store_with(
            _make_alert(triggered_at=now),
            _make_alert(triggered_at=old),
        )
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?since=2026-04-19T00:00:00Z")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_until_filter(self) -> None:
        now = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        old = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
        store = _store_with(
            _make_alert(triggered_at=now),
            _make_alert(triggered_at=old),
        )
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?until=2026-04-19T00:00:00Z")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_invalid_trigger_type_returns_422(self) -> None:
        store = InMemoryAlertStore()
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?trigger_type=not_a_type")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_invalid_severity_returns_422(self) -> None:
        store = InMemoryAlertStore()
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?severity=super_critical")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_limit_applied(self) -> None:
        store = _store_with(*[_make_alert() for _ in range(10)])
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/recent?limit=3")
            assert resp.status_code == 200
            payload = resp.json()
            assert len(payload["alerts"]) == 3
            assert payload["limit_applied"] == 3
        finally:
            app.dependency_overrides.clear()


class TestAlertGetByIdRoute:
    def test_returns_200_for_existing_alert(self) -> None:
        alert = _make_alert()
        store = _store_with(alert)
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get(f"/api/alerts/{alert.alert_id}")
            assert resp.status_code == 200
            assert resp.json()["alert_id"] == alert.alert_id
        finally:
            app.dependency_overrides.clear()

    def test_returns_404_for_missing_alert(self) -> None:
        store = InMemoryAlertStore()
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get("/api/alerts/nonexistent-id")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestAlertAcknowledgeRoute:
    def test_acknowledge_sets_state(self) -> None:
        alert = _make_alert()
        store = _store_with(alert)
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.patch(f"/api/alerts/{alert.alert_id}/acknowledge")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["acknowledgement_state"] == "acknowledged"
            assert payload["acknowledged_at"] is not None
        finally:
            app.dependency_overrides.clear()

    def test_acknowledge_missing_alert_returns_404(self) -> None:
        store = InMemoryAlertStore()
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.patch("/api/alerts/nonexistent/acknowledge")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestAlertSnoozeRoute:
    def test_snooze_sets_state(self) -> None:
        alert = _make_alert()
        store = _store_with(alert)
        app.dependency_overrides[get_alert_repository] = lambda: store
        snooze_until = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
        try:
            tc = TestClient(app)
            resp = tc.patch(
                f"/api/alerts/{alert.alert_id}/snooze",
                json={"snoozed_until": snooze_until.isoformat()},
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["acknowledgement_state"] == "snoozed"
            assert payload["snoozed_until"] is not None
        finally:
            app.dependency_overrides.clear()

    def test_snooze_missing_alert_returns_404(self) -> None:
        store = InMemoryAlertStore()
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.patch(
                "/api/alerts/nonexistent/snooze",
                json={"snoozed_until": "2026-05-01T00:00:00Z"},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestAlertEventDTOShape:
    def test_dto_has_all_expected_fields(self) -> None:
        alert = _make_alert()
        store = _store_with(alert)
        app.dependency_overrides[get_alert_repository] = lambda: store
        try:
            tc = TestClient(app)
            resp = tc.get(f"/api/alerts/{alert.alert_id}")
            payload = resp.json()
            expected_fields = {
                "alert_id",
                "triggered_at",
                "trigger_type",
                "severity",
                "source_regime",
                "target_regime",
                "indicator_type",
                "context_snapshot_id",
                "country",
                "rule_id",
                "rule_name",
                "message",
                "acknowledgement_state",
                "acknowledged_at",
                "snoozed_until",
                "metadata",
            }
            assert expected_fields.issubset(set(payload.keys()))
        finally:
            app.dependency_overrides.clear()
