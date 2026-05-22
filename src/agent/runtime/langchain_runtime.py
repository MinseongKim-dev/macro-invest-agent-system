"""LangChain-wired agent runtime.

This module provides :class:`LangChainAgentRuntime` — a runtime adapter that
wraps the existing :class:`~agent.service.AgentService` with LangChain prompt
templates, tool bindings, and output schema validation.

Architecture
------------
::

    Caller
      │
      │  AgentRequest (optional session_id)
      ▼
    ┌──────────────────────────┐
    │  LangChainAgentRuntime   │ ← prompt templates + context + validation
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │     AgentService         │ ← unchanged
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │     MCPAdapter           │ ← unchanged
    └───────────┬──────────────┘
                │
                ▼
          MCP Tool Handlers

Design constraints
------------------
* **Read-only**: the runtime only dispatches to read-only service methods.
* **No LLM calls**: prompt templates are rendered directly; no model is invoked.
* **Deterministic**: prompts never override or reinterpret tool results.
* **Schema-safe**: every output is validated at the boundary before return.
* **Backward-compatible**: the runtime exposes the same ``invoke`` interface
  as :class:`~agent.runtime.agent_runtime.AgentRuntime`.
* **Session-scoped context**: when a request carries a ``session_id`` the
  runtime injects recent-turn context into the prompt and records the turn.
  Context never overrides tool results.

Backward compatibility
----------------------
:class:`~agent.context.models.ConversationTurn` and
:class:`~agent.context.models.ConversationContext` were previously defined
in this module.  They have moved to :mod:`agent.context.models` and are
re-exported here so that any code importing them from this module continues
to work without change.
"""

from __future__ import annotations

from typing import Any

from agent.context.models import AnalysisParameters, ConversationContext, ConversationTurn
from agent.context.store import InMemoryContextStore
from agent.formatting.summaries import dominant_signal_type
from agent.mcp_adapter import MCPAdapter
from agent.prompts.templates import (
    render_signal_review_summary,
    render_snapshot_comparison_summary,
    render_snapshot_summary,
)
from agent.runtime.agent_runtime import (
    AgentOperation,
    AgentRequestInput,
    AgentRuntimeResult,
)
from agent.runtime.output_validation import validate_runtime_result
from agent.schemas import (
    MacroSnapshotSummaryRequest,
    MacroSnapshotSummaryResponse,
    SignalReviewRequest,
    SignalReviewResponse,
    SnapshotComparisonRequest,
    SnapshotComparisonResponse,
)
from agent.service import AgentService
from core.logging.logger import get_logger

_log = get_logger(__name__)

_DEFAULT_MAX_TURNS = 10

__all__ = [
    "ConversationContext",
    "ConversationTurn",
    "LangChainAgentRuntime",
]


# ---------------------------------------------------------------------------
# LangChain agent runtime
# ---------------------------------------------------------------------------


