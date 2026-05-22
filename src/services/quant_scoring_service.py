"""Quant Scoring Service.

Thin service wrapper around :func:`~domain.quant.scoring.score_snapshot`.
Provides a composable, injectable interface for downstream consumers
(regime service, signal service, API layer).

This service is intentionally minimal — v1 only needs synchronous
snapshot-to-score computation.  Future iterations may add caching,
time-series delta scoring, or calibration adjustments here.
"""

from __future__ import annotations

from domain.macro.snapshot import MacroSnapshotState
from domain.quant.models import QuantScoreBundle
from domain.quant.scoring import score_snapshot


class QuantScoringService:
    """Compute quant scores from a macro snapshot.

    The service is stateless and produces deterministic output given the
    same snapshot input.  It can be instantiated once and shared across
    callers without side effects.
    """

    def compute(self, snapshot: MacroSnapshotState) -> QuantScoreBundle:
        """Compute a :class:`~domain.quant.models.QuantScoreBundle` from *snapshot*.

        Args:
            snapshot: A fully-derived macro snapshot state.

        Returns:
            :class:`~domain.quant.models.QuantScoreBundle` with per-dimension
            scores and secondary measures.
        """
        return score_snapshot(snapshot)
