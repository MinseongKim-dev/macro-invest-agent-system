"""MCP tool handlers for macro feature retrieval.

These thin handler functions translate MCP request objects into service-layer
calls and map the results (or exceptions) back into structured MCP responses.
They contain no business logic: validation lives in the request schema and
domain models; data access lives in the service layer.

Callable boundary contract
---------------------------
* Handlers are **async** to match the async service interface.
* Handlers **never raise**; all errors are captured and returned as
  ``MCPResponse(success=False, error_message=…)``.
* Handlers are **read-only**: they query data but do not mutate state.
"""

from __future__ import annotations

import asyncio

from core.exceptions.base import PartialDataError, ProviderError, StaleDataError
from core.exceptions.failure_category import FailureCategory
from core.logging.logger import get_logger
from core.logging.timing import timed_operation
from core.tracing import get_tracer
from core.tracing.span_attributes import (
    COUNTRY,
    FEATURES_COUNT,
    MCP_TOOL,
    REQUEST_ID,
    RESULT_SUCCESS,
)
from mcp.schemas.get_macro_features import (
    GetMacroFeaturesRequest,
    GetMacroFeaturesResponse,
    GetMacroSnapshotRequest,
    GetMacroSnapshotResponse,
)
from services.interfaces import MacroServiceInterface

_log = get_logger(__name__)
_tracer = get_tracer(__name__)


def _provider_error_to_category(exc: ProviderError) -> FailureCategory:
    """Map a ProviderError subclass to the appropriate FailureCategory."""
    from core.exceptions.base import ProviderHTTPError, ProviderNetworkError, ProviderTimeoutError

    if isinstance(exc, ProviderTimeoutError):
        return FailureCategory.PROVIDER_TIMEOUT
    if isinstance(exc, ProviderHTTPError):
        return FailureCategory.PROVIDER_HTTP
    if isinstance(exc, ProviderNetworkError):
        return FailureCategory.PROVIDER_NETWORK
    return FailureCategory.UNKNOWN


