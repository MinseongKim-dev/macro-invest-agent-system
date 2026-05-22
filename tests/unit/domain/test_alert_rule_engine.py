"""Tests for the AlertRuleEngine (Chapter 6)."""

from __future__ import annotations

from src.domain.alerts.models import AlertSeverity, AlertTriggerType
from src.domain.alerts.rule_engine import AlertRuleEngine
from src.domain.alerts.rules import AlertRule
from src.domain.macro.change_detection import RegimeDelta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _delta(
    *,
    is_initial: bool = False,
    label_changed: bool = False,
    family_changed: bool = False,
    confidence_changed: bool = False,
    is_regime_transition: bool = False,
    severity: str = "unchanged",
    prior_label: str | None = "goldilocks",
    current_label: str = "goldilocks",
    prior_confidence: str | None = "high",
    current_confidence: str = "high",
    current_family: str = "expansion",
    label_transition: str | None = None,
    confidence_direction: str = "unchanged",
) -> RegimeDelta:
    return RegimeDelta(
        is_initial=is_initial,
        label_changed=label_changed,
        family_changed=family_changed,
        confidence_changed=confidence_changed,
        confidence_direction=confidence_direction,
        severity=severity,
        changed_dimensions=[],
        prior_label=prior_label,
        prior_family="expansion" if prior_label else None,
        prior_confidence=prior_confidence,
        current_label=current_label,
        current_family=current_family,
        current_confidence=current_confidence,
        label_transition=label_transition,
        confidence_transition=None,
        is_regime_transition=is_regime_transition,
        notable_flags=[],
        severity_rationale="test",
    )


# ---------------------------------------------------------------------------
# Regime transition rules
# ---------------------------------------------------------------------------


