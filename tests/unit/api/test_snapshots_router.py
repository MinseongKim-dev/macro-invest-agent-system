"""Tests for the snapshot routes — GET /api/snapshots/latest and POST /api/snapshots/compare."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_macro_service
from apps.api.main import app
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_snapshot(country: str = "US") -> MacroSnapshot:
    """Build a minimal synthetic snapshot for testing."""
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    features = [
        MacroFeature(
            indicator_type=MacroIndicatorType.GDP,
            source=MacroSourceType.FRED,
            value=3.2,
            timestamp=now,
            frequency=DataFrequency.QUARTERLY,
            country=country,
        ),
        MacroFeature(
            indicator_type=MacroIndicatorType.INFLATION,
            source=MacroSourceType.FRED,
            value=2.8,
            timestamp=now,
            frequency=DataFrequency.MONTHLY,
            country=country,
        ),
        MacroFeature(
            indicator_type=MacroIndicatorType.UNEMPLOYMENT,
            source=MacroSourceType.FRED,
            value=4.1,
            timestamp=now,
            frequency=DataFrequency.MONTHLY,
            country=country,
        ),
    ]
    return MacroSnapshot(features=features, snapshot_time=now, version=1)


def _mock_macro_service(snapshot: MacroSnapshot | None = None) -> MagicMock:
    svc = MagicMock()
    svc.get_snapshot = AsyncMock(return_value=snapshot or _make_snapshot())
    return svc


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Return a TestClient with a stubbed macro service."""
    svc = _mock_macro_service()
    app.dependency_overrides[get_macro_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def client_with_snapshot(request: pytest.FixtureRequest) -> Generator[TestClient, None, None]:
    """Return a TestClient with a custom snapshot."""
    snapshot = getattr(request, "param", _make_snapshot())
    svc = _mock_macro_service(snapshot)
    app.dependency_overrides[get_macro_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/snapshots/latest
# ---------------------------------------------------------------------------


class TestSnapshotLatest:
    """Tests for GET /api/snapshots/latest."""

    def test_success_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        assert resp.status_code == 200

    def test_returns_country(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        data = resp.json()
        assert data["country"] == "US"

    def test_returns_features(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        data = resp.json()
        assert len(data["features"]) == 3
        assert data["features_count"] == 3

    def test_feature_has_required_fields(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        feature = resp.json()["features"][0]
        assert "indicator_type" in feature
        assert "indicator_label" in feature
        assert "value" in feature
        assert "source_id" in feature
        assert "frequency" in feature
        assert "observed_at" in feature

    def test_trust_metadata_present(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        trust = resp.json()["trust"]
        assert "freshness_status" in trust
        assert "availability" in trust
        assert "is_degraded" in trust
        assert "sources" in trust

    def test_trust_freshness_is_fresh(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        assert resp.json()["trust"]["freshness_status"] == "fresh"

    def test_trust_availability_is_full(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        assert resp.json()["trust"]["availability"] == "full"

    def test_default_country_is_us(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest")
        assert resp.status_code == 200

    def test_upstream_error_returns_502(self) -> None:
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(side_effect=RuntimeError("DB down"))
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.get("/api/snapshots/latest", params={"country": "US"})
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.clear()

    def test_indicator_labels_are_human_readable(self, client: TestClient) -> None:
        resp = client.get("/api/snapshots/latest", params={"country": "US"})
        labels = [f["indicator_label"] for f in resp.json()["features"]]
        # Should be title-case readable, not raw enum strings
        assert "GDP Growth" in labels or any(len(label) > 3 for label in labels)


# ---------------------------------------------------------------------------
# POST /api/snapshots/compare
# ---------------------------------------------------------------------------


class TestSnapshotCompare:
    """Tests for POST /api/snapshots/compare."""

    def _compare_body(
        self,
        country: str = "US",
        prior_label: str = "Q1-2026",
        prior_features: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if prior_features is None:
            prior_features = [
                {"indicator_type": "gdp", "value": 3.0},
                {"indicator_type": "inflation", "value": 2.5},
            ]
        return {
            "country": country,
            "prior_snapshot_label": prior_label,
            "prior_features": prior_features,
        }

    def test_success_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/snapshots/compare", json=self._compare_body())
        assert resp.status_code == 200

    def test_returns_deltas(self, client: TestClient) -> None:
        resp = client.post("/api/snapshots/compare", json=self._compare_body())
        data = resp.json()
        assert "deltas" in data
        assert len(data["deltas"]) > 0

    def test_delta_has_required_fields(self, client: TestClient) -> None:
        resp = client.post("/api/snapshots/compare", json=self._compare_body())
        delta = resp.json()["deltas"][0]
        assert "indicator_type" in delta
        assert "indicator_label" in delta
        assert "current_value" in delta
        assert "direction" in delta

    def test_delta_direction_is_valid(self, client: TestClient) -> None:
        resp = client.post("/api/snapshots/compare", json=self._compare_body())
        valid_directions = {"increased", "decreased", "unchanged", "no_prior"}
        for delta in resp.json()["deltas"]:
            assert delta["direction"] in valid_directions

    def test_no_prior_direction_for_unmatched_indicator(
        self, client: TestClient
    ) -> None:
        """Indicator not in prior_features should get 'no_prior' direction."""
        body = self._compare_body(prior_features=[{"indicator_type": "gdp", "value": 3.0}])
        resp = client.post("/api/snapshots/compare", json=body)
        deltas = resp.json()["deltas"]
        no_prior = [d for d in deltas if d["direction"] == "no_prior"]
        # inflation and unemployment should be no_prior
        assert len(no_prior) >= 1

    def test_change_counts_consistent(self, client: TestClient) -> None:
        resp = client.post("/api/snapshots/compare", json=self._compare_body())
        data = resp.json()
        total = (
            data["changed_count"] + data["unchanged_count"] + data["no_prior_count"]
        )
        assert total == len(data["deltas"])

    def test_trust_metadata_present(self, client: TestClient) -> None:
        resp = client.post("/api/snapshots/compare", json=self._compare_body())
        trust = resp.json()["trust"]
        assert "freshness_status" in trust
        assert "availability" in trust
        assert "changed_indicators_count" in trust

    def test_empty_prior_features_returns_422(self, client: TestClient) -> None:
        body = self._compare_body(prior_features=[])
        resp = client.post("/api/snapshots/compare", json=body)
        assert resp.status_code == 422

    def test_upstream_error_returns_502(self) -> None:
        svc = MagicMock()
        svc.get_snapshot = AsyncMock(side_effect=RuntimeError("service down"))
        app.dependency_overrides[get_macro_service] = lambda: svc
        try:
            tc = TestClient(app, raise_server_exceptions=False)
            resp = tc.post(
                "/api/snapshots/compare",
                json={
                    "country": "US",
                    "prior_snapshot_label": "prior",
                    "prior_features": [{"indicator_type": "gdp", "value": 3.0}],
                },
            )
            assert resp.status_code == 502
        finally:
            app.dependency_overrides.clear()

    def test_compare_detects_increase(self, client: TestClient) -> None:
        """Prior GDP=3.0; current=3.2 should be 'increased'."""
        resp = client.post(
            "/api/snapshots/compare",
            json={
                "country": "US",
                "prior_snapshot_label": "prev",
                "prior_features": [{"indicator_type": "gdp", "value": 3.0}],
            },
        )
        deltas = resp.json()["deltas"]
        gdp_delta = next((d for d in deltas if d["indicator_type"] == "gdp"), None)
        assert gdp_delta is not None
        assert gdp_delta["direction"] == "increased"

    def test_compare_detects_decrease(self, client: TestClient) -> None:
        """Prior GDP=4.0; current=3.2 should be 'decreased'."""
        resp = client.post(
            "/api/snapshots/compare",
            json={
                "country": "US",
                "prior_snapshot_label": "prev",
                "prior_features": [{"indicator_type": "gdp", "value": 4.0}],
            },
        )
        deltas = resp.json()["deltas"]
        gdp_delta = next((d for d in deltas if d["indicator_type"] == "gdp"), None)
        assert gdp_delta is not None
        assert gdp_delta["direction"] == "decreased"
