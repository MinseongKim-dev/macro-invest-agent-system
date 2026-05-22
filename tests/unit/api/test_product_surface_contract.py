"""Product surface and API contract tests — Chunk 3.

These tests verify:
1. Explicit state semantics: success / degraded / stale / bootstrap / fallback / empty
2. Response envelope consistency between regime and signal endpoints
3. That no working baseline routes are broken
4. Edge cases for empty, degraded, and error states

Design notes
------------
* These are contract-level tests, not unit tests of domain logic.
* They focus on the *shape* and *state fields* of API responses rather
  than the exact content of rationale strings.
* Existing unit tests in test_regimes_router.py and test_signals_router.py
  remain the authoritative functional tests; this module adds cross-cutting
  contract coverage.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from apps.api.dependencies import (
    get_macro_service,
    get_regime_service,
    get_signal_service,
)
from apps.api.main import app
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.models import MacroFeature, MacroSnapshot
from src.domain.macro.regime import (
    MacroRegime,
    RegimeConfidence,
    RegimeFamily,
    RegimeLabel,
    RegimeTransition,
    RegimeTransitionType,
)
from src.domain.macro.snapshot import DegradedStatus
from src.domain.signals.enums import SignalStrength, SignalType, TrendDirection
from src.domain.signals.models import SignalOutput, SignalResult
from src.pipelines.ingestion.models import FreshnessStatus

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
_AS_OF = date(2026, 4, 1)


def _make_regime(
    label: RegimeLabel = RegimeLabel.GOLDILOCKS,
    family: RegimeFamily = RegimeFamily.EXPANSION,
    confidence: RegimeConfidence = RegimeConfidence.HIGH,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    degraded: DegradedStatus = DegradedStatus.NONE,
    transition_type: RegimeTransitionType = RegimeTransitionType.INITIAL,
    metadata: dict[str, str] | None = None,
    warnings: list[str] | None = None,
    rationale_summary: str = "growth=accelerating",
) -> MacroRegime:
    return MacroRegime(
        as_of_date=_AS_OF,
        regime_timestamp=_NOW,
        regime_label=label,
        regime_family=family,
        supporting_snapshot_id="snap-test",
        confidence=confidence,
        freshness_status=freshness,
        degraded_status=degraded,
        transition=RegimeTransition(
            transition_from_prior=None if transition_type == RegimeTransitionType.INITIAL else "slowdown",
            transition_type=transition_type,
            changed=transition_type in {
                RegimeTransitionType.SHIFT,
                RegimeTransitionType.STRENGTHENING,
                RegimeTransitionType.WEAKENING,
            },
        ),
        rationale_summary=rationale_summary,
        warnings=warnings or [],
        metadata=metadata or {},
    )


def _make_snapshot() -> MacroSnapshot:
    return MacroSnapshot(
        features=[
            MacroFeature(
                indicator_type=MacroIndicatorType.PMI,
                source=MacroSourceType.FRED,
                value=52.5,
                timestamp=_NOW,
                frequency=DataFrequency.MONTHLY,
                country="US",
            )
        ],
        snapshot_time=_NOW,
    )


def _make_signal_result(degraded: bool = False) -> SignalResult:
    return SignalResult(
        run_id="run-contract-test",
        timestamp=_NOW,
        macro_snapshot=_make_snapshot(),
        signals=[
            SignalOutput(
                signal_id="test_buy",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                score=0.8,
                triggered_at=_NOW,
                trend=TrendDirection.UP,
                rationale="Test rationale",
                is_degraded=degraded,
                caveat="Test caveat" if degraded else None,
            )
        ],
        success=True,
    )


# ---------------------------------------------------------------------------
# Regime Latest — status field contract
# ---------------------------------------------------------------------------


class TestRegimeLatestStatusContract:
    """Verify that /api/regimes/latest returns the correct `status` value
    for each regime state combination."""

    def _client_with_regime(self, regime: MacroRegime) -> TestClient:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        return TestClient(app)

    def teardown_method(self) -> None:
        app.dependency_overrides.clear()

    def test_healthy_regime_returns_status_success(self) -> None:
        tc = self._client_with_regime(_make_regime())
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_seeded_regime_returns_status_bootstrap(self) -> None:
        regime = _make_regime(metadata={"seeded": "true", "source": "synthetic_seed"})
        tc = self._client_with_regime(regime)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "bootstrap"

    def test_stale_regime_returns_status_stale(self) -> None:
        regime = _make_regime(
            freshness=FreshnessStatus.STALE,
            confidence=RegimeConfidence.LOW,
        )
        tc = self._client_with_regime(regime)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stale"

    def test_unknown_freshness_returns_status_stale(self) -> None:
        regime = _make_regime(
            freshness=FreshnessStatus.UNKNOWN,
            confidence=RegimeConfidence.LOW,
        )
        tc = self._client_with_regime(regime)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stale"

    def test_partial_degraded_returns_status_degraded(self) -> None:
        regime = _make_regime(
            degraded=DegradedStatus.PARTIAL,
            confidence=RegimeConfidence.MEDIUM,
        )
        tc = self._client_with_regime(regime)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    def test_low_confidence_returns_status_degraded(self) -> None:
        regime = _make_regime(confidence=RegimeConfidence.LOW)
        tc = self._client_with_regime(regime)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    def test_mixed_regime_returns_status_degraded(self) -> None:
        regime = _make_regime(
            label=RegimeLabel.MIXED,
            family=RegimeFamily.UNCERTAIN,
            confidence=RegimeConfidence.LOW,
        )
        tc = self._client_with_regime(regime)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    def test_no_regime_returns_404(self) -> None:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=None)
        app.dependency_overrides[get_regime_service] = lambda: svc
        tc = TestClient(app)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 404

    def test_regime_service_error_returns_502(self) -> None:
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(side_effect=ValueError("Store error"))
        app.dependency_overrides[get_regime_service] = lambda: svc
        tc = TestClient(app)
        resp = tc.get("/api/regimes/latest")
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Regime Latest — response envelope completeness
# ---------------------------------------------------------------------------


class TestRegimeLatestEnvelope:
    """Verify all required product-surface fields are present."""

    _REQUIRED_FIELDS = {
        "as_of_date",
        "regime_id",
        "regime_timestamp",
        "regime_label",
        "regime_family",
        "confidence",
        "freshness_status",
        "degraded_status",
        "missing_inputs",
        "supporting_snapshot_id",
        "supporting_states",
        "transition",
        "rationale_summary",
        "warnings",
        "status",
        "is_seeded",
        "data_source",
    }

    def test_all_required_fields_present(self) -> None:
        regime = _make_regime()
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            payload = tc.get("/api/regimes/latest").json()
            missing = self._REQUIRED_FIELDS - set(payload.keys())
            assert not missing, f"Missing fields in /api/regimes/latest: {missing}"
        finally:
            app.dependency_overrides.clear()

    def test_transition_has_required_subfields(self) -> None:
        regime = _make_regime()
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            transition = tc.get("/api/regimes/latest").json()["transition"]
            assert "transition_from_prior" in transition
            assert "transition_type" in transition
            assert "changed" in transition
        finally:
            app.dependency_overrides.clear()

    def test_warnings_is_list(self) -> None:
        regime = _make_regime(warnings=["test warning"])
        svc = MagicMock()
        svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            payload = tc.get("/api/regimes/latest").json()
            assert isinstance(payload["warnings"], list)
            assert payload["warnings"] == ["test warning"]
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Regime Compare — contract
# ---------------------------------------------------------------------------


class TestRegimeCompareContract:
    """Verify /api/regimes/compare returns the expected extended fields."""

    _REQUIRED_FIELDS = {
        "as_of_date",
        "baseline_available",
        "current_regime_label",
        "prior_regime_label",
        "transition_type",
        "changed",
        "current_confidence",
        "prior_confidence",
        "current_rationale_summary",
        "warnings",
        "is_seeded",
    }

    def test_compare_response_has_all_required_fields(self) -> None:
        current = _make_regime(
            label=RegimeLabel.GOLDILOCKS,
            transition_type=RegimeTransitionType.SHIFT,
            rationale_summary="growth=accelerating, inflation=cooling",
        )
        previous = _make_regime(
            label=RegimeLabel.SLOWDOWN,
            family=RegimeFamily.DOWNSHIFT,
        )
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, previous))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            payload = tc.get("/api/regimes/compare").json()
            missing = self._REQUIRED_FIELDS - set(payload.keys())
            assert not missing, f"Missing fields in /api/regimes/compare: {missing}"
        finally:
            app.dependency_overrides.clear()

    def test_compare_rationale_matches_current(self) -> None:
        current = _make_regime(rationale_summary="growth=accelerating")
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, None))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            payload = tc.get("/api/regimes/compare").json()
            assert payload["current_rationale_summary"] == "growth=accelerating"
        finally:
            app.dependency_overrides.clear()

    def test_compare_seeded_flag_for_bootstrap_regime(self) -> None:
        current = _make_regime(metadata={"seeded": "true"})
        svc = MagicMock()
        svc.compare_latest_with_prior = AsyncMock(return_value=(current, None))
        app.dependency_overrides[get_regime_service] = lambda: svc
        try:
            tc = TestClient(app)
            payload = tc.get("/api/regimes/compare").json()
            assert payload["is_seeded"] is True
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Signals Latest — status and regime-grounding contract
# ---------------------------------------------------------------------------


class TestSignalsLatestStatusContract:
    """Verify /api/signals/latest returns correct `status` and `is_regime_grounded`."""

    def teardown_method(self) -> None:
        app.dependency_overrides.clear()

    def test_regime_grounded_success_status(self) -> None:
        from src.services.signal_service import SignalService

        regime = _make_regime()
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()

        tc = TestClient(app)
        payload = tc.get("/api/signals/latest", params={"country": "US"}).json()
        assert payload["is_regime_grounded"] is True
        assert payload["status"] == "success"
        assert payload["regime_label"] == "goldilocks"
        assert payload["as_of_date"] == "2026-04-01"

    def test_regime_grounded_degraded_status_for_bootstrap(self) -> None:
        from src.services.signal_service import SignalService

        regime = _make_regime(metadata={"seeded": "true"})
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()

        tc = TestClient(app)
        payload = tc.get("/api/signals/latest", params={"country": "US"}).json()
        assert payload["is_regime_grounded"] is True
        assert payload["status"] == "degraded"

    def test_fallback_path_sets_status_fallback(self) -> None:
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=None)
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=_make_snapshot())
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(return_value=_make_signal_result())

        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc

        tc = TestClient(app)
        payload = tc.get("/api/signals/latest", params={"country": "US"}).json()
        assert payload["status"] == "fallback"
        assert payload["is_regime_grounded"] is False
        assert payload["regime_label"] is None

    def test_fallback_trust_is_degraded(self) -> None:
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=None)
        macro_svc = MagicMock()
        macro_svc.get_snapshot = AsyncMock(return_value=_make_snapshot())
        signal_svc = MagicMock()
        signal_svc.run_engine = AsyncMock(return_value=_make_signal_result())

        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_macro_service] = lambda: macro_svc
        app.dependency_overrides[get_signal_service] = lambda: signal_svc

        tc = TestClient(app)
        payload = tc.get("/api/signals/latest", params={"country": "US"}).json()
        assert payload["trust"]["is_degraded"] is True
        assert payload["trust"]["degraded_reason"] == "regime_unavailable_fallback_engine_used"


# ---------------------------------------------------------------------------
# Signals Latest — envelope completeness
# ---------------------------------------------------------------------------


class TestSignalsLatestEnvelope:
    """Verify all required product-surface fields are present in signal responses."""

    _REQUIRED_FIELDS = {
        "country",
        "run_id",
        "signals",
        "signals_count",
        "buy_count",
        "sell_count",
        "hold_count",
        "strongest_signal_id",
        "trust",
        "regime_label",
        "as_of_date",
        "is_regime_grounded",
        "status",
    }

    _SIGNAL_REQUIRED_FIELDS = {
        "signal_id",
        "signal_type",
        "strength",
        "score",
        "trend",
        "rationale",
        "triggered_at",
        "rule_results",
        "rules_passed",
        "rules_total",
        "asset_class",
        "supporting_regime",
        "supporting_drivers",
        "conflicting_drivers",
        "is_degraded",
        "caveat",
    }

    def teardown_method(self) -> None:
        app.dependency_overrides.clear()

    def test_response_envelope_has_all_required_fields(self) -> None:
        from src.services.signal_service import SignalService

        regime = _make_regime()
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()

        tc = TestClient(app)
        payload = tc.get("/api/signals/latest", params={"country": "US"}).json()
        missing = self._REQUIRED_FIELDS - set(payload.keys())
        assert not missing, f"Missing top-level fields: {missing}"

    def test_each_signal_has_all_required_fields(self) -> None:
        from src.services.signal_service import SignalService

        regime = _make_regime()
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()

        tc = TestClient(app)
        payload = tc.get("/api/signals/latest", params={"country": "US"}).json()
        assert len(payload["signals"]) > 0
        for sig in payload["signals"]:
            missing = self._SIGNAL_REQUIRED_FIELDS - set(sig.keys())
            assert not missing, f"Signal {sig.get('signal_id', '?')} missing fields: {missing}"

    def test_trust_has_required_subfields(self) -> None:
        from src.services.signal_service import SignalService

        regime = _make_regime()
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()

        tc = TestClient(app)
        trust = tc.get("/api/signals/latest", params={"country": "US"}).json()["trust"]
        assert "freshness_status" in trust
        assert "availability" in trust
        assert "is_degraded" in trust


# ---------------------------------------------------------------------------
# Cross-endpoint state consistency
# ---------------------------------------------------------------------------


class TestCrossEndpointStateConsistency:
    """Verify that regime and signal endpoints consistently represent the same state."""

    def teardown_method(self) -> None:
        app.dependency_overrides.clear()

    def test_bootstrap_regime_surfaces_as_seeded_in_both_endpoints(self) -> None:
        """When regime is seeded, both /api/regimes/latest and /api/signals/latest
        reflect degraded/bootstrap state."""
        from src.services.signal_service import SignalService

        regime = _make_regime(metadata={"seeded": "true", "source": "synthetic_seed"})
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()

        tc = TestClient(app)
        regime_resp = tc.get("/api/regimes/latest").json()
        signal_resp = tc.get("/api/signals/latest", params={"country": "US"}).json()

        # Both should reflect bootstrap state
        assert regime_resp["is_seeded"] is True
        assert regime_resp["status"] == "bootstrap"
        # Signals derived from seeded regime must be marked degraded
        assert signal_resp["status"] == "degraded"
        for sig in signal_resp["signals"]:
            assert sig["is_degraded"] is True
            assert "bootstrap" in (sig["caveat"] or "").lower() or "synthetic" in (sig["caveat"] or "").lower()

    def test_high_quality_regime_produces_clean_signals(self) -> None:
        """A healthy, fresh, non-seeded regime should produce non-degraded signals."""
        from src.services.signal_service import SignalService

        regime = _make_regime()  # HIGH confidence, FRESH, NONE degraded, not seeded
        regime_svc = MagicMock()
        regime_svc.get_latest_regime = AsyncMock(return_value=regime)
        app.dependency_overrides[get_regime_service] = lambda: regime_svc
        app.dependency_overrides[get_signal_service] = lambda: SignalService()

        tc = TestClient(app)
        regime_resp = tc.get("/api/regimes/latest").json()
        signal_resp = tc.get("/api/signals/latest", params={"country": "US"}).json()

        assert regime_resp["status"] == "success"
        assert regime_resp["is_seeded"] is False
        assert regime_resp["warnings"] == []
        assert signal_resp["status"] == "success"
        assert signal_resp["is_regime_grounded"] is True
        for sig in signal_resp["signals"]:
            assert sig["is_degraded"] is False
            assert sig["caveat"] is None