class TestRegimeTransitionRule:
    def test_fires_on_transition(self) -> None:
        rule = AlertRule(
            rule_name="All transitions",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(
            label_changed=True,
            is_regime_transition=True,
            severity="major",
            prior_label="goldilocks",
            current_label="contraction",
            current_family="contraction",
            label_transition="goldilocks → contraction",
        )
        events = engine.evaluate(delta)
        assert len(events) == 1
        assert events[0].trigger_type == AlertTriggerType.REGIME_TRANSITION
        assert events[0].source_regime == "goldilocks"
        assert events[0].target_regime == "contraction"

    def test_does_not_fire_without_transition(self) -> None:
        rule = AlertRule(
            rule_name="All transitions",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
        )
        engine = AlertRuleEngine([rule])
        assert engine.evaluate(_delta(is_regime_transition=False)) == []

    def test_source_regime_filter_matches(self) -> None:
        rule = AlertRule(
            rule_name="From goldilocks",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
            source_regime="goldilocks",
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(
            is_regime_transition=True,
            severity="major",
            prior_label="goldilocks",
            current_label="contraction",
            current_family="contraction",
        )
        assert len(engine.evaluate(delta)) == 1

    def test_source_regime_filter_blocks(self) -> None:
        rule = AlertRule(
            rule_name="From slowdown",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
            source_regime="slowdown",
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(
            is_regime_transition=True,
            prior_label="goldilocks",
            current_label="contraction",
            current_family="contraction",
        )
        assert engine.evaluate(delta) == []

    def test_target_regime_filter_matches(self) -> None:
        rule = AlertRule(
            rule_name="To stagflation",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
            target_regime="stagflation_risk",
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(
            is_regime_transition=True,
            prior_label="goldilocks",
            current_label="stagflation_risk",
            current_family="late_cycle",
        )
        assert len(engine.evaluate(delta)) == 1

    def test_target_regime_filter_blocks(self) -> None:
        rule = AlertRule(
            rule_name="To stagflation",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
            target_regime="stagflation_risk",
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(
            is_regime_transition=True,
            prior_label="goldilocks",
            current_label="contraction",
            current_family="contraction",
        )
        assert engine.evaluate(delta) == []

    def test_min_change_severity_major_blocks_moderate(self) -> None:
        rule = AlertRule(
            rule_name="Major only",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
            min_change_severity="major",
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(
            is_regime_transition=True,
            severity="moderate",
            prior_label="goldilocks",
            current_label="disinflation",
            current_family="inflation_transition",
        )
        assert engine.evaluate(delta) == []

    def test_min_change_severity_moderate_fires_on_major(self) -> None:
        rule = AlertRule(
            rule_name="Moderate and above",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
            min_change_severity="moderate",
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(
            is_regime_transition=True,
            severity="major",
            prior_label="goldilocks",
            current_label="contraction",
            current_family="contraction",
        )
        assert len(engine.evaluate(delta)) == 1

    def test_disabled_rule_does_not_fire(self) -> None:
        rule = AlertRule(
            rule_name="Disabled",
            trigger_type=AlertTriggerType.REGIME_TRANSITION,
            alert_severity=AlertSeverity.WARNING,
            enabled=False,
        )
        engine = AlertRuleEngine([rule])
        delta = _delta(is_regime_transition=True, severity="major")
        assert engine.evaluate(delta) == []


# ---------------------------------------------------------------------------
# Staleness warning rules
# ---------------------------------------------------------------------------


class TestStalenessRule:
    def _rule(self) -> AlertRule:
        return AlertRule(
            rule_name="Staleness",
            trigger_type=AlertTriggerType.STALENESS_WARNING,
            alert_severity=AlertSeverity.WARNING,
        )

    def test_fires_on_stale(self) -> None:
        events = AlertRuleEngine([self._rule()]).evaluate(_delta(), regime_freshness_status="stale")
        assert len(events) == 1
        assert events[0].trigger_type == AlertTriggerType.STALENESS_WARNING

    def test_fires_on_unknown(self) -> None:
        events = AlertRuleEngine([self._rule()]).evaluate(
            _delta(), regime_freshness_status="unknown"
        )
        assert len(events) == 1

    def test_does_not_fire_on_fresh(self) -> None:
        assert (
            AlertRuleEngine([self._rule()]).evaluate(_delta(), regime_freshness_status="fresh")
            == []
        )

    def test_does_not_fire_on_late(self) -> None:
        assert (
            AlertRuleEngine([self._rule()]).evaluate(_delta(), regime_freshness_status="late") == []
        )


# ---------------------------------------------------------------------------
# Trust degradation rules
# ---------------------------------------------------------------------------


class TestTrustDegradationRule:
    def _rule(self) -> AlertRule:
        return AlertRule(
            rule_name="Trust degradation",
            trigger_type=AlertTriggerType.TRUST_DEGRADATION,
            alert_severity=AlertSeverity.CRITICAL,
        )

    def test_fires_on_low_confidence(self) -> None:
        events = AlertRuleEngine([self._rule()]).evaluate(_delta(), regime_confidence="low")
        assert len(events) == 1
        assert events[0].trigger_type == AlertTriggerType.TRUST_DEGRADATION
        assert events[0].severity == AlertSeverity.CRITICAL

    def test_fires_on_partial_degraded(self) -> None:
        events = AlertRuleEngine([self._rule()]).evaluate(
            _delta(), regime_confidence="medium", regime_degraded_status="partial"
        )
        assert len(events) == 1

    def test_fires_on_missing_degraded(self) -> None:
        assert (
            len(
                AlertRuleEngine([self._rule()]).evaluate(_delta(), regime_degraded_status="missing")
            )
            == 1
        )

    def test_fires_on_source_unavailable(self) -> None:
        assert (
            len(
                AlertRuleEngine([self._rule()]).evaluate(
                    _delta(), regime_degraded_status="source_unavailable"
                )
            )
            == 1
        )

    def test_does_not_fire_on_high_confidence_none_degraded(self) -> None:
        assert (
            AlertRuleEngine([self._rule()]).evaluate(
                _delta(), regime_confidence="high", regime_degraded_status="none"
            )
            == []
        )


# ---------------------------------------------------------------------------
# Signal reversal rules
# ---------------------------------------------------------------------------


class TestSignalReversalRule:
    def _rule(self) -> AlertRule:
        return AlertRule(
            rule_name="Signal reversal",
            trigger_type=AlertTriggerType.SIGNAL_REVERSAL,
            alert_severity=AlertSeverity.WARNING,
        )

    def test_fires_on_label_change(self) -> None:
        delta = _delta(
            label_changed=True,
            is_regime_transition=True,
            prior_label="goldilocks",
            current_label="contraction",
            current_family="contraction",
        )
        events = AlertRuleEngine([self._rule()]).evaluate(delta)
        assert len(events) == 1
        assert events[0].trigger_type == AlertTriggerType.SIGNAL_REVERSAL

    def test_does_not_fire_without_label_change(self) -> None:
        assert AlertRuleEngine([self._rule()]).evaluate(_delta(label_changed=False)) == []


# ---------------------------------------------------------------------------
# Multiple rules, context metadata
# ---------------------------------------------------------------------------


class TestMultipleRules:
    def test_multiple_rules_can_fire(self) -> None:
        rules = [
            AlertRule(
                rule_name="Transitions",
                trigger_type=AlertTriggerType.REGIME_TRANSITION,
                alert_severity=AlertSeverity.WARNING,
            ),
            AlertRule(
                rule_name="Signal reversals",
                trigger_type=AlertTriggerType.SIGNAL_REVERSAL,
                alert_severity=AlertSeverity.WARNING,
            ),
        ]
        delta = _delta(
            label_changed=True,
            is_regime_transition=True,
            severity="major",
            prior_label="goldilocks",
            current_label="contraction",
            current_family="contraction",
        )
        events = AlertRuleEngine(rules).evaluate(delta)
        assert len(events) == 2
        types = {e.trigger_type for e in events}
        assert AlertTriggerType.REGIME_TRANSITION in types
        assert AlertTriggerType.SIGNAL_REVERSAL in types

    def test_context_snapshot_id_attached(self) -> None:
        rule = AlertRule(
            rule_name="Staleness",
            trigger_type=AlertTriggerType.STALENESS_WARNING,
            alert_severity=AlertSeverity.WARNING,
        )
        events = AlertRuleEngine([rule]).evaluate(
            _delta(),
            regime_freshness_status="stale",
            context_snapshot_id="snap-xyz",
        )
        assert events[0].context_snapshot_id == "snap-xyz"

    def test_country_attached(self) -> None:
        rule = AlertRule(
            rule_name="Staleness",
            trigger_type=AlertTriggerType.STALENESS_WARNING,
            alert_severity=AlertSeverity.WARNING,
        )
        events = AlertRuleEngine([rule]).evaluate(
            _delta(),
            regime_freshness_status="stale",
            country="US",
        )
        assert events[0].country == "US"

    def test_empty_rules_list(self) -> None:
        delta = _delta(is_regime_transition=True)
        assert AlertRuleEngine([]).evaluate(delta) == []
