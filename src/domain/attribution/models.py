"""Attribution domain models for Catalyst-Aware Interpretation (Chapter 8).

This module defines:
* ``AttributionRule`` — a deterministic matching rule that links an event type
  to a macro indicator type within a maximum lag window.
* ``ChangeAttribution`` — the read model produced when a ``FeatureDelta`` is
  matched against candidate external events using attribution rules.

Architecture notes
------------------
* Attribution is **advisory** — it adds candidate-cause context to analytical
  outputs.  It never directly overrides regime labels, signal directions, or
  confidence levels.
* Rules are keyed on ``(event_type, indicator_type)`` pairs.  Fine-grained
  per-entity or per-provider rules are deferred to later phases.
* ``ChangeAttribution`` carries a ``catalyst_context`` block that downstream
  explanation and conflict layers can embed in their outputs.
* All timestamps are UTC-aware ``datetime`` objects.

Design constraints
------------------
* **Deterministic** — same inputs always produce the same attribution output.
* **Heuristic** — matching rules reflect analyst domain knowledge, not
  statistically calibrated causal models.  All outputs are explicitly labelled
  advisory.
* **Non-overriding** — attribution cannot change regime or signal outputs
  directly.
* **Bounded** — only the closest event within the lag window is selected as
  the primary candidate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, model_validator

from domain.attribution.enums import AttributionConfidence, AttributionMatchStatus

# ---------------------------------------------------------------------------
# Attribution Rule
# ---------------------------------------------------------------------------


class AttributionRule(BaseModel, extra="forbid"):
    """A deterministic rule linking an event type to a macro indicator type.

    An ``AttributionRule`` expresses: "a ``{event_type}`` event occurring
    within ``{max_lag_days}`` days before a feature delta in ``{indicator_type}``
    is a plausible candidate cause for that delta."

    Attributes:
        rule_id: Unique identifier for this rule.
        event_type: The external event category that may be the cause
            (value from :class:`~domain.events.enums.ExternalEventType`).
        indicator_type: The macro indicator type affected
            (value from :class:`~domain.macro.enums.MacroIndicatorType` or a
            free-form indicator string for extensibility).
        max_lag_days: Maximum calendar days between the event's ``occurred_at``
            and the snapshot ``as_of_date`` for the delta to qualify as a match.
        description: Optional human-readable rule description.
        is_active: Whether the rule is active.  Inactive rules are skipped
            during matching.
    """

    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(..., min_length=1, description="ExternalEventType string value")
    indicator_type: str = Field(
        ..., min_length=1, description="MacroIndicatorType string value or free-form indicator"
    )
    max_lag_days: int = Field(
        ..., ge=0, description="Maximum days between event and delta for a match"
    )
    description: str | None = Field(default=None)
    is_active: bool = Field(default=True)

    @model_validator(mode="after")
    def _validate_max_lag(self) -> AttributionRule:
        if self.max_lag_days < 0:
            msg = "max_lag_days must be >= 0"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Candidate attribution context
# ---------------------------------------------------------------------------


class CandidateEventContext(BaseModel, extra="forbid"):
    """Minimal context for a candidate external event contributing to an attribution.

    Attributes:
        event_id: The candidate event's unique identifier.
        event_type: The event's type string.
        title: Short human-readable event title.
        source: Source of the event.
        occurred_at: UTC datetime when the event occurred.
        lag_days: Measured calendar days between event and delta.
        match_status: Whether this candidate fully or partially satisfies the rule.
        reliability_tier: Source reliability tier (heuristic).
    """

    event_id: str
    event_type: str
    title: str
    source: str
    occurred_at: datetime
    lag_days: int
    match_status: AttributionMatchStatus
    reliability_tier: str = Field(default="unknown")


# ---------------------------------------------------------------------------
# Change Attribution (read model)
# ---------------------------------------------------------------------------


class CatalystContext(BaseModel, extra="forbid"):
    """Structured catalyst context block for embedding in explanation DTOs.

    This is the analyst-facing summary of what external event(s) may have
    contributed to an observed feature delta.

    Attributes:
        indicator_type: The macro indicator that changed.
        candidate_event_id: ID of the primary candidate event; ``None`` when
            unattributed.
        candidate_event_title: Short title of the primary candidate event.
        candidate_event_type: Type of the primary candidate event.
        lag_days: Days between the event and the observed delta; ``None`` when
            unattributed.
        confidence: Advisory confidence level.
        advisory_note: Analyst-facing explanation of the attribution result.
        rule_id: The rule that triggered this attribution; ``None`` when
            unattributed.
    """

    indicator_type: str
    candidate_event_id: str | None = None
    candidate_event_title: str | None = None
    candidate_event_type: str | None = None
    lag_days: int | None = None
    confidence: AttributionConfidence
    advisory_note: str
    rule_id: str | None = None


class ChangeAttribution(BaseModel, extra="forbid"):
    """Read model linking a ``FeatureDelta`` to candidate external event causes.

    This is the output of the attribution engine for a single feature delta.
    It is always advisory — it adds context to existing analytical outputs
    without overriding them.

    Attributes:
        attribution_id: Unique identifier for this attribution result.
        indicator_type: The macro indicator that changed.
        direction: The observed change direction (from ``FeatureDelta``).
        delta: The measured change value; ``None`` if no prior was available.
        confidence: Advisory confidence level of the best attribution found.
        candidates: All candidate events evaluated (best match first).
        catalyst_context: Structured context block for downstream embedding.
        attributed_at: UTC datetime when this attribution was computed.
    """

    attribution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    indicator_type: str
    direction: str = Field(
        ..., description="'increased' | 'decreased' | 'unchanged' | 'no_prior'"
    )
    delta: float | None = None
    confidence: AttributionConfidence
    candidates: list[CandidateEventContext] = Field(default_factory=list)
    catalyst_context: CatalystContext
    attributed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def is_attributed(self) -> bool:
        """Return True when at least one candidate event was identified."""
        return self.confidence != AttributionConfidence.UNATTRIBUTED

    def best_candidate(self) -> CandidateEventContext | None:
        """Return the highest-confidence candidate event, or ``None``."""
        return self.candidates[0] if self.candidates else None

    @property
    def lag_days(self) -> int | None:
        """Return the lag days from the best candidate, or ``None``."""
        best = self.best_candidate()
        return best.lag_days if best is not None else None

    def with_lag_window(self, max_days: int) -> bool:
        """Return True when the best candidate falls within *max_days*."""
        best = self.best_candidate()
        if best is None:
            return False
        return best.lag_days <= max_days


# ---------------------------------------------------------------------------
# Attribution run result
# ---------------------------------------------------------------------------


class AttributionRunResult(BaseModel, extra="forbid"):
    """Container for all attribution results computed for a snapshot comparison.

    Attributes:
        snapshot_id: The snapshot ID for which attributions were computed;
            ``None`` when not associated with a persisted snapshot.
        as_of_date: The as-of date of the comparison.
        attributions: Attribution result per feature delta (changed indicators only).
        total_attributed: Count of deltas with at least one candidate.
        total_unattributed: Count of deltas with no candidate.
        computed_at: UTC datetime when this run was computed.
    """

    snapshot_id: str | None = None
    as_of_date: datetime
    attributions: list[ChangeAttribution] = Field(default_factory=list)
    total_attributed: int = Field(default=0)
    total_unattributed: int = Field(default=0)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _compute_counts(self) -> AttributionRunResult:
        attributed = sum(1 for a in self.attributions if a.is_attributed())
        object.__setattr__(self, "total_attributed", attributed)
        object.__setattr__(self, "total_unattributed", len(self.attributions) - attributed)
        return self

    def summary_context(self) -> list[CatalystContext]:
        """Return the catalyst context blocks for all attributed deltas."""
        return [a.catalyst_context for a in self.attributions if a.is_attributed()]
