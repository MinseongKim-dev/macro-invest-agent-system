"""Unit tests for src/domain/whatif/engine.py — deterministic what-if projections.

No database, no I/O — all inputs are constructed in-process.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domain.synthesis.engine import compute_synthesis_view
from src.domain.synthesis.models import SynthesisStatus
from src.domain.whatif.engine import compute_whatif_result
from src.domain.whatif.models import WhatIfResult, WhatIfScenario

# ── helpers ───────────────────────────────────────────────────────────────────

_BULLISH_INPUTS = {
    "regime_label":         "expansion",
    "macro_confidence":     0.85,
    "quant_overall_support": "strong_positive",
    "conflict_status":      "low_conflict",
    "avg_var_95":           1.2,
    "worst_mdd_pct":        -5.0,
}


def _baseline() -> dict[str, object]:
    return dict(_BULLISH_INPUTS)


def _compute_baseline_view() -> object:
    return compute_synthesis_view(**_BULLISH_INPUTS)  # type: ignore[arg-type]


# ── WhatIfScenario validation ─────────────────────────────────────────────────


def test_scenario_all_nones_is_valid() -> None:
    scenario = WhatIfScenario(label="no_change")
    assert scenario.regime_label_override is None
    assert scenario.avg_var_95_override is None


def test_scenario_macro_confidence_bounds() -> None:
    s = WhatIfScenario(label="test", macro_confidence_override=1.0)
    assert s.macro_confidence_override == pytest.approx(1.0)


def test_scenario_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        WhatIfScenario(label="bad", macro_confidence_override=1.5)


def test_scenario_rejects_positive_mdd() -> None:
    with pytest.raises(ValidationError):
        WhatIfScenario(label="bad", worst_mdd_pct_override=5.0)


def test_scenario_rejects_negative_var() -> None:
    with pytest.raises(ValidationError):
        WhatIfScenario(label="bad", avg_var_95_override=-1.0)


# ── compute_whatif_result — output contract ───────────────────────────────────


def test_whatif_result_returns_correct_type() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(label="noop")
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert isinstance(result, WhatIfResult)


def test_whatif_noop_scenario_status_unchanged() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(label="noop")
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.status_changed is False
    assert result.conviction_delta == pytest.approx(0.0, abs=1e-4)


def test_whatif_noop_scenario_baseline_and_projected_equal() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(label="noop")
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.projected.synthesis_status == result.baseline.synthesis_status


# ── compute_whatif_result — override routing ──────────────────────────────────


def test_var_spike_triggers_risk_dominant() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(label="var_spike", avg_var_95_override=6.0)
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.projected.synthesis_status == SynthesisStatus.RISK_DOMINANT
    assert result.status_changed is True


def test_mdd_crash_triggers_risk_dominant() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(label="market_crash", worst_mdd_pct_override=-45.0)
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.projected.synthesis_status == SynthesisStatus.RISK_DOMINANT
    assert result.conviction_delta < 0.0


def test_recession_regime_triggers_cautious() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(
        label="recession",
        regime_label_override="contraction",
        conflict_status_override="low_conflict",
    )
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.projected.synthesis_status == SynthesisStatus.ALIGNED_CAUTIOUS
    assert result.status_changed is True


def test_high_conflict_triggers_mixed_signals() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(label="conflict_spike", conflict_status_override="high_conflict")
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.projected.synthesis_status == SynthesisStatus.MIXED_SIGNALS


def test_improved_confidence_increases_conviction() -> None:
    low_conf_inputs = {**_BULLISH_INPUTS, "macro_confidence": 0.4}
    baseline = compute_synthesis_view(**low_conf_inputs)  # type: ignore[arg-type]
    scenario = WhatIfScenario(label="confidence_boost", macro_confidence_override=0.9)
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **low_conf_inputs)  # type: ignore[arg-type]
    assert result.conviction_delta > 0.0


def test_quant_downgrade_from_strong_to_negative() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(
        label="quant_reversal",
        quant_support_override="strong_negative",
        conflict_status_override="low_conflict",
    )
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.projected.synthesis_status == SynthesisStatus.ALIGNED_CAUTIOUS


def test_scenario_label_preserved_in_result() -> None:
    baseline = _compute_baseline_view()
    scenario = WhatIfScenario(label="my_scenario", avg_var_95_override=3.0)
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.scenario_label == "my_scenario"


def test_conviction_delta_sign_matches_status_direction() -> None:
    baseline = _compute_baseline_view()
    # Worsening: crash
    scenario = WhatIfScenario(label="crash", avg_var_95_override=7.0, worst_mdd_pct_override=-50.0)
    result = compute_whatif_result(scenario=scenario, baseline=baseline, **_baseline())  # type: ignore[arg-type]
    assert result.conviction_delta <= 0.0
