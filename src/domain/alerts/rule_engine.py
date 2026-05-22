"""Alert rule engine — evaluates alert rules against regime change events.

The :class:`AlertRuleEngine` is the single entry point for alert evaluation.
It is stateless: given a :class:`~domain.macro.change_detection.RegimeDelta`
and the current :class:`~domain.macro.regime.MacroRegime`, it evaluates all
enabled :class:`~domain.alerts.rules.AlertRule` objects and returns the
:class:`~domain.alerts.models.AlertEvent` records that fired.

Evaluation order
----------------
Rules are evaluated in the order they appear in ``rules`` list.  Multiple
rules can fire for a single event.

Rule evaluation logic (per trigger type)
-----------------------------------------
``regime_transition``
    Fires when ``delta.is_regime_transition`` is ``True``.
    Optionally filtered by ``source_regime``, ``target_regime``, and
    ``min_change_severity``.

``threshold_breach``
    Fires when ``delta.metadata`` contains a key matching
    ``rule.indicator_type`` whose float value meets or exceeds
    ``rule.threshold_delta``.  This enables forward-compatible enrichment:
    callers attach indicator deltas to the ``RegimeDelta.metadata`` and
    threshold rules activate automatically.

``staleness_warning``
    Fires when ``regime.freshness_status`` is ``"stale"`` or ``"unknown"``.

``trust_degradation``
    Fires when ``regime.confidence == "low"`` or ``regime.degraded_status``
    is ``"partial"``, ``"missing"``, or ``"source_unavailable"``.

``signal_reversal``
    Fires when ``delta.label_changed`` is ``True`` — a label change is the
    primary deterministic proxy for a potential signal direction reversal.

Design principles
-----------------
* **Deterministic and pure** — no I/O, no side effects, no randomness.
* **No silent suppression** — the engine never drops a fired alert.
* **Composable** — any number of rules can fire per evaluation call.
"""

from __future__ import annotations

from domain.alerts.models import AlertEvent, AlertTriggerType
from domain.alerts.rules import AlertRule
from domain.macro.change_detection import RegimeDelta

# Ordered rank for change severity comparison
_SEVERITY_RANK: dict[str, int] = {
    "unchanged": 0,
    "minor": 1,
    "moderate": 2,
    "major": 3,
}


