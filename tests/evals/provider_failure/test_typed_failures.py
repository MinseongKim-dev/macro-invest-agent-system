"""Eval: typed failure categories propagate correctly through the MCP tool layer.

Verifies that ProviderHTTPError (503), ProviderTimeoutError, and PartialDataError
each produce the correct failure_category on the MCP response, and that
is_degraded=True is set for partial/stale paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.exceptions.base import (
    PartialDataError,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from core.exceptions.failure_category import FailureCategory
from mcp.schemas.get_macro_features import GetMacroSnapshotRequest
from mcp.schemas.run_signal_engine import RunSignalEngineRequest
from mcp.tools.get_macro_features import handle_get_macro_snapshot
from mcp.tools.run_signal_engine import handle_run_signal_engine
from services.macro_service import MacroService
from services.signal_service import SignalService


@pytest.mark.asyncio
class TestTypedFailureCategories:
    """Each typed exception maps to the correct failure_category on the response."""

    async def test_provider_http_503_produces_provider_http_category(self) -> None:
        macro_svc = MacroService()
        macro_svc.get_snapshot = AsyncMock(  # type: ignore[method-assign]
            side_effect=ProviderHTTPError(
                "FRED returned HTTP 503",
                provider_id="fred",
                http_status=503,
            )
        )
        req = GetMacroSnapshotRequest(request_id="typed-req-001", country="US")
        response = await handle_get_macro_snapshot(req, macro_svc)

        assert response.success is False
        assert response.failure_category == FailureCategory.PROVIDER_HTTP
        assert response.is_degraded is False  # HTTP error is a hard failure

    async def test_provider_timeout_produces_timeout_category(self) -> None:
        macro_svc = MacroService()
        macro_svc.get_snapshot = AsyncMock(  # type: ignore[method-assign]
            side_effect=ProviderTimeoutError(
                "FRED timed out",
                provider_id="fred",
                timeout_s=30.0,
            )
        )
        req = GetMacroSnapshotRequest(request_id="typed-req-002", country="US")
        response = await handle_get_macro_snapshot(req, macro_svc)

        assert response.success is False
        assert response.failure_category == FailureCategory.PROVIDER_TIMEOUT
        assert response.is_degraded is False

    async def test_provider_http_503_on_signal_engine(self) -> None:
        macro_svc = MacroService()
        macro_svc.get_snapshot = AsyncMock(  # type: ignore[method-assign]
            side_effect=ProviderHTTPError(
                "FRED returned HTTP 503",
                provider_id="fred",
                http_status=503,
            )
        )
        signal_svc = SignalService()
        req = RunSignalEngineRequest(
            request_id="typed-req-003",
            signal_ids=["bull_market"],
            country="US",
        )
        response = await handle_run_signal_engine(
            request=req,
            macro_service=macro_svc,
            signal_service=signal_svc,
        )
        assert response.success is False
        assert response.failure_category == FailureCategory.PROVIDER_HTTP

    async def test_provider_timeout_on_signal_engine(self) -> None:
        macro_svc = MacroService()
        macro_svc.get_snapshot = AsyncMock(  # type: ignore[method-assign]
            side_effect=ProviderTimeoutError("timed out", provider_id="fred")
        )
        signal_svc = SignalService()
        req = RunSignalEngineRequest(
            request_id="typed-req-004",
            signal_ids=["bull_market"],
            country="US",
        )
        response = await handle_run_signal_engine(
            request=req,
            macro_service=macro_svc,
            signal_service=signal_svc,
        )
        assert response.success is False
        assert response.failure_category == FailureCategory.PROVIDER_TIMEOUT

    async def test_partial_data_produces_partial_category_and_is_degraded(self) -> None:
        macro_svc = MacroService()
        macro_svc.fetch_features = AsyncMock(  # type: ignore[method-assign]
            side_effect=PartialDataError(
                "Only 2 of 5 indicators available",
                available_count=2,
                requested_count=5,
            )
        )
        from mcp.schemas.get_macro_features import GetMacroFeaturesRequest
        from mcp.tools.get_macro_features import handle_get_macro_features

        req = GetMacroFeaturesRequest(
            request_id="typed-req-005",
            country="US",
            indicator_types=["gdp", "inflation", "unemployment", "bond_yield", "pmi"],
        )
        response = await handle_get_macro_features(req, macro_svc)

        assert response.success is False
        assert response.failure_category == FailureCategory.PARTIAL_DATA
        assert response.is_degraded is True

    async def test_failure_category_is_none_on_success(self) -> None:
        macro_svc = MacroService()
        req = GetMacroSnapshotRequest(request_id="typed-req-006", country="US")
        response = await handle_get_macro_snapshot(req, macro_svc)

        assert response.success is True
        assert response.failure_category is None
        assert response.is_degraded is False
