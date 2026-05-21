"""Aleph-One — FastAPI intelligence API.

Endpoints::

    GET  /health
    GET  /api/v1/intelligence?ticker=AAPL&persona=BALANCED
         One-shot intelligence analysis (quant + sentiment → BUY/HOLD/SELL)

    GET  /api/v1/intelligence/stream?ticker=AAPL&persona=AGGRESSIVE
         SSE stream: PersonaAdapterEngine result emitted every second

    GET  /api/v1/regimes/latest
         Latest macro regime from TimescaleDB; placeholder for LangChain RAG

Run locally::

    uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from datetime import date, timedelta
from typing import Annotated, Any

import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse

from src.engines import PersonaAdapterEngine, PersonaProfile

logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Aleph-One Intelligence API",
    version="1.0.0",
    description=(
        "Hyper-personalised macro investment intelligence — "
        "J.A.R.V.I.S. for markets. Polymorphic engine layer: "
        "QuantEngine + SentimentEngine → PersonaAdapterEngine."
    ),
    docs_url="/docs",
    redoc_url=None,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_SUPPORTED_TICKERS: frozenset[str] = frozenset({"AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"})

_BASELINE_PRICES: dict[str, float] = {
    "AAPL": 195.0,
    "MSFT": 415.0,
    "GOOGL": 178.0,
    "TSLA": 245.0,
    "NVDA": 875.0,
}

_PLACEHOLDER_NEWS: dict[str, list[str]] = {
    "AAPL": [
        "Apple beats earnings expectations with record iPhone sales",
        "Strong growth in services revenue drives margin expansion",
    ],
    "MSFT": [
        "Microsoft Azure revenue surges on AI infrastructure demand",
        "Cloud business outperforms analyst forecasts for third consecutive quarter",
    ],
    "GOOGL": [
        "Google search ad revenue recovery beats analyst estimates",
        "Waymo robotaxi expansion boosts sentiment in autonomous driving",
    ],
    "TSLA": [
        "Tesla deliveries miss targets amid production ramp concerns",
        "Price cuts weigh on margin outlook and analyst downgrades follow",
    ],
    "NVDA": [
        "Nvidia GPU demand surges on hyperscaler AI infrastructure build-out",
        "Data center revenue sets new record, beating estimates by wide margin",
    ],
}

_DB_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://aleph_admin:aleph_secure_pass@localhost:5432/aleph_core",
)

# ── Market data helpers ───────────────────────────────────────────────────────


def _market_data_from_db(ticker: str) -> pd.DataFrame:
    """Load 30 days of OHLCV from TimescaleDB; fall back to synthetic GBM."""
    try:
        import psycopg  # type: ignore[import-untyped]

        with psycopg.connect(_DB_URL) as conn:
            rows = conn.execute(
                """
                SELECT timestamp, open_price, high_price, low_price, close_price, volume
                FROM   market_ticks
                WHERE  ticker    = %s
                  AND  timestamp >= NOW() - INTERVAL '30 days'
                ORDER BY timestamp ASC
                """,
                (ticker,),
            ).fetchall()

        if rows:
            df = pd.DataFrame(
                rows,
                columns=["timestamp", "open_price", "high_price", "low_price", "close_price", "volume"],
            )
            logger.debug("market_data_from_db", extra={"ticker": ticker, "rows": len(df)})
            return df

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "market_data_db_fallback",
            extra={"ticker": ticker, "error": str(exc)},
        )

    return _synthetic_market_data(ticker)


def _synthetic_market_data(ticker: str) -> pd.DataFrame:
    """GBM-generated OHLCV when TimescaleDB is unavailable or empty."""
    rng = np.random.default_rng(hash(ticker) % (2**31))
    n = 30
    mu, sigma, dt = 0.10, 0.25, 1.0 / 252
    start = _BASELINE_PRICES.get(ticker, 100.0)

    closes: list[float] = [start]
    for _ in range(n - 1):
        z = float(rng.standard_normal())
        closes.append(closes[-1] * float(np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z)))

    def _jitter(p: float, factor: float) -> float:
        return p * (1.0 + factor * abs(float(rng.standard_normal())) * 0.01)

    today = date.today()
    return pd.DataFrame({
        "timestamp":   [today - timedelta(days=n - 1 - i) for i in range(n)],
        "open_price":  [_jitter(p, 1.0) for p in closes],
        "high_price":  [_jitter(p, 1.5) for p in closes],
        "low_price":   [_jitter(p, -1.0) for p in closes],
        "close_price": closes,
        "volume":      [int(rng.integers(1_000_000, 10_000_000)) for _ in closes],
    })


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["ops"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return ``{"status": "ok"}`` — no dependency checks."""
    return {"status": "ok"}


