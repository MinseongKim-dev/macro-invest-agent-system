"""MCP tool handler for signal engine execution.

Translates a :class:`~mcp.schemas.run_signal_engine.RunSignalEngineRequest`
into a coordinated sequence of service calls:

1. Resolve signal IDs → :class:`~domain.signals.models.SignalDefinition` objects
   via the :class:`~domain.signals.registry.SignalRegistry`.
2. Fetch the current macro snapshot via
   :class:`~services.interfaces.MacroServiceInterface`.
3. Run the signal engine via
   :class:`~services.interfaces.SignalServiceInterface`.
4. Return a structured :class:`~mcp.schemas.run_signal_engine.RunSignalEngineResponse`.

Callable boundary contract
---------------------------
* The handler is **async** to match the async service interface.
* The handler **never raises**; all errors are captured and returned as
  ``MCPResponse(success=False, error_message=…)``.
* The handler is **read-only**: it queries data but does not mutate state.
"""

from __future__ import annotations

import asyncio
import time

from core.exceptions.base import ProviderError, StaleDataError
from core.exceptions.failure_category import FailureCategory
from core.logging.logger import get_logger
from core.logging.timing import timed_operation
from core.tracing import get_tracer
from core.tracing.span_attributes import (
    COUNTRY,
    ENGINE_RUN_ID,
    MCP_TOOL,
    REQUEST_ID,
    RESULT_SUCCESS,
    SIGNAL_COUNT,
)
from domain.signals.enums import SignalType
from domain.signals.registry import SignalRegistry, default_registry
from mcp.schemas.run_signal_engine import RunSignalEngineRequest, RunSignalEngineResponse
from services.interfaces import MacroServiceInterface, SignalServiceInterface

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

# Sentinel returned in error responses where no run ID was generated.
_NO_RUN_ID = ""


