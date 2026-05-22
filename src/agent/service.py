"""Thin, read-only agent service for signal review and macro snapshot summarisation.

The agent service orchestrates MCP tool calls and formats the results into
schema-validated :class:`~agent.schemas.SignalReviewResponse` or
:class:`~agent.schemas.MacroSnapshotSummaryResponse` objects.

Design principles
-----------------
* **Read-only**: the service never mutates state.
* **Deterministic**: outputs depend only on tool responses; no LLM or
  randomness is involved.
* **Thin**: no business logic lives here — domain rules stay in ``domain/``,
  data access stays in ``services/``, and tool wiring stays in ``mcp/``.
* **Error-safe**: :class:`~agent.mcp_adapter.MCPToolError` from the adapter
  is caught and converted into a failed agent response so callers never
  receive uncaught exceptions.
* **Separated concerns**: summary and error formatting are delegated to
  :mod:`agent.formatting.summaries` and :mod:`agent.formatting.errors`
  respectively so each concern can be tested and evolved independently.

Usage example::

    from services.macro_service import MacroService
    from services.signal_service import SignalService
    from agent.service import AgentService
    from agent.schemas import SignalReviewRequest

    service = AgentService(MacroService(), SignalService())
    response = await service.review_signals(
        SignalReviewRequest(request_id="req-001", signal_ids=["bull_market"])
    )
    if response.success:
        print(response.summary)
"""

from __future__ import annotations

from agent.formatting.comparison import (
    format_comparison_error,
    format_comparison_summary,
    format_prior_missing_error,
)
from agent.formatting.errors import format_signal_review_error, format_snapshot_summary_error
from agent.formatting.summaries import format_signal_review_summary, format_snapshot_summary
from agent.mcp_adapter import MCPAdapter, MCPToolError
from agent.schemas import (
    MacroSnapshotSummaryRequest,
    MacroSnapshotSummaryResponse,
    SignalReviewRequest,
    SignalReviewResponse,
    SnapshotComparisonRequest,
    SnapshotComparisonResponse,
)
from core.logging.logger import get_logger
from core.logging.timing import timed_operation
from domain.macro.comparison import compare_snapshots as domain_compare_snapshots
from domain.signals.registry import SignalRegistry
from services.interfaces import MacroServiceInterface, SignalServiceInterface

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Agent service
# ---------------------------------------------------------------------------


