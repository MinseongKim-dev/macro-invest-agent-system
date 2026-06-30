"""Tests for quant score routes — GET /api/quant/latest."""

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
from src.domain.quant.models import DimensionScore, QuantScoreBundle, ScoreDimension, ScoreLevel
from src.pipelines.ingestion.models import FreshnessStatus


def _quant_scores() -> QuantScoreBundle:
    return QuantScoreBundle(
        growth=DimensionScore(
            dimension=ScoreDimension.GROWTH,
            score=0.9,
            level=ScoreLevel.STRONG,
            contributing_states=["accelerating"],
        ),
        inflation=DimensionScore(
            dimension=ScoreDimension.INFLATION,
            score=0.85,
            level=ScoreLevel.STRONG,
            contributing_states=["cooling"],
        ),
        labor=DimensionScore(
            dimension=ScoreDimension.LABOR,
            score=0.9,
            level=ScoreLevel.STRONG,
            contributing_states=["tight"],
        ),
        policy=DimensionScore(
            dimension=ScoreDimension.POLICY,
            score=0.6,
            level=ScoreLevel.MODERATE,
            contributing_states=["neutral"],
        ),
        financial_conditions=DimensionScore(
            dimension=ScoreDimension.FINANCIAL_CONDITIONS,
            score=0.55,
            level=ScoreLevel.MODERATE,
            contributing_states=["neutral"],
        ),
        momentum=0.8,
        breadth=1.0,
        change_intensity=0.35,
        overall_support=0.76,
    )


def _regime(*, quant_scores: QuantScoreBundle | None) -> MacroRegime:
    return MacroRegime(
        as_of_date=date(2026, 2, 1),
        regime_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        regime_label=RegimeLabel.GOLDILOCKS,
        regime_family=RegimeFamily.EXPANSION,
        supporting_snapshot_id="snap-1",
        confidence=RegimeConfidence.HIGH,
        freshness_status=FreshnessStatus.FRESH,
        degraded_status=DegradedStatus.NONE,
        transition=RegimeTransition(
            transition_from_prior=None,
            transition_type=RegimeTransitionType.UNCHANGED,
            changed=False,
        ),
        quant_scores=quant_scores,
    )


class TestQuantRouter:
    def test_latest_returns_200(self) -> None:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=_regime(quant_scores=_quant_scores()))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/quant/latest")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["regime_label"] == "goldilocks"
            assert payload["growth"]["score"] == 0.9
            assert payload["overall_support"] == 0.76
            assert payload["status"] == "success"
        finally:
            app.dependency_overrides.clear()

    def test_latest_returns_404_when_no_regime(self) -> None:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=None)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/quant/latest")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_latest_returns_404_when_no_quant_scores(self) -> None:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=_regime(quant_scores=None))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            resp = tc.get("/api/quant/latest")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()
