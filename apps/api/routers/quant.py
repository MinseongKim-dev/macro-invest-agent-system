"""Quant Score read routes for the analyst-facing product API.

Routes
------
``GET /api/quant/latest``
    Return the Quant Scoring Engine v1 bundle attached to the latest
    persisted macro regime.

Design constraints
------------------
* Read-only.
* Quant scores are sourced from the same persisted regime used by
  ``/api/regimes/latest`` — no independent recomputation, so the scores
  returned here never drift from the ones that actually informed regime
  confidence.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import get_regime_service
from apps.api.dto.quant import DimensionScoreDTO, QuantScoreLatestResponse
from apps.api.routers.regimes import _compute_regime_status
from src.domain.macro.regime import MacroRegime
from src.domain.quant.models import DimensionScore
from src.services.interfaces import RegimeServiceInterface

router = APIRouter(prefix="/api/quant", tags=["quant"])


def _dimension_to_dto(dimension_score: DimensionScore) -> DimensionScoreDTO:
    return DimensionScoreDTO(
        dimension=dimension_score.dimension.value,
        score=dimension_score.score,
        level=dimension_score.level.value,
        contributing_states=list(dimension_score.contributing_states),
    )


@router.get(
    "/latest",
    response_model=QuantScoreLatestResponse,
    summary="Get latest quant score bundle",
    description=(
        "Return the Quant Scoring Engine v1 output (per-dimension scores plus "
        "momentum/breadth/change_intensity/overall_support) attached to the "
        "latest persisted macro regime."
    ),
)
async def get_latest_quant_scores(
    as_of_date: date = Query(default_factory=date.today),
    regime_service: RegimeServiceInterface = Depends(get_regime_service),
) -> QuantScoreLatestResponse:
    try:
        regime: MacroRegime | None = await regime_service.get_latest_regime(as_of_date=as_of_date)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if regime is None:
        raise HTTPException(status_code=404, detail="No persisted regime available")
    if regime.quant_scores is None:
        raise HTTPException(
            status_code=404, detail="No quant scores available for the latest regime"
        )

    bundle = regime.quant_scores
    return QuantScoreLatestResponse(
        as_of_date=regime.as_of_date,
        regime_id=regime.regime_id,
        regime_label=regime.regime_label.value,
        growth=_dimension_to_dto(bundle.growth),
        inflation=_dimension_to_dto(bundle.inflation),
        labor=_dimension_to_dto(bundle.labor),
        policy=_dimension_to_dto(bundle.policy),
        financial_conditions=_dimension_to_dto(bundle.financial_conditions),
        momentum=bundle.momentum,
        breadth=bundle.breadth,
        change_intensity=bundle.change_intensity,
        overall_support=bundle.overall_support,
        status=_compute_regime_status(regime),
    )
