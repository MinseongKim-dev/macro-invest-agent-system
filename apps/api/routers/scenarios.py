"""What-if scenario routes for the analyst-facing product API.

Routes
------
``GET /api/scenarios/presets``
    Return the list of built-in named scenarios.

``POST /api/scenarios/run``
    Apply a what-if scenario against the current regime baseline and return
    the before/after synthesis comparison.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import get_regime_service
from apps.api.dto.scenarios import (
    ScenarioPreset,
    ScenarioPresetsResponse,
    ScenarioRunRequest,
    ScenarioRunResponse,
    SynthesisViewDTO,
    WhatIfResultDTO,
)
from src.domain.synthesis.engine import compute_synthesis_view
from src.domain.whatif.engine import compute_whatif_result
from src.domain.whatif.models import WhatIfScenario
from src.services.interfaces import RegimeServiceInterface

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

# ── Built-in preset scenarios ──────────────────────────────────────────────────

_PRESETS: list[ScenarioPreset] = [
    ScenarioPreset(
        id="goldilocks",
        label="골디락스",
        description="이상적인 성장·저인플레이션 환경",
        scenario=WhatIfScenario(
            label="골디락스",
            regime_label_override="expansion",
            macro_confidence_override=0.85,
            quant_support_override="strong_positive",
            conflict_status_override="low",
            avg_var_95_override=1.5,
            worst_mdd_pct_override=-8.0,
        ),
    ),
    ScenarioPreset(
        id="crisis",
        label="공황 리스크",
        description="VIX 급등 + 심각한 MDD",
        scenario=WhatIfScenario(
            label="공황 리스크",
            regime_label_override="contraction",
            macro_confidence_override=0.3,
            quant_support_override="strong_negative",
            conflict_status_override="high",
            avg_var_95_override=8.0,
            worst_mdd_pct_override=-45.0,
        ),
    ),
    ScenarioPreset(
        id="stagflation",
        label="스태그플레이션",
        description="고인플레이션 + 경기 침체 동시 발생",
        scenario=WhatIfScenario(
            label="스태그플레이션",
            regime_label_override="stagflation",
            macro_confidence_override=0.55,
            quant_support_override="moderate_negative",
            conflict_status_override="elevated",
            avg_var_95_override=4.5,
            worst_mdd_pct_override=-28.0,
        ),
    ),
    ScenarioPreset(
        id="fed_tightening",
        label="연준 긴축",
        description="금리 100bps 인상 — 긴축 레짐",
        scenario=WhatIfScenario(
            label="연준 긴축",
            regime_label_override="policy_tightening_drag",
            macro_confidence_override=0.6,
            quant_support_override="neutral",
            conflict_status_override="moderate",
            avg_var_95_override=3.2,
            worst_mdd_pct_override=-20.0,
        ),
    ),
    ScenarioPreset(
        id="soft_landing",
        label="소프트랜딩",
        description="점진적 금리 인하 + 경기 회복",
        scenario=WhatIfScenario(
            label="소프트랜딩",
            regime_label_override="recovery",
            macro_confidence_override=0.72,
            quant_support_override="moderate_positive",
            conflict_status_override="low",
            avg_var_95_override=2.0,
            worst_mdd_pct_override=-12.0,
        ),
    ),
]

_PRESET_MAP = {p.id: p for p in _PRESETS}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _overall_support_to_label(score: float) -> str:
    """Map Quant overall_support float [0,1] to synthesis-engine categorical label."""
    if score >= 0.65:
        return "strong_positive"
    if score >= 0.45:
        return "moderate_positive"
    if score >= 0.30:
        return "neutral"
    if score >= 0.15:
        return "moderate_negative"
    return "strong_negative"


def _to_synthesis_dto(view: object) -> SynthesisViewDTO:
    from src.domain.synthesis.models import SynthesisView  # noqa: PLC0415
    assert isinstance(view, SynthesisView)
    return SynthesisViewDTO(
        synthesis_status=view.synthesis_status.value,
        conviction_score=view.conviction_score,
        risk_penalty=view.risk_penalty,
        quant_support=view.quant_support,
        conflict_status=view.conflict_status,
        dominant_concern=view.dominant_concern,
        note=view.note,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get(
    "/presets",
    response_model=ScenarioPresetsResponse,
    summary="List built-in what-if scenario presets",
)
async def list_presets() -> ScenarioPresetsResponse:
    return ScenarioPresetsResponse(presets=_PRESETS)


@router.post(
    "/run",
    response_model=ScenarioRunResponse,
    summary="Run a what-if scenario against the current regime baseline",
)
async def run_scenario(
    body: ScenarioRunRequest,
    as_of_date: date = Query(default_factory=date.today),
    regime_service: RegimeServiceInterface = Depends(get_regime_service),
) -> ScenarioRunResponse:
    """Apply *body.scenario* on top of the current regime baseline.

    If *body.preset_id* is provided the matching built-in scenario is used
    and *body.scenario* is ignored.
    """
    # Resolve scenario — preset takes priority
    if body.preset_id:
        preset = _PRESET_MAP.get(body.preset_id)
        if preset is None:
            raise HTTPException(status_code=404, detail=f"Preset '{body.preset_id}' not found")
        scenario = preset.scenario
    elif body.scenario:
        scenario = body.scenario
    else:
        raise HTTPException(status_code=422, detail="Either preset_id or scenario must be provided")

    # Load current regime for baseline
    try:
        regime = await regime_service.get_latest_regime(as_of_date=as_of_date)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if regime is None:
        raise HTTPException(status_code=404, detail="No regime available to use as baseline")

    confidence_map = {"high": 0.85, "medium": 0.6, "low": 0.35}
    baseline_confidence = confidence_map.get(regime.confidence.value, 0.6)
    baseline_quant: str = (
        _overall_support_to_label(regime.quant_scores.overall_support)
        if regime.quant_scores
        else "no_data"
    )

    baseline = compute_synthesis_view(
        regime_label=regime.regime_label.value,
        macro_confidence=baseline_confidence,
        quant_overall_support=baseline_quant,
        conflict_status="low",
        avg_var_95=2.5,
        worst_mdd_pct=-15.0,
    )

    result = compute_whatif_result(
        scenario=scenario,
        baseline=baseline,
        regime_label=regime.regime_label.value,
        macro_confidence=baseline_confidence,
        quant_overall_support=baseline_quant,
        conflict_status="low",
        avg_var_95=2.5,
        worst_mdd_pct=-15.0,
    )

    return ScenarioRunResponse(
        result=WhatIfResultDTO(
            scenario_label=result.scenario_label,
            baseline=_to_synthesis_dto(result.baseline),
            projected=_to_synthesis_dto(result.projected),
            status_changed=result.status_changed,
            conviction_delta=result.conviction_delta,
        ),
        baseline_regime=regime.regime_label.value,
        baseline_confidence=baseline_confidence,
    )
