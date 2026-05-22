"""Lightweight runtime adapter for the agent layer.

This module provides :class:`AgentRuntime` — a thin wrapper around
:class:`~agent.service.AgentService` that:

* Exposes a single ``invoke`` entry-point for dispatching agent operations.
* Returns a normalised :class:`AgentRuntimeResult` with a typed ``operation``
  label so callers can route on the response without inspecting free-form text.
* Acts as the **future integration point for LangChain / LangGraph** — when
  that integration is needed, the runtime can be subclassed or replaced without
  touching the service or MCP adapter layers.

Design constraints
------------------
* The runtime is **read-only** — it only dispatches to read-only service
  methods.
* The runtime is **stateless** — no memory or session state is stored between
  calls.
* The runtime does **not** call any LLM in the current implementation.
* Every ``invoke`` call returns a schema-valid :class:`AgentRuntimeResult`
  regardless of success or failure.
"""

from __future__ import annotations

import time
from enum import StrEnum

from pydantic import BaseModel, Field

from agent.schemas import (
    AgentResponse,
    MacroSnapshotSummaryRequest,
    MacroSnapshotSummaryResponse,
    SignalReviewRequest,
    SignalReviewResponse,
    SnapshotComparisonRequest,
    SnapshotComparisonResponse,
)
from agent.service import AgentService
from core.logging.logger import bind_request_context, get_logger, set_trace_id
from core.logging.timing import timed_operation
from core.metrics import AGENT_REQUEST_DURATION, AGENT_REQUESTS_TOTAL
from core.tracing import get_tracer
from core.tracing.span_attributes import (
    AGENT_OPERATION,
    REQUEST_ID,
    RESULT_SUCCESS,
    SESSION_ID,
)

_log = get_logger(__name__)
_tracer = get_tracer(__name__)

# ---------------------------------------------------------------------------
# Operation registry
# ---------------------------------------------------------------------------


class AgentOperation(StrEnum):
    """Enumeration of supported agent runtime operations.

    Each value corresponds to a method on :class:`~agent.service.AgentService`.
    """

    REVIEW_SIGNALS = "review_signals"
    SUMMARIZE_MACRO_SNAPSHOT = "summarize_macro_snapshot"
    COMPARE_SNAPSHOTS = "compare_snapshots"


# ---------------------------------------------------------------------------
# Runtime result
# ---------------------------------------------------------------------------


class AgentRuntimeResult(BaseModel, extra="forbid"):
    """Normalised result envelope returned by :class:`AgentRuntime.invoke`.

    Wraps an :class:`~agent.schemas.AgentResponse` subclass with a typed
    ``operation`` label so downstream code can dispatch on the operation
    without inspecting the response payload.

    Attributes:
        operation: The operation that was executed.
        response: The schema-validated agent response for that operation.
    """

    operation: AgentOperation = Field(
        ...,
        description="Agent operation that was executed",
    )
    response: SignalReviewResponse | MacroSnapshotSummaryResponse | SnapshotComparisonResponse = Field(
        ...,
        description="Schema-validated agent response",
    )

    @property
    def success(self) -> bool:
        """Convenience proxy — ``True`` iff the wrapped response succeeded."""
        return self.response.success

    @property
    def error_message(self) -> str | None:
        """Convenience proxy — error message from the wrapped response."""
        return self.response.error_message


# ---------------------------------------------------------------------------
# AgentRuntime
# ---------------------------------------------------------------------------

# Supported request type union
AgentRequestInput = SignalReviewRequest | MacroSnapshotSummaryRequest | SnapshotComparisonRequest


