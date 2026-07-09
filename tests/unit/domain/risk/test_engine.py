"""Unit tests for src/domain/risk/engine.py — pure risk computation functions.

No database, no I/O — all inputs are constructed in-process.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.domain.risk.engine import (
    compute_annualized_volatility,
    compute_correlation_matrix,
    compute_max_drawdown,
    compute_risk_summary,
    compute_sector_concentration,
    compute_ticker_risk,
    compute_var_95,
)
from src.domain.risk.models import RiskSummary, TickerRisk

# ── helpers ───────────────────────────────────────────────────────────────────


def _prices(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def _returns(values: list[float]) -> pd.Series:
    return _prices(values).pct_change().dropna()


# ── compute_max_drawdown ──────────────────────────────────────────────────────


def test_max_drawdown_monotone_rise() -> None:
    prices = _prices([100.0, 105.0, 110.0, 115.0])
    assert compute_max_drawdown(prices) == pytest.approx(0.0, abs=1e-6)


def test_max_drawdown_single_drop() -> None:
    # 100 → 80 = 20 % drawdown
    prices = _prices([100.0, 80.0])
    assert compute_max_drawdown(prices) == pytest.approx(-0.20, abs=1e-6)


def test_max_drawdown_recovery() -> None:
    # Peak 100, trough 70 (30 % drawdown), then recovers to 110
    prices = _prices([100.0, 90.0, 70.0, 80.0, 110.0])
    assert compute_max_drawdown(prices) == pytest.approx(-0.30, abs=1e-4)


def test_max_drawdown_insufficient_data() -> None:
    assert compute_max_drawdown(_prices([100.0])) == pytest.approx(0.0)


def test_max_drawdown_negative_result() -> None:
    prices = _prices([100.0, 95.0, 80.0, 90.0])
    result = compute_max_drawdown(prices)
    assert result <= 0.0


# ── compute_var_95 ────────────────────────────────────────────────────────────


def test_var_95_positive_value() -> None:
    # Normally distributed returns — VaR should be a positive loss %
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.0, 0.02, 252))
    result = compute_var_95(returns)
    assert result > 0.0


def test_var_95_insufficient_data_returns_zero() -> None:
    assert compute_var_95(_prices([0.01, -0.02])) == pytest.approx(0.0)


def test_var_95_all_positive_returns() -> None:
    # When all returns are positive, 5th pct is still positive → VaR is negative.
    # This is a degenerate case (no loss risk); the function should return 0 or negative.
    returns = pd.Series([0.01] * 50)
    result = compute_var_95(returns)
    # -percentile(positive values, 5) is negative or zero → clamp to >= 0 is NOT applied
    # here; the function returns the raw value. We just check it doesn't raise.
    assert isinstance(result, float)


# ── compute_annualized_volatility ─────────────────────────────────────────────


def test_annualized_vol_positive() -> None:
    np.random.seed(0)
    returns = pd.Series(np.random.normal(0, 0.01, 252))
    result = compute_annualized_volatility(returns)
    assert result > 0.0


def test_annualized_vol_zero_variance() -> None:
    returns = pd.Series([0.0] * 50)
    assert compute_annualized_volatility(returns) == pytest.approx(0.0)


def test_annualized_vol_insufficient_data() -> None:
    assert compute_annualized_volatility(pd.Series([0.01])) == pytest.approx(0.0)


def test_annualized_vol_known_value() -> None:
    # Daily vol 1 % → annualised = 1 % × sqrt(252) ≈ 15.87 %
    returns = pd.Series([0.01] * 10 + [-0.01] * 10)  # std ≈ 0.01
    result = compute_annualized_volatility(returns)
    expected = returns.std() * math.sqrt(252) * 100
    assert result == pytest.approx(expected, rel=1e-4)


# ── compute_ticker_risk ───────────────────────────────────────────────────────


def test_ticker_risk_returns_correct_type() -> None:
    prices = _prices([100.0, 102.0, 98.0, 105.0, 103.0] * 10)
    result = compute_ticker_risk("AAPL", prices)
    assert isinstance(result, TickerRisk)
    assert result.ticker == "AAPL"
    assert result.data_bars == 50


def test_ticker_risk_mdd_non_positive() -> None:
    prices = _prices([100.0, 110.0, 90.0, 105.0] * 10)
    result = compute_ticker_risk("MSFT", prices)
    assert result.max_drawdown_pct <= 0.0


def test_ticker_risk_volatility_non_negative() -> None:
    prices = _prices([100.0 + i * 0.5 for i in range(50)])
    result = compute_ticker_risk("TSLA", prices)
    assert result.volatility_ann_pct >= 0.0


# ── compute_correlation_matrix ────────────────────────────────────────────────


def test_correlation_matrix_perfect_correlation() -> None:
    prices = [100.0 + i for i in range(10)]
    df = pd.DataFrame({"A": prices, "B": prices})
    result = compute_correlation_matrix(df)
    assert result["A"]["B"] == pytest.approx(1.0, abs=1e-4)
    assert result["B"]["A"] == pytest.approx(1.0, abs=1e-4)


def test_correlation_matrix_negative_correlation() -> None:
    a = [100.0 + i for i in range(10)]
    b = [100.0 - i for i in range(10)]
    df = pd.DataFrame({"A": a, "B": b})
    result = compute_correlation_matrix(df)
    assert result["A"]["B"] == pytest.approx(-1.0, abs=1e-4)


def test_correlation_matrix_too_few_tickers() -> None:
    df = pd.DataFrame({"A": [1.0, 2.0, 3.0]})
    assert compute_correlation_matrix(df) == {}


def test_correlation_matrix_too_few_rows() -> None:
    df = pd.DataFrame({"A": [1.0], "B": [2.0]})
    assert compute_correlation_matrix(df) == {}


# ── compute_sector_concentration ──────────────────────────────────────────────


def test_sector_concentration_single_sector() -> None:
    holdings = {"AAPL": 1000.0, "MSFT": 2000.0}
    groups = {"AAPL": "US_TECH", "MSFT": "US_TECH"}
    result = compute_sector_concentration(holdings, groups)
    assert result == {"US_TECH": pytest.approx(1.0)}


def test_sector_concentration_two_sectors() -> None:
    holdings = {"AAPL": 1000.0, "BND": 1000.0}
    groups = {"AAPL": "US_TECH", "BND": "US_BOND"}
    result = compute_sector_concentration(holdings, groups)
    assert result["US_TECH"] == pytest.approx(0.5, abs=1e-4)
    assert result["US_BOND"] == pytest.approx(0.5, abs=1e-4)


def test_sector_concentration_unknown_ticker_goes_to_other() -> None:
    holdings = {"UNKNOWN": 500.0}
    result = compute_sector_concentration(holdings, {})
    assert "OTHER" in result
    assert result["OTHER"] == pytest.approx(1.0)


def test_sector_concentration_empty_portfolio() -> None:
    assert compute_sector_concentration({}, {}) == {}


def test_sector_concentration_zero_values_ignored() -> None:
    holdings = {"AAPL": 0.0, "MSFT": 1000.0}
    groups = {"AAPL": "US_TECH", "MSFT": "US_TECH"}
    result = compute_sector_concentration(holdings, groups)
    assert result["US_TECH"] == pytest.approx(1.0)


# ── compute_risk_summary ──────────────────────────────────────────────────────


def test_risk_summary_returns_correct_type() -> None:
    prices = _prices([100.0 + i * 0.3 for i in range(60)])
    result = compute_risk_summary(
        prices_by_ticker={"AAPL": prices, "MSFT": prices * 1.1},
        holdings={"AAPL": 5000.0, "MSFT": 3000.0},
        ticker_groups={"AAPL": "US_TECH", "MSFT": "US_TECH"},
    )
    assert isinstance(result, RiskSummary)
    assert "AAPL" in result.ticker_risks
    assert "MSFT" in result.ticker_risks


def test_risk_summary_correlation_present_for_two_tickers() -> None:
    prices = _prices([100.0 + i for i in range(30)])
    result = compute_risk_summary(
        prices_by_ticker={"A": prices, "B": prices * 0.9},
        holdings={},
        ticker_groups={},
    )
    assert len(result.correlation_matrix) == 2


def test_risk_summary_sector_concentration_empty_for_flat_portfolio() -> None:
    prices = _prices([100.0 + i for i in range(30)])
    result = compute_risk_summary(
        prices_by_ticker={"AAPL": prices},
        holdings={},
        ticker_groups={"AAPL": "US_TECH"},
    )
    assert result.sector_concentration == {}


def test_risk_summary_window_days_matches_longest_series() -> None:
    short = _prices([100.0] * 10)
    long = _prices([100.0] * 50)
    result = compute_risk_summary(
        prices_by_ticker={"S": short, "L": long},
        holdings={},
        ticker_groups={},
    )
    assert result.window_days == 50


def test_risk_summary_skips_single_bar_tickers() -> None:
    """Tickers with only 1 bar must not appear in ticker_risks."""
    result = compute_risk_summary(
        prices_by_ticker={"A": _prices([100.0])},
        holdings={},
        ticker_groups={},
    )
    assert result.ticker_risks == {}
