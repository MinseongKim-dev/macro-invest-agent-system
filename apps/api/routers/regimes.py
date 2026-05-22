"""Regime read routes for the analyst-facing product API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import get_regime_service
from apps.api.dto.history import HistoricalRegimeDTO, RegimeHistoryResponse
from apps.api.dto.regimes import (
    RegimeCompareResponse,
    RegimeDeltaDTO,
    RegimeLatestResponse,
    RegimeTransitionDTO,
)
from src.domain.macro.change_detection import RegimeDelta, detect_regime_change
from src.domain.macro.history import (
    HistoricalRegimeRecord,
    build_regime_history_bundle,
)
from src.domain.macro.regime import MacroRegime, RegimeConfidence, RegimeLabel
from src.domain.macro.snapshot import DegradedStatus
from src.pipelines.ingestion.models import FreshnessStatus
from src.services.interfaces import RegimeServiceInterface

router = APIRouter(prefix="/api/regimes", tags=["regimes"])


def _compute_regime_status(regime: MacroRegime) -> str:
    """Derive a single product-surface status token from a regime object.

    Returns one of: ``'success'``, ``'degraded'``, ``'stale'``, ``'bootstrap'``.
    Priority order: bootstrap → stale → degraded → success.
    """
    if regime.metadata.get("seeded") == "true":
        return "bootstrap"
    if regime.freshness_status in {FreshnessStatus.STALE, FreshnessStatus.UNKNOWN}:
        return "stale"
    if (
        regime.degraded_status
        in {DegradedStatus.PARTIAL, DegradedStatus.MISSING, DegradedStatus.SOURCE_UNAVAILABLE}
        or regime.confidence == RegimeConfidence.LOW
        or regime.regime_label in {RegimeLabel.MIXED, RegimeLabel.UNCLEAR}
    ):
        return "degraded"
    return "success"


def _to_latest_response(regime: MacroRegime) -> RegimeLatestResponse:
    is_seeded = regime.metadata.get("seeded") == "true"
    data_source = regime.metadata.get("source", "")
    return RegimeLatestResponse(
        as_of_date=regime.as_of_date,
        regime_id=regime.regime_id,
        regime_timestamp=regime.regime_timestamp,
        regime_label=regime.regime_label.value,
        regime_family=regime.regime_family.value,
        confidence=regime.confidence.value,
        freshness_status=regime.freshness_status.value,
        degraded_status=regime.degraded_status.value,
        missing_inputs=list(regime.missing_inputs),
        supporting_snapshot_id=regime.supporting_snapshot_id,
        supporting_states=dict(regime.supporting_states),
        transition=RegimeTransitionDTO(
            transition_from_prior=regime.transition.transition_from_prior,
            transition_type=regime.transition.transition_type.value,
            changed=regime.transition.changed,
        ),
        rationale_summary=regime.rationale_summary,
        warnings=list(regime.warnings),
        status=_compute_regime_status(regime),
        is_seeded=is_seeded,
        data_source=data_source,
    )


def _delta_to_dto(delta: RegimeDelta) -> RegimeDeltaDTO:
    """Map a domain :class:`~domain.macro.change_detection.RegimeDelta` to :class:`RegimeDeltaDTO`."""
    return RegimeDeltaDTO(
        is_initial=delta.is_initial,
        label_changed=delta.label_changed,
        family_changed=delta.family_changed,
        confidence_changed=delta.confidence_changed,
        confidence_direction=delta.confidence_direction,
        severity=delta.severity,
        changed_dimensions=list(delta.changed_dimensions),
        prior_label=delta.prior_label,
        prior_family=delta.prior_family,
        prior_confidence=delta.prior_confidence,
        label_transition=delta.label_transition,
        confidence_transition=delta.confidence_transition,
        is_regime_transition=delta.is_regime_transition,
        notable_flags=list(delta.notable_flags),
        severity_rationale=delta.severity_rationale,
    )


def _historical_record_to_dto(record: HistoricalRegimeRecord) -> HistoricalRegimeDTO:
    """Convert a :class:`~domain.macro.history.HistoricalRegimeRecord` to DTO."""
    return HistoricalRegimeDTO(
        regime_id=record.regime_id,
        as_of_date=record.as_of_date,
        generated_at=record.generated_at,
        regime_label=record.regime_label,
        regime_family=record.regime_family,
        confidence=record.confidence,
        freshness_status=record.freshness_status,
        degraded_status=record.degraded_status,
        transition_type=record.transition_type,
        transition_from_prior=record.transition_from_prior,
        changed=record.changed,
        warnings=list(record.warnings),
        is_seeded=record.is_seeded,
        missing_inputs=list(record.missing_inputs),
        supporting_snapshot_id=record.supporting_snapshot_id,
    )


@router.get(
    "/latest",
    response_model=RegimeLatestResponse,
    summary="Get latest persisted macro regime",
)
async def get_latest_regime(
    as_of_date: date = Query(default_factory=date.today),
    regime_service: RegimeServiceInterface = Depends(get_regime_service),
) -> RegimeLatestResponse:
    try:
        regime = await regime_service.get_latest_regime(as_of_date=as_of_date)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if regime is None:
        raise HTTPException(status_code=404, detail="No persisted regime available")
    return _to_latest_response(regime)


@router.get(
    "/compare",
    response_model=RegimeCompareResponse,
    summary="Compare current regime against prior baseline",
    description=(
        "Compare the current macro regime against the prior baseline. "
        "The response includes a structured ``delta`` object from the Change Detection "
        "Engine v1 that classifies what changed (label, family, confidence), the "
        "direction of confidence change, and a heuristic severity rating "
        "(unchanged / minor / moderate / major). "
        "Severity is explicitly heuristic (v1) — see ``delta.severity_rationale``."
    ),
)
async def compare_regimes(
    as_of_date: date = Query(default_factory=date.today),
    regime_service: RegimeServiceInterface = Depends(get_regime_service),
) -> RegimeCompareResponse:
    try:
        current, previous = await regime_service.compare_latest_with_prior(as_of_date=as_of_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Run Change Detection Engine v1
    delta = detect_regime_change(current=current, previous=previous)
    delta_dto = _delta_to_dto(delta) if previous is not None else None

    return RegimeCompareResponse(
        as_of_date=current.as_of_date,
        baseline_available=previous is not None,
        current_regime_label=current.regime_label.value,
        prior_regime_label=previous.regime_label.value if previous is not None else None,
        transition_type=current.transition.transition_type.value,
        changed=current.transition.changed,
        current_confidence=current.confidence.value,
        prior_confidence=previous.confidence.value if previous is not None else None,
        current_rationale_summary=current.rationale_summary,
        warnings=list(current.warnings),
        is_seeded=current.metadata.get("seeded") == "true",
        delta=delta_dto,
    )


@router.get(
    "/history",
    response_model=RegimeHistoryResponse,
    summary="Retrieve recent regime history",
    description=(
        "Return up to *limit* persisted macro regimes on or before *as_of_date*, "
        "ordered most recent first. "
        "Each record carries full quality metadata (freshness, degraded status, "
        "confidence, warnings) so compare/trend surfaces can render context without "
        "re-deriving it. "
        "The ``latest_regime_id`` and ``previous_regime_id`` fields identify the two "
        "most recent entries, which the compare endpoint uses as its baseline pair."
    ),
)
async def get_regime_history(
    as_of_date: date = Query(default_factory=date.today),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of records to return"),
    regime_service: RegimeServiceInterface = Depends(get_regime_service),
) -> RegimeHistoryResponse:
    try:
        regimes = await regime_service.list_recent_regimes(as_of_date=as_of_date, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    bundle = build_regime_history_bundle(regimes=regimes, as_of_date=as_of_date)
    dtos = [_historical_record_to_dto(r) for r in bundle.records]

    return RegimeHistoryResponse(
        as_of_date=bundle.as_of_date,
        records=dtos,
        total=bundle.total,
        limit_applied=limit,
        latest_regime_id=bundle.latest.regime_id if bundle.latest else None,
        previous_regime_id=bundle.previous.regime_id if bundle.previous else None,
    )
