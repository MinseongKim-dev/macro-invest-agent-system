"""Snapshot read routes for the analyst-facing product API.

Routes
------
``GET /api/snapshots/latest``
    Return the latest macro observation table for a given country.

``POST /api/snapshots/compare``
    Compare the current macro observation table against provided prior values.

Design constraints
------------------
* All routes are **read-only** — no writes or mutations.
* Deterministic domain outputs are the authoritative source.
* Agent-generated text is not exposed here; summaries are deterministic.
* Trust metadata is always included in the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import get_macro_service
from apps.api.dto.builders import (
    build_trust_from_comparison,
    build_trust_from_snapshot,
    delta_to_dto,
    feature_to_dto,
)
from apps.api.dto.snapshots import (
    SnapshotCompareRequest,
    SnapshotCompareResponse,
    SnapshotLatestResponse,
)
from src.domain.macro.comparison import PriorFeatureInput, compare_snapshots
from src.services.interfaces import MacroServiceInterface

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get(
    "/latest",
    response_model=SnapshotLatestResponse,
    summary="Get latest macro observations",
    description=(
        "Return the latest macroeconomic observation table for a given country. "
        "The response includes all available indicator values and trust metadata "
        "(freshness, source attribution, availability)."
    ),
)
async def get_latest_snapshot(
    country: str = Query(default="US", description="ISO 3166-1 alpha-2 country code"),
    macro_service: MacroServiceInterface = Depends(get_macro_service),
) -> SnapshotLatestResponse:
    """Retrieve the latest macro observation table for *country*.

    Returns HTTP 200 with :class:`~apps.api.dto.snapshots.SnapshotLatestResponse`
    on success, or HTTP 502 if the macro service cannot be reached.
    """
    try:
        snapshot = await macro_service.get_snapshot(country=country)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Macro data service unavailable: {exc}",
        ) from exc

    features = [feature_to_dto(f) for f in snapshot.features]
    trust = build_trust_from_snapshot(snapshot)

    return SnapshotLatestResponse(
        country=country,
        features=features,
        features_count=len(features),
        trust=trust,
    )


@router.post(
    "/compare",
    response_model=SnapshotCompareResponse,
    summary="Compare current vs prior macro observations",
    description=(
        "Compare the current macro observation table for a given country against a set of "
        "prior indicator values supplied by the caller. Returns per-indicator deltas "
        "with direction (increased/decreased/unchanged/no_prior), before/after values, "
        "and trust metadata. Useful for rendering comparison cards and change tables."
    ),
)
async def compare_snapshot(
    body: SnapshotCompareRequest,
    macro_service: MacroServiceInterface = Depends(get_macro_service),
) -> SnapshotCompareResponse:
    """Compare the current snapshot against caller-supplied prior values.

    Returns HTTP 200 with :class:`~apps.api.dto.snapshots.SnapshotCompareResponse`
    on success.  Returns HTTP 422 if *prior_features* is empty (no prior data
    supplied).  Returns HTTP 502 if the macro service cannot be reached.
    """
    if not body.prior_features:
        raise HTTPException(
            status_code=422,
            detail=(
                f"prior_features must not be empty. "
                f"Provide at least one prior indicator value for label "
                f"'{body.prior_snapshot_label}'."
            ),
        )

    try:
        snapshot = await macro_service.get_snapshot(country=body.country)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Macro data service unavailable: {exc}",
        ) from exc

    prior_inputs = [
        PriorFeatureInput(indicator_type=p.indicator_type, value=p.value)
        for p in body.prior_features
    ]
    comparison = compare_snapshots(
        current=snapshot,
        prior_features=prior_inputs,
        prior_snapshot_label=body.prior_snapshot_label,
        country=body.country,
    )

    deltas = [delta_to_dto(d) for d in comparison.deltas]
    trust = build_trust_from_comparison(
        comparison=comparison,
        current_snapshot=snapshot,
        prior_snapshot_timestamp=body.prior_snapshot_timestamp,
    )

    return SnapshotCompareResponse(
        country=body.country,
        prior_snapshot_label=body.prior_snapshot_label,
        deltas=deltas,
        changed_count=comparison.changed_count,
        unchanged_count=comparison.unchanged_count,
        no_prior_count=comparison.no_prior_count,
        trust=trust,
    )
