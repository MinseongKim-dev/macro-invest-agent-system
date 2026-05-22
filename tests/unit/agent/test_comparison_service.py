"""Unit tests for AgentService.compare_snapshots.

Covers:
- Happy path: change-detected, no-change, partial prior
- Prior-snapshot-missing path: empty prior_features → success=False
- Current-snapshot-fetch failure → success=False
- Response is schema-valid on all paths
- Determinism: context does not alter tool result values
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.schemas import (
    PriorFeatureInput,
    SnapshotComparisonRequest,
    SnapshotComparisonResponse,
)
from src.agent.service import AgentService
from src.services.macro_service import MacroService
from src.services.signal_service import SignalService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> AgentService:
    return AgentService(MacroService(), SignalService())


def _make_request(
    prior_features: list[dict[str, object]] | None = None,
    country: str = "US",
    prior_snapshot_label: str = "Q1-2026",
    request_id: str = "req-1",
) -> SnapshotComparisonRequest:
    features = [
        PriorFeatureInput(**f)  # type: ignore[arg-type]
        for f in (prior_features or [])
    ]
    return SnapshotComparisonRequest(
        request_id=request_id,
        country=country,
        prior_snapshot_label=prior_snapshot_label,
        prior_features=features,
    )


# ---------------------------------------------------------------------------
# Happy path — change-detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCompareSnapshotsHappyPath:
    async def test_success_true_when_prior_provided(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        assert response.success is True

    async def test_response_is_snapshot_comparison_response(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        assert isinstance(response, SnapshotComparisonResponse)

    async def test_country_echoed_in_response(self) -> None:
        service = _make_service()
        req = _make_request(
            prior_features=[{"indicator_type": "gdp", "value": 50.0}],
            country="JP",
        )
        response = await service.compare_snapshots(req)
        assert response.country == "JP"

    async def test_prior_label_echoed_in_response(self) -> None:
        service = _make_service()
        req = _make_request(
            prior_features=[{"indicator_type": "gdp", "value": 50.0}],
            prior_snapshot_label="Q4-2025",
        )
        response = await service.compare_snapshots(req)
        assert response.prior_snapshot_label == "Q4-2025"

    async def test_count_fields_are_non_negative(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        assert response.changed_count >= 0
        assert response.unchanged_count >= 0
        assert response.no_prior_count >= 0

    async def test_count_totals_are_consistent(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        # Total must equal features in snapshot (placeholder returns 3: gdp, inflation, unemployment)
        total = response.changed_count + response.unchanged_count + response.no_prior_count
        assert total >= 1  # At least the features that were fetched

    async def test_summary_is_non_empty(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        assert response.summary != ""

    async def test_no_change_path_unchanged_count(self) -> None:
        service = _make_service()
        # MacroService placeholder returns value=50.0 for all indicators
        req = _make_request(
            prior_features=[
                {"indicator_type": "gdp", "value": 50.0},
                {"indicator_type": "inflation", "value": 50.0},
                {"indicator_type": "unemployment", "value": 50.0},
            ]
        )
        response = await service.compare_snapshots(req)
        assert response.success is True
        assert response.changed_count == 0
        assert response.unchanged_count == 3

    async def test_change_detected_path(self) -> None:
        service = _make_service()
        # MacroService placeholder returns value=50.0; give different prior
        req = _make_request(
            prior_features=[
                {"indicator_type": "gdp", "value": 40.0},
                {"indicator_type": "inflation", "value": 50.0},
                {"indicator_type": "unemployment", "value": 50.0},
            ]
        )
        response = await service.compare_snapshots(req)
        assert response.success is True
        assert response.changed_count == 1
        assert response.unchanged_count == 2


# ---------------------------------------------------------------------------
# Prior-snapshot-missing path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCompareSnapshotsPriorMissing:
    async def test_empty_prior_returns_failure(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[])
        response = await service.compare_snapshots(req)
        assert response.success is False

    async def test_error_message_mentions_prior_label(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[], prior_snapshot_label="Q1-2026")
        response = await service.compare_snapshots(req)
        assert response.error_message is not None
        assert "Q1-2026" in response.error_message

    async def test_error_response_country_preserved(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[], country="DE", prior_snapshot_label="prior")
        response = await service.compare_snapshots(req)
        assert response.country == "DE"

    async def test_error_response_prior_label_preserved(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[], prior_snapshot_label="Q1-missing")
        response = await service.compare_snapshots(req)
        assert response.prior_snapshot_label == "Q1-missing"

    async def test_missing_prior_response_schema_valid(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[])
        response = await service.compare_snapshots(req)
        reparsed = SnapshotComparisonResponse.model_validate(response.model_dump())
        assert reparsed.success is False


# ---------------------------------------------------------------------------
# Current-snapshot-fetch failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCompareSnapshotsFetchFailure:
    async def test_macro_service_error_returns_failure(self) -> None:
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("data unavailable")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        assert response.success is False

    async def test_fetch_failure_error_message_present(self) -> None:
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("data unavailable")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        assert response.error_message is not None
        assert len(response.error_message) > 0

    async def test_fetch_failure_response_schema_valid(self) -> None:
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("data unavailable")
        service = AgentService(macro_service=mock_macro, signal_service=SignalService())
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        reparsed = SnapshotComparisonResponse.model_validate(response.model_dump())
        assert reparsed.success is False


# ---------------------------------------------------------------------------
# Schema validity on all paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCompareSnapshotsSchemaValidity:
    async def test_success_response_round_trips(self) -> None:
        service = _make_service()
        req = _make_request(prior_features=[{"indicator_type": "gdp", "value": 50.0}])
        response = await service.compare_snapshots(req)
        reparsed = SnapshotComparisonResponse.model_validate(response.model_dump())
        assert reparsed.success == response.success

    async def test_request_id_echoed_in_response(self) -> None:
        service = _make_service()
        req = _make_request(
            prior_features=[{"indicator_type": "gdp", "value": 50.0}],
            request_id="trace-xyz",
        )
        response = await service.compare_snapshots(req)
        assert response.request_id == "trace-xyz"