class LangChainAgentRuntime:
    """LangChain-wired runtime adapter for the agent layer.

    Delegates to :class:`~agent.service.AgentService` for tool invocation,
    uses LangChain prompt templates for summary formatting, and validates
    every output against the typed agent schemas before returning.

    Supports two context modes:

    1. **Legacy single-context mode** (``enable_context=True``): maintains one
       :class:`~agent.context.models.ConversationContext` per runtime instance.
       Requests without a ``session_id`` use this shared context.
    2. **Session-scoped mode**: when a request carries a non-empty
       ``session_id``, that ID is used to look up (or create) an isolated
       :class:`~agent.context.models.ConversationContext` in the internal
       :class:`~agent.context.store.InMemoryContextStore`.  Sessions are
       completely isolated — no context leaks between different IDs.

    Context is in-memory only.  It is not persisted and does not survive
    process restarts.  Context never overrides deterministic tool results.

    Args:
        service: The :class:`~agent.service.AgentService` instance.
        adapter: The :class:`~agent.mcp_adapter.MCPAdapter` instance used to
            create LangChain tool bindings.
        enable_context: When ``True``, maintain a per-instance conversation
            context for requests that carry no ``session_id``.  Defaults to
            ``False``.
        max_context_turns: Maximum number of turns to retain in any context.
    """

    def __init__(
        self,
        service: AgentService,
        adapter: MCPAdapter,
        *,
        enable_context: bool = False,
        max_context_turns: int = _DEFAULT_MAX_TURNS,
    ) -> None:
        self._service = service
        self._adapter = adapter
        self._max_context_turns = max_context_turns

        # Legacy single-instance context (enable_context=True, no session_id).
        self._context: ConversationContext | None = (
            ConversationContext(max_turns=max_context_turns) if enable_context else None
        )

        # Session-keyed store for requests that supply a session_id.
        self._session_store = InMemoryContextStore()

        from agent.runtime.tools import (
            create_macro_snapshot_tool,
            create_signal_engine_tool,
        )

        self._tools = [
            create_signal_engine_tool(adapter),
            create_macro_snapshot_tool(adapter),
        ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[Any]:
        """Bound LangChain tools (read-only access for introspection)."""
        return list(self._tools)

    @property
    def context(self) -> ConversationContext | None:
        """The legacy per-instance context, or ``None`` if disabled."""
        return self._context

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    async def invoke(self, request: AgentRequestInput) -> AgentRuntimeResult:
        """Dispatch an agent request through the LangChain-wired pipeline.

        Pipeline steps:

        1. Resolve the active :class:`~agent.context.models.ConversationContext`
           for this request (session-keyed or legacy per-instance).
        2. Build a context summary hint for prompt injection (empty when no
           context has been established yet).
        3. Delegate to ``AgentService`` for deterministic tool execution.
        4. Re-format the ``summary`` field using the LangChain prompt template
           with the context hint injected into the system message.
        5. Validate the complete result against the output schema.
        6. Record the turn in the active context.

        Args:
            request: A validated agent request.

        Returns:
            :class:`AgentRuntimeResult` with schema-validated response.

        Raises:
            TypeError: If an unsupported request type is passed.
            OutputValidationError: If the output fails schema validation.
        """
        active_ctx = self._resolve_context(request)
        context_hint = active_ctx.context_summary() if active_ctx is not None else ""

        if isinstance(request, SignalReviewRequest):
            result = await self._invoke_review_signals(request, context_hint)
        elif isinstance(request, MacroSnapshotSummaryRequest):
            result = await self._invoke_summarize_snapshot(request, context_hint)
        elif isinstance(request, SnapshotComparisonRequest):
            result = await self._invoke_compare_snapshots(request, context_hint)
        else:
            raise TypeError(
                f"Unsupported request type: {type(request).__name__}. "
                f"Expected SignalReviewRequest, MacroSnapshotSummaryRequest, "
                f"or SnapshotComparisonRequest."
            )

        validate_runtime_result(result)

        if active_ctx is not None:
            params = _extract_parameters(request)
            active_ctx.add_turn(
                ConversationTurn(
                    request_type=type(request).__name__,
                    request_snapshot=request.model_dump(mode="json"),
                    response_summary=result.response.summary,
                    success=result.success,
                    active_parameters=params,
                )
            )

        return result

    # ------------------------------------------------------------------
    # Context resolution
    # ------------------------------------------------------------------

    def _resolve_context(self, request: AgentRequestInput) -> ConversationContext | None:
        """Return the active context for *request*, or ``None``.

        Resolution order:
        1. If the request has a non-empty ``session_id``, use (or create)
           the session-keyed context in the internal store.
        2. Otherwise fall back to the per-instance context (may be ``None``
           when ``enable_context=False``).
        """
        session_id = getattr(request, "session_id", None)
        if session_id:
            return self._session_store.get_or_create(
                session_id, max_turns=self._max_context_turns
            )
        return self._context

    # ------------------------------------------------------------------
    # Private dispatchers
    # ------------------------------------------------------------------

    async def _invoke_review_signals(
        self,
        request: SignalReviewRequest,
        context_hint: str,
    ) -> AgentRuntimeResult:
        _log.debug("dispatching_operation", operation="review_signals")
        response = await self._service.review_signals(request)
        if response.success:
            response = self._reformat_signal_review(response, request, context_hint)
        return AgentRuntimeResult(
            operation=AgentOperation.REVIEW_SIGNALS,
            response=response,
        )

    async def _invoke_summarize_snapshot(
        self,
        request: MacroSnapshotSummaryRequest,
        context_hint: str,
    ) -> AgentRuntimeResult:
        _log.debug("dispatching_operation", operation="summarize_macro_snapshot")
        response = await self._service.summarize_macro_snapshot(request)
        if response.success:
            response = self._reformat_snapshot_summary(response, context_hint)
        return AgentRuntimeResult(
            operation=AgentOperation.SUMMARIZE_MACRO_SNAPSHOT,
            response=response,
        )

    async def _invoke_compare_snapshots(
        self,
        request: SnapshotComparisonRequest,
        context_hint: str,
    ) -> AgentRuntimeResult:
        _log.debug("dispatching_operation", operation="compare_snapshots")
        response = await self._service.compare_snapshots(request)
        if response.success:
            response = self._reformat_comparison_summary(response, context_hint)
        return AgentRuntimeResult(
            operation=AgentOperation.COMPARE_SNAPSHOTS,
            response=response,
        )

    # ------------------------------------------------------------------
    # Prompt-driven reformatting
    # ------------------------------------------------------------------

    @staticmethod
    def _reformat_signal_review(
        response: SignalReviewResponse,
        request: SignalReviewRequest,
        context_hint: str = "",
    ) -> SignalReviewResponse:
        """Re-render the summary using the LangChain prompt template.

        All numeric / metadata fields are preserved; only ``summary`` is
        regenerated.  *context_hint* is appended to the system message when
        non-empty but never overrides the deterministic tool results.
        """
        from mcp.schemas.run_signal_engine import RunSignalEngineResponse

        engine_like = RunSignalEngineResponse(
            request_id=response.request_id,
            success=True,
            engine_run_id=response.engine_run_id,
            signals_generated=response.signals_generated,
            buy_signals=response.buy_signals,
            sell_signals=response.sell_signals,
            hold_signals=response.hold_signals,
            execution_time_ms=response.execution_time_ms,
        )
        dominance = dominant_signal_type(engine_like)

        new_summary = render_signal_review_summary(
            signal_ids=", ".join(request.signal_ids),
            country=request.country,
            signals_generated=response.signals_generated,
            buy_signals=response.buy_signals,
            sell_signals=response.sell_signals,
            hold_signals=response.hold_signals,
            dominant_direction=dominance,
            engine_run_id=response.engine_run_id,
            execution_time_ms=f"{response.execution_time_ms:.1f}",
            context_summary=context_hint,
        )

        return SignalReviewResponse(
            request_id=response.request_id,
            timestamp=response.timestamp,
            success=True,
            summary=new_summary,
            engine_run_id=response.engine_run_id,
            signals_generated=response.signals_generated,
            buy_signals=response.buy_signals,
            sell_signals=response.sell_signals,
            hold_signals=response.hold_signals,
            execution_time_ms=response.execution_time_ms,
        )

    @staticmethod
    def _reformat_snapshot_summary(
        response: MacroSnapshotSummaryResponse,
        context_hint: str = "",
    ) -> MacroSnapshotSummaryResponse:
        """Re-render the summary using the LangChain prompt template."""
        ts_str = (
            response.snapshot_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
            if response.snapshot_timestamp is not None
            else "unknown"
        )
        new_summary = render_snapshot_summary(
            country=response.country,
            features_count=response.features_count,
            snapshot_timestamp=ts_str,
            context_summary=context_hint,
        )
        return MacroSnapshotSummaryResponse(
            request_id=response.request_id,
            timestamp=response.timestamp,
            success=True,
            summary=new_summary,
            country=response.country,
            snapshot_timestamp=response.snapshot_timestamp,
            features_count=response.features_count,
        )


    @staticmethod
    def _reformat_comparison_summary(
        response: SnapshotComparisonResponse,
        context_hint: str = "",
    ) -> SnapshotComparisonResponse:
        """Re-render the comparison summary using the LangChain prompt template.

        All numeric / metadata fields are preserved; only ``summary`` is
        regenerated.  *context_hint* is appended to the system message when
        non-empty but never overrides the deterministic comparison results.
        """
        new_summary = render_snapshot_comparison_summary(
            country=response.country,
            prior_snapshot_label=response.prior_snapshot_label,
            changed_count=response.changed_count,
            unchanged_count=response.unchanged_count,
            no_prior_count=response.no_prior_count,
            context_summary=context_hint,
        )
        return SnapshotComparisonResponse(
            request_id=response.request_id,
            timestamp=response.timestamp,
            success=True,
            summary=new_summary,
            country=response.country,
            prior_snapshot_label=response.prior_snapshot_label,
            current_snapshot_timestamp=response.current_snapshot_timestamp,
            changed_count=response.changed_count,
            unchanged_count=response.unchanged_count,
            no_prior_count=response.no_prior_count,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_parameters(request: AgentRequestInput) -> AnalysisParameters:
    """Extract :class:`~agent.context.models.AnalysisParameters` from a request.

    Reads ``country`` from the request if present.  For
    :class:`~agent.schemas.SnapshotComparisonRequest`, also reads
    ``prior_snapshot_label`` as the ``comparison_target`` parameter.
    """
    country: str | None = getattr(request, "country", None)
    comparison_target: str | None = getattr(request, "prior_snapshot_label", None)
    return AnalysisParameters(country=country, comparison_target=comparison_target)

