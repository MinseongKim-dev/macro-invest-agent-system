"""Phase 3 macro regime schema and vocabulary contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from domain.macro.snapshot import DegradedStatus
from domain.quant.models import QuantScoreBundle
from pipelines.ingestion.models import FreshnessStatus


class RegimeLabel(StrEnum):
    GOLDILOCKS = "goldilocks"
    DISINFLATION = "disinflation"
    SLOWDOWN = "slowdown"
    REFLATION = "reflation"
    STAGFLATION_RISK = "stagflation_risk"
    CONTRACTION = "contraction"
    POLICY_TIGHTENING_DRAG = "policy_tightening_drag"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class RegimeFamily(StrEnum):
    EXPANSION = "expansion"
    INFLATION_TRANSITION = "inflation_transition"
    LATE_CYCLE = "late_cycle"
    DOWNSHIFT = "downshift"
    CONTRACTION = "contraction"
    UNCERTAIN = "uncertain"


class RegimeConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RegimeTransitionType(StrEnum):
    INITIAL = "initial"
    UNCHANGED = "unchanged"
    SHIFT = "shift"
    WEAKENING = "weakening"
    STRENGTHENING = "strengthening"
    UNKNOWN = "unknown"


REGIME_LABEL_FAMILY_MAP: dict[RegimeLabel, RegimeFamily] = {
    RegimeLabel.GOLDILOCKS: RegimeFamily.EXPANSION,
    RegimeLabel.DISINFLATION: RegimeFamily.INFLATION_TRANSITION,
    RegimeLabel.SLOWDOWN: RegimeFamily.DOWNSHIFT,
    RegimeLabel.REFLATION: RegimeFamily.INFLATION_TRANSITION,
    RegimeLabel.STAGFLATION_RISK: RegimeFamily.LATE_CYCLE,
    RegimeLabel.CONTRACTION: RegimeFamily.CONTRACTION,
    RegimeLabel.POLICY_TIGHTENING_DRAG: RegimeFamily.LATE_CYCLE,
    RegimeLabel.MIXED: RegimeFamily.UNCERTAIN,
    RegimeLabel.UNCLEAR: RegimeFamily.UNCERTAIN,
}


def regime_family_for_label(label: RegimeLabel) -> RegimeFamily:
    return REGIME_LABEL_FAMILY_MAP[label]


class RegimeTransition(BaseModel, extra="forbid"):
    transition_from_prior: str | None = Field(default=None, description="Prior regime label")
    transition_type: RegimeTransitionType = Field(default=RegimeTransitionType.UNKNOWN)
    changed: bool = Field(default=False)


class MacroRegime(BaseModel, extra="forbid"):
    """Structured macro regime contract for a given as-of date."""

    regime_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    as_of_date: date
    regime_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    regime_label: RegimeLabel = Field(default=RegimeLabel.UNCLEAR)
    regime_family: RegimeFamily = Field(default=RegimeFamily.UNCERTAIN)
    supporting_snapshot_id: str = Field(..., min_length=1)
    supporting_states: dict[str, str] = Field(default_factory=dict)

    confidence: RegimeConfidence = Field(default=RegimeConfidence.LOW)
    freshness_status: FreshnessStatus = Field(default=FreshnessStatus.UNKNOWN)
    degraded_status: DegradedStatus = Field(default=DegradedStatus.UNKNOWN)
    missing_inputs: list[str] = Field(default_factory=list)

    quant_scores: QuantScoreBundle | None = Field(
        default=None,
        description=(
            "Quant Scoring Engine v1 output for this regime's supporting snapshot. "
            "Present when the regime was built via MacroRegimeService (not bootstrap/seed). "
            "Downstream consumers (signal confidence, conflict surface) should use this "
            "to refine their outputs rather than relying solely on categorical states."
        ),
    )

    transition: RegimeTransition = Field(default_factory=RegimeTransition)
    rationale_summary: str = Field(default="")
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Pre-computed analyst-facing warnings summarising degraded, stale, "
            "missing-input, or bootstrap conditions.  Populated at build time so "
            "downstream API and UI layers do not need to re-derive these states "
            "from multiple individual fields."
        ),
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Arbitrary key/value metadata attached at regime creation time. "
            "Seeded/bootstrap regimes carry: seeded='true', source='synthetic_seed'. "
            "Production regimes leave this empty."
        ),
    )

    @model_validator(mode="after")
    def validate_label_family_alignment(self) -> MacroRegime:
        expected_family = regime_family_for_label(self.regime_label)
        if self.regime_family != expected_family:
            msg = (
                f"regime_family '{self.regime_family.value}' must match "
                f"regime_label '{self.regime_label.value}'"
            )
            raise ValueError(msg)
        return self
