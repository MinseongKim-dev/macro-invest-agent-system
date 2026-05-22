"""Tests for regime routes — GET /api/regimes/latest and /api/regimes/compare."""

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
    transition_type: RegimeTransitionType = RegimeTransitionType.UNCHANGED,
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
            transition_from_prior="slowdown",
            transition_type=transition_type,
            changed=transition_type != RegimeTransitionType.UNCHANGED,
        ),
    )


class TestRegimesRouter:
    def test_latest_returns_200(self) -> None:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=_regime())
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/latest")
            assert resp.status_code == 200
            assert resp.json()["regime_label"] == "goldilocks"
        finally:
            app.dependency_overrides.clear()

    def test_latest_returns_404_when_missing(self) -> None:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=None)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/latest")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_compare_returns_transition(self) -> None:
        current = _regime(transition_type=RegimeTransitionType.SHIFT)
        previous = _regime(label=RegimeLabel.SLOWDOWN, family=RegimeFamily.DOWNSHIFT)
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["baseline_available"] is True
            assert payload["transition_type"] == "shift"
            assert payload["prior_regime_label"] == "slowdown"
        finally:
            app.dependency_overrides.clear()

    def test_compare_returns_404_when_no_current_regime(self) -> None:
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(
            side_effect=ValueError("No regime available on or before 2026-02-01")
        )
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_compare_no_prior_baseline_available(self) -> None:
        current = _regime(transition_type=RegimeTransitionType.UNCHANGED)
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, None))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["baseline_available"] is False
            assert payload["prior_regime_label"] is None
            assert payload["prior_confidence"] is None
        finally:
            app.dependency_overrides.clear()
