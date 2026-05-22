"""Interpreted external event impact models (Chapter 7, Chunk 2).

This module defines ``ExternalEventImpact`` — the structured downstream
effects produced by the Event Impact Adapter when it processes a
:class:`~domain.events.models.NormalizedExternalEvent`.

Architecture boundary
---------------------
* This is **interpretation layer output** — distinct from both raw source
  payloads and normalized event records.
* Impact objects are conservative by design: they add evidence, caveats,
  and conflict context to existing analytical outputs.  They do **not**
  override regime labels or signal directions directly.
* Routing priority (from spec):
  1. explanation evidence
  2. caveats / notes
  3. conflict enrichment
  4. confidence downgrade hint
  5. limited score/signal adjustment (deferred to later PRs)
  6. direct signal override (deferred — must be explicitly justified)

Design notes
------------
* ``ExternalEventImpactRouting`` is a typed summary of which downstream
  effects are populated, so consumers can branch without checking nulls.
* All text fields are analyst-facing strings; no raw event content is
  copied here directly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.events.enums import ExternalEventType


class ExternalEventImpactRouting(BaseModel, extra="forbid"):
    """Summary flags indicating which downstream effects are populated.

    Used by downstream consumers to decide which parts of the impact to
    apply without checking every optional field for emptiness.
    """

    has_explanation_evidence: bool = Field(
        default=False,
        description="True when explanation_evidence is non-empty",
    )
    has_caveat_notes: bool = Field(
        default=False,
        description="True when caveat_notes is non-empty",
    )
    has_conflict_contributors: bool = Field(
        default=False,
        description="True when conflict_contributors is non-empty",
    )
    has_confidence_downgrade: bool = Field(
        default=False,
        description="True when confidence_downgrade_hint is True",
    )
    has_change_context: bool = Field(
        default=False,
        description="True when change_context_annotation is not None",
    )


class ExternalEventImpact(BaseModel, extra="forbid"):
    """Conservative structured downstream effects from a single external event.

    This is the output of the Event Impact Adapter.  It carries interpreted
    analytical effects that downstream layers (explanation, conflict, confidence)
    can safely consume without being aware of the raw event source.

    Impact semantics
    ----------------
    * ``explanation_evidence`` — bullet points to include in analyst explanations.
    * ``caveat_notes`` — caveats to surface alongside confidence/conflict output.
    * ``conflict_contributors`` — labels identifying external analytical tension.
    * ``confidence_downgrade_hint`` — signals that confidence should be reduced;
      does not specify the magnitude (left to the confidence layer).
    * ``confidence_downgrade_reason`` — analyst-facing rationale for the hint.
    * ``change_context_annotation`` — free-form note for change-detection context.
    * ``impact_severity`` — heuristic severity: ``"low"`` | ``"moderate"`` | ``"high"``.
    * ``routing`` — typed summary of which effects are populated.

    Provenance
    ----------
    * ``source_event_id`` — traceability back to the source event.
    * ``source_event_type`` — event type for consumer filtering.
    * ``is_heuristic`` — always ``True`` in v1; mapping rules are heuristic.

    Constraints
    -----------
    * This object does NOT override regime labels or signal directions.
    * ``confidence_downgrade_hint=True`` is advisory — the confidence layer
      decides whether and how much to adjust.
    * All text is analyst-facing; no raw source content appears here.
    """

    source_event_id: str = Field(..., description="ID of the source NormalizedExternalEvent")
    source_event_type: ExternalEventType = Field(
        ..., description="Event type of the source event (for consumer filtering)"
    )

    # Conservative downstream effects (priority order from spec)
    explanation_evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Analyst-facing bullet points for inclusion in explanation rationale. "
            "Priority 1 downstream effect."
        ),
    )
    caveat_notes: list[str] = Field(
        default_factory=list,
        description=(
            "Caveats to surface alongside confidence/conflict. "
            "Priority 2 downstream effect."
        ),
    )
    conflict_contributors: list[str] = Field(
        default_factory=list,
        description=(
            "Labels identifying external analytical tension for the conflict surface. "
            "Priority 3 downstream effect."
        ),
    )
    confidence_downgrade_hint: bool = Field(
        default=False,
        description=(
            "Advisory signal that confidence should be reduced. "
            "Priority 4 downstream effect. Does not specify magnitude."
        ),
    )
    confidence_downgrade_reason: str | None = Field(
        default=None,
        description="Analyst-facing reason for the confidence downgrade hint.",
    )
    change_context_annotation: str | None = Field(
        default=None,
        description=(
            "Free-form note for change-detection context. "
            "Priority 5 downstream effect."
        ),
    )

    # Metadata
    impact_severity: str = Field(
        default="low",
        description="Heuristic impact severity: low | moderate | high",
    )
    affected_domains: list[str] = Field(
        default_factory=list,
        description="Macro domains affected by this event (forwarded from normalized event)",
    )
    routing: ExternalEventImpactRouting = Field(
        default_factory=ExternalEventImpactRouting,
        description="Typed summary of which downstream effects are populated",
    )
    is_heuristic: bool = Field(
        default=True,
        description=(
            "Always True in v1 — impact mapping rules are heuristic and not "
            "statistically validated."
        ),
    )
