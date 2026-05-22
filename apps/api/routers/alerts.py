"""Alert read routes for the analyst-facing product API (Chapter 6).

Routes
------
``GET /api/alerts/recent``
    Return recent alert events, filterable by trigger type, severity,
    country, and time range.

``GET /api/alerts/{alert_id}``
    Return a single alert event by ID.

``PATCH /api/alerts/{alert_id}/acknowledge``
    Mark an alert as acknowledged by the analyst.

``PATCH /api/alerts/{alert_id}/snooze``
    Snooze an alert until a specified UTC datetime.

Design notes
------------
* Acknowledgement and snooze are analyst-facing state transitions.  They are
  never autonomous — the engine never suppresses alerts on its own.
* The routes are intentionally minimal: no bulk operations, no write-capable
  alert creation via API (alerts are fired only by the rule engine).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.dependencies import get_alert_repository
from apps.api.dto.alerts import (
    AlertAcknowledgeRequest,
    AlertEventDTO,
    AlertSnoozeRequest,
    AlertsRecentResponse,
)
from src.core.storage.repositories.alert_repository import AlertRepositoryInterface
from src.domain.alerts.models import AlertAcknowledgementState, AlertSeverity, AlertTriggerType

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _alert_to_dto(alert: object) -> AlertEventDTO:
    """Map a domain :class:`~domain.alerts.models.AlertEvent` to an :class:`AlertEventDTO`."""
    from src.domain.alerts.models import AlertEvent

    a: AlertEvent = alert  # type: ignore[assignment]
    return AlertEventDTO(
        alert_id=a.alert_id,
        triggered_at=a.triggered_at,
        trigger_type=a.trigger_type.value,
        severity=a.severity.value,
        source_regime=a.source_regime,
        target_regime=a.target_regime,
        indicator_type=a.indicator_type,
        context_snapshot_id=a.context_snapshot_id,
        country=a.country,
        rule_id=a.rule_id,
        rule_name=a.rule_name,
        message=a.message,
        acknowledgement_state=a.acknowledgement_state.value,
        acknowledged_at=a.acknowledged_at,
        snoozed_until=a.snoozed_until,
        metadata=dict(a.metadata),
    )


@router.get(
    "/recent",
    response_model=AlertsRecentResponse,
    summary="List recent alert events",
    description=(
        "Return recent alert events, ordered most-recent first. "
        "Filterable by ``trigger_type``, ``severity``, ``country``, "
        "``since`` (ISO 8601), and ``until`` (ISO 8601). "
        "``limit`` caps the result set (max 200)."
    ),
)
async def list_recent_alerts(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of records"),
    trigger_type: str | None = Query(
        default=None,
        description=(
            "Filter by trigger type: threshold_breach | regime_transition | "
            "signal_reversal | staleness_warning | trust_degradation"
        ),
    ),
    severity: str | None = Query(
        default=None,
        description="Filter by severity: info | warning | critical",
    ),
    country: str | None = Query(
        default=None,
        description="Filter by country code (ISO 3166-1 alpha-2)",
    ),
    since: datetime | None = Query(
        default=None,
        description="Return alerts at or after this UTC datetime (ISO 8601)",
    ),
    until: datetime | None = Query(
        default=None,
        description="Return alerts at or before this UTC datetime (ISO 8601)",
    ),
    alert_repo: AlertRepositoryInterface = Depends(get_alert_repository),
) -> AlertsRecentResponse:
    # Validate and convert trigger_type filter
    parsed_trigger: AlertTriggerType | None = None
    if trigger_type is not None:
        try:
            parsed_trigger = AlertTriggerType(trigger_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid trigger_type '{trigger_type}'. "
                f"Valid values: {[t.value for t in AlertTriggerType]}",
            ) from exc

    # Validate and convert severity filter
    parsed_severity: AlertSeverity | None = None
    if severity is not None:
        try:
            parsed_severity = AlertSeverity(severity)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid severity '{severity}'. "
                f"Valid values: {[s.value for s in AlertSeverity]}",
            ) from exc

    alerts = alert_repo.list_recent(
        limit=limit,
        trigger_type=parsed_trigger,
        severity=parsed_severity,
        country=country,
        since=since,
        until=until,
    )
    dtos = [_alert_to_dto(a) for a in alerts]
    return AlertsRecentResponse(alerts=dtos, total=len(dtos), limit_applied=limit)


@router.get(
    "/{alert_id}",
    response_model=AlertEventDTO,
    summary="Get alert event by ID",
)
async def get_alert(
    alert_id: str,
    alert_repo: AlertRepositoryInterface = Depends(get_alert_repository),
) -> AlertEventDTO:
    alert = alert_repo.get_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return _alert_to_dto(alert)


@router.patch(
    "/{alert_id}/acknowledge",
    response_model=AlertEventDTO,
    summary="Acknowledge an alert",
    description=(
        "Mark the alert as acknowledged by the analyst. "
        "This is a soft state transition — acknowledgement does not suppress "
        "future alerts from the same rule."
    ),
)
async def acknowledge_alert(
    alert_id: str,
    _body: AlertAcknowledgeRequest = AlertAcknowledgeRequest(),
    alert_repo: AlertRepositoryInterface = Depends(get_alert_repository),
) -> AlertEventDTO:
    updated = alert_repo.update_acknowledgement(
        alert_id=alert_id,
        state=AlertAcknowledgementState.ACKNOWLEDGED,
        acknowledged_at=datetime.now(UTC),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return _alert_to_dto(updated)


@router.patch(
    "/{alert_id}/snooze",
    response_model=AlertEventDTO,
    summary="Snooze an alert until a specified datetime",
    description=(
        "Snooze the alert until ``snoozed_until``. "
        "This is analyst-initiated suppression only — the engine never "
        "silently drops alerts."
    ),
)
async def snooze_alert(
    alert_id: str,
    body: AlertSnoozeRequest,
    alert_repo: AlertRepositoryInterface = Depends(get_alert_repository),
) -> AlertEventDTO:
    updated = alert_repo.update_acknowledgement(
        alert_id=alert_id,
        state=AlertAcknowledgementState.SNOOZED,
        snoozed_until=body.snoozed_until,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return _alert_to_dto(updated)