class AgentRuntime:
    """Lightweight runtime adapter over :class:`~agent.service.AgentService`.

    Provides a single :meth:`invoke` entry-point that accepts any supported
    agent request and returns a typed :class:`AgentRuntimeResult`.

    This class is the **recommended integration point** for future
    LangChain / LangGraph wiring.  A subclass can override :meth:`invoke` to
    inject chain-of-thought reasoning, tool selection, or memory while keeping
    the underlying service and MCP layers unchanged.

    Args:
        service: The :class:`~agent.service.AgentService` instance to delegate
            operations to.

    Example::

        from agent.runtime.agent_runtime import AgentRuntime, AgentOperation
        from agent.schemas import SignalReviewRequest
        from agent.service import AgentService
        from services.macro_service import MacroService
        from services.signal_service import SignalService

        runtime = AgentRuntime(AgentService(MacroService(), SignalService()))
        result = await runtime.invoke(
            SignalReviewRequest(request_id="req-001", signal_ids=["bull_market"])
        )
        if result.success:
            print(result.response.summary)
    """

    def __init__(self, service: AgentService) -> None:
        self._service = service

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    async def invoke(self, request: AgentRequestInput) -> AgentRuntimeResult:
        """Dispatch an agent request and return a normalised runtime result.

        The operation is inferred from the request type:

        * :class:`~agent.schemas.SignalReviewRequest` → ``review_signals``
        * :class:`~agent.schemas.MacroSnapshotSummaryRequest` →
          ``summarize_macro_snapshot``
        * :class:`~agent.schemas.SnapshotComparisonRequest` →
          ``compare_snapshots``

        A fresh trace ID is generated for every ``invoke`` call (unless one
        is already set).  The ``request_id`` and optional ``session_id`` are
        bound into the structlog context so they appear on all downstream log
        records for the same async task.

        Args:
            request: A validated agent request (
                :class:`~agent.schemas.SignalReviewRequest`,
                :class:`~agent.schemas.MacroSnapshotSummaryRequest`, or
                :class:`~agent.schemas.SnapshotComparisonRequest`).

        Returns:
            :class:`AgentRuntimeResult` wrapping the schema-validated response.
            The ``success`` property reflects whether the underlying operation
            succeeded.

        Raises:
            TypeError: If an unsupported request type is passed.  Callers
                should only pass the supported union types documented above.
        """
        # Validate request type before accessing its attributes.
        if not isinstance(request, (SignalReviewRequest, MacroSnapshotSummaryRequest, SnapshotComparisonRequest)):
            raise TypeError(
                f"Unsupported request type: {type(request).__name__}. "
                f"Expected SignalReviewRequest, MacroSnapshotSummaryRequest, "
                f"or SnapshotComparisonRequest."
            )

        bind_request_context(
            request_id=request.request_id,
            trace_id=set_trace_id(),
            session_id=getattr(request, "session_id", None),
        )
        _log.info("request_started", request_type=type(request).__name__)

        operation = (
            AgentOperation.REVIEW_SIGNALS
            if isinstance(request, SignalReviewRequest)
            else AgentOperation.SUMMARIZE_MACRO_SNAPSHOT
            if isinstance(request, MacroSnapshotSummaryRequest)
            else AgentOperation.COMPARE_SNAPSHOTS
        )

        with _tracer.start_as_current_span("agent.invoke") as span:
            span.set_attribute(REQUEST_ID, request.request_id)
            span.set_attribute(AGENT_OPERATION, operation.value)
            session_id = getattr(request, "session_id", None) or ""
            if session_id:
                span.set_attribute(SESSION_ID, session_id)

            _start = time.perf_counter()
            try:
                if isinstance(request, SignalReviewRequest):
                    result = await self._invoke_review_signals(request)
                elif isinstance(request, MacroSnapshotSummaryRequest):
                    result = await self._invoke_summarize_snapshot(request)
                else:
                    result = await self._invoke_compare_snapshots(request)
            except Exception:
                AGENT_REQUEST_DURATION.labels(operation=operation.value).observe(
                    time.perf_counter() - _start
                )
                AGENT_REQUESTS_TOTAL.labels(operation=operation.value, result="failure").inc()
                raise

            AGENT_REQUEST_DURATION.labels(operation=operation.value).observe(
                time.perf_counter() - _start
            )
            AGENT_REQUESTS_TOTAL.labels(
                operation=operation.value,
                result="success" if result.success else "failure",
            ).inc()

            span.set_attribute(RESULT_SUCCESS, result.success)

        _log.info(
            "request_completed",
            request_type=type(request).__name__,
            success=result.success,
        )
        return result

    # ------------------------------------------------------------------
    # Private dispatchers
    # ------------------------------------------------------------------

    async def _invoke_review_signals(
        self, request: SignalReviewRequest
    ) -> AgentRuntimeResult:
        async with timed_operation("runtime", "review_signals", _log):
            _log.debug("dispatching_operation", operation="review_signals")
            response: AgentResponse = await self._service.review_signals(request)
        return AgentRuntimeResult(
            operation=AgentOperation.REVIEW_SIGNALS,
            response=response,  # type: ignore[arg-type]
        )

    async def _invoke_summarize_snapshot(
        self, request: MacroSnapshotSummaryRequest
    ) -> AgentRuntimeResult:
        async with timed_operation("runtime", "summarize_macro_snapshot", _log):
            _log.debug("dispatching_operation", operation="summarize_macro_snapshot")
            response: AgentResponse = await self._service.summarize_macro_snapshot(request)
        return AgentRuntimeResult(
            operation=AgentOperation.SUMMARIZE_MACRO_SNAPSHOT,
            response=response,  # type: ignore[arg-type]
        )

    async def _invoke_compare_snapshots(
        self, request: SnapshotComparisonRequest
    ) -> AgentRuntimeResult:
        async with timed_operation("runtime", "compare_snapshots", _log):
            _log.debug("dispatching_operation", operation="compare_snapshots")
            response: AgentResponse = await self._service.compare_snapshots(request)
        return AgentRuntimeResult(
            operation=AgentOperation.COMPARE_SNAPSHOTS,
            response=response,  # type: ignore[arg-type]
        )
