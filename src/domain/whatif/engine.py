"""What-if scenario engine — deterministic, side-effect-free.

Applies a :class:`~domain.whatif.models.WhatIfScenario` on top of the
current synthesis inputs, re-runs
:func:`~domain.synthesis.engine.compute_synthesis_view`, and returns a
:class:`~domain.whatif.models.WhatIfResult` containing the before/after
pair.

Usage
-----
::

    from src.domain.whatif.engine import compute_whatif_result
    from src.domain.whatif.models import WhatIfScenario

    scenario = WhatIfScenario(
        label="vix_spike",
        quant_support_override="strong_negative",
        avg_var_95_override=7.5,
    )
    result = compute_whatif_result(scenario=scenario, baseline=current_view, ...)
"""

from __future__ import annotations

from src.domain.synthesis.engine import compute_synthesis_view
from src.domain.synthesis.models import SynthesisView
from src.domain.whatif.models import WhatIfResult, WhatIfScenario


def compute_whatif_result(
    *,
    scenario: WhatIfScenario,
    baseline: SynthesisView,
    regime_label: str,
    macro_confidence: float,
    quant_overall_support: str,
    conflict_status: str,
    avg_var_95: float,
    worst_mdd_pct: float,
) -> WhatIfResult:
    """Apply *scenario* overrides and re-run the synthesis engine.

    Each ``*_override`` field in *scenario* that is not ``None`` replaces
    the corresponding baseline input.  Fields that are ``None`` keep the
    original value.

    Args:
        scenario:             The :class:`~domain.whatif.models.WhatIfScenario`
                              to evaluate.
        baseline:             The current :class:`~domain.synthesis.models.SynthesisView`
                              (pre-computed from the unmodified inputs).
        regime_label:         Current macro regime label.
        macro_confidence:     Current macro confidence [0.0, 1.0].
        quant_overall_support: Current quant support label.
        conflict_status:      Current conflict surface label.
        avg_var_95:           Current average portfolio VaR (%).
        worst_mdd_pct:        Current worst max-drawdown (%).

    Returns:
        :class:`~domain.whatif.models.WhatIfResult` with the projected
        :class:`~domain.synthesis.models.SynthesisView` and delta metrics.
    """
    projected_regime      = scenario.regime_label_override    or regime_label
    projected_confidence  = scenario.macro_confidence_override if scenario.macro_confidence_override is not None else macro_confidence
    projected_quant       = scenario.quant_support_override   or quant_overall_support
    projected_conflict    = scenario.conflict_status_override  or conflict_status
    projected_var_95      = scenario.avg_var_95_override      if scenario.avg_var_95_override      is not None else avg_var_95
    projected_mdd         = scenario.worst_mdd_pct_override   if scenario.worst_mdd_pct_override   is not None else worst_mdd_pct

    projected: SynthesisView = compute_synthesis_view(
        regime_label=projected_regime,
        macro_confidence=projected_confidence,
        quant_overall_support=projected_quant,
        conflict_status=projected_conflict,
        avg_var_95=projected_var_95,
        worst_mdd_pct=projected_mdd,
    )

    return WhatIfResult(
        scenario_label=scenario.label,
        baseline=baseline,
        projected=projected,
        status_changed=projected.synthesis_status != baseline.synthesis_status,
        conviction_delta=round(
            projected.conviction_score - baseline.conviction_score, 4
        ),
    )
