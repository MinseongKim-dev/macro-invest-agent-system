"""Fundamentals and portfolio-allocation routes.

Routes
------
``GET /api/fundamentals/{ticker}``
    Live yfinance fundamentals for a single ticker (P/E, EPS, market cap,
    dividend yield, beta, revenue growth, gross margin, debt/equity).
    Results are cached 10 minutes in-process.

``GET /api/portfolio/allocation``
    Sector allocation derived from virtual portfolio holdings.
    Returns sector weights, HHI concentration index, and a warning when
    any single sector exceeds 40% of the portfolio.

``GET /api/portfolio/correlation``
    Pearson correlation matrix for the 16 live tickers over the past 30
    calendar days, computed via a yfinance batch download and pandas.
    Results are cached 15 minutes in-process.
"""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException

from apps.api.dto.fundamentals import (
    CorrelationMatrixDTO,
    PortfolioAllocationDTO,
    SectorAllocationItem,
    TickerFundamentalsDTO,
)

router = APIRouter(prefix="/api", tags=["fundamentals"])

# ── Static maps ────────────────────────────────────────────────────────────────

_SECTOR_MAP: dict[str, str] = {
    "AAPL":   "Technology",
    "MSFT":   "Technology",
    "TSLA":   "Consumer Discretionary",
    "005930": "Technology",
    "000660": "Technology",
    "035420": "Communication Services",
    "051910": "Materials",
    "006400": "Materials",
    "122630": "Leveraged ETF",
    "005380": "Consumer Discretionary",
    "207940": "Healthcare",
    "005490": "Materials",
    "105560": "Financials",
    "QQQ":    "Technology ETF",
    "BND":    "Fixed Income ETF",
    "GLD":    "Commodity ETF",
}

_ALL_TICKERS = list(_SECTOR_MAP.keys())

# ── Simple TTL cache ───────────────────────────────────────────────────────────

_CACHE: dict[str, tuple[float, Any]] = {}
_FUND_TTL = 600.0    # 10 min
_CORR_TTL = 900.0    # 15 min
_ALLOC_TTL = 120.0   # 2 min


def _get(key: str, ttl: float) -> Any | None:
    entry = _CACHE.get(key)
    if entry and monotonic() - entry[0] < ttl:
        return entry[1]
    return None


def _put(key: str, val: Any) -> None:
    _CACHE[key] = (monotonic(), val)


# ── yfinance helpers ───────────────────────────────────────────────────────────

def _yf_sym(ticker: str) -> str:
    from src.database import LIVE_TICKERS  # noqa: PLC0415
    return LIVE_TICKERS.get(ticker, ticker)


def _fetch_fundamentals_sync(ticker: str) -> dict[str, Any]:
    import yfinance as yf  # noqa: PLC0415

    yf_symbol = _yf_sym(ticker)
    try:
        t = yf.Ticker(yf_symbol)
        info = t.info or {}
        fast = t.fast_info

        dy = info.get("dividendYield")
        gm = info.get("grossMargins")

        return {
            "ticker": ticker,
            "display_name": info.get("shortName") or info.get("longName"),
            "sector": info.get("sector") or _SECTOR_MAP.get(ticker),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
            "pe_trailing": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "eps_trailing": info.get("trailingEps"),
            "dividend_yield_pct": dy * 100 if dy is not None else None,
            "beta": info.get("beta"),
            "week52_high": getattr(fast, "year_high", None),
            "week52_low": getattr(fast, "year_low", None),
            "volume": getattr(fast, "three_month_average_volume", None),
            "avg_volume_10d": info.get("averageVolume10days"),
            "revenue_growth_yoy": info.get("revenueGrowth"),
            "gross_margin_pct": gm * 100 if gm is not None else None,
            "debt_to_equity": info.get("debtToEquity"),
        }
    except Exception:
        return {"ticker": ticker, "sector": _SECTOR_MAP.get(ticker)}


def _fetch_correlation_sync(tickers: list[str], period_days: int = 30) -> dict[str, Any]:
    import pandas as pd  # noqa: PLC0415
    import yfinance as yf  # noqa: PLC0415

    yf_symbols = [_yf_sym(t) for t in tickers]
    sym_to_ticker = {_yf_sym(t): t for t in tickers}

    try:
        raw = yf.download(
            tickers=" ".join(yf_symbols),
            period=f"{period_days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        close: pd.DataFrame = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        available = [s for s in yf_symbols if s in close.columns]
        corr = close[available].corr().fillna(0).round(3)

        clean = [sym_to_ticker.get(s, s) for s in available]
        return {
            "tickers": clean,
            "matrix": corr.values.tolist(),
            "period_days": period_days,
        }
    except Exception:
        n = len(tickers)
        return {
            "tickers": tickers,
            "matrix": [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)],
            "period_days": period_days,
        }


