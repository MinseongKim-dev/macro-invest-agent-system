"""MCP adapter layer for agent-to-tool invocation.

The adapter provides a clean, raise-on-failure interface over the MCP tool
handlers so that the agent service can handle errors in one place rather than
inspecting ``success`` flags after every tool call.

Callable boundary contract
---------------------------
* Adapter methods are **async** to match the MCP tool interface.
* On ``MCPResponse.success=True`` the raw MCP response is returned.
* On ``MCPResponse.success=False`` an :class:`MCPToolError` is raised; the
  caller (agent service) catches this and converts it to a failed agent
  response.
* The adapter is **read-only** — it only calls read-only MCP tools.
* The adapter does not contain business logic.
"""

from __future__ import annotations

from core.logging.logger import get_logger
from core.logging.timing import timed_operation
from core.metrics import MCP_TOOL_CALLS_TOTAL, MCP_TOOL_DURATION
from core.tracing import get_tracer
from core.tracing.span_attributes import COUNTRY, MCP_TOOL, REQUEST_ID, RESULT_SUCCESS
from domain.signals.registry import SignalRegistry, default_registry
from mcp.schemas.get_macro_features import GetMacroSnapshotRequest, GetMacroSnapshotResponse
from mcp.schemas.run_signal_engine import RunSignalEngineRequest, RunSignalEngineResponse
from mcp.tools.get_macro_features import handle_get_macro_snapshot
from mcp.tools.run_signal_engine import handle_run_signal_engine
from services.interfaces import MacroServiceInterface, SignalServiceInterface

_log = get_logger(__name__)
_tracer = get_tracer(__name__)


class MCPToolError(Exception):
    """Raised when an MCP tool returns ``success=False``.

    Attributes:
        tool_name: Name of the MCP tool that failed.
        error_message: The ``error_message`` from the MCP response.
    """

    def __init__(self, tool_name: str, error_message: str) -> None:
        self.tool_name = tool_name
        self.error_message = error_message
        super().__init__(f"[{tool_name}] {error_message}")


class MCPAdapter:
    """Thin adapter that exposes MCP tools as raising async methods.

    The agent service uses this adapter so that every tool failure surfaces
    as an :class:`MCPToolError` exception rather than requiring ``success``
    flag checks throughout the orchestration logic.

    Args:
        macro_service: Macro data service implementation.
        signal_service: Signal evaluation service implementation.
        registry: Signal definition registry.  Defaults to
            :data:`~domain.signals.registry.default_registry` when ``None``.
    """

    def __init__(
        self,
        macro_service: MacroServiceInterface,
        signal_service: SignalServiceInterface,
        registry: SignalRegistry | None = None,
    ) -> None:
        self._macro_service = macro_service
        self._signal_service = signal_service
        self._registry: SignalRegistry = registry if registry is not None else default_registry

    # ------------------------------------------------------------------
    # Tool wrappers
    # ------------------------------------------------------------------

    async def get_macro_snapshot(
        self,
        request_id: str,
        country: str,
    ) -> GetMacroSnapshotResponse:
        """Fetch the current macro snapshot via the MCP tool.

        Args:
            request_id: Tracing ID to forward to the MCP tool.
            country: ISO 3166-1 alpha-2 country code.

        Returns:
            :class:`~mcp.schemas.get_macro_features.GetMacroSnapshotResponse`
            with ``success=True``.

        Raises:
            MCPToolError: If the MCP tool returns ``success=False``.
        """
        _log.debug("tool_called", tool="get_macro_snapshot", country=country)
        request = GetMacroSnapshotRequest(request_id=request_id, country=country)
        with _tracer.start_as_current_span("mcp_adapter.get_macro_snapshot") as span:
            span.set_attribute(MCP_TOOL, "get_macro_snapshot")
            span.set_attribute(REQUEST_ID, request_id)
            span.set_attribute(COUNTRY, country)
            with MCP_TOOL_DURATION.labels(tool="get_macro_snapshot").time():
                async with timed_operation("mcp_adapter", "get_macro_snapshot", _log):
                    response = await handle_get_macro_snapshot(request, self._macro_service)
            span.set_attribute(RESULT_SUCCESS, response.success)

        if not response.success:
            _log.warning(
                "tool_failed",
                tool="get_macro_snapshot",
                error=response.error_message,
            )
            MCP_TOOL_CALLS_TOTAL.labels(tool="get_macro_snapshot", result="failure").inc()
            raise MCPToolError("get_macro_snapshot", response.error_message or "unknown error")

        MCP_TOOL_CALLS_TOTAL.labels(tool="get_macro_snapshot", result="success").inc()
        _log.debug("tool_done", tool="get_macro_snapshot", success=True)
        return response

    async def run_signal_engine(
        self,
        request_id: str,
        signal_ids: list[str],
        country: str,
    ) -> RunSignalEngineResponse:
        """Run the signal engine via the MCP tool.

        Args:
            request_id: Tracing ID to forward to the MCP tool.
            signal_ids: Signal definition IDs to evaluate.
            country: ISO 3166-1 alpha-2 country code.

        Returns:
            :class:`~mcp.schemas.run_signal_engine.RunSignalEngineResponse`
            with ``success=True``.

        Raises:
            MCPToolError: If the MCP tool returns ``success=False``.
        """
        _log.debug("tool_called", tool="run_signal_engine", country=country)
        request = RunSignalEngineRequest(
            request_id=request_id,
            signal_ids=signal_ids,
            country=country,
        )
        with _tracer.start_as_current_span("mcp_adapter.run_signal_engine") as span:
            span.set_attribute(MCP_TOOL, "run_signal_engine")
            span.set_attribute(REQUEST_ID, request_id)
            span.set_attribute(COUNTRY, country)
            span.set_attribute("signal.ids_count", len(signal_ids))
            with MCP_TOOL_DURATION.labels(tool="run_signal_engine").time():
                async with timed_operation("mcp_adapter", "run_signal_engine", _log):
                    response = await handle_run_signal_engine(
                        request=request,
                        macro_service=self._macro_service,
                        signal_service=self._signal_service,
                        registry=self._registry,
                    )
            span.set_attribute(RESULT_SUCCESS, response.success)

        if not response.success:
            _log.warning(
                "tool_failed",
                tool="run_signal_engine",
                error=response.error_message,
            )
            MCP_TOOL_CALLS_TOTAL.labels(tool="run_signal_engine", result="failure").inc()
            raise MCPToolError("run_signal_engine", response.error_message or "unknown error")

        MCP_TOOL_CALLS_TOTAL.labels(tool="run_signal_engine", result="success").inc()
        _log.debug("tool_done", tool="run_signal_engine", success=True)
        return response