class AlertRuleEngine:
    """Evaluates alert rules against a ``RegimeDelta`` and current regime state.

    Args:
        rules: The ordered list of :class:`~domain.alerts.rules.AlertRule`
            objects to evaluate.  Disabled rules (``enabled=False``) are
            skipped automatically.
    """

    def __init__(self, rules: list[AlertRule]) -> None:
        self._rules = rules

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        delta: RegimeDelta,
        regime_freshness_status: str = "unknown",
        regime_confidence: str = "low",
        regime_degraded_status: str = "unknown",
        context_snapshot_id: str | None = None,
        country: str | None = None,
    ) -> list[AlertEvent]:
        """Evaluate all enabled rules against the supplied delta and regime state.

        Args:
            delta: The :class:`~domain.macro.change_detection.RegimeDelta`
                produced by the change detection engine.
            regime_freshness_status: String value of the regime's
                ``FreshnessStatus`` (e.g. ``"fresh"``, ``"stale"``).
            regime_confidence: String value of the regime's
                ``RegimeConfidence`` (e.g. ``"high"``, ``"medium"``, ``"low"``).
            regime_degraded_status: String value of the regime's
                ``DegradedStatus`` (e.g. ``"none"``, ``"partial"``).
            context_snapshot_id: ID of the supporting snapshot, attached to
                every fired ``AlertEvent`` for explanation pre-fetch.
            country: Optional country code attached to fired events.

        Returns:
            List of :class:`~domain.alerts.models.AlertEvent` records for
            every rule that fired.  Empty list when no rules match.
        """
        fired: list[AlertEvent] = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            event = self._evaluate_rule(
                rule=rule,
                delta=delta,
                freshness_status=regime_freshness_status,
                confidence=regime_confidence,
                degraded_status=regime_degraded_status,
                context_snapshot_id=context_snapshot_id,
                country=country,
            )
            if event is not None:
                fired.append(event)
        return fired

    # ------------------------------------------------------------------
    # Per-rule evaluation helpers
    # ------------------------------------------------------------------

    def _evaluate_rule(
        self,
        *,
        rule: AlertRule,
        delta: RegimeDelta,
        freshness_status: str,
        confidence: str,
        degraded_status: str,
        context_snapshot_id: str | None,
        country: str | None,
    ) -> AlertEvent | None:
        """Return an ``AlertEvent`` if the rule fires; ``None`` otherwise."""
        if rule.trigger_type == AlertTriggerType.REGIME_TRANSITION:
            return self._eval_regime_transition(
                rule=rule,
                delta=delta,
                context_snapshot_id=context_snapshot_id,
                country=country,
            )
        if rule.trigger_type == AlertTriggerType.THRESHOLD_BREACH:
            return self._eval_threshold_breach(
                rule=rule,
                delta=delta,
                context_snapshot_id=context_snapshot_id,
                country=country,
            )
        if rule.trigger_type == AlertTriggerType.STALENESS_WARNING:
            return self._eval_staleness(
                rule=rule,
                delta=delta,
                freshness_status=freshness_status,
                context_snapshot_id=context_snapshot_id,
                country=country,
            )
        if rule.trigger_type == AlertTriggerType.TRUST_DEGRADATION:
            return self._eval_trust_degradation(
                rule=rule,
                delta=delta,
                confidence=confidence,
                degraded_status=degraded_status,
                context_snapshot_id=context_snapshot_id,
                country=country,
            )
        if rule.trigger_type == AlertTriggerType.SIGNAL_REVERSAL:
            return self._eval_signal_reversal(
                rule=rule,
                delta=delta,
                context_snapshot_id=context_snapshot_id,
                country=country,
            )
        return None

    def _eval_regime_transition(
        self,
        *,
        rule: AlertRule,
        delta: RegimeDelta,
        context_snapshot_id: str | None,
        country: str | None,
    ) -> AlertEvent | None:
        if not delta.is_regime_transition:
            return None
        # source_regime filter
        if rule.source_regime is not None and delta.prior_label != rule.source_regime:
            return None
        # target_regime filter
        if rule.target_regime is not None and delta.current_label != rule.target_regime:
            return None
        # min_change_severity filter
        if rule.min_change_severity is not None:
            required_rank = _SEVERITY_RANK.get(rule.min_change_severity, 0)
            actual_rank = _SEVERITY_RANK.get(delta.severity, 0)
            if actual_rank < required_rank:
                return None
        message = (
            f"Regime transition: {delta.prior_label} → {delta.current_label} "
            f"(severity: {delta.severity})"
        )
        return AlertEvent(
            trigger_type=rule.trigger_type,
            severity=rule.alert_severity,
            source_regime=delta.prior_label,
            target_regime=delta.current_label,
            context_snapshot_id=context_snapshot_id,
            country=country,
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            message=message,
            metadata={
                "severity": delta.severity,
                "label_transition": delta.label_transition or "",
                "confidence_direction": delta.confidence_direction,
            },
        )

    def _eval_threshold_breach(
        self,
        *,
        rule: AlertRule,
        delta: RegimeDelta,
        context_snapshot_id: str | None,
        country: str | None,
    ) -> AlertEvent | None:
        if rule.indicator_type is None or rule.threshold_delta is None:
            return None
        # RegimeDelta does not yet carry per-indicator delta values.
        # This hook is forward-compatible: once indicator-level deltas are
        # attached to the delta metadata, this code path will activate.
        raw: str | None = getattr(delta, "metadata", {}).get(rule.indicator_type)
        if raw is None:
            return None
        try:
            actual_delta = abs(float(raw))
        except (ValueError, TypeError):
            return None
        if actual_delta < rule.threshold_delta:
            return None
        message = (
            f"Threshold breach: {rule.indicator_type} changed by "
            f"{actual_delta:+.3f} (threshold: {rule.threshold_delta:+.3f})"
        )
        return AlertEvent(
            trigger_type=rule.trigger_type,
            severity=rule.alert_severity,
            indicator_type=rule.indicator_type,
            context_snapshot_id=context_snapshot_id,
            country=country,
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            message=message,
            metadata={
                "indicator_type": rule.indicator_type,
                "delta_value": str(actual_delta),
                "threshold": str(rule.threshold_delta),
            },
        )

    def _eval_staleness(
        self,
        *,
        rule: AlertRule,
        delta: RegimeDelta,
        freshness_status: str,
        context_snapshot_id: str | None,
        country: str | None,
    ) -> AlertEvent | None:
        if freshness_status not in {"stale", "unknown"}:
            return None
        message = f"Data staleness detected: freshness_status={freshness_status}"
        return AlertEvent(
            trigger_type=rule.trigger_type,
            severity=rule.alert_severity,
            source_regime=delta.current_label or None,
            context_snapshot_id=context_snapshot_id,
            country=country,
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            message=message,
            metadata={"freshness_status": freshness_status},
        )

    def _eval_trust_degradation(
        self,
        *,
        rule: AlertRule,
        delta: RegimeDelta,
        confidence: str,
        degraded_status: str,
        context_snapshot_id: str | None,
        country: str | None,
    ) -> AlertEvent | None:
        low_confidence = confidence == "low"
        bad_degraded = degraded_status in {"partial", "missing", "source_unavailable"}
        if not low_confidence and not bad_degraded:
            return None
        reasons: list[str] = []
        if low_confidence:
            reasons.append(f"confidence={confidence}")
        if bad_degraded:
            reasons.append(f"degraded_status={degraded_status}")
        message = "Trust degradation detected: " + "; ".join(reasons)
        return AlertEvent(
            trigger_type=rule.trigger_type,
            severity=rule.alert_severity,
            source_regime=delta.current_label or None,
            context_snapshot_id=context_snapshot_id,
            country=country,
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            message=message,
            metadata={
                "confidence": confidence,
                "degraded_status": degraded_status,
            },
        )

    def _eval_signal_reversal(
        self,
        *,
        rule: AlertRule,
        delta: RegimeDelta,
        context_snapshot_id: str | None,
        country: str | None,
    ) -> AlertEvent | None:
        if not delta.label_changed:
            return None
        message = (
            f"Signal reversal likely: regime label changed "
            f"({delta.prior_label} → {delta.current_label})"
        )
        return AlertEvent(
            trigger_type=rule.trigger_type,
            severity=rule.alert_severity,
            source_regime=delta.prior_label,
            target_regime=delta.current_label,
            context_snapshot_id=context_snapshot_id,
            country=country,
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            message=message,
            metadata={
                "label_transition": delta.label_transition or "",
                "severity": delta.severity,
            },
        )
