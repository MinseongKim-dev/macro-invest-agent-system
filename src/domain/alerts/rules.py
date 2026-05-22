"""Alert rule definitions for the configurable alert-rule engine.

An :class:`AlertRule` declares a single condition.  The
:class:`~domain.alerts.rule_engine.AlertRuleEngine` evaluates all enabled
rules against an incoming :class:`~domain.macro.change_detection.RegimeDelta`
and current :class:`~domain.macro.regime.MacroRegime`, and returns the list of
:class:`~domain.alerts.models.AlertEvent` records that fired.

Rule types
----------
``regime_transition``
    Fires when ``RegimeDelta.is_regime_transition`` is ``True`` and the
    optional ``source_regime`` / ``target_regime`` filters match (``None``
    matches any).  An optional ``min_change_severity`` filter restricts firing
    to deltas at or above the specified severity level.

``threshold_breach``
    Fires when the ``RegimeDelta`` carries a metadata value for
    ``indicator_type`` that exceeds ``threshold_delta``.  This mechanism
    supports future extension: when indicator-level deltas are attached to the
    regime delta metadata, this rule type activates automatically.

``staleness_warning``
    Fires when the current regime ``freshness_status`` is ``stale`` or
    ``unknown``.

``trust_degradation``
    Fires when the current regime ``confidence`` drops to ``low``, or when
    ``degraded_status`` is ``partial``, ``missing``, or
    ``source_unavailable``.

``signal_reversal``
    Fires when ``RegimeDelta.label_changed`` is ``True`` — a label change is
    the primary deterministic proxy for a potential signal direction flip.
    Callers can extend this rule type with signal-level delta metadata when
    the signal layer produces structured deltas.

Design principles
-----------------
* **Explicit over implicit** — every firing condition is listed in this module.
* **Composable** — rules are independent; multiple rules can fire for one event.
* **Idempotent** — the engine is pure: same inputs → same outputs, no side
  effects.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from domain.alerts.models import AlertSeverity, AlertTriggerType


class AlertRule(BaseModel, extra="forbid"):
    """A single configurable alert rule evaluated by the rule engine.

    Attributes:
        rule_id: Unique identifier for this rule.
        rule_name: Human-readable name shown on fired alert events.
        trigger_type: The category of condition this rule watches for.
        enabled: When ``False`` the rule is skipped entirely.
        alert_severity: Severity assigned to ``AlertEvent`` records fired by
            this rule.
        source_regime: For ``regime_transition`` rules — the prior regime
            label that must match (``None`` = any prior label).
        target_regime: For ``regime_transition`` rules — the new regime label
            that must match (``None`` = any new label).
        min_change_severity: For ``regime_transition`` rules — the minimum
            ``ChangeSeverity`` level required to fire.  ``None`` = any severity
            (including ``minor``).  Valid string values: ``"unchanged"``,
            ``"minor"``, ``"moderate"``, ``"major"``.
        indicator_type: For ``threshold_breach`` rules — the macro indicator
            type to watch (matches ``MacroIndicatorType`` string values).
        threshold_delta: For ``threshold_breach`` rules — the minimum absolute
            change magnitude required to fire (e.g. ``0.5`` for 0.5 pp).
        description: Optional long-form description of the rule for
            documentation and admin UI display.
    """

    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_name: str
    trigger_type: AlertTriggerType
    enabled: bool = Field(default=True)
    alert_severity: AlertSeverity = Field(default=AlertSeverity.WARNING)
    # regime_transition fields
    source_regime: str | None = Field(
        default=None,
        description=(
            "Prior regime label filter for regime_transition rules "
            "(None = match any)"
        ),
    )
    target_regime: str | None = Field(
        default=None,
        description=(
            "New regime label filter for regime_transition rules "
            "(None = match any)"
        ),
    )
    min_change_severity: str | None = Field(
        default=None,
        description=(
            "Minimum ChangeSeverity to fire: unchanged | minor | moderate | major. "
            "None = any severity including minor."
        ),
    )
    # threshold_breach fields
    indicator_type: str | None = Field(
        default=None,
        description="Macro indicator type for threshold_breach rules",
    )
    threshold_delta: float | None = Field(
        default=None,
        description=(
            "Minimum absolute change magnitude for threshold_breach rules "
            "(e.g. 0.5 for 0.5 pp)"
        ),
    )
    description: str = Field(
        default="",
        description="Optional rule description for documentation",
    )
