"""Risk Engine v1 — deterministic, side-effect-free risk functions.

All functions accept plain pandas/numpy data and return domain models.
No database access, no I/O — callers are responsible for data fetching.

Computation methods
-------------------
- **VaR**: historical simulation at the 5th percentile of daily returns.
  Requires at least 20 bars for a meaningful estimate.
- **Max Drawdown**: peak-to-trough percentage decline over the full window.
- **Annualised volatility**: daily-return standard deviation × √252.
- **Correlation matrix**: pairwise Pearson correlation of daily returns.
- **Sector concentration**: portfolio market-value fraction per sector.

Public entry points
-------------------
:func:`compute_ticker_risk` — per-ticker metrics from a price series.
:func:`compute_risk_summary` — full portfolio risk from price dict + holdings.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.domain.risk.models import RiskSummary, TickerRisk

# ── Single-ticker helpers ─────────────────────────────────────────────────────


def compute_max_drawdown(prices: pd.Series) -> float:
    """Return the maximum peak-to-trough drawdown fraction (≤ 0).

    Drawdown is normalised to the running peak, so a return of −0.25
    means the worst trough was 25 % below the prior peak.
    Returns 0.0 when fewer than 2 data points are available.
    """
    if len(prices) < 2:
        return 0.0
    cumulative = prices / float(prices.iloc[0])
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    return float(drawdown.min())


def compute_var_95(returns: pd.Series) -> float:
    """Return 1-day historical VaR at 95 % confidence as a positive loss %.

    Uses the 5th-percentile of the empirical return distribution.
    Requires at least 20 observations; returns 0.0 otherwise.
    """
    if len(returns) < 20:
        return 0.0
    # Clamp to 0: when the 5th-percentile return is positive (all returns positive),
    # the historical loss is 0 — convention: VaR is always a non-negative loss amount.
    return max(0.0, float(-np.percentile(returns.to_numpy(), 5) * 100))


def compute_annualized_volatility(returns: pd.Series) -> float:
    """Return annualised daily-return volatility as a %.

    Uses sqrt(252) as the trading-day annualisation factor.
    Returns 0.0 when fewer than 2 observations are available.
    """
    if len(returns) < 2:
        return 0.0
    return float(returns.std() * math.sqrt(252) * 100)


def compute_ticker_risk(ticker: str, prices: pd.Series) -> TickerRisk:
    """Compute :class:`~domain.risk.models.TickerRisk` for a single ticker.

    Args:
        ticker: Internal ticker identifier.
        prices: Daily close prices, oldest-first, at least 2 data points.

    Returns:
        :class:`~domain.risk.models.TickerRisk` with VaR, MDD, and vol.
    """
    returns = prices.pct_change().dropna()
    return TickerRisk(
        ticker=ticker,
        var_95_pct=compute_var_95(returns),
        max_drawdown_pct=compute_max_drawdown(prices) * 100,
        volatility_ann_pct=compute_annualized_volatility(returns),
        data_bars=len(prices),
    )


# ── Cross-ticker helpers ──────────────────────────────────────────────────────


def compute_correlation_matrix(price_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Return a pairwise return-correlation matrix as a nested dict.

    Args:
        price_df: DataFrame with columns = ticker IDs, rows = trading dates,
                  values = daily close prices.

    Returns:
        ``{ticker: {other_ticker: coefficient}}`` with coefficients rounded
        to 4 decimal places.  Returns ``{}`` when fewer than 2 tickers or
        fewer than 2 rows are present.
    """
    if price_df.shape[0] < 2 or price_df.shape[1] < 2:
        return {}
    returns_df = price_df.pct_change().dropna()
    if len(returns_df) < 2:
        return {}
    corr = returns_df.corr()
    result: dict[str, dict[str, float]] = {}
    for col in corr.columns:
        result[col] = {
            row: round(float(corr.loc[row, col]), 4)
            for row in corr.index
            if not pd.isna(corr.loc[row, col])
        }
    return result


def compute_sector_concentration(
    holdings: dict[str, float],
    ticker_groups: dict[str, str],
) -> dict[str, float]:
    """Return portfolio sector concentration as fractions of total market value.

    Args:
        holdings:       ``{ticker: current_market_value}``; non-positive values
                        are ignored.
        ticker_groups:  ``{ticker: sector_label}``; tickers not in the map are
                        bucketed under ``"OTHER"``.

    Returns:
        ``{sector_label: fraction}`` where fractions sum to ≤ 1.0.
        Returns ``{}`` when the portfolio is empty or all values are non-positive.
    """
    total = sum(v for v in holdings.values() if v > 0)
    if total <= 0:
        return {}
    sector_value: dict[str, float] = {}
    for ticker, value in holdings.items():
        if value <= 0:
            continue
        sector = ticker_groups.get(ticker, "OTHER")
        sector_value[sector] = sector_value.get(sector, 0.0) + value
    return {sector: round(val / total, 4) for sector, val in sector_value.items()}


# ── Portfolio-level entry point ───────────────────────────────────────────────


def compute_risk_summary(
    prices_by_ticker: dict[str, pd.Series],
    holdings: dict[str, float],
    ticker_groups: dict[str, str],
) -> RiskSummary:
    """Compute a full :class:`~domain.risk.models.RiskSummary`.

    Args:
        prices_by_ticker: ``{ticker: daily_close_series}`` — oldest first,
                          each series must have at least 2 data points to
                          contribute to ``ticker_risks`` and the correlation matrix.
        holdings:         ``{ticker: current_market_value}`` for sector
                          concentration; may be empty (flat portfolio).
        ticker_groups:    ``{ticker: sector_label}`` passed through to
                          :func:`compute_sector_concentration`.

    Returns:
        :class:`~domain.risk.models.RiskSummary` with per-ticker risks,
        correlation matrix, and sector concentration.
    """
    ticker_risks: dict[str, TickerRisk] = {}
    for ticker, prices in prices_by_ticker.items():
        if len(prices) >= 2:
            ticker_risks[ticker] = compute_ticker_risk(ticker, prices)

    if len(ticker_risks) >= 2:
        price_df = pd.DataFrame(
            {t: s for t, s in prices_by_ticker.items() if t in ticker_risks}
        )
        correlation_matrix = compute_correlation_matrix(price_df)
    else:
        correlation_matrix = {}

    sector_concentration = compute_sector_concentration(holdings, ticker_groups)
    window_days = max((len(s) for s in prices_by_ticker.values()), default=0)

    return RiskSummary(
        ticker_risks=ticker_risks,
        correlation_matrix=correlation_matrix,
        sector_concentration=sector_concentration,
        window_days=window_days,
    )
