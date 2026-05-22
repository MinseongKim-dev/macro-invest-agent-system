"""Alert domain models for Chapter 6 — Alerting & Monitoring Intelligence.

This module defines the core alert vocabulary used across the alerting layer:

* :class:`AlertTriggerType` — what kind of condition fired the alert.
* :class:`AlertSeverity` — analyst-facing importance level.
* :class:`AlertAcknowledgementState` — analyst acknowledgement / snooze state.
* :class:`AlertEvent` — the immutable structured record produced when an alert
  fires.  Every field maps directly to an observable fact in the analytical
  pipeline — nothing is inferred here.
* :class:`AlertRule` — a configurable rule evaluated by the
  :class:`~domain.alerts.rule_engine.AlertRuleEngine`.

Design principles
-----------------
* **Deterministic** — same inputs to the rule engine always produce the same
  alert outputs.
* **Fact-grounded** — every ``AlertEvent`` field is traceable to a structured
  fact in the pipeline (``RegimeDelta``, ``MacroRegime``, or snapshot).
* **Advisory, not autonomous** — alert suppression (acknowledge / snooze) is
  always analyst-initiated.  The engine never silently drops alerts.
* **Explicit severity** — severity is assigned by the rule, not inferred at
  delivery time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AlertTriggerType(StrEnum):
    """The category of condition that caused an alert to fire.

    ``threshold_breach``
        A numeric indicator crossed a configured threshold delta
        (e.g. inflation up > 0.5 pp).
    ``regime_transition``
        The macro regime label changed (optionally filtered by source/target
        regime and minimum change severity).
    ``signal_reversal``
        An investment signal flipped direction (e.g. BUY → SELL for equities).
    ``staleness_warning``
        One or more macro data inputs became stale / past their freshness window.
    ``trust_degradation``
        Regime confidence dropped or the regime entered a degraded / mixed state.
    """

    THRESHOLD_BREACH = "threshold_breach"
    REGIME_TRANSITION = "regime_transition"
    SIGNAL_REVERSAL = "signal_reversal"
    STALENESS_WARNING = "staleness_warning"
    TRUST_DEGRADATION = "trust_degradation"


class AlertSeverity(StrEnum):
    """Analyst-facing importance level of an alert.

    ``info``
        Informational — noteworthy but not action-requiring.
    ``warning``
        Analyst should review; may warrant portfolio action.
    ``critical``
        High-priority; analyst action strongly recommended.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertAcknowledgementState(StrEnum):
    """Analyst-facing lifecycle state of an alert.

    ``active``
        Alert has fired and has not been acknowledged or snoozed.
    ``acknowledged``
        Analyst has read and explicitly acknowledged the alert.
    ``snoozed``
        Analyst has temporarily suppressed the alert until ``snoozed_until``.
    """

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    SNOOZED = "snoozed"


class AlertEvent(BaseModel, extra="forbid"):
    """A structured alert record produced when an alert rule fires.

    Every ``AlertEvent`` is immutable after creation.  Analyst
    acknowledgement/snooze state is stored alongside the event but does not
    mutate the underlying analytical facts.

    Attributes:
        alert_id: Unique identifier for this alert instance.
        triggered_at: UTC datetime when the alert fired.
        trigger_type: The category of condition that caused the alert.
        severity: Analyst-facing importance level.
        source_regime: Regime label before the transition (if applicable).
        target_regime: Regime label after the transition (if applicable).
        indicator_type: Macro indicator involved (for threshold breach alerts).
        context_snapshot_id: ID of the supporting snapshot that grounded this
            alert — enables pre-fetching of explanation context.
        country: Country code (ISO 3166-1 alpha-2) associated with the alert,
            if applicable.
        rule_id: ID of the ``AlertRule`` that triggered this event.
        rule_name: Human-readable rule name for analyst display.
        message: Short analyst-facing description of what triggered the alert.
        acknowledgement_state: Current analyst acknowledgement state.
        acknowledged_at: UTC datetime when the alert was acknowledged (if any).
        snoozed_until: UTC datetime until which the alert is snoozed (if any).
        metadata: Arbitrary supplemental key/value pairs (e.g. delta values,
            confidence levels) for downstream enrichment.
    """

    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trigger_type: AlertTriggerType
    severity: AlertSeverity
    source_regime: str | None = Field(
        default=None,
        description="Regime label before transition (regime_transition alerts)",
    )
    target_regime: str | None = Field(
        default=None,
        description="Regime label after transition (regime_transition alerts)",
    )
    indicator_type: str | None = Field(
        default=None,
        description="Macro indicator involved (threshold_breach alerts)",
    )
    context_snapshot_id: str | None = Field(
        default=None,
        description=(
            "Supporting snapshot ID for pre-fetching explanation context "
            "when the alert fires"
        ),
    )
    country: str | None = Field(
        default=None,
        description="ISO 3166-1 alpha-2 country code, if applicable",
    )
    rule_id: str = Field(description="ID of the AlertRule that triggered this event")
    rule_name: str = Field(description="Human-readable rule name for analyst display")
    message: str = Field(description="Short analyst-facing description of the trigger")
    acknowledgement_state: AlertAcknowledgementState = Field(
        default=AlertAcknowledgementState.ACTIVE,
        description="Current analyst acknowledgement lifecycle state",
    )
    acknowledged_at: datetime | None = Field(
        default=None,
        description="UTC datetime when the alert was acknowledged",
    )
    snoozed_until: datetime | None = Field(
        default=None,
        description="UTC datetime until which the alert is snoozed",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Supplemental key/value pairs attached at rule evaluation time "
            "(e.g. delta values, confidence levels)"
        ),
    )
