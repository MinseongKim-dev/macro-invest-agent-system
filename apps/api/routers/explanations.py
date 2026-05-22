"""Explanation read routes for the analyst-facing product API.

Routes
------
``GET /api/explanations/regime/latest``
    Return an analyst-facing narrative explanation for the current macro regime.
    Grounded in the persisted regime label, supporting states, confidence, and
    transition.  Includes the full v2 reasoning chain, conflict surface, and
    analyst workflow DTO.

``GET /api/explanations/run/{run_id}``
    Return all explanations associated with a signal engine run.

``GET /api/explanations/{id}``
    Retrieve the explanation associated with a signal engine run or snapshot
    context identified by *id*.

Design notes
------------
* Regime-level explanations are built deterministically from the persisted
  regime using :func:`~domain.macro.narrative_builder.build_regime_narrative`.
* The v2 reasoning chain and analyst workflow are populated by
  :func:`~apps.api.dto.builders.build_reasoning_chain` and
  :func:`~apps.api.dto.builders.build_analyst_workflow`.
* Explanation persistence uses the injected
  :class:`~storage.repositories.explanation_repository.ExplanationRepositoryInterface`.
* Trust metadata marks the explanation as fresh when the run is found.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path

from apps.api.dependencies import get_explanation_repository, get_regime_service
from apps.api.dto.builders import (
    build_analyst_workflow,
    build_reasoning_chain,
    build_what_changed,
)
from apps.api.dto.explanations import ExplanationResponse
from apps.api.dto.trust import DataAvailability, FreshnessStatus, TrustMetadata
from src.domain.macro.narrative_builder import RegimeNarrative, build_regime_narrative
from src.pipelines.ingestion.models import FreshnessStatus as PipelineFreshnessStatus
from src.services.interfaces import RegimeServiceInterface
from src.core.storage.repositories.explanation_repository import ExplanationRepositoryInterface

router = APIRouter(prefix="/api/explanations", tags=["explanations"])


# ---------------------------------------------------------------------------
# Helpers — called by both route handlers and the signals router
# ---------------------------------------------------------------------------


def register_explanation(
    explanation: ExplanationResponse,
    repository: ExplanationRepositoryInterface,
) -> None:
    """Persist *explanation* in the given repository.

    Called by the signals router (or tests) after a run completes so that
    ``GET /api/explanations/{id}`` can retrieve it.
    """
    repository.save(explanation)


def clear_explanation_store(
    repository: ExplanationRepositoryInterface | None = None,
) -> None:
    """Clear the explanation store.  Used in tests.

    When *repository* is ``None`` the function is a no-op (provided for
    backward compatibility with tests that call it before DI is configured).
    """
    if repository is not None:
        repository.clear()


# ---------------------------------------------------------------------------
# Route: GET /api/explanations/regime/latest
# ---------------------------------------------------------------------------


@router.get(
    "/regime/latest",
    response_model=ExplanationResponse,
    summary="Get analyst narrative for the current macro regime",
    description=(
        "Return a structured analyst-facing narrative explanation for the current "
        "persisted macro regime.  The explanation includes a concise summary paragraph, "
        "supporting rationale bullet points (regime label, supporting states, confidence, "
        "freshness, transition), the v2 reasoning chain (6 ordered steps: current_state → "
        "why → confidence → conflict → caveats → what_changed), and the analyst workflow DTO. "
        "Returns 404 when no persisted regime is available."
    ),
)
async def get_regime_explanation(
    regime_service: RegimeServiceInterface = Depends(get_regime_service),
    repository: ExplanationRepositoryInterface = Depends(get_explanation_repository),
) -> ExplanationResponse:
    """Build and return an analyst narrative for the latest persisted regime."""
    from datetime import date

    try:
        regime = await regime_service.get_latest_regime(as_of_date=date.today())
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if regime is None:
        raise HTTPException(
            status_code=404,
            detail="No persisted regime available for narrative explanation.",
        )

    narrative: RegimeNarrative = build_regime_narrative(regime)

    is_degraded = regime.freshness_status in {
        PipelineFreshnessStatus.STALE,
        PipelineFreshnessStatus.UNKNOWN,
    } or str(regime.degraded_status) not in {"none", "DegradedStatus.NONE"}
    availability = (
        DataAvailability.PARTIAL
        if str(regime.degraded_status)
        not in {"none", "DegradedStatus.NONE", "DegradedStatus.UNKNOWN"}
        else DataAvailability.FULL
    )

    # Derive conflict surface from quant scores if available
    conflict_status = "clean"
    conflict_note = None
    quant_support_level = "unknown"
    if regime.quant_scores is not None:
        from src.domain.signals.conflict import _quant_support_label

        quant_support_level = _quant_support_label(regime.quant_scores.overall_support)
        if regime.quant_scores.overall_support < 0.35:
            conflict_status = "low_conviction"
            conflict_note = (
                f"Quant support is very weak ({quant_support_level}). "
                "Regime may not be backed by sufficient macroeconomic evidence."
            )
        elif regime.quant_scores.overall_support < 0.40:
            conflict_status = "tension"
            conflict_note = (
                f"Quant support is moderate ({quant_support_level}). "
                "Some analytical uncertainty in the current classification."
            )

    # Build v2 reasoning chain and analyst workflow
    reasoning_chain = build_reasoning_chain(
        narrative=narrative,
        conflict_status=conflict_status,
        conflict_note=conflict_note,
        quant_support_level=quant_support_level,
    )
    analyst_workflow = build_analyst_workflow(reasoning_chain)
    what_changed = build_what_changed(narrative)

    explanation = ExplanationResponse(
        explanation_id=f"regime:{regime.regime_id}",
        run_id=regime.regime_id,
        signal_id=None,
        summary=narrative["summary"],
        rationale_points=narrative["rationale_points"],
        caveats=narrative["caveats"],
        data_quality_notes=narrative["data_quality_notes"],
        regime_label=narrative["regime_label"],
        regime_context=narrative["regime_context"],
        reasoning_chain=reasoning_chain,
        what_changed=what_changed,
        analyst_workflow=analyst_workflow,
        conflict_status=conflict_status,
        conflict_note=conflict_note,
        quant_support_level=quant_support_level,
        generated_at=datetime.now(UTC),
        trust=TrustMetadata(
            freshness_status=FreshnessStatus(regime.freshness_status.value),
            availability=availability,
            is_degraded=is_degraded,
        ),
    )
    repository.save(explanation)
    return explanation


# ---------------------------------------------------------------------------
# Route: GET /api/explanations/run/{run_id}
# ---------------------------------------------------------------------------


@router.get(
    "/run/{run_id}",
    response_model=list[ExplanationResponse],
    summary="List all explanations for a signal run",
    description=(
        "Return all explanation objects associated with the given signal engine run ID. "
        "Explanations are ordered by generation time (oldest first). "
        "Returns an empty list when no explanations are found for the given run."
    ),
)
async def list_explanations_by_run(
    run_id: str = Path(..., description="Signal engine run identifier"),
    repository: ExplanationRepositoryInterface = Depends(get_explanation_repository),
) -> list[ExplanationResponse]:
    """Return all explanations for *run_id*, ordered by ``generated_at``."""
    return repository.list_by_run_id(run_id)


# ---------------------------------------------------------------------------
# Route: GET /api/explanations/{explanation_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{explanation_id}",
    response_model=ExplanationResponse,
    summary="Get explanation by ID",
    description=(
        "Retrieve the explanation associated with a signal engine run or snapshot "
        "context. The explanation includes a short summary, supporting rationale "
        "bullet points, and trust metadata. Returns 404 if not found."
    ),
)
async def get_explanation(
    explanation_id: str = Path(
        ...,
        description="Explanation ID (typically the signal engine run_id or composite ID)",
    ),
    repository: ExplanationRepositoryInterface = Depends(get_explanation_repository),
) -> ExplanationResponse:
    """Retrieve an explanation by *explanation_id*."""
    explanation = repository.get_by_id(explanation_id)
    if explanation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Explanation '{explanation_id}' not found.",
        )
    return explanation


# ---------------------------------------------------------------------------
# Built-in explanation builder — creates a deterministic explanation from a
# signal summary text and associates it with a run_id.
# ---------------------------------------------------------------------------


def build_and_register_explanation(
    run_id: str,
    signal_id: str | None,
    summary: str,
    rationale_points: list[str],
    repository: ExplanationRepositoryInterface,
    regime_label: str | None = None,
    regime_context: dict[str, str] | None = None,
    conflict_status: str = "clean",
    conflict_note: str | None = None,
    quant_support_level: str = "unknown",
) -> ExplanationResponse:
    """Build and store a deterministic explanation for a signal run.

    Args:
        run_id: The signal engine run identifier.
        signal_id: The specific signal; ``None`` for run-level explanations.
        summary: Short summary text.
        rationale_points: Supporting bullet points.
        repository: The explanation repository to persist into.
        regime_label: Optional regime label this explanation is grounded in.
        regime_context: Optional regime context dict for UI rendering.
        conflict_status: Conflict/conviction status from ConflictSurface.
        conflict_note: Analyst-facing conflict explanation.
        quant_support_level: Quant support level label.

    Returns:
        The newly created and registered :class:`ExplanationResponse`.
    """
    explanation_id = f"{run_id}:{signal_id}" if signal_id else run_id
    explanation = ExplanationResponse(
        explanation_id=explanation_id,
        run_id=run_id,
        signal_id=signal_id,
        summary=summary,
        rationale_points=rationale_points,
        regime_label=regime_label,
        regime_context=regime_context or {},
        conflict_status=conflict_status,
        conflict_note=conflict_note,
        quant_support_level=quant_support_level,
        generated_at=datetime.now(UTC),
        trust=TrustMetadata(
            freshness_status=FreshnessStatus.FRESH,
            availability=DataAvailability.FULL,
            is_degraded=False,
        ),
    )
    repository.save(explanation)
    return explanation
