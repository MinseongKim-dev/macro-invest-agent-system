"""Tests for the signals route — GET /api/signals/latest."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_macro_service, get_signal_service
from apps.api.main import app
from apps.api.routers.explanations import clear_explanation_store
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.signals.enums import SignalStrength, SignalType, TrendDirection
from src.domain.signals.models import SignalOutput, SignalResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot() -> MacroSnapshot:
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    return MacroSnapshot(
        features=[
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=3.2,
                timestamp=now,
                frequency=DataFrequency.QUARTERLY,
                country="US",
            )
        ],
        snapshot_time=now,
        version=1,
    )


def _make_signal_result(signals: list[SignalOutput] | None = None) -> SignalResult:
    if signals is None:
        signals = [
            SignalOutput(
                signal_id="bull_market",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                score=0.85,
                triggered_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                trend=TrendDirection.UP,
                rationale="GDP is positive and inflation contained.",
                rule_results={"gdp_growth_positive": True, "inflation_contained": True},
            )
        ]
    return SignalResult(
        run_id="run-001",
        timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        macro_snapshot=_make_snapshot(),
        signals=signals,
        success=True,
    )


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    macro_svc = MagicMock()
    macro_svc.get_snapshot = AsyncMock(return_value=_make_snapshot())
    signal_svc = MagicMock()
    signal_svc.run_engine = AsyncMock(return_value=_make_signal_result())
    app.dependency_overrides[get_macro_service] = lambda: macro_svc
    app.dependency_overrides[get_signal_service] = lambda: signal_svc
    yield TestClient(app)
    app.dependency_overrides.clear()
    clear_explanation_store()


@pytest.fixture()
def client_empty_signals() -> Generator[TestClient, None, None]:
    macro_svc = MagicMock()
    macro_svc.get_snapshot = AsyncMock(return_value=_make_snapshot())
    signal_svc = MagicMock()
    signal_svc.run_engine = AsyncMock(return_value=_make_signal_result(signals=[]))
    app.dependency_overrides[get_macro_service] = lambda: macro_svc
    app.dependency_overrides[get_signal_service] = lambda: signal_svc
    yield TestClient(app)
    app.dependency_overrides.clear()
    clear_explanation_store()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSignalsLatest:
    """Tests for GET /api/signals/latest."""

    def test_success_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        assert resp.status_code == 200

    def test_returns_country(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        assert resp.json()["country"] == "US"

    def test_returns_run_id(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        assert resp.json()["run_id"] == "run-001"

    def test_returns_signals(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        data = resp.json()
        assert data["signals_count"] == 1
        assert len(data["signals"]) == 1

    def test_signal_has_required_fields(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        signal = resp.json()["signals"][0]
        assert "signal_id" in signal
        assert "signal_type" in signal
        assert "strength" in signal
        assert "score" in signal
        assert "trend" in signal
        assert "rationale" in signal
        assert "triggered_at" in signal
        assert "rule_results" in signal
        assert "rules_passed" in signal
        assert "rules_total" in signal

    def test_signal_counts_by_type(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        data = resp.json()
        assert data["buy_count"] == 1
        assert data["sell_count"] == 0
        assert data["hold_count"] == 0

    def test_strongest_signal_id_set(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        assert resp.json()["strongest_signal_id"] == "bull_market"

    def test_trust_metadata_present(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        trust = resp.json()["trust"]
        assert "freshness_status" in trust
        assert "availability" in trust
        assert "is_degraded" in trust

    def test_rules_passed_count(self, client: TestClient) -> None:
        resp = client.get("/api/signals/latest", params={"country": "US"})
        signal = resp.json()["signals"][0]
        assert signal["rules_passed"] == 2
        assert signal["rules_total"] == 2

    def test_empty_signals_returns_200_with_zero_count(
        self, client_empty_signals: TestClient
    ) -> None:
        resp = client_empty_signals.get("/api/signals/latest", params={"country": "US"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["signals_count"] == 0
        assert data["strongest_signal_id"] is None

    def test_unknown_signal_id_filter_returns_422(self, client: TestClient) -> None:
        resp = client.get(
            "/api/signals/latest",
            params={"country": "US", "signal_ids": ["nonexistent_signal"]},
        )
        assert resp.status_code == 422

    def test_macro_service_error_returns_502(self) -> None:
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(side_effect=RuntimeError("macro down"))
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(return_value=_make_signal_result())
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.clear()

    def test_signal_engine_error_returns_502(self) -> None:
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=_make_snapshot())
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(side_effect=RuntimeError("engine down"))
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.clear()

    def test_latest_signals_registers_explanation(self, client: TestClient) -> None:
        latest = client.get("/api/signals/latest", params={"country": "US"})
        run_id = latest.json()["run_id"]
        strongest = latest.json()["strongest_signal_id"]

        explanation = client.get(f"/api/explanations/{run_id}:{strongest}")
        assert explanation.status_code == 200