async def handle_get_macro_features(
    request: GetMacroFeaturesRequest,
    service: MacroServiceInterface,
) -> GetMacroFeaturesResponse:
    """Execute the ``get_macro_features`` MCP tool.

    Fetches the requested macro indicators via *service* and returns a
    response containing the count of features retrieved.

    Args:
        request: Validated :class:`~mcp.schemas.get_macro_features.GetMacroFeaturesRequest`.
        service: Macro data service implementation.

    Returns:
        :class:`~mcp.schemas.get_macro_features.GetMacroFeaturesResponse` —
        ``success=True`` with ``features_count`` on success, or
        ``success=False`` with ``error_message`` on failure.
    """
    if not request.indicator_types:
        return GetMacroFeaturesResponse(
            request_id=request.request_id,
            success=False,
            error_message="indicator_types must not be empty.",
            features_count=0,
        )

    _log.debug("mcp_tool_invoked", tool="get_macro_features", request_id=request.request_id)
    with _tracer.start_as_current_span("mcp_tool.get_macro_features") as span:
        span.set_attribute(MCP_TOOL, "get_macro_features")
        span.set_attribute(REQUEST_ID, request.request_id)
        span.set_attribute(COUNTRY, request.country)
        span.set_attribute("indicator_count", len(request.indicator_types))
        try:
            async with timed_operation("mcp_tool", "get_macro_features", _log):
                features = await service.fetch_features(
                    indicator_types=request.indicator_types,
                    country=request.country,
                )
        except ValueError as exc:
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning("mcp_tool_returned", tool="get_macro_features", success=False, error=str(exc))
            return GetMacroFeaturesResponse(
                request_id=request.request_id,
                success=False,
                error_message=str(exc),
                features_count=0,
            )
        except ProviderError as exc:
            category = _provider_error_to_category(exc)
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning(
                "mcp_tool_returned",
                tool="get_macro_features",
                success=False,
                failure_category=category,
            )
            return GetMacroFeaturesResponse(
                request_id=request.request_id,
                success=False,
                error_message=str(exc),
                features_count=0,
                failure_category=category,
            )
        except StaleDataError as exc:
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning(
                "mcp_tool_returned",
                tool="get_macro_features",
                success=False,
                failure_category=FailureCategory.STALE_DATA,
            )
            return GetMacroFeaturesResponse(
                request_id=request.request_id,
                success=False,
                error_message=str(exc),
                features_count=0,
                failure_category=FailureCategory.STALE_DATA,
                is_degraded=True,
            )
        except PartialDataError as exc:
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning(
                "mcp_tool_returned",
                tool="get_macro_features",
                success=False,
                failure_category=FailureCategory.PARTIAL_DATA,
            )
            return GetMacroFeaturesResponse(
                request_id=request.request_id,
                success=False,
                error_message=str(exc),
                features_count=exc.available_count,
                failure_category=FailureCategory.PARTIAL_DATA,
                is_degraded=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            span.set_attribute(RESULT_SUCCESS, False)
            _log.exception(
                "mcp_tool_returned",
                tool="get_macro_features",
                success=False,
                request_id=request.request_id,
            )
            return GetMacroFeaturesResponse(
                request_id=request.request_id,
                success=False,
                error_message="Failed to fetch macro features.",
                features_count=0,
                failure_category=FailureCategory.UNKNOWN,
            )

        span.set_attribute(RESULT_SUCCESS, True)
        span.set_attribute(FEATURES_COUNT, len(features))

    _log.debug(
        "mcp_tool_returned",
        tool="get_macro_features",
        success=True,
        features_count=len(features),
    )
    return GetMacroFeaturesResponse(
        request_id=request.request_id,
        success=True,
        features_count=len(features),
    )


async def handle_get_macro_snapshot(
    request: GetMacroSnapshotRequest,
    service: MacroServiceInterface,
) -> GetMacroSnapshotResponse:
    """Execute the ``get_macro_snapshot`` MCP tool.

    Retrieves a complete macro snapshot for the requested country via *service*.

    Args:
        request: Validated :class:`~mcp.schemas.get_macro_features.GetMacroSnapshotRequest`.
        service: Macro data service implementation.

    Returns:
        :class:`~mcp.schemas.get_macro_features.GetMacroSnapshotResponse` —
        ``success=True`` with snapshot metadata on success, or
        ``success=False`` with ``error_message`` on failure.
    """
    _log.debug("mcp_tool_invoked", tool="get_macro_snapshot", request_id=request.request_id)
    with _tracer.start_as_current_span("mcp_tool.get_macro_snapshot") as span:
        span.set_attribute(MCP_TOOL, "get_macro_snapshot")
        span.set_attribute(REQUEST_ID, request.request_id)
        span.set_attribute(COUNTRY, request.country)
        try:
            async with timed_operation("mcp_tool", "get_macro_snapshot", _log):
                snapshot = await service.get_snapshot(country=request.country)
        except ProviderError as exc:
            category = _provider_error_to_category(exc)
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning(
                "mcp_tool_returned",
                tool="get_macro_snapshot",
                success=False,
                failure_category=category,
            )
            return GetMacroSnapshotResponse(
                request_id=request.request_id,
                success=False,
                error_message=str(exc),
                snapshot_timestamp=None,
                features_count=0,
                failure_category=category,
            )
        except StaleDataError as exc:
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning(
                "mcp_tool_returned",
                tool="get_macro_snapshot",
                success=False,
                failure_category=FailureCategory.STALE_DATA,
            )
            return GetMacroSnapshotResponse(
                request_id=request.request_id,
                success=False,
                error_message=str(exc),
                snapshot_timestamp=None,
                features_count=0,
                failure_category=FailureCategory.STALE_DATA,
                is_degraded=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            span.set_attribute(RESULT_SUCCESS, False)
            _log.exception(
                "mcp_tool_returned",
                tool="get_macro_snapshot",
                success=False,
                request_id=request.request_id,
            )
            return GetMacroSnapshotResponse(
                request_id=request.request_id,
                success=False,
                error_message="Failed to fetch macro snapshot.",
                snapshot_timestamp=None,
                features_count=0,
                failure_category=FailureCategory.UNKNOWN,
            )

        span.set_attribute(RESULT_SUCCESS, True)
        span.set_attribute(FEATURES_COUNT, len(snapshot.features))

    _log.debug(
        "mcp_tool_returned",
        tool="get_macro_snapshot",
        success=True,
        features_count=len(snapshot.features),
    )
    return GetMacroSnapshotResponse(
        request_id=request.request_id,
        success=True,
        snapshot_timestamp=snapshot.snapshot_time,
        features_count=len(snapshot.features),
    )
