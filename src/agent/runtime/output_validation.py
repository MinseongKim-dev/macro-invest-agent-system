"""Output schema validation for the agent runtime boundary.

This module enforces that every value returned from the agent runtime is
schema-valid according to the existing Pydantic models.  Validation is applied
at the **final boundary** — after formatting and before the result is returned
to the caller — so that invalid outputs are caught regardless of how the
summary was produced (deterministic formatter, prompt template, or future LLM).

Design constraints
------------------
* Validation never modifies the response; it only raises on violations.
* Both success and failure responses must be schema-valid.
* The module does not import or depend on LangChain — it works with plain
  Pydantic models so it can be reused by any runtime implementation.
"""

from __future__ import annotations

from pydantic import ValidationError

from agent.runtime.agent_runtime import AgentRuntimeResult
from agent.schemas import (
    AgentResponse,
    MacroSnapshotSummaryResponse,
    SignalReviewResponse,
    SnapshotComparisonResponse,
)
from core.metrics import SCHEMA_VALIDATION_FAILURES_TOTAL


class OutputValidationError(Exception):
    """Raised when an agent output fails schema validation.

    Attributes:
        detail: Human-readable description of the validation failure.
        pydantic_error: The underlying Pydantic ``ValidationError``, if any.
    """

    def __init__(
        self,
        detail: str,
        pydantic_error: ValidationError | None = None,
    ) -> None:
        self.detail = detail
        self.pydantic_error = pydantic_error
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Response-level validation
# ---------------------------------------------------------------------------


def validate_agent_response(response: AgentResponse) -> AgentResponse:
    """Re-validate an agent response against its schema.

    Performs a ``model_dump → model_validate`` round-trip to ensure the
    response is fully schema-compliant.

    Args:
        response: Any :class:`~agent.schemas.AgentResponse` subclass.

    Returns:
        The original ``response`` if validation passes.

    Raises:
        OutputValidationError: If the response fails schema validation.
    """
    response_cls = type(response)
    try:
        response_cls.model_validate(response.model_dump())
    except ValidationError as exc:
        SCHEMA_VALIDATION_FAILURES_TOTAL.labels(response_type=response_cls.__name__).inc()
        raise OutputValidationError(
            detail=(
                f"Agent response failed schema validation (type={response_cls.__name__}): {exc}"
            ),
            pydantic_error=exc,
        ) from exc
    return response


def validate_signal_review_response(
    response: SignalReviewResponse,
) -> SignalReviewResponse:
    """Validate a :class:`~agent.schemas.SignalReviewResponse`.

    In addition to the generic round-trip, this checks domain invariants:

    * ``signals_generated == buy_signals + sell_signals + hold_signals``
      (on success only).

    Args:
        response: The signal review response to validate.

    Returns:
        The original ``response`` if validation passes.

    Raises:
        OutputValidationError: If any check fails.
    """
    validate_agent_response(response)

    if response.success:
        expected_total = response.buy_signals + response.sell_signals + response.hold_signals
        if response.signals_generated != expected_total:
            raise OutputValidationError(
                detail=(
                    f"signals_generated ({response.signals_generated}) does not equal "
                    f"buy + sell + hold ({expected_total})"
                ),
            )
    return response


def validate_snapshot_summary_response(
    response: MacroSnapshotSummaryResponse,
) -> MacroSnapshotSummaryResponse:
    """Validate a :class:`~agent.schemas.MacroSnapshotSummaryResponse`.

    Args:
        response: The snapshot summary response to validate.

    Returns:
        The original ``response`` if validation passes.

    Raises:
        OutputValidationError: If schema validation fails.
    """
    validate_agent_response(response)
    return response


def validate_snapshot_comparison_response(
    response: SnapshotComparisonResponse,
) -> SnapshotComparisonResponse:
    """Validate a :class:`~agent.schemas.SnapshotComparisonResponse`.

    In addition to the generic round-trip, this checks that change count
    fields are non-negative (enforced by the schema, but re-verified here
    for defence-in-depth).

    Args:
        response: The snapshot comparison response to validate.

    Returns:
        The original ``response`` if validation passes.

    Raises:
        OutputValidationError: If schema validation fails.
    """
    validate_agent_response(response)
    if response.success:
        for field_name in ("changed_count", "unchanged_count", "no_prior_count"):
            value = getattr(response, field_name)
            if value < 0:
                raise OutputValidationError(
                    detail=f"{field_name} must be >= 0, got {value}",
                )
    return response


# ---------------------------------------------------------------------------
# Runtime result validation
# ---------------------------------------------------------------------------


def validate_runtime_result(result: AgentRuntimeResult) -> AgentRuntimeResult:
    """Validate a complete :class:`AgentRuntimeResult`.

    Performs both the envelope-level and the inner-response-level validation.

    Args:
        result: The runtime result to validate.

    Returns:
        The original ``result`` if validation passes.

    Raises:
        OutputValidationError: If any check fails.
    """
    # Validate the envelope.
    try:
        AgentRuntimeResult.model_validate(result.model_dump())
    except ValidationError as exc:
        raise OutputValidationError(
            detail=f"AgentRuntimeResult failed schema validation: {exc}",
            pydantic_error=exc,
        ) from exc

    # Validate the inner response with type-specific checks.
    if isinstance(result.response, SignalReviewResponse):
        validate_signal_review_response(result.response)
    elif isinstance(result.response, MacroSnapshotSummaryResponse):
        validate_snapshot_summary_response(result.response)
    elif isinstance(result.response, SnapshotComparisonResponse):
        validate_snapshot_comparison_response(result.response)
    else:
        validate_agent_response(result.response)

    return result
