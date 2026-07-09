"""Risk domain models.

Contract between the Risk Engine and downstream consumers
(API layer, SSE stream, LangChain risk tool).

All percentage fields use the same sign convention:
  - ``var_95_pct``       : positive value = loss (e.g. 2.1 means −2.1 % in a day)
  - ``max_drawdown_pct`` : negative value (e.g. −25.0 means the peak-to-trough
                           loss over the window was 25 %)
  - ``volatility_ann_pct``: positive value (e.g. 22.0 = annualised vol of 22 %)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TickerRisk(BaseModel, extra="forbid"):
    """Per-ticker risk metrics computed from historical daily close prices.

    Attributes:
        ticker:            Internal ticker identifier.
        var_95_pct:        1-day historical VaR at 95 % confidence, expressed as
                           a positive loss percentage.  A value of 2.1 means
                           "there is a 5 % chance of losing ≥ 2.1 % in one day."
        max_drawdown_pct:  Maximum peak-to-trough drawdown over the computation
                           window as a negative percentage.
        volatility_ann_pct: Annualised daily-return volatility (sqrt-252 scaled).
        data_bars:         Number of daily close-price bars used.
    """

    ticker: str
    var_95_pct: float = Field(
        description="1-day VaR at 95 % confidence as a positive loss %",
        ge=0.0,
    )
    max_drawdown_pct: float = Field(
        description="Realised MDD over the window as a negative %",
        le=0.0,
    )
    volatility_ann_pct: float = Field(
        description="Annualised return volatility %",
        ge=0.0,
    )
    data_bars: int = Field(
        description="Daily price bars used for computation",
        ge=1,
    )


class RiskSummary(BaseModel, extra="forbid"):
    """Portfolio-level risk snapshot.

    Attributes:
        ticker_risks:          Per-ticker :class:`TickerRisk` keyed by ticker ID.
        correlation_matrix:    Return correlation matrix as nested dict
                               ``ticker → ticker → coeff ∈ [−1, 1]``.
                               Empty when fewer than 2 tickers have history.
        sector_concentration:  Fraction of total portfolio market value per
                               sector label (values sum to ≤ 1.0; may be empty
                               when portfolio is flat).
        window_days:           Maximum number of daily bars used across all tickers.
    """

    ticker_risks: dict[str, TickerRisk]
    correlation_matrix: dict[str, dict[str, float]]
    sector_concentration: dict[str, float] = Field(
        description="Sector → fraction of total portfolio market value [0, 1]",
    )
    window_days: int = Field(
        description="Max daily bars used across all tickers",
        ge=0,
    )