@app.get("/api/v1/intelligence", tags=["intelligence"], summary="One-shot analysis")
async def intelligence(
    ticker: Annotated[str, Query(description="Ticker symbol — AAPL, MSFT, GOOGL, TSLA, NVDA")] = "AAPL",
    persona: Annotated[PersonaProfile, Query(description="Investment persona")] = "BALANCED",
) -> dict[str, Any]:
    """Run QuantEngine + SentimentEngine → PersonaAdapterEngine for one tick.

    Returns a JSON object with ``signal`` (BUY/HOLD/SELL), ``confidence``,
    and nested quant / sentiment sub-results.
    """
    ticker = ticker.upper()
    if ticker not in _SUPPORTED_TICKERS:
        return {"ok": False, "error": f"Unsupported ticker. Choose from {sorted(_SUPPORTED_TICKERS)}."}

    market_data = _market_data_from_db(ticker)
    context = _PLACEHOLDER_NEWS.get(ticker, [])
    engine = PersonaAdapterEngine(persona=persona)

    try:
        result = engine.analyze(ticker, market_data, context)
        return {"ok": True, "data": result}
    except Exception as exc:
        logger.error("intelligence_error", extra={"ticker": ticker, "error": str(exc)})
        return {"ok": False, "error": str(exc)}


async def _stream_ticks(ticker: str, persona: PersonaProfile) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted intelligence payloads at 1-second intervals."""
    engine = PersonaAdapterEngine(persona=persona)
    while True:
        try:
            market_data = _market_data_from_db(ticker)
            context = _PLACEHOLDER_NEWS.get(ticker, [])
            result = engine.analyze(ticker, market_data, context)
            yield f"data: {json.dumps({'ok': True, 'data': result})}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.error("stream_tick_error", extra={"ticker": ticker, "error": str(exc)})
            yield f"data: {json.dumps({'ok': False, 'error': str(exc)})}\n\n"
        await asyncio.sleep(1.0)


@app.get("/api/v1/intelligence/stream", tags=["intelligence"], summary="SSE stream")
async def intelligence_stream(
    ticker: Annotated[str, Query()] = "AAPL",
    persona: Annotated[PersonaProfile, Query()] = "BALANCED",
) -> StreamingResponse:
    """Server-Sent Events stream of intelligence results (1-second tick).

    Connect with ``EventSource('/api/v1/intelligence/stream?ticker=AAPL')``.
    """
    ticker = ticker.upper()
    return StreamingResponse(
        _stream_ticks(ticker, persona),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


@app.get("/api/v1/regimes/latest", tags=["regimes"], summary="Latest macro regime")
async def regimes_latest() -> dict[str, Any]:
    """Return the most recent macro regime record from TimescaleDB.

    Placeholder endpoint for the Phase 4 LangChain RAG integration — the RAG
    layer will enrich this with narrative context from the vector store.
    """
    try:
        import psycopg  # type: ignore[import-untyped]

        with psycopg.connect(_DB_URL) as conn:
            row = conn.execute(
                """
                SELECT regime_name, market_phase, confidence_score, updated_at
                FROM   macro_regimes
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()

        if row:
            return {
                "ok": True,
                "regime_name":      row[0],
                "market_phase":     row[1],
                "confidence_score": float(row[2]),
                "updated_at":       str(row[3]),
                # Phase 4: RAG narrative will be injected here
                "rag_narrative":    None,
            }

        return {
            "ok": True,
            "regime_name":      "UNKNOWN",
            "market_phase":     "N/A",
            "confidence_score": 0.0,
            "updated_at":       None,
            "rag_narrative":    None,
        }

    except Exception as exc:  # noqa: BLE001
        logger.warning("regimes_latest_error", extra={"error": str(exc)})
        return {"ok": False, "error": str(exc)}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("src.main:app", host="0.0.0.0", port=8001, reload=True)
