"""Tests for the updated /api/regimes/compare endpoint with change detection delta."""

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
    transition_type: RegimeTransitionType = RegimeTransitionType.INITIAL,
    transition_from_prior: str | None = None,
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
            transition_from_prior=transition_from_prior,
            transition_type=transition_type,
            changed=transition_type in {RegimeTransitionType.SHIFT, RegimeTransitionType.WEAKENING},
        ),
    )


class TestCompareWithDelta:
    """Verify compare endpoint returns structured delta from Change Detection Engine."""

    def test_compare_no_prior_has_null_delta(self) -> None:
        current = _regime()
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, None))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["baseline_available"] is False
            assert payload["delta"] is None
        finally:
            app.dependency_overrides.clear()

    def test_compare_unchanged_regimes_has_unchanged_delta(self) -> None:
        current = _regime(transition_type=RegimeTransitionType.UNCHANGED)
        previous = _regime()
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            payload = resp.json()
            assert payload["baseline_available"] is True
            delta = payload["delta"]
            assert delta is not None
            assert delta["severity"] == "unchanged"
            assert delta["label_changed"] is False
            assert delta["is_initial"] is False
        finally:
            app.dependency_overrides.clear()

    def test_compare_cross_family_shift_has_major_delta(self) -> None:
        current = _regime(
            label=RegimeLabel.CONTRACTION,
            family=RegimeFamily.CONTRACTION,
            transition_type=RegimeTransitionType.SHIFT,
        )
        previous = _regime(
            label=RegimeLabel.GOLDILOCKS,
            family=RegimeFamily.EXPANSION,
        )
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            delta = resp.json()["delta"]
            assert delta["severity"] == "major"
            assert delta["label_changed"] is True
            assert delta["family_changed"] is True
            assert "cross_family_transition" in delta["notable_flags"]
            assert delta["label_transition"] == "goldilocks → contraction"
            assert delta["prior_label"] == "goldilocks"
        finally:
            app.dependency_overrides.clear()

    def test_compare_confidence_weakening_has_minor_delta(self) -> None:
        current = _regime(
            confidence=RegimeConfidence.MEDIUM,
            transition_type=RegimeTransitionType.WEAKENING,
        )
        previous = _regime(confidence=RegimeConfidence.HIGH)
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            delta = resp.json()["delta"]
            assert delta["severity"] == "minor"
            assert delta["confidence_changed"] is True
            assert delta["confidence_direction"] == "weakened"
            assert delta["label_changed"] is False
            assert delta["confidence_transition"] == "high → medium"
        finally:
            app.dependency_overrides.clear()

    def test_compare_same_family_label_change_moderate_delta(self) -> None:
        current = _regime(
            label=RegimeLabel.REFLATION,
            family=RegimeFamily.INFLATION_TRANSITION,
            transition_type=RegimeTransitionType.SHIFT,
        )
        previous = _regime(
            label=RegimeLabel.DISINFLATION,
            family=RegimeFamily.INFLATION_TRANSITION,
        )
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            delta = resp.json()["delta"]
            assert delta["severity"] == "moderate"
            assert delta["label_changed"] is True
            assert delta["family_changed"] is False
            assert delta["is_regime_transition"] is True
        finally:
            app.dependency_overrides.clear()

    def test_compare_delta_has_severity_rationale(self) -> None:
        current = _regime(
            label=RegimeLabel.CONTRACTION,
            family=RegimeFamily.CONTRACTION,
            transition_type=RegimeTransitionType.SHIFT,
        )
        previous = _regime()
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/regimes/compare")
            delta = resp.json()["delta"]
            assert len(delta["severity_rationale"]) > 0
        finally:
            app.dependency_overrides.clear()

    def test_compare_existing_fields_unchanged(self) -> None:
        """Ensure existing compare fields (pre-PR) still work correctly."""
        current = _regime(
            transition_type=RegimeTransitionType.SHIFT,
            transition_from_prior="slowdown",
        )
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
            assert payload["current_regime_label"] == "goldilocks"
        finally:
            app.dependency_overrides.clear()
