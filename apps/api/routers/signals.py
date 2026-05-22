"""Regime-grounded signal read routes for the analyst-facing product API.

Routes
------
``GET /api/signals/latest``
    Derive signals from the current persisted macro regime.  When a regime
    is available the response reflects regime-grounded investment signals
    with analyst-facing rationale.  When no regime is available the
    endpoint falls back to the experimental snapshot-based signal engine and
    marks the response as degraded.

Design constraints
------------------
* All routes are **read-only**.
* Signals are **regime-grounded** when a persisted regime is available.
* Trust metadata is always included in the response.
"""

from __future__ import annotations

import contextlib
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import (
    get_explanation_repository,
    get_macro_service,
    get_regime_service,
    get_signal_service,
)
from apps.api.dto.builders import build_trust_from_signal_result, signal_output_to_dto
from apps.api.dto.signals import SignalsLatestResponse
from apps.api.dto.trust import DataAvailability, FreshnessStatus, TrustMetadata
from apps.api.routers.explanations import build_and_register_explanation
from src.core.storage.repositories.explanation_repository import ExplanationRepositoryInterface
from src.domain.signals.registry import default_registry
from src.services.interfaces import (
    MacroServiceInterface,
    RegimeServiceInterface,
    SignalServiceInterface,
)
from src.services.signal_service import SignalService

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get(
    "/latest",
    response_model=SignalsLatestResponse,
    summary="Get latest regime-grounded signal evaluations",
    description=(
        "Derive investment signals from the current persisted macro regime. "
        "When a regime is available all signals are grounded in the regime label "
        "with analyst-facing rationale.  When no regime is persisted yet the endpoint "
        "falls back to the snapshot-based experimental engine and marks the result as "
        "degraded.  The response includes per-signal type, strength, score, trend, "
        "rationale, and trust metadata."
    ),
)
async def get_latest_signals(
    country: str = Query(default="US", description="ISO 3166-1 alpha-2 country code"),
    signal_ids: list[str] | None = Query(
        default=None,
        description=(
            "Optional filter: comma-separated list of signal IDs to return. "
            "Only applies to the fallback snapshot-based path."
        ),
    ),
    macro_service: MacroServiceInterface = Depends(get_macro_service),
    signal_service: SignalServiceInterface = Depends(get_signal_service),
    regime_service: RegimeServiceInterface = Depends(get_regime_service),
    explanation_repository: ExplanationRepositoryInterface = Depends(get_explanation_repository),
) -> SignalsLatestResponse:
    """Return latest regime-grounded signals for *country*.

    Attempts to load the latest persisted regime and derive signals from it.
    Falls back to the experimental snapshot-based engine when no regime is
    available.
    """
    # --- Attempt regime-grounded path ---
    regime = None
    with contextlib.suppress(Exception):
        regime = await regime_service.get_latest_regime(as_of_date=date.today())

    if regime is not None and isinstance(signal_service, SignalService):
        result = await signal_service.run_regime_grounded_engine(regime)

        signals_dtos = [signal_output_to_dto(s) for s in result.signals]
        trust = build_trust_from_signal_result(result)

        # Determine response status based on regime state
        any_degraded = any(s.is_degraded for s in result.signals)
        if any_degraded:
            response_status = "degraded"
        elif not signals_dtos:
            response_status = "empty"
        else:
            response_status = "success"

        for signal in result.signals:
            signal_rationale_points = [
                f"Regime: {regime.regime_label.value} ({regime.regime_family.value})",
                f"Confidence: {regime.confidence.value}",
                f"Asset class: {signal.asset_class or 'all'}",
                f"Signal direction: {signal.signal_type}",
                f"Strength: {signal.strength}",
                f"Score: {signal.score:.2f}",
            ]
            if signal.supporting_drivers:
                signal_rationale_points.append(
                    f"Supporting drivers: {', '.join(signal.supporting_drivers)}"
                )
            if signal.conflicting_drivers:
                signal_rationale_points.append(
                    f"Conflicting drivers: {', '.join(signal.conflicting_drivers)}"
                )
            if signal.caveat:
                signal_rationale_points.append(f"Caveat: {signal.caveat}")

            # Propagate conflict surface fields if available
            sig_conflict_status = "clean"
            sig_conflict_note = None
            sig_quant_support = "unknown"
            if signal.conflict is not None:
                sig_conflict_status = signal.conflict.conflict_status.value
                sig_conflict_note = signal.conflict.conflict_note
                sig_quant_support = signal.conflict.quant_support_level

            build_and_register_explanation(
                run_id=result.run_id,
                signal_id=signal.signal_id,
                summary=signal.rationale or f"Signal {signal.signal_id} evaluated successfully.",
                rationale_points=signal_rationale_points,
                repository=explanation_repository,
                regime_label=regime.regime_label.value,
                regime_context={
                    "label": regime.regime_label.value,
                    "family": regime.regime_family.value,
                    "confidence": regime.confidence.value,
                    "transition": regime.transition.transition_type.value,
                    "freshness": regime.freshness_status.value,
                    "degraded_status": regime.degraded_status.value,
                },
                conflict_status=sig_conflict_status,
                conflict_note=sig_conflict_note,
                quant_support_level=sig_quant_support,
            )

        strongest = result.strongest_signal()
        strongest_id = strongest.signal_id if strongest else None
        buy_count = sum(1 for s in result.signals if str(s.signal_type) == "buy")
        sell_count = sum(1 for s in result.signals if str(s.signal_type) == "sell")
        hold_count = sum(1 for s in result.signals if str(s.signal_type) == "hold")

        return SignalsLatestResponse(
            country=country,
            run_id=result.run_id,
            signals=signals_dtos,
            signals_count=len(signals_dtos),
            buy_count=buy_count,
            sell_count=sell_count,
            hold_count=hold_count,
            strongest_signal_id=strongest_id,
            trust=trust,
            regime_label=regime.regime_label.value,
            as_of_date=regime.as_of_date.isoformat(),
            is_regime_grounded=True,
            status=response_status,
        )

    # --- Fallback: experimental snapshot-based engine ---
    registry = default_registry
    if signal_ids:
        definitions = []
        missing = []
        for sid in signal_ids:
            try:
                defn = registry.get(sid)
                definitions.append(defn)
            except KeyError:
                missing.append(sid)
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown signal IDs: {missing}. Available: {registry.list_ids()}",
            )
    else:
        definitions = [registry.get(sid) for sid in registry.list_ids()]

    if not definitions:
        # No signal definitions registered — the registry itself is empty.
        # This is distinct from a successful fallback run that produced zero signals,
        # so "empty" is the correct status rather than "fallback".
        return SignalsLatestResponse(
            country=country,
            run_id="",
            signals=[],
            signals_count=0,
            buy_count=0,
            sell_count=0,
            hold_count=0,
            strongest_signal_id=None,
            trust=TrustMetadata(
                freshness_status=FreshnessStatus.UNKNOWN,
                availability=DataAvailability.UNAVAILABLE,
                is_degraded=True,
            ),
            is_regime_grounded=False,
            status="empty",
        )

    try:
        snapshot = await macro_service.get_snapshot(country=country)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Macro data service unavailable: {exc}",
        ) from exc

    try:
        result = await signal_service.run_engine(
            signal_definitions=definitions,
            snapshot=snapshot,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Signal engine error: {exc}",
        ) from exc

    signals_dtos = [signal_output_to_dto(s) for s in result.signals]
    trust = build_trust_from_signal_result(result)
    # Mark as degraded since we're running without a persisted regime
    trust = trust.model_copy(update={
        "is_degraded": True,
        "availability": DataAvailability.DEGRADED,
        "degraded_reason": "regime_unavailable_fallback_engine_used",
    })

    if result.signals:
        for signal in result.signals:
            rationale_points = [
                "Fallback: no persisted regime available",
                f"signal_type={signal.signal_type}",
                f"strength={signal.strength}",
                f"score={signal.score:.3f}",
                f"rules_passed={sum(1 for passed in signal.rule_results.values() if passed)}/{len(signal.rule_results)}",
            ]
            build_and_register_explanation(
                run_id=result.run_id,
                signal_id=signal.signal_id,
                summary=signal.rationale or f"Signal {signal.signal_id} evaluated (degraded).",
                rationale_points=rationale_points,
                repository=explanation_repository,
            )
    else:
        build_and_register_explanation(
            run_id=result.run_id,
            signal_id=None,
            summary=f"No signals generated for country={country}. No regime available.",
            rationale_points=["The signal engine completed with an empty result set (no regime)."],
            repository=explanation_repository,
        )

    strongest = result.strongest_signal()
    strongest_id = strongest.signal_id if strongest else None
    buy_count = sum(1 for s in result.signals if str(s.signal_type) == "buy")
    sell_count = sum(1 for s in result.signals if str(s.signal_type) == "sell")
    hold_count = sum(1 for s in result.signals if str(s.signal_type) == "hold")

    return SignalsLatestResponse(
        country=country,
        run_id=result.run_id,
        signals=signals_dtos,
        signals_count=len(signals_dtos),
        buy_count=buy_count,
        sell_count=sell_count,
        hold_count=hold_count,
        strongest_signal_id=strongest_id,
        trust=trust,
        is_regime_grounded=False,
        status="fallback",
    )
