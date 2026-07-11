"""What-if scenario domain models.

A :class:`WhatIfScenario` describes a hypothetical change to the synthesis
engine inputs.  :class:`WhatIfResult` captures the baseline and projected
:class:`~domain.synthesis.models.SynthesisView` so callers can compare
conviction scores and status transitions side-by-side.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.synthesis.models import SynthesisView


class WhatIfScenario(BaseModel, extra="forbid"):
    """A single what-if projection — overrides one or more synthesis inputs.

    All override fields are optional.  ``None`` means "keep the baseline
    value."  At least one override should be set; a scenario with no
    overrides is a no-op that still validates correctly.

    Attributes:
        label:                    Human-readable scenario name.
        regime_label_override:    Replace the macro regime label.
        macro_confidence_override: Replace macro confidence [0.0, 1.0].
        quant_support_override:   Replace the quant support label.
        conflict_status_override: Replace the conflict surface label.
        avg_var_95_override:      Replace average portfolio VaR (%, ≥ 0).
        worst_mdd_pct_override:   Replace worst MDD (%, ≤ 0).
    """

    label: str
    regime_label_override: str | None = None
    macro_confidence_override: float | None = Field(default=None, ge=0.0, le=1.0)
    quant_support_override: str | None = None
    conflict_status_override: str | None = None
    avg_var_95_override: float | None = Field(default=None, ge=0.0)
    worst_mdd_pct_override: float | None = Field(default=None, le=0.0)


class WhatIfResult(BaseModel, extra="forbid"):
    """Before/after synthesis comparison for a single scenario.

    Attributes:
        scenario_label:   The label from the originating :class:`WhatIfScenario`.
        baseline:         :class:`~domain.synthesis.models.SynthesisView` with
                          the original unmodified inputs.
        projected:        :class:`~domain.synthesis.models.SynthesisView` with
                          the scenario overrides applied.
        status_changed:   ``True`` when ``projected.synthesis_status`` differs
                          from ``baseline.synthesis_status``.
        conviction_delta: ``projected.conviction_score − baseline.conviction_score``,
                          rounded to 4 decimal places.  Negative means risk
                          increased; positive means conditions improved.
    """

    scenario_label: str
    baseline: SynthesisView
    projected: SynthesisView
    status_changed: bool
    conviction_delta: float
