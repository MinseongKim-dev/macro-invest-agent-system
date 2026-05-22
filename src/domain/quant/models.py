"""Quant Score domain models.

These models are the stable contract between the Quant Scoring Engine and
downstream consumers (regime confidence, signal confidence, conflict surface).

Design principles
-----------------
- All scores are in [0.0, 1.0] — higher = more supportive / bullish / healthy.
- Each dimension produces one :class:`DimensionScore`.
- A :class:`QuantScoreBundle` groups all dimension scores for a single snapshot.
- The bundle also carries three lightweight secondary measures:
  * ``momentum``    — cross-dimension directional momentum [0.0, 1.0]
  * ``breadth``     — proportion of known/non-UNKNOWN dimensions [0.0, 1.0]
  * ``change_intensity`` — average absolute rate-of-change estimate [0.0, 1.0]
- ``overall_support`` is a simple breadth-weighted mean of primary dimension
  scores, clamped to [0.0, 1.0].

Consumers
---------
- ``domain/macro/regime_mapping.py`` — confidence refactor (Chunk 2)
- ``domain/signals/conflict.py`` — conflict surface (Chunk 3)
- ``services/quant_scoring_service.py`` — service wrapper
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ScoreDimension(StrEnum):
    """Named scoring dimensions produced by the Quant Scoring Engine."""

    GROWTH = "growth"
    INFLATION = "inflation"
    LABOR = "labor"
    POLICY = "policy"
    FINANCIAL_CONDITIONS = "financial_conditions"


class ScoreLevel(StrEnum):
    """Coarse human-readable label for a dimension score.

    Mapping (applied after scoring):
    - ``strong``   → score >= 0.70
    - ``moderate`` → score >= 0.40
    - ``weak``     → score < 0.40
    - ``unknown``  → no data available to score this dimension
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNKNOWN = "unknown"


def _score_to_level(score: float | None) -> ScoreLevel:
    if score is None:
        return ScoreLevel.UNKNOWN
    if score >= 0.70:
        return ScoreLevel.STRONG
    if score >= 0.40:
        return ScoreLevel.MODERATE
    return ScoreLevel.WEAK


class DimensionScore(BaseModel, extra="forbid"):
    """Quantitative score for a single macro dimension.

    Attributes:
        dimension: The scored dimension.
        score: Raw score in [0.0, 1.0] or None when no data is available.
        level: Human-readable label derived from ``score``.
        contributing_states: Snapshot states that were used to derive this score.
            Useful for downstream rationale building and debugging.
    """

    dimension: ScoreDimension
    score: float | None = Field(
        default=None,
        description="Raw score [0.0, 1.0] or None when no data available",
        ge=0.0,
        le=1.0,
    )
    level: ScoreLevel = Field(default=ScoreLevel.UNKNOWN)
    contributing_states: list[str] = Field(
        default_factory=list,
        description="Snapshot state values that contributed to this score",
    )


class QuantScoreBundle(BaseModel, extra="forbid"):
    """Full quant score bundle for a single macro snapshot.

    Primary dimension scores
    ------------------------
    One :class:`DimensionScore` per :class:`ScoreDimension`.

    Secondary measures
    ------------------
    - ``momentum``         — directional momentum across dimensions [0.0, 1.0]
    - ``breadth``          — fraction of dimensions with known scores [0.0, 1.0]
    - ``change_intensity`` — estimated rate-of-change signal [0.0, 1.0]
    - ``overall_support``  — breadth-weighted mean of dimension scores [0.0, 1.0]

    Interpretation
    --------------
    - ``overall_support >= 0.65`` → quant-supported high confidence
    - ``overall_support >= 0.40`` → quant-supported medium confidence
    - ``overall_support < 0.40``  → weak quant support → low confidence
    - ``breadth < 0.60``          → insufficient coverage → cap at medium
    """

    growth: DimensionScore
    inflation: DimensionScore
    labor: DimensionScore
    policy: DimensionScore
    financial_conditions: DimensionScore

    # Secondary measures
    momentum: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Cross-dimension directional momentum [0.0, 1.0]",
    )
    breadth: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Proportion of dimensions with known (non-None) scores [0.0, 1.0]",
    )
    change_intensity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Estimated average absolute rate-of-change signal [0.0, 1.0]",
    )
    overall_support: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Breadth-weighted mean of known dimension scores [0.0, 1.0]",
    )

    @property
    def dimensions(self) -> list[DimensionScore]:
        """Return all dimension scores as an ordered list."""
        return [
            self.growth,
            self.inflation,
            self.labor,
            self.policy,
            self.financial_conditions,
        ]

    @property
    def known_dimensions(self) -> list[DimensionScore]:
        """Return only dimensions with non-None scores."""
        return [d for d in self.dimensions if d.score is not None]

    def get_dimension(self, dim: ScoreDimension) -> DimensionScore:
        """Look up a dimension score by :class:`ScoreDimension`."""
        mapping = {
            ScoreDimension.GROWTH: self.growth,
            ScoreDimension.INFLATION: self.inflation,
            ScoreDimension.LABOR: self.labor,
            ScoreDimension.POLICY: self.policy,
            ScoreDimension.FINANCIAL_CONDITIONS: self.financial_conditions,
        }
        return mapping[dim]
