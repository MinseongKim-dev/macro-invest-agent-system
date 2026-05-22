"""Tests for ExternalEventImpact model (Chunk 2)."""

from __future__ import annotations

from src.domain.events.enums import ExternalEventType
from src.domain.events.impact import ExternalEventImpact, ExternalEventImpactRouting


class TestExternalEventImpactRouting:
    def test_defaults_all_false(self) -> None:
        routing = ExternalEventImpactRouting()
        assert routing.has_explanation_evidence is False
        assert routing.has_caveat_notes is False
        assert routing.has_conflict_contributors is False
        assert routing.has_confidence_downgrade is False
        assert routing.has_change_context is False

    def test_set_flags(self) -> None:
        routing = ExternalEventImpactRouting(
            has_explanation_evidence=True,
            has_caveat_notes=True,
        )
        assert routing.has_explanation_evidence is True
        assert routing.has_caveat_notes is True
        assert routing.has_conflict_contributors is False


class TestExternalEventImpact:
    def test_defaults(self) -> None:
        impact = ExternalEventImpact(
            source_event_id="evt-1",
            source_event_type=ExternalEventType.MACRO_RELEASE,
        )
        assert impact.explanation_evidence == []
        assert impact.caveat_notes == []
        assert impact.conflict_contributors == []
        assert impact.confidence_downgrade_hint is False
        assert impact.confidence_downgrade_reason is None
        assert impact.change_context_annotation is None
        assert impact.impact_severity == "low"
        assert impact.is_heuristic is True

    def test_full_construction(self) -> None:
        impact = ExternalEventImpact(
            source_event_id="evt-2",
            source_event_type=ExternalEventType.CENTRAL_BANK_DECISION,
            explanation_evidence=["Fed raised rates by 25bps"],
            caveat_notes=["Policy uncertainty may affect regime"],
            conflict_contributors=["policy_catalyst_active"],
            confidence_downgrade_hint=True,
            confidence_downgrade_reason="Policy decision introduces forward uncertainty",
            change_context_annotation="Rate hike noted",
            impact_severity="high",
            affected_domains=["policy", "inflation"],
            routing=ExternalEventImpactRouting(
                has_explanation_evidence=True,
                has_caveat_notes=True,
                has_conflict_contributors=True,
                has_confidence_downgrade=True,
                has_change_context=True,
            ),
        )
        assert impact.confidence_downgrade_hint is True
        assert impact.impact_severity == "high"
        assert "policy_catalyst_active" in impact.conflict_contributors
        assert impact.routing.has_explanation_evidence is True

    def test_extra_fields_forbidden(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ExternalEventImpact(
                source_event_id="x",
                source_event_type=ExternalEventType.OTHER,
                unknown_field="bad",  # type: ignore[call-arg]
            )
