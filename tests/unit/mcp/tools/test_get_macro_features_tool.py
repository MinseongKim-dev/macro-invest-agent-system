"""Tests for the get_macro_features MCP tool handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.mcp.schemas.get_macro_features import (
    GetMacroFeaturesRequest,
    GetMacroSnapshotRequest,
)
from src.agent.mcp.tools.get_macro_features import (
    handle_get_macro_features,
    handle_get_macro_snapshot,
)
from src.services.macro_service import MacroService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _features_request(
    indicator_types: list[str],
    country: str = "US",
    request_id: str = "req-test-001",
) -> GetMacroFeaturesRequest:
    return GetMacroFeaturesRequest(
        request_id=request_id,
        indicator_types=indicator_types,
        country=country,
    )


def _snapshot_request(
    country: str = "US",
    request_id: str = "req-test-002",
) -> GetMacroSnapshotRequest:
    return GetMacroSnapshotRequest(request_id=request_id, country=country)


# ---------------------------------------------------------------------------
# handle_get_macro_features
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHandleGetMacroFeatures:
    """Tests for handle_get_macro_features."""

    async def test_success_returns_feature_count(self) -> None:
        """Valid request returns success response with features_count."""
        service = MacroService()
        request = _features_request(["gdp", "inflation"])

        response = await handle_get_macro_features(request, service)

        assert response.success is True
        assert response.request_id == "req-test-001"
        assert response.error_message is None
        assert response.features_count >= 0

    async def test_success_echoes_request_id(self) -> None:
        """Response request_id matches request."""
        service = MacroService()
        request = _features_request(["gdp"], request_id="unique-xyz")

        response = await handle_get_macro_features(request, service)

        assert response.request_id == "unique-xyz"

    async def test_empty_indicator_types_returns_error(self) -> None:
        """Empty indicator list returns an error response without calling service."""
        mock_service = AsyncMock(spec=MacroService)
        request = _features_request([])

        response = await handle_get_macro_features(request, mock_service)

        assert response.success is False
        assert "empty" in response.error_message.lower()  # type: ignore[union-attr]
        assert response.features_count == 0
        mock_service.fetch_features.assert_not_called()

    async def test_service_value_error_returns_error(self) -> None:
        """ValueError from service is captured and returned as error response."""
        mock_service = AsyncMock(spec=MacroService)
        mock_service.fetch_features.side_effect = ValueError("bad indicator")
        request = _features_request(["unknown_indicator"])

        response = await handle_get_macro_features(request, mock_service)

        assert response.success is False
        assert response.error_message is not None
        assert response.features_count == 0

    async def test_service_runtime_error_returns_error(self) -> None:
        """Unexpected exception from service is captured and returned as error response."""
        mock_service = AsyncMock(spec=MacroService)
        mock_service.fetch_features.side_effect = RuntimeError("upstream timeout")
        request = _features_request(["gdp"])

        response = await handle_get_macro_features(request, mock_service)

        assert response.success is False
        assert response.error_message == "Failed to fetch macro features."
        assert response.features_count == 0

    async def test_non_us_country_accepted(self) -> None:
        """Country codes other than US are forwarded to the service."""
        service = MacroService()
        request = _features_request(["gdp"], country="GB")

        response = await handle_get_macro_features(request, service)

        assert response.request_id == "req-test-001"
        # Whether features are returned or not, the handler must not crash.
        assert response.success is True or response.error_message is not None


# ---------------------------------------------------------------------------
# handle_get_macro_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHandleGetMacroSnapshot:
    """Tests for handle_get_macro_snapshot."""

    async def test_success_returns_snapshot_metadata(self) -> None:
        """Valid request returns success response with features_count."""
        service = MacroService()
        request = _snapshot_request()

        response = await handle_get_macro_snapshot(request, service)

        assert response.success is True
        assert response.request_id == "req-test-002"
        assert response.error_message is None
        assert response.features_count > 0
        assert response.snapshot_timestamp is not None

    async def test_success_echoes_request_id(self) -> None:
        """Response request_id matches request."""
        service = MacroService()
        request = _snapshot_request(request_id="snap-abc")

        response = await handle_get_macro_snapshot(request, service)

        assert response.request_id == "snap-abc"

    async def test_service_runtime_error_returns_error(self) -> None:
        """RuntimeError from service is captured and returned as error response."""
        mock_service = AsyncMock(spec=MacroService)
        mock_service.get_snapshot.side_effect = RuntimeError("no data")
        request = _snapshot_request()

        response = await handle_get_macro_snapshot(request, mock_service)

        assert response.success is False
        assert response.error_message == "Failed to fetch macro snapshot."
        assert response.features_count == 0

    async def test_non_us_country(self) -> None:
        """Country codes other than US are forwarded correctly."""
        service = MacroService()
        request = _snapshot_request(country="DE")

        response = await handle_get_macro_snapshot(request, service)

        assert response.request_id == "req-test-002"