class AgentService:
    """Read-only agent service that orchestrates MCP tool calls.

    Provides three operations:

    * :meth:`review_signals` — run the signal engine and summarise results.
    * :meth:`summarize_macro_snapshot` — fetch and summarise the macro snapshot.
    * :meth:`compare_snapshots` — compare the current snapshot against prior
      feature values and return a structured "what changed" summary.

    All operations return schema-validated response objects and never raise.

    Args:
        macro_service: Macro data service implementation.
        signal_service: Signal evaluation service implementation.
        registry: Signal definition registry.  Defaults to the built-in
            :data:`~domain.signals.registry.default_registry` when ``None``.
    """

    def __init__(
        self,
        macro_service: MacroServiceInterface,
        signal_service: SignalServiceInterface,
        registry: SignalRegistry | None = None,
    ) -> None:
        self._macro_service = macro_service
        self._adapter = MCPAdapter(macro_service, signal_service, registry)

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    async def review_signals(self, request: SignalReviewRequest) -> SignalReviewResponse:
        """Review one or more signals against the current macro snapshot.

        Calls the ``run_signal_engine`` MCP tool and formats the engine output
        into a :class:`~agent.schemas.SignalReviewResponse`.

        Args:
            request: Validated :class:`~agent.schemas.SignalReviewRequest`.

        Returns:
            :class:`~agent.schemas.SignalReviewResponse` — ``success=True``
            with signal counts and a deterministic ``summary`` on success, or
            ``success=False`` with ``error_message`` on any tool failure.
        """
        _log.info("service_called", operation="review_signals", country=request.country)
        try:
            async with timed_operation("service", "review_signals", _log):
                engine_response = await self._adapter.run_signal_engine(
                    request_id=request.request_id,
                    signal_ids=request.signal_ids,
                    country=request.country,
                )
        except MCPToolError as exc:
            _log.warning(
                "service_failed",
                operation="review_signals",
                tool=exc.tool_name,
                error=exc.error_message,
            )
            return SignalReviewResponse(
                request_id=request.request_id,
                success=False,
                error_message=format_signal_review_error(
                    raw_error=exc.error_message,
                    request_id=request.request_id,
                ),
            )

        _log.info("service_done", operation="review_signals", success=True)
        summary = format_signal_review_summary(
            engine_response, request.signal_ids, request.country
        )
        return SignalReviewResponse(
            request_id=request.request_id,
            success=True,
            summary=summary,
            engine_run_id=engine_response.engine_run_id,
            signals_generated=engine_response.signals_generated,
            buy_signals=engine_response.buy_signals,
            sell_signals=engine_response.sell_signals,
            hold_signals=engine_response.hold_signals,
            execution_time_ms=engine_response.execution_time_ms,
        )

    async def summarize_macro_snapshot(
        self,
        request: MacroSnapshotSummaryRequest,
    ) -> MacroSnapshotSummaryResponse:
        """Summarise the current macro snapshot for a given country.

        Calls the ``get_macro_snapshot`` MCP tool and formats the result into
        a :class:`~agent.schemas.MacroSnapshotSummaryResponse`.

        Args:
            request: Validated :class:`~agent.schemas.MacroSnapshotSummaryRequest`.

        Returns:
            :class:`~agent.schemas.MacroSnapshotSummaryResponse` —
            ``success=True`` with snapshot metadata and a deterministic
            ``summary`` on success, or ``success=False`` with
            ``error_message`` on any tool failure.
        """
        _log.info("service_called", operation="summarize_macro_snapshot", country=request.country)
        try:
            async with timed_operation("service", "summarize_macro_snapshot", _log):
                snapshot_response = await self._adapter.get_macro_snapshot(
                    request_id=request.request_id,
                    country=request.country,
                )
        except MCPToolError as exc:
            _log.warning(
                "service_failed",
                operation="summarize_macro_snapshot",
                tool=exc.tool_name,
                error=exc.error_message,
            )
            return MacroSnapshotSummaryResponse(
                request_id=request.request_id,
                success=False,
                error_message=format_snapshot_summary_error(
                    raw_error=exc.error_message,
                    request_id=request.request_id,
                    country=request.country,
                ),
                country=request.country,
            )

        _log.info("service_done", operation="summarize_macro_snapshot", success=True)
        summary = format_snapshot_summary(snapshot_response, request.country)
        return MacroSnapshotSummaryResponse(
            request_id=request.request_id,
            success=True,
            summary=summary,
            country=request.country,
            snapshot_timestamp=snapshot_response.snapshot_timestamp,
            features_count=snapshot_response.features_count,
        )

    async def compare_snapshots(
        self,
        request: SnapshotComparisonRequest,
    ) -> SnapshotComparisonResponse:
        """Compare the current macro snapshot against provided prior values.

        Pipeline:

        1. Reject requests with empty *prior_features* (prior snapshot missing).
        2. Fetch the current snapshot directly from the macro service.
        3. Run the deterministic :func:`~domain.macro.comparison.compare_snapshots`
           function against the provided prior feature values.
        4. Format the result into a :class:`~agent.schemas.SnapshotComparisonResponse`.

        Args:
            request: Validated :class:`~agent.schemas.SnapshotComparisonRequest`.

        Returns:
            :class:`~agent.schemas.SnapshotComparisonResponse` —
            ``success=True`` with change counts and a deterministic ``summary``
            on success, or ``success=False`` with ``error_message`` on any
            failure (prior missing, tool failure).
        """
        # ------------------------------------------------------------------
        # Guard: prior snapshot missing
        # ------------------------------------------------------------------
        if not request.prior_features:
            _log.warning(
                "service_prior_missing",
                operation="compare_snapshots",
                prior_label=request.prior_snapshot_label,
            )
            return SnapshotComparisonResponse(
                request_id=request.request_id,
                success=False,
                error_message=format_prior_missing_error(
                    prior_snapshot_label=request.prior_snapshot_label,
                    request_id=request.request_id,
                    country=request.country,
                ),
                country=request.country,
                prior_snapshot_label=request.prior_snapshot_label,
            )

        # ------------------------------------------------------------------
        # Fetch current snapshot and compare
        # ------------------------------------------------------------------
        # We call the macro service directly here to obtain the full domain
        # MacroSnapshot with typed MacroFeature objects for comparison.
        # The MCP tool layer only returns a lightweight response (count +
        # timestamp), which is insufficient for per-indicator comparison.
        _log.info("service_called", operation="compare_snapshots", country=request.country)
        try:
            async with timed_operation("service", "compare_snapshots", _log):
                full_snapshot = await self._macro_service.get_snapshot(country=request.country)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "service_failed",
                operation="compare_snapshots",
                error=type(exc).__name__,
            )
            return SnapshotComparisonResponse(
                request_id=request.request_id,
                success=False,
                error_message=format_comparison_error(
                    raw_error=str(exc),
                    request_id=request.request_id,
                    country=request.country,
                ),
                country=request.country,
                prior_snapshot_label=request.prior_snapshot_label,
            )

        comparison = domain_compare_snapshots(
            current=full_snapshot,
            prior_features=request.prior_features,
            prior_snapshot_label=request.prior_snapshot_label,
            country=request.country,
        )

        summary = format_comparison_summary(comparison)
        return SnapshotComparisonResponse(
            request_id=request.request_id,
            success=True,
            summary=summary,
            country=request.country,
            prior_snapshot_label=request.prior_snapshot_label,
            current_snapshot_timestamp=comparison.current_snapshot_timestamp,
            changed_count=comparison.changed_count,
            unchanged_count=comparison.unchanged_count,
            no_prior_count=comparison.no_prior_count,
        )
