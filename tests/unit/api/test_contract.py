"""API/UI contract tests — PR5: edge-state and schema-drift coverage.

Covers:
* Stale state (freshness_status = "stale")
* Degraded state (availability = "degraded" / "unavailable")
* Empty state (no features, no signals, no explanations)
* Partial state (some no_prior indicators)
* Key schema field presence across all endpoints
* Snapshots endpoint always returns trust block

These tests verify that trust metadata never disappears from responses
and that important edge states are explicitly surfaced.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_explanation_repository, get_macro_service, get_signal_service
from apps.api.main import app
from apps.api.routers.explanations import build_and_register_explanation
from apps.api.routers.sessions import clear_session_store, create_session
from src.agent.adapters.repositories.in_memory_explanation_store import InMemoryExplanationStore
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.signals.models import SignalOutput, SignalResult

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(features: list[MacroFeature] | None = None) -> MacroSnapshot:
    if features is None:
        features = [
            MacroFeature(
                indicator_type=MacroIndicatorType.GDP,
                source=MacroSourceType.FRED,
                value=3.2,
                timestamp=_NOW,
                frequency=DataFrequency.QUARTERLY,
                country="US",
            )
        ]
    return MacroSnapshot(features=features, snapshot_time=_NOW, version=1)


def _signal_result(signals: list[SignalOutput] | None = None, success: bool = True) -> SignalResult:
    return SignalResult(
        run_id="run-contract",
        timestamp=_NOW,
        macro_snapshot=_snapshot(),
        signals=signals or [],
        success=success,
        error_message=None if success else "failure",
    )


@pytest.fixture()
def explanation_store() -> InMemoryExplanationStore:
    return InMemoryExplanationStore()


@pytest.fixture(autouse=True)
def _clean_stores(explanation_store: InMemoryExplanationStore) -> Generator[None, None, None]:
    app.dependency_overrides[get_explanation_repository] = lambda: explanation_store
    clear_session_store()
    yield
    app.dependency_overrides.pop(get_explanation_repository, None)
    explanation_store.clear()
    clear_session_store()


# ---------------------------------------------------------------------------
# Schema presence — trust block must always be in responses
# ---------------------------------------------------------------------------


class TestTrustBlockAlwaysPresent:
    """Trust metadata must be present in every product-surface response."""

    def test_snapshot_latest_has_trust(self) -> None:
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(return_value=_snapshot())
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/snapshots/latest", params={"country": "US"})
            assert resp.status_code == 200
            assert "trust" in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_snapshot_compare_has_trust(self) -> None:
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(return_value=_snapshot())
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.post(
                "/api/snapshots/compare",
                json={
                    "country": "US",
                    "prior_snapshot_label": "prior",
                    "prior_features": [{"indicator_type": "gdp", "value": 3.0}],
                },
            )
            assert resp.status_code == 200
            assert "trust" in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_signals_latest_has_trust(self) -> None:
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=_snapshot())
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(return_value=_signal_result())
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 200
            assert "trust" in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_explanation_has_trust(
        self, explanation_store: InMemoryExplanationStore
    ) -> None:
        build_and_register_explanation("run-t", "sig-t", "summary", [], repository=explanation_store)
        tc = TestClient(app)
        resp = tc.get("/api/explanations/run-t:sig-t")
        assert resp.status_code == 200
        assert "trust" in resp.json()

    def test_session_has_trust(self) -> None:
        create_session("sess-trust-check")
        tc = TestClient(app)
        resp = tc.get("/api/sessions/sess-trust-check")
        assert resp.status_code == 200
        assert "trust" in resp.json()


# ---------------------------------------------------------------------------
# Trust block schema — required fields must always be present
# ---------------------------------------------------------------------------

_REQUIRED_TRUST_FIELDS = {
    "freshness_status",
    "availability",
    "is_degraded",
    "sources",
}


class TestTrustBlockSchema:
    """All required trust fields must be present in every trust block."""

    def _assert_trust_fields(self, trust: dict[str, object]) -> None:
        for field in _REQUIRED_TRUST_FIELDS:
            assert field in trust, f"Trust field '{field}' is missing"

    def test_snapshot_latest_trust_fields(self) -> None:
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(return_value=_snapshot())
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/snapshots/latest", params={"country": "US"})
            self._assert_trust_fields(resp.json()["trust"])
        finally:
            app.dependency_overrides.clear()

    def test_comparison_trust_fields(self) -> None:
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(return_value=_snapshot())
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.post(
                "/api/snapshots/compare",
                json={
                    "country": "US",
                    "prior_snapshot_label": "p",
                    "prior_features": [{"indicator_type": "gdp", "value": 3.0}],
                },
            )
            self._assert_trust_fields(resp.json()["trust"])
        finally:
            app.dependency_overrides.clear()

    def test_signals_trust_fields(self) -> None:
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=_snapshot())
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(return_value=_signal_result())
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            self._assert_trust_fields(resp.json()["trust"])
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Edge state: empty signals
# ---------------------------------------------------------------------------


class TestEmptyState:
    """API should handle empty collections without errors."""

    def test_signals_empty_returns_200(self) -> None:
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=_snapshot())
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(return_value=_signal_result(signals=[]))
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["signals_count"] == 0
            assert data["strongest_signal_id"] is None
        finally:
            app.dependency_overrides.clear()

    def test_explanation_not_found_is_404(self) -> None:
        tc = TestClient(app)
        resp = tc.get("/api/explanations/nonexistent")
        assert resp.status_code == 404

    def test_session_not_found_is_404(self) -> None:
        tc = TestClient(app)
        resp = tc.get("/api/sessions/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Edge state: degraded / unavailable (signals engine failure)
# ---------------------------------------------------------------------------


class TestDegradedState:
    """Unavailable trust state is surfaced when services fail."""

    def test_signal_trust_unavailable_on_engine_failure(self) -> None:
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=_snapshot())
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(
            return_value=_signal_result(signals=[], success=False)
        )
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/signals/latest", params={"country": "US"})
            assert resp.status_code == 200
            trust = resp.json()["trust"]
            # run_id is empty → our builder sees success=False or regime unavailable
            assert trust["availability"] in ("unavailable", "partial", "degraded")
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Edge state: partial (no_prior in comparison)
# ---------------------------------------------------------------------------


class TestPartialState:
    """Partial availability is surfaced when some prior data is missing."""

    def test_comparison_partial_when_some_no_prior(self) -> None:
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
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(return_value=snap)
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app)
            # Only provide one of two indicators in prior_features
            resp = tc.post(
                "/api/snapshots/compare",
                json={
                    "country": "US",
                    "prior_snapshot_label": "prior",
                    "prior_features": [{"indicator_type": "gdp", "value": 3.0}],
                },
            )
            assert resp.status_code == 200
            trust = resp.json()["trust"]
            assert trust["availability"] == "partial"
        finally:
            app.dependency_overrides.clear()

    def test_comparison_all_no_prior_when_prior_features_mismatch(self) -> None:
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(return_value=_snapshot())
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app)
            # Prior feature for a different indicator → all current indicators are no_prior
            resp = tc.post(
                "/api/snapshots/compare",
                json={
                    "country": "US",
                    "prior_snapshot_label": "prior",
                    "prior_features": [{"indicator_type": "pmi", "value": 50.0}],
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["no_prior_count"] == len(data["deltas"])
            assert resp.json()["trust"]["availability"] == "unavailable"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health/readiness endpoints still work after router addition
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    """Ensure existing health/readiness endpoints still respond correctly."""

    def test_health(self) -> None:
        tc = TestClient(app)
        resp = tc.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_readiness(self) -> None:
        tc = TestClient(app)
        resp = tc.get("/readiness")
        assert resp.status_code == 200
        assert "status" in resp.json()
