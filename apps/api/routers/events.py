"""External event read routes for the analyst-facing product API (Chapter 7).

Routes
------
``GET /api/events/recent``
    Return recent normalized external events, filterable by event type,
    status, region, and time range.

``GET /api/events/{event_id}``
    Return a single normalized external event by ID.

Design notes
------------
* These routes are strictly read-only.  External event records are written
  by the ingestion layer, never via the analyst API.
* The event repository dependency is overridable in tests via
  ``app.dependency_overrides[get_event_repository]``.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import get_event_repository
from apps.api.dto.events import EventsRecentResponse, ExternalEventDTO
from src.core.storage.repositories.event_repository import EventRepositoryInterface
from src.domain.events.enums import ExternalEventStatus, ExternalEventType
from src.domain.events.models import NormalizedExternalEvent

router = APIRouter(prefix="/api/events", tags=["events"])


def _event_to_dto(event: NormalizedExternalEvent) -> ExternalEventDTO:
    """Map a domain :class:`~domain.events.models.NormalizedExternalEvent` to an :class:`ExternalEventDTO`."""
    return ExternalEventDTO(
        event_id=event.event_id,
        event_type=event.event_type.value,
        title=event.title,
        summary=event.summary,
        entity=event.entity,
        region=event.region,
        market_scope=list(event.market_scope),
        occurred_at=event.occurred_at,
        published_at=event.published_at,
        ingested_at=event.ingested_at,
        source=event.source,
        source_url=event.source_url,
        provider=event.provider,
        freshness=event.freshness.value,
        provenance=event.provenance,
        reliability_tier=event.reliability_tier.value,
        tags=list(event.tags),
        affected_domains=list(event.affected_domains),
        status=event.status.value,
        raw_payload_ref=event.raw_payload_ref,
        metadata=dict(event.metadata),
    )


@router.get(
    "/recent",
    response_model=EventsRecentResponse,
    summary="List recent normalized external events",
    description=(
        "Return recent normalized external events, ordered most-recent first. "
        "Filterable by ``event_type``, ``status``, ``region``, "
        "``since`` (ISO 8601), and ``until`` (ISO 8601). "
        "``limit`` caps the result set (max 200)."
    ),
)
async def list_recent_events(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of records"),
    event_type: str | None = Query(
        default=None,
        description=(
            "Filter by event type: macro_release | central_bank_decision | "
            "policy_announcement | earnings_event | geopolitical_development | "
            "market_catalyst | other"
        ),
    ),
    status: str | None = Query(
        default=None,
        description="Filter by lifecycle status: active | stale | partial | duplicate | degraded",
    ),
    region: str | None = Query(
        default=None,
        description="Filter by region string (e.g. 'US', 'EU', 'GLOBAL')",
    ),
    since: datetime | None = Query(
        default=None,
        description="Return events at or after this UTC datetime (ISO 8601)",
    ),
    until: datetime | None = Query(
        default=None,
        description="Return events at or before this UTC datetime (ISO 8601)",
    ),
    event_repo: EventRepositoryInterface = Depends(get_event_repository),
) -> EventsRecentResponse:
    parsed_event_type: ExternalEventType | None = None
    if event_type is not None:
        try:
            parsed_event_type = ExternalEventType(event_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid event_type '{event_type}'. "
                f"Valid values: {[t.value for t in ExternalEventType]}",
            ) from exc

    parsed_status: ExternalEventStatus | None = None
    if status is not None:
        try:
            parsed_status = ExternalEventStatus(status)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. "
                f"Valid values: {[s.value for s in ExternalEventStatus]}",
            ) from exc

    events = event_repo.list_recent(
        limit=limit,
        event_type=parsed_event_type,
        status=parsed_status,
        region=region,
        since=since,
        until=until,
    )
    dtos = [_event_to_dto(e) for e in events]
    return EventsRecentResponse(events=dtos, total=len(dtos), limit_applied=limit)


@router.get(
    "/{event_id}",
    response_model=ExternalEventDTO,
    summary="Get external event by ID",
)
async def get_event(
    event_id: str,
    event_repo: EventRepositoryInterface = Depends(get_event_repository),
) -> ExternalEventDTO:
    event = event_repo.get_by_id(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return _event_to_dto(event)