def _fetch_allocation_sync() -> dict[str, Any]:
    from src.database import get_portfolio_holdings  # noqa: PLC0415

    holdings = get_portfolio_holdings()

    if not holdings:
        return {
            "sectors": [],
            "concentration_warning": "가상 포트폴리오에 보유 종목이 없습니다 — APPLY로 가상 매매를 실행하면 배분 현황이 표시됩니다",
            "top_sector": None,
            "hhi": 0.0,
            "total_value": 0.0,
        }

    # Group by sector using cost-basis value
    sector_tickers: dict[str, list[str]] = {}
    sector_values: dict[str, float] = {}
    sector_currencies: dict[str, str] = {}

    for h in holdings:
        ticker: str = h["ticker"]
        qty: float = float(h["quantity"])
        avg: float = float(h["avg_cost"])
        currency: str = h.get("currency", "KRW")
        sector = _SECTOR_MAP.get(ticker, "Other")
        val = qty * avg

        sector_tickers.setdefault(sector, []).append(ticker)
        sector_values[sector] = sector_values.get(sector, 0.0) + val
        sector_currencies[sector] = currency

    total = sum(sector_values.values())
    if total == 0:
        return {
            "sectors": [],
            "concentration_warning": None,
            "top_sector": None,
            "hhi": 0.0,
            "total_value": 0.0,
        }

    items = []
    hhi = 0.0
    for sector, val in sorted(sector_values.items(), key=lambda x: -x[1]):
        w = val / total
        hhi += w * w
        items.append({
            "sector": sector,
            "tickers": sector_tickers[sector],
            "weight_pct": round(w * 100, 1),
            "value": round(val, 0),
            "currency": sector_currencies[sector],
        })

    top = items[0]["sector"] if items else None
    top_w = items[0]["weight_pct"] if items else 0.0
    warning = (
        f"{top} 비중 {top_w:.1f}% — 40% 임계치 초과, 분산투자 검토 권장"
        if top_w > 40.0
        else None
    )

    return {
        "sectors": items,
        "concentration_warning": warning,
        "top_sector": top,
        "hhi": round(hhi, 4),
        "total_value": round(total, 0),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get(
    "/fundamentals/{ticker}",
    response_model=TickerFundamentalsDTO,
    summary="Live fundamentals for a single ticker",
)
async def get_fundamentals(ticker: str) -> TickerFundamentalsDTO:
    ticker = ticker.upper()
    cached = _get(f"fund:{ticker}", _FUND_TTL)
    if cached is not None:
        return cached

    data = await asyncio.to_thread(_fetch_fundamentals_sync, ticker)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data for ticker '{ticker}'")

    result = TickerFundamentalsDTO(**data)
    _put(f"fund:{ticker}", result)
    return result


@router.get(
    "/portfolio/allocation",
    response_model=PortfolioAllocationDTO,
    summary="Portfolio sector allocation from virtual holdings",
)
async def get_portfolio_allocation() -> PortfolioAllocationDTO:
    cached = _get("allocation", _ALLOC_TTL)
    if cached is not None:
        return cached

    data = await asyncio.to_thread(_fetch_allocation_sync)
    result = PortfolioAllocationDTO(
        sectors=[SectorAllocationItem(**s) for s in data["sectors"]],
        concentration_warning=data["concentration_warning"],
        top_sector=data["top_sector"],
        hhi=data["hhi"],
        total_value=data["total_value"],
    )
    _put("allocation", result)
    return result


@router.get(
    "/portfolio/correlation",
    response_model=CorrelationMatrixDTO,
    summary="Pearson correlation matrix for all live tickers (30-day daily)",
)
async def get_correlation_matrix(period_days: int = 30) -> CorrelationMatrixDTO:
    key = f"corr:{period_days}"
    cached = _get(key, _CORR_TTL)
    if cached is not None:
        return cached

    data = await asyncio.to_thread(_fetch_correlation_sync, _ALL_TICKERS, period_days)
    result = CorrelationMatrixDTO(**data)
    _put(key, result)
    return result
