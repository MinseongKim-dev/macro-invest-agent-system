"""Mock real-time market data — Phase 2 design-driven development.

Endpoints
---------
GET /api/mock/prices
    Returns current simulated prices for all portfolio tickers.
    Designed for 1-second SWR polling from the frontend.

GET /api/stream/market
    Server-Sent Events stream.  Emits one JSON event per second.
    Each SSE connection gets its own independent GBM price path
    (no shared mutable state across connections).

GET /api/mock/timeseries/{ticker}?points=60
    Returns a synthetic historical price series (GBM walk) for a
    single ticker.  Used by the LiveChart sparkline on first load.

Design notes
------------
* All prices are synthetic Geometric Brownian Motion.
* mu / sigma parameters are rough approximations of real-world
  annualised drift and volatility — not calibrated estimates.
* The shared polling state (_POLL) and per-connection SSE state are
  kept separate so they don't interfere with each other.
* No database reads occur in this router.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/mock", tags=["mock"])

# ── Simulation parameters ─────────────────────────────────────────────────

_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"price": 195.00, "mu": 0.08, "sigma": 0.22},
    "MSFT":  {"price": 415.00, "mu": 0.10, "sigma": 0.20},
    "GOOGL": {"price": 178.00, "mu": 0.09, "sigma": 0.24},
    "TSLA":  {"price": 245.00, "mu": 0.15, "sigma": 0.45},
    "NVDA":  {"price": 875.00, "mu": 0.20, "sigma": 0.50},
}

# 1 second expressed as a fraction of a 252-day, 390-minute trading year
_DT: float = 1.0 / (252 * 390 * 60)

# ── Shared polling state (all /api/mock/prices calls advance this) ────────

_POLL: dict[str, float] = {t: d["price"] for t, d in _PARAMS.items()}


def _poll_step() -> dict[str, float]:
    """Advance the shared polling state by one GBM step."""
    out: dict[str, float] = {}
    for ticker, p in _POLL.items():
        mu    = _PARAMS[ticker]["mu"]
        sigma = _PARAMS[ticker]["sigma"]
        z     = random.gauss(0.0, 1.0)
        new_p = p * math.exp((mu - 0.5 * sigma**2) * _DT + sigma * math.sqrt(_DT) * z)
        _POLL[ticker] = round(new_p, 2)
        out[ticker]   = _POLL[ticker]
    return out


# ── Routes ────────────────────────────────────────────────────────────────


@router.get("/prices", summary="Current mock portfolio prices (poll at 1 s)")
async def mock_prices() -> dict[str, object]:
    """Return simulated prices for all portfolio tickers.

    Advances the shared GBM state by one step on every call.
    Designed for 1-second ``refreshInterval`` SWR polling.
    """
    prices = _poll_step()
    return {
        "prices":          prices,
        "portfolio_value": round(sum(prices.values()), 2),
        "ts":              datetime.now(UTC).isoformat(),
    }


@router.get("/timeseries/{ticker}", summary="Historical GBM series for a ticker")
async def mock_timeseries(
    ticker: str,
    points: int = Query(default=60, ge=10, le=300),
) -> dict[str, object]:
    """Return a synthetic historical price series for *ticker*.

    Generates *points* GBM steps starting from the ticker's base price.
    Each call produces a fresh random path — determinism is not required
    for mock data.

    Args:
        ticker: One of AAPL, MSFT, GOOGL, TSLA, NVDA.
        points: Number of data points to generate (10–300, default 60).
    """
    if ticker not in _PARAMS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown ticker '{ticker}'. Available: {list(_PARAMS)}",
        )
    params = _PARAMS[ticker]
    mu, sigma = params["mu"], params["sigma"]
    price = params["price"] * (0.90 + random.random() * 0.10)  # slight random start
    series: list[float] = []
    # Use a longer dt per point so the series shows visible movement
    dt_point = 1.0 / (252 * 8)  # ~1 point per 5 minutes
    for _ in range(points):
        z = random.gauss(0.0, 1.0)
        price *= math.exp((mu - 0.5 * sigma**2) * dt_point + sigma * math.sqrt(dt_point) * z)
        series.append(round(price, 2))
    return {
        "ticker":  ticker,
        "prices":  series,
        "current": series[-1],
        "count":   len(series),
    }


@router.get(
    "/stream/market",
    summary="SSE: live mock portfolio prices (1 s interval)",
    # Omit from OpenAPI schema — browsers can't send headers to EventSource
    include_in_schema=False,
)
async def stream_market() -> StreamingResponse:
    """Server-Sent Events stream of simulated portfolio prices.

    Each connection receives its own independent GBM price path so that
    multiple clients don't interfere with each other.  Emits one JSON
    event per second.
    """
    # Clone initial prices for this connection
    conn_prices: dict[str, float] = {t: d["price"] for t, d in _PARAMS.items()}

    async def _generate() -> object:
        while True:
            out: dict[str, float] = {}
            for ticker, price in conn_prices.items():
                mu    = _PARAMS[ticker]["mu"]
                sigma = _PARAMS[ticker]["sigma"]
                z     = random.gauss(0.0, 1.0)
                new_p = price * math.exp(
                    (mu - 0.5 * sigma**2) * _DT + sigma * math.sqrt(_DT) * z
                )
                conn_prices[ticker] = round(new_p, 2)
                out[ticker]         = conn_prices[ticker]

            payload = json.dumps({
                "type":            "market",
                "prices":          out,
                "portfolio_value": round(sum(out.values()), 2),
                "ts":              datetime.now(UTC).isoformat(),
            })
            yield f"data: {payload}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )
