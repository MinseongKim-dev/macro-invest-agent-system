"""Tests for GET /api/regimes/history — regime history endpoint."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from apps.api.dependencies import get_regime_service
from apps.api.main import app
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


def _regime(
    *,
    as_of_date: date = date(2026, 2, 1),
    label: RegimeLabel = RegimeLabel.GOLDILOCKS,
    family: RegimeFamily = RegimeFamily.EXPANSION,
    confidence: RegimeConfidence = RegimeConfidence.HIGH,
) -> MacroRegime:
    return MacroRegime(
        as_of_date=as_of_date,
        regime_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        regime_label=label,
        regime_family=family,
        supporting_snapshot_id="snap-1",
        confidence=confidence,
        freshness_status=FreshnessStatus.FRESH,
        degraded_status=DegradedStatus.NONE,
        transition=RegimeTransition(
            transition_type=RegimeTransitionType.INITIAL,
            changed=False,
        ),
    )


class TestRegimeHistoryEndpoint:
    def test_history_returns_200_with_regimes(self) -> None:
        regimes = [
            _regime(as_of_date=date(2026, 3, 1)),
            _regime(as_of_date=date(2026, 2, 1)),
        ]
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(return_value=regimes)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/history")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["total"] == 2
            assert len(payload["records"]) == 2
        finally:
            app.dependency_overrides.clear()

    def test_history_empty_store_returns_200_empty(self) -> None:
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(return_value=[])
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/history")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["total"] == 0
            assert payload["records"] == []
            assert payload["latest_regime_id"] is None
            assert payload["previous_regime_id"] is None
        finally:
            app.dependency_overrides.clear()

    def test_history_populates_latest_and_previous_ids(self) -> None:
        r1 = _regime(as_of_date=date(2026, 3, 1))
        r2 = _regime(as_of_date=date(2026, 2, 1))
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(return_value=[r1, r2])
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/history")
            payload = resp.json()
            assert payload["latest_regime_id"] == r1.regime_id
            assert payload["previous_regime_id"] == r2.regime_id
        finally:
            app.dependency_overrides.clear()

    def test_history_record_fields_present(self) -> None:
        regime = _regime()
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(return_value=[regime])
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/history")
            record = resp.json()["records"][0]
            assert record["regime_label"] == "goldilocks"
            assert record["regime_family"] == "expansion"
            assert record["confidence"] == "high"
            assert record["freshness_status"] == "fresh"
            assert record["degraded_status"] == "none"
            assert "regime_id" in record
            assert "as_of_date" in record
            assert "generated_at" in record
        finally:
            app.dependency_overrides.clear()

    def test_history_respects_limit_param(self) -> None:
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(return_value=[])
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/history?limit=5")
            assert resp.status_code == 200
            # Verify the service was called with limit=5
            svc.list_recent_regimes.assert_called_once()
            call_kwargs = svc.list_recent_regimes.call_args.kwargs
            assert call_kwargs["limit"] == 5
        finally:
            app.dependency_overrides.clear()

    def test_history_limit_out_of_range_returns_422(self) -> None:
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(return_value=[])
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            # limit=0 is invalid (ge=1)
            resp = tc.get("/api/regimes/history?limit=0")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_history_service_error_returns_502(self) -> None:
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(side_effect=ValueError("Regime repository not configured"))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/history")
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.clear()

    def test_history_limit_applied_reflected_in_response(self) -> None:
        svc = MagicMock()
        svc.list_recent_regimes = AsyncMock(return_value=[])
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/history?limit=7")
            assert resp.json()["limit_applied"] == 7
        finally:
            app.dependency_overrides.clear()