async def handle_run_signal_engine(
    request: RunSignalEngineRequest,
    macro_service: MacroServiceInterface,
    signal_service: SignalServiceInterface,
    registry: SignalRegistry | None = None,
) -> RunSignalEngineResponse:
    """Execute the ``run_signal_engine`` MCP tool.

    Resolves the requested signal IDs against *registry*, fetches the macro
    snapshot for ``request.country``, and runs the signal engine.  Execution
    time is measured in milliseconds and included in the response.

    Args:
        request: Validated :class:`~mcp.schemas.run_signal_engine.RunSignalEngineRequest`.
        macro_service: Macro data service for snapshot retrieval.
        signal_service: Signal evaluation service.
        registry: Signal definition registry.  Defaults to
            :data:`~domain.signals.registry.default_registry` when ``None``.

    Returns:
        :class:`~mcp.schemas.run_signal_engine.RunSignalEngineResponse` —
        ``success=True`` with signal counts and ``engine_run_id`` on success,
        or ``success=False`` with ``error_message`` on failure.
    """
    if registry is None:
        registry = default_registry

    # ------------------------------------------------------------------
    # 1. Validate that the request contains at least one signal ID.
    # ------------------------------------------------------------------
    if not request.signal_ids:
        return RunSignalEngineResponse(
            request_id=request.request_id,
            engine_run_id=_NO_RUN_ID,
            success=False,
            error_message="signal_ids must not be empty.",
        )

    # ------------------------------------------------------------------
    # 1b. Reject use_latest_snapshot=False until the alternate path is
    #     implemented: always fetch a live snapshot for now.
    # ------------------------------------------------------------------
    if not request.use_latest_snapshot:
        return RunSignalEngineResponse(
            request_id=request.request_id,
            engine_run_id=_NO_RUN_ID,
            success=False,
            error_message=(
                "use_latest_snapshot=False is not yet supported; "
                "only live snapshot fetching is available."
            ),
        )

    # ------------------------------------------------------------------
    # 2. Resolve signal IDs → SignalDefinition objects.
    # ------------------------------------------------------------------
    signal_definitions = []
    unknown_ids: list[str] = []

    for signal_id in request.signal_ids:
        try:
            signal_definitions.append(registry.get(signal_id))
        except KeyError:
            unknown_ids.append(signal_id)

    if unknown_ids:
        joined = ", ".join(f"'{sid}'" for sid in unknown_ids)
        return RunSignalEngineResponse(
            request_id=request.request_id,
            engine_run_id=_NO_RUN_ID,
            success=False,
            error_message=f"Unknown signal ID(s): {joined}.",
        )

    # ------------------------------------------------------------------
    # 3. Fetch the macro snapshot.
    # ------------------------------------------------------------------
    _log.debug("mcp_tool_invoked", tool="run_signal_engine", request_id=request.request_id)
    with _tracer.start_as_current_span("mcp_tool.run_signal_engine") as span:
        span.set_attribute(MCP_TOOL, "run_signal_engine")
        span.set_attribute(REQUEST_ID, request.request_id)
        span.set_attribute(COUNTRY, request.country)
        span.set_attribute("signal.ids_count", len(request.signal_ids))

        try:
            async with timed_operation("mcp_tool", "fetch_snapshot_for_engine", _log):
                snapshot = await macro_service.get_snapshot(country=request.country)
        except ProviderError as exc:
            category = _provider_error_to_category(exc)
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning(
                "mcp_tool_returned",
                tool="run_signal_engine",
                success=False,
                failure_category=category,
            )
            return RunSignalEngineResponse(
                request_id=request.request_id,
                engine_run_id=_NO_RUN_ID,
                success=False,
                error_message=str(exc),
                failure_category=category,
            )
        except StaleDataError as exc:
            span.set_attribute(RESULT_SUCCESS, False)
            _log.warning(
                "mcp_tool_returned",
                tool="run_signal_engine",
                success=False,
                failure_category=FailureCategory.STALE_DATA,
            )
            return RunSignalEngineResponse(
                request_id=request.request_id,
                engine_run_id=_NO_RUN_ID,
                success=False,
                error_message=str(exc),
                failure_category=FailureCategory.STALE_DATA,
                is_degraded=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            span.set_attribute(RESULT_SUCCESS, False)
            _log.exception(
                "mcp_tool_returned",
                tool="run_signal_engine",
                success=False,
                step="fetch_snapshot",
                request_id=request.request_id,
            )
            return RunSignalEngineResponse(
                request_id=request.request_id,
                engine_run_id=_NO_RUN_ID,
                success=False,
                error_message="Failed to fetch macro snapshot.",
                failure_category=FailureCategory.UNKNOWN,
            )

        # ------------------------------------------------------------------
        # 4. Run the signal engine and measure wall-clock execution time.
        # ------------------------------------------------------------------
        start = time.perf_counter()
        try:
            async with timed_operation("mcp_tool", "run_signal_engine_core", _log):
                result = await signal_service.run_engine(signal_definitions, snapshot)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            span.set_attribute(RESULT_SUCCESS, False)
            _log.exception(
                "mcp_tool_returned",
                tool="run_signal_engine",
                success=False,
                step="run_engine",
                request_id=request.request_id,
            )
            return RunSignalEngineResponse(
                request_id=request.request_id,
                engine_run_id=_NO_RUN_ID,
                success=False,
                error_message="Signal engine execution failed.",
                failure_category=FailureCategory.UNKNOWN,
            )
        execution_ms = (time.perf_counter() - start) * 1000.0

        span.set_attribute(RESULT_SUCCESS, True)
        span.set_attribute(SIGNAL_COUNT, len(result.signals))
        span.set_attribute(ENGINE_RUN_ID, result.run_id)

    _log.debug(
        "mcp_tool_returned",
        tool="run_signal_engine",
        success=True,
        signals_generated=len(result.signals),
    )
    return RunSignalEngineResponse(
        request_id=request.request_id,
        engine_run_id=result.run_id,
        success=True,
        signals_generated=len(result.signals),
        buy_signals=len(result.get_signals_by_type(SignalType.BUY)),
        sell_signals=len(result.get_signals_by_type(SignalType.SELL)),
        hold_signals=len(result.get_signals_by_type(SignalType.HOLD)),
        execution_time_ms=round(execution_ms, 3),
    )
