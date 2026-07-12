"""DTOs for fundamentals and portfolio-allocation API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TickerFundamentalsDTO(BaseModel):
    ticker: str
    display_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    pe_trailing: float | None = None
    pe_forward: float | None = None
    eps_trailing: float | None = None
    dividend_yield_pct: float | None = None
    beta: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    volume: float | None = None
    avg_volume_10d: float | None = None
    revenue_growth_yoy: float | None = None
    gross_margin_pct: float | None = None
    debt_to_equity: float | None = None


class SectorAllocationItem(BaseModel):
    sector: str
    tickers: list[str]
    weight_pct: float
    value: float
    currency: str = "KRW"


class PortfolioAllocationDTO(BaseModel):
    sectors: list[SectorAllocationItem]
    concentration_warning: str | None = None
    top_sector: str | None = None
    hhi: float = Field(ge=0.0, le=1.0, description="Herfindahl-Hirschman Index [0,1]")
    total_value: float


class CorrelationMatrixDTO(BaseModel):
    tickers: list[str]
    matrix: list[list[float]]
    period_days: int = 30
