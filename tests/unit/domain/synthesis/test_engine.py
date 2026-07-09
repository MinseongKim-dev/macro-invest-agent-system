"""Unit tests for src/domain/synthesis/engine.py — deterministic synthesis rules.

No database, no I/O — all inputs are constructed in-process.
"""

from __future__ import annotations

import pytest

from src.domain.synthesis.engine import (
    _compute_risk_penalty,
    _count_engines,
    _parse_conflict_level,
    compute_synthesis_view,
)
from src.domain.synthesis.models import SynthesisStatus, SynthesisView

# ── helpers ───────────────────────────────────────────────────────────────────


def _base_kwargs(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "regime_label": "expansion",
        "macro_confidence": 0.8,
        "quant_overall_support": "strong_positive",
        "conflict_status": "low",
        "avg_var_95": 1.5,
        "worst_mdd_pct": -8.0,
    }
    defaults.update(overrides)
    return defaults


# ── _count_engines ────────────────────────────────────────────────────────────


def test_count_engines_all_four() -> None:
    assert _count_engines("expansion", "strong_positive", "low", 1.5) == 4


def test_count_engines_unknown_regime_not_counted() -> None:
    assert _count_engines("unknown", "strong_positive", "low", 1.5) == 3


def test_count_engines_no_var_not_counted() -> None:
    assert _count_engines("expansion", "strong_positive", "low", 0.0) == 3


def test_count_engines_two_missing() -> None:
    assert _count_engines("unknown", "no_data", "low", 1.5) == 2


def test_count_engines_all_missing() -> None:
    assert _count_engines("unknown", "no_data", "unknown", 0.0) == 0


# ── _parse_conflict_level ─────────────────────────────────────────────────────


def test_parse_conflict_level_low() -> None:
    assert _parse_conflict_level("low_conflict") == 1


def test_parse_conflict_level_medium() -> None:
    assert _parse_conflict_level("medium") == 2


def test_parse_conflict_level_high() -> None:
    assert _parse_conflict_level("high_conflict") == 3


def test_parse_conflict_level_critical() -> None:
    assert _parse_conflict_level("critical") == 3


def test_parse_conflict_level_unknown() -> None:
    assert _parse_conflict_level("unknown") == 0


# ── _compute_risk_penalty ─────────────────────────────────────────────────────


def test_risk_penalty_zero_for_benign_inputs() -> None:
    assert _compute_risk_penalty(0.5, -5.0) == pytest.approx(0.0)


def test_risk_penalty_var_only_contribution() -> None:
    # VaR=6 → var_weight=(6-1)/10=0.5; MDD=-5 → mdd_weight=0
    penalty = _compute_risk_penalty(6.0, -5.0)
    assert penalty == pytest.approx(0.5, abs=1e-4)


def test_risk_penalty_mdd_only_contribution() -> None:
    # VaR=0 → var_weight=0; MDD=-40 → mdd_weight=(40-10)/60=0.5
    penalty = _compute_risk_penalty(0.0, -40.0)
    assert penalty == pytest.approx(0.5, abs=1e-4)


def test_risk_penalty_clamped_to_one() -> None:
    # Extreme inputs must not exceed 1.0
    assert _compute_risk_penalty(100.0, -100.0) == pytest.approx(1.0)


def test_risk_penalty_partial() -> None:
    # VaR=3.5 → (3.5-1)/10=0.25; MDD=-25 → (25-10)/60=0.25 → total 0.5
    assert _compute_risk_penalty(3.5, -25.0) == pytest.approx(0.5, abs=1e-4)


# ── compute_synthesis_view — status routing ───────────────────────────────────


def test_synthesis_insufficient_data_when_one_engine() -> None:
    result = compute_synthesis_view(
        regime_label="unknown",
        macro_confidence=0.5,
        quant_overall_support="no_data",
        conflict_status="unknown",
        avg_var_95=0.0,
        worst_mdd_pct=0.0,
    )
    assert result.synthesis_status == SynthesisStatus.INSUFFICIENT_DATA
    assert result.conviction_score == pytest.approx(0.0)


def test_synthesis_risk_dominant_var() -> None:
    result = compute_synthesis_view(**_base_kwargs(avg_var_95=5.5))  # type: ignore[arg-type]
    assert result.synthesis_status == SynthesisStatus.RISK_DOMINANT
    assert result.dominant_concern == "elevated_var"


