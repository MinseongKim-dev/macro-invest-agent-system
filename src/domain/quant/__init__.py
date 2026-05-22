"""Quant Scoring Engine v1 — domain layer.

Provides a lightweight, deterministic quantitative scoring layer beneath
the regime and signal interpretation layers.  All scoring is rule-based,
testable, and isolated from presentation code.

Public surface
--------------
- :class:`~domain.quant.models.ScoreDimension` — enum of scored dimensions
- :class:`~domain.quant.models.DimensionScore` — single dimension score
- :class:`~domain.quant.models.QuantScoreBundle` — full bundle for a snapshot
- :func:`~domain.quant.scoring.score_snapshot` — main entry point
"""