def test_synthesis_risk_dominant_mdd() -> None:
    result = compute_synthesis_view(**_base_kwargs(worst_mdd_pct=-41.0))  # type: ignore[arg-type]
    assert result.synthesis_status == SynthesisStatus.RISK_DOMINANT
    assert result.dominant_concern == "severe_drawdown"


def test_synthesis_aligned_bullish() -> None:
    result = compute_synthesis_view(**_base_kwargs())  # type: ignore[arg-type]
    assert result.synthesis_status == SynthesisStatus.ALIGNED_BULLISH
    assert result.dominant_concern is None


def test_synthesis_aligned_bullish_recovery_regime() -> None:
    result = compute_synthesis_view(**_base_kwargs(regime_label="recovery"))  # type: ignore[arg-type]
    assert result.synthesis_status == SynthesisStatus.ALIGNED_BULLISH


def test_synthesis_aligned_cautious_regime() -> None:
    result = compute_synthesis_view(
        **_base_kwargs(  # type: ignore[arg-type]
            regime_label="contraction",
            conflict_status="low",
        )
    )
    assert result.synthesis_status == SynthesisStatus.ALIGNED_CAUTIOUS
    assert result.dominant_concern == "cautious_macro"


def test_synthesis_aligned_cautious_weak_quant() -> None:
    result = compute_synthesis_view(
        **_base_kwargs(  # type: ignore[arg-type]
            regime_label="expansion",
            quant_overall_support="strong_negative",
            conflict_status="low",
        )
    )
    assert result.synthesis_status == SynthesisStatus.ALIGNED_CAUTIOUS
    assert result.dominant_concern == "weak_quant"


def test_synthesis_mixed_signals_high_conflict() -> None:
    result = compute_synthesis_view(
        **_base_kwargs(  # type: ignore[arg-type]
            conflict_status="high_conflict",
        )
    )
    assert result.synthesis_status == SynthesisStatus.MIXED_SIGNALS
    assert result.dominant_concern == "mixed_conflict"


def test_synthesis_mixed_signals_unknown_regime_and_moderate_quant() -> None:
    result = compute_synthesis_view(
        regime_label="sideways",
        macro_confidence=0.5,
        quant_overall_support="moderate_positive",
        conflict_status="medium",
        avg_var_95=1.0,
        worst_mdd_pct=-5.0,
    )
    assert result.synthesis_status == SynthesisStatus.MIXED_SIGNALS


# ── compute_synthesis_view — output contract ──────────────────────────────────


def test_synthesis_returns_correct_type() -> None:
    result = compute_synthesis_view(**_base_kwargs())  # type: ignore[arg-type]
    assert isinstance(result, SynthesisView)


def test_synthesis_conviction_score_clamped() -> None:
    # Even with zero penalty and confidence=1, score must be in [0, 1]
    result = compute_synthesis_view(**_base_kwargs(macro_confidence=1.0))  # type: ignore[arg-type]
    assert 0.0 <= result.conviction_score <= 1.0


def test_synthesis_conviction_reduced_by_penalty() -> None:
    # High VaR → penalty applied → conviction < macro_confidence
    high_var_kwargs = _base_kwargs(avg_var_95=4.0, macro_confidence=0.9)
    low_var_kwargs = _base_kwargs(avg_var_95=0.5, macro_confidence=0.9)
    high_var_result = compute_synthesis_view(**high_var_kwargs)  # type: ignore[arg-type]
    low_var_result = compute_synthesis_view(**low_var_kwargs)  # type: ignore[arg-type]
    assert high_var_result.conviction_score < low_var_result.conviction_score


def test_synthesis_note_is_non_empty_string() -> None:
    result = compute_synthesis_view(**_base_kwargs())  # type: ignore[arg-type]
    assert isinstance(result.note, str)
    assert len(result.note) > 0


def test_synthesis_risk_penalty_non_negative() -> None:
    result = compute_synthesis_view(**_base_kwargs())  # type: ignore[arg-type]
    assert result.risk_penalty >= 0.0


def test_synthesis_fields_passed_through() -> None:
    result = compute_synthesis_view(**_base_kwargs())  # type: ignore[arg-type]
    assert result.quant_support == "strong_positive"
    assert result.conflict_status == "low"
