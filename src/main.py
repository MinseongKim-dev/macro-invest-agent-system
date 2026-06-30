"""Aleph-One — FastAPI intelligence API (SSE streaming + OMNI command).

Endpoints::

    GET  /health
    GET  /api/v1/intelligence/stream   — SSE, 1-second tick, full UI contract
    POST /api/v1/intelligence/command  — OMNI:// terminal, scenario-based response

Run locally::

    uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import pytz
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.tools import tool
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src import config
from src.database import (
    FRED_API_KEY,
    _PoolManager,
    execute_virtual_order,
    fetch_fund_nav,
    fetch_live_index_data,
    fetch_live_market_data,
    fetch_live_news,
    fetch_macro_indicators,
    get_connection,
    get_latest_prices,
    get_portfolio_holdings,
    get_virtual_accounts,
    init_db,
    init_milvus,
    search_milvus_news,
    seed_mock_data,
)
from src.engines import (
    DISPLAY_NAMES,
    TICKER_GROUPS,
    TICKERS,
    BacktestEngine,
    PersonaProfile,
    QuantEngine,
    SentimentEngine,
    _compute_rsi,
    build_intelligence_row,
)

logger = logging.getLogger(__name__)

_KST = pytz.timezone("Asia/Seoul")

# ── In-memory live state ──────────────────────────────────────────────────────

_BASELINE_PRICES: dict[str, float] = {
    "AAPL":   195.0,
    "MSFT":   415.0,
    "TSLA":   245.0,
    "005930": 72_000.0,
    "000660": 195_000.0,
    "QQQ":    490.0,
    "BND":     73.0,
    "GLD":    240.0,
    "035420": 230_000.0,
    "051910": 340_000.0,
    "006400": 380_000.0,
    "122630":  18_000.0,
}

# Rolling price history buffer — populated on startup, updated each tick
_PRICE_HISTORY: dict[str, list[float]] = {t: [] for t in TICKERS}
_PRICE_STATE:   dict[str, float]       = dict(_BASELINE_PRICES)
_HISTORY_LEN:   int                    = 60   # rolling window kept in memory
_HISTORY_SEED:  int                    = 30   # synthetic points generated at boot

# Cached macro regime (refreshed from DB at startup, stays in memory)
_REGIME_CACHE: dict[str, Any] = {
    "regime_name":      "POLICY_TIGHTENING",
    "market_phase":     "LATE_CYCLE",
    "confidence_score": 0.85,
}

# Per-ticker placeholder news (seed for SentimentEngine)
_TICKER_NEWS: dict[str, list[str]] = {
    "AAPL":  [
        "Apple beats earnings expectations; services revenue surges record high",
        "Strong iPhone 16 demand growth drives positive bullish outlook for Q4",
    ],
    "MSFT":  [
        "Microsoft Azure surpasses growth targets; AI copilot expansion accelerates",
        "Cloud business bullish momentum outperforms analyst forecasts third quarter",
    ],
    "TSLA":  [
        "Tesla deliveries drop below targets; margin drag from price cuts bearish",
        "Demand concerns bear risk as EV competition intensifies, volume decline",
    ],
    "005930": [
        "Samsung Electronics HBM chip surpass supply targets; AI memory bullish growth",
        "Strong semiconductor demand expansion drives record profit recovery quarter",
    ],
    "000660": [
        "SK Hynix DRAM bullish surge; HBM3E outperforms expectations, profit growth",
        "Memory chip recovery expansion strong; AI-driven demand exceeds bearish forecasts",
    ],
    "QQQ": [
        "Nasdaq 100 ETF bullish momentum; mega-cap tech earnings beat expectations broadly",
        "QQQ inflows surge as institutional investors rotate into growth technology assets",
    ],
    "BND": [
        "Bond market stabilizes; Fed signals rate pause supporting fixed-income recovery",
        "BND yield curve normalization; defensive allocation demand grows amid uncertainty",
    ],
    "GLD": [
        "Gold ETF surges on dollar weakness; safe-haven demand bullish amid macro uncertainty",
        "GLD holdings expand as central banks increase reserve gold allocation globally",
    ],
    "035420": [
        "NAVER Cloud AI growth accelerates; enterprise contracts expand across Southeast Asia",
        "NAVER webtoon global expansion bullish; content monetization beats expectations",
    ],
    "051910": [
        "LG화학 battery materials demand surge; EV supply chain recovery signals bullish",
        "LG화학 NCMA cathode expansion drives record sales; margin improvement confirmed",
    ],
    "006400": [
        "삼성SDI solid-state battery prototype milestone; EV maker partnerships expand",
        "삼성SDI Q3 earnings beat; premium cylindrical cell demand remains strong",
    ],
    "122630": [
        "KODEX 레버리지 volume surge as KOSPI 200 momentum accelerates bullish trend",
        "Korean ETF inflows rise; institutional rotation into domestic equities confirmed",
    ],
}

# ── DB price cache ────────────────────────────────────────────────────────────
# Keyed by ticker → (DataFrame | None, monotonic timestamp of last fetch)
_DB_PRICE_CACHE: dict[str, tuple[pd.DataFrame | None, float]] = {}
_DB_CACHE_TTL:   float = 10.0   # seconds — avoids a DB hit on every 1-second SSE tick

# ── Live collector state ──────────────────────────────────────────────────────
# News cache updated by the background collector; falls back to _TICKER_NEWS.
_LIVE_NEWS_CACHE:     dict[str, list[str]]    = {}
# Single shared background task — started on first SSE connect, cancelled on last disconnect.
_LIVE_COLLECTOR_TASK: asyncio.Task[None] | None = None
_SSE_CONNECTION_COUNT: int                      = 0
# Latest market index values — updated by _live_collector_loop every cycle
_INDEX_CACHE: dict[str, float] = {
    "KOSPI":  2540.0,
    "SP500":  5000.0,
    "USDKRW": 1360.0,
}
# Macro economic indicators — updated by _macro_collector_loop every hour
_MACRO_CACHE: dict[str, float] = {
    "T10Y":    4.35,   # 10-year Treasury yield (%)
    "T3M":     5.28,   # 3-month T-bill (%)
    "VIX":     18.5,   # CBOE VIX
    "FED_RATE": 5.33,  # Fed funds rate (%)
}
# Hourly macro collector task (lifecycle: startup → shutdown)
_MACRO_COLLECTOR_TASK: asyncio.Task[None] | None = None

# Daily fund NAV collector task (lifecycle: startup → shutdown).
# Stays empty until KOFIA_API_KEY + FUND_NAV_TARGETS are configured — see
# src/database.py fetch_fund_nav() scaffold notes.
_FUND_NAV_CACHE: dict[str, float] = {}
_FUND_NAV_COLLECTOR_TASK: asyncio.Task[None] | None = None


def _fetch_price_df_from_db(ticker: str, n_rows: int = 20) -> pd.DataFrame | None:
    """Return the last ``n_rows`` close prices for ``ticker`` from market_ticks.

    Result is cached for ``_DB_CACHE_TTL`` seconds to keep DB load minimal.
    Returns ``None`` when the ticker has no rows yet or the DB is unavailable.
    """
    now    = time.monotonic()
    cached = _DB_PRICE_CACHE.get(ticker)
    if cached is not None:
        df_c, ts = cached
        if now - ts < _DB_CACHE_TTL:
            return df_c

    df: pd.DataFrame | None = None
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT close_price FROM ("
                "  SELECT close_price, timestamp FROM market_ticks"
                "  WHERE ticker = %s ORDER BY timestamp DESC LIMIT %s"
                ") sub ORDER BY timestamp ASC",
                (ticker, n_rows),
            ).fetchall()
        if rows:
            df = pd.DataFrame({"close_price": [float(r[0]) for r in rows]})
    except Exception as exc:
        logger.warning("db_price_fetch_failed", extra={"ticker": ticker, "error": str(exc)})

    _DB_PRICE_CACHE[ticker] = (df, now)
    return df


_PortfolioCacheEntry = tuple[dict[str, dict[str, float]], list[dict[str, Any]]]
_PORTFOLIO_SUMMARY_CACHE: tuple[_PortfolioCacheEntry, float] | None = None


def _build_portfolio_summary(*, force_refresh: bool = False) -> dict[str, Any]:
    """Assemble the current virtual-broker state: cash, holdings, P&L by currency.

    Holdings are marked to market using ``_PRICE_STATE`` (the same live price
    cache the SSE stream and quant tools read from). Cash/holdings rows are
    cached for ``_DB_CACHE_TTL`` seconds (same pattern as ``_fetch_price_df_from_db``)
    to avoid a DB round-trip on every 1-second SSE tick; pass ``force_refresh=True``
    right after placing an order so the next read reflects it immediately.
    """
    global _PORTFOLIO_SUMMARY_CACHE
    now = time.monotonic()
    if not force_refresh and _PORTFOLIO_SUMMARY_CACHE is not None:
        cached, ts = _PORTFOLIO_SUMMARY_CACHE
        if now - ts < _DB_CACHE_TTL:
            accounts, holdings = cached
        else:
            accounts, holdings = get_virtual_accounts(), get_portfolio_holdings()
            _PORTFOLIO_SUMMARY_CACHE = ((accounts, holdings), now)
    else:
        accounts, holdings = get_virtual_accounts(), get_portfolio_holdings()
        _PORTFOLIO_SUMMARY_CACHE = ((accounts, holdings), now)

    enriched_holdings: list[dict[str, Any]] = []
    market_value_by_currency: dict[str, float] = dict.fromkeys(accounts, 0.0)

    for h in holdings:
        ticker        = h["ticker"]
        live_price    = _PRICE_STATE.get(ticker, h["avg_cost"])
        market_value  = round(h["quantity"] * live_price, 4)
        unrealized_pl = round(market_value - h["quantity"] * h["avg_cost"], 4)
        market_value_by_currency[h["currency"]] = (
            market_value_by_currency.get(h["currency"], 0.0) + market_value
        )
        enriched_holdings.append({
            **h,
            "display_name":  DISPLAY_NAMES.get(ticker, ticker),
            "live_price":    round(live_price, 4),
            "market_value":  market_value,
            "unrealized_pl": unrealized_pl,
        })

    accounts_summary: dict[str, dict[str, float]] = {}
    for currency, acct in accounts.items():
        total_value = acct["cash_balance"] + market_value_by_currency.get(currency, 0.0)
        accounts_summary[currency] = {
            "cash_balance":    round(acct["cash_balance"], 4),
            "market_value":    round(market_value_by_currency.get(currency, 0.0), 4),
            "total_value":     round(total_value, 4),
            "initial_balance": round(acct["initial_balance"], 4),
            "total_pl":        round(total_value - acct["initial_balance"], 4),
            "total_pl_pct":    round(
                (total_value / acct["initial_balance"] - 1.0) * 100.0, 3,
            ) if acct["initial_balance"] else 0.0,
        }

    return {
        "accounts": accounts_summary,
        "holdings": enriched_holdings,
    }


# ── Fibonacci sphere node positions ──────────────────────────────────────────

def _fibonacci_sphere(tickers: list[str], r: float = 1.0) -> list[dict[str, Any]]:
    n = len(tickers)
    nodes: list[dict[str, Any]] = []
    for i, ticker in enumerate(tickers):
        theta = math.acos(1.0 - (2.0 * (i + 0.5)) / n)
        phi   = math.pi * (1.0 + math.sqrt(5.0)) * i
        nodes.append({
            "id":    DISPLAY_NAMES.get(ticker, ticker),
            "x":     round(r * math.sin(theta) * math.cos(phi), 4),
            "y":     round(r * math.cos(theta), 4),
            "z":     round(r * math.sin(theta) * math.sin(phi), 4),
            "group": TICKER_GROUPS.get(ticker, "TECH"),
        })
    return nodes


_BASE_NODES: list[dict[str, Any]] = _fibonacci_sphere(TICKERS)


def _perturb_nodes(
    base:  list[dict[str, Any]],
    sigma: float = 0.025,
    rng:   random.Random | None = None,
) -> list[dict[str, Any]]:
    """Apply small Gaussian jitter to node positions for live animation."""
    r = rng or random.Random()
    return [
        {**node,
         "x": round(node["x"] + r.gauss(0.0, sigma), 4),
         "y": round(node["y"] + r.gauss(0.0, sigma), 4),
         "z": round(node["z"] + r.gauss(0.0, sigma), 4)}
        for node in base
    ]


# ── Startup helpers ───────────────────────────────────────────────────────────

def _sync_price_state_from_db() -> None:
    """Pull the latest close per ticker from market_ticks into ``_PRICE_STATE``.

    Called once at startup after ``fetch_live_market_data()`` populates the DB.
    This ensures the SSE stream shows real market prices from the first tick,
    not the GBM mock values seeded by ``_init_price_history()``.
    """
    prices = get_latest_prices()
    synced = 0
    for ticker, data in prices.items():
        if ticker in _PRICE_STATE:
            real_price = data["price"]
            _PRICE_STATE[ticker] = real_price
            buf = _PRICE_HISTORY.get(ticker)
            if buf:
                buf[-1] = real_price   # anchor last history point to the real close
            synced += 1
    logger.info("price_state_synced_from_db", extra={"synced": synced, "total": len(prices)})


def _init_price_history() -> None:
    """Seed the in-memory rolling buffer with synthetic GBM data."""
    rng = np.random.default_rng(42)
    dt  = 1.0 / 252.0

    for ticker, start in _BASELINE_PRICES.items():
        mu, sigma = 0.10, 0.22
        z          = rng.standard_normal(_HISTORY_SEED)
        log_ret    = (mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z
        closes     = start * np.exp(np.cumsum(log_ret))
        _PRICE_HISTORY[ticker] = list(closes.round(4))
        _PRICE_STATE[ticker]   = float(closes[-1])

    logger.info("price_history_initialised", extra={"tickers": TICKERS, "points": _HISTORY_SEED})


def _load_regime_from_db() -> None:
    """Attempt to read the latest macro regime from TimescaleDB into the cache."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT regime_name, market_phase, confidence_score "
                "FROM macro_regimes ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if row:
            _REGIME_CACHE.update({
                "regime_name":      row[0],
                "market_phase":     row[1],
                "confidence_score": float(row[2]),
            })
            logger.info("regime_loaded_from_db", extra=_REGIME_CACHE)
    except Exception as exc:
        logger.warning("regime_load_fallback", extra={"error": str(exc)})


# ── Live collector loop ───────────────────────────────────────────────────────

_KST = pytz.timezone("Asia/Seoul")


def _get_collection_interval() -> int:
    """Return collection interval in seconds based on KST market hours.

    10 s during KR session (09:00–15:30 KST) or US session (22:30–05:00 KST).
    60 s otherwise.
    """
    now = datetime.now(_KST)
    h, m = now.hour, now.minute
    in_kr = (h == 9 and m >= 0) or (9 < h < 15) or (h == 15 and m <= 30)
    in_us = h >= 22 or h < 5
    return 10 if (in_kr or in_us) else 60


async def _live_collector_loop() -> None:
    """Background task: fetch real OHLCV + news from Yahoo Finance every 60 s.

    Lifecycle:
    - Created (asyncio.create_task) when the first SSE client connects.
    - Cancelled automatically when the last SSE client disconnects.
    - Each cycle: fetch market data → upsert DB → clear price cache → fetch news.
    - Network errors are logged and swallowed so the loop never crashes.
    """
    logger.info("live_collector_started")
    while True:
        # ── Market data ───────────────────────────────────────────────────────
        try:
            rows = await asyncio.to_thread(fetch_live_market_data)
            logger.info("live_collector_market_ok", extra={"rows": rows})
            # Invalidate the DB price cache so the next SSE tick reads fresh data
            _DB_PRICE_CACHE.clear()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("live_collector_market_error", extra={"error": str(exc)})

        # ── News ──────────────────────────────────────────────────────────────
        try:
            news = await asyncio.to_thread(fetch_live_news)
            _LIVE_NEWS_CACHE.update(news)
            logger.info("live_collector_news_ok", extra={"tickers": list(news.keys())})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("live_collector_news_error", extra={"error": str(exc)})

        # ── Market indices ────────────────────────────────────────────────────
        try:
            idx = await asyncio.to_thread(fetch_live_index_data)
            _INDEX_CACHE.update(idx)
            logger.info("live_collector_index_ok", extra={"indices": list(idx.keys())})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("live_collector_index_error", extra={"error": str(exc)})

        interval = _get_collection_interval()
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("live_collector_stopped")
            raise


async def _on_sse_disconnect() -> None:
    """Decrement connection counter; cancel the collector task when idle."""
    global _LIVE_COLLECTOR_TASK, _SSE_CONNECTION_COUNT
    _SSE_CONNECTION_COUNT = max(0, _SSE_CONNECTION_COUNT - 1)
    if _SSE_CONNECTION_COUNT == 0 and _LIVE_COLLECTOR_TASK is not None:
        _LIVE_COLLECTOR_TASK.cancel()
        _LIVE_COLLECTOR_TASK = None
        logger.info("live_collector_task_cancelled", extra={"reason": "no_active_connections"})


# ── Live tick ─────────────────────────────────────────────────────────────────

def _tick(rng: random.Random) -> None:
    """Advance prices by one random-walk step and append to history buffer."""
    for ticker in TICKERS:
        current = _PRICE_STATE[ticker]
        noise   = rng.gauss(0.0, 0.0004) * current
        new_px  = max(current + noise, current * 0.85)
        _PRICE_STATE[ticker] = round(new_px, 4)

        buf = _PRICE_HISTORY[ticker]
        buf.append(round(new_px, 4))
        if len(buf) > _HISTORY_LEN:
            buf.pop(0)


# ── Payload assembly ──────────────────────────────────────────────────────────

def _build_payload(rng: random.Random, persona: PersonaProfile = "AGGRESSIVE") -> dict[str, Any]:
    """Assemble the full UI-contract JSON payload for one SSE tick.

    Price data source (per ticker, in priority order):
      1. Last 20 rows from ``market_ticks`` (DB, real seeded OHLCV) + latest live tick
      2. In-memory rolling buffer ``_PRICE_HISTORY`` (GBM fallback when DB unavailable)
    """
    macro_phase = _REGIME_CACHE.get("market_phase", "LATE_CYCLE")

    risk_matrix: list[dict[str, Any]] = []
    confidences: list[float]          = []

    for ticker in TICKERS:
        # ── Prefer DB-backed price history ────────────────────────────────────
        db_df = _fetch_price_df_from_db(ticker, n_rows=20)
        if db_df is not None and len(db_df) >= 5:
            # Append current live tick so the engine sees the freshest price
            live_row = pd.DataFrame({"close_price": [_PRICE_STATE[ticker]]})
            price_df = pd.concat([db_df, live_row], ignore_index=True)
        else:
            # Fallback: in-memory GBM buffer (always available)
            price_df = pd.DataFrame({"close_price": _PRICE_HISTORY[ticker]})

        # Prefer live Yahoo Finance headlines; fall back to static seed corpus
        news = _LIVE_NEWS_CACHE.get(ticker) or _TICKER_NEWS.get(ticker, [])
        row  = build_intelligence_row(ticker, price_df, news, macro_phase, persona)

        risk_matrix.append(row)
        confidences.append(float(row.get("_confidence", 0.5)))

    # Portfolio health: average confidence scaled to 0–100
    health_score = round(float(np.mean(confidences)) * 100, 1)

    # James Simons — Regime Switching: if any ticker triggered crisis mode,
    # escalate macro_regime to CRISIS_MODE in the SSE payload.
    any_regime_switch = any(row.get("_regime_switch", False) for row in risk_matrix)
    any_vol_spike     = any(row.get("_vol_spike", False)     for row in risk_matrix)

    if any_regime_switch:
        live_regime_name   = "CRISIS_MODE"
        live_regime_conf   = 0.95
    elif any_vol_spike:
        live_regime_name   = "VOLATILITY_REGIME"
        live_regime_conf   = 0.88
    else:
        live_regime_name   = _REGIME_CACHE.get("regime_name", "POLICY_TIGHTENING")
        live_regime_conf   = _REGIME_CACHE.get("confidence_score", 0.85)

    # Derive active_signals from risk_matrix (top 3 by confidence)
    sorted_rows = sorted(
        zip(TICKERS, risk_matrix, confidences, strict=False),
        key=lambda t: t[2],
        reverse=True,
    )
    active_signals = [
        {
            "action":      row["sig_score"],
            "strategy":    f"{DISPLAY_NAMES.get(t, t)}: {row['momentum']} momentum, "
                           f"{row['sentiment']} sentiment"
                           + (" [MoS-LOCK]" if row.get("_margin_of_safety_lock") else ""),
            "probability": round(conf, 3),
        }
        for t, row, conf in sorted_rows[:3]
    ]

    # Clean risk_matrix rows (drop internal fields)
    clean_matrix = [
        {k: v for k, v in row.items() if not k.startswith("_")}
        for row in risk_matrix
    ]

    return {
        "timestamp": datetime.now(tz=_KST).isoformat(),
        "status":    "LIVE",
        "portfolio_health": {
            "score":  health_score,
            "source": "MARKET_DATA",
        },
        "macro_regime": {
            "regime_name":      live_regime_name,
            "market_phase":     _REGIME_CACHE.get("market_phase", "LATE_CYCLE"),
            "confidence_score": live_regime_conf,
        },
        "active_signals":        active_signals,
        "intelligence_synthesis": {
            "assets_count":  len(TICKERS),
            "vector_mode":   "AI-WEIGHTED VECTORS",
            "network_nodes": _perturb_nodes(_BASE_NODES, sigma=0.025, rng=rng),
            "risk_matrix":   clean_matrix,
        },
        "market_indices":    dict(_INDEX_CACHE),
        "macro_indicators":  dict(_MACRO_CACHE),
        "virtual_portfolio": _build_portfolio_summary(),
    }


# ── OMNI command scenarios ────────────────────────────────────────────────────

def _twist_nodes_tech_reduce() -> list[dict[str, Any]]:
    """TECH nodes pulled inward, KR_TECH pushed outward — reduce tech posture."""
    return [
        {**node,
         "x": round(node["x"] * (0.55 if node["group"] == "TECH" else 1.45), 4),
         "y": round(node["y"] * (0.55 if node["group"] == "TECH" else 1.45), 4),
         "z": round(node["z"] * (0.55 if node["group"] == "TECH" else 1.45), 4)}
        for node in _BASE_NODES
    ]


def _twist_nodes_kr_focus() -> list[dict[str, Any]]:
    """KR_TECH nodes pulled to centre — deep dive KR semi focus."""
    return [
        {**node,
         "x": round(node["x"] * (0.40 if node["group"] == "KR_TECH" else 1.0), 4),
         "y": round(node["y"] * (0.40 if node["group"] == "KR_TECH" else 1.0), 4),
         "z": round(node["z"] * (0.40 if node["group"] == "KR_TECH" else 1.0), 4)}
        for node in _BASE_NODES
    ]


def _twist_nodes_defensive() -> list[dict[str, Any]]:
    """All nodes compact cluster — defensive formation on regime shift."""
    return [
        {**node, "x": round(node["x"] * 0.35, 4),
                 "y": round(node["y"] * 0.35, 4),
                 "z": round(node["z"] * 0.35, 4)}
        for node in _BASE_NODES
    ]


_SCENARIO_TECH_Q3: dict[str, Any] = {
    "report": (
        "▌ ALEPH-ONE MACRO SYNTHESIS — Q3 TECH SECTOR POSTURE\n"
        "═══════════════════════════════════════════════════════\n\n"
        "REGIME  : POLICY_TIGHTENING / LATE_CYCLE\n"
        "VECTOR  : RISK-ADJUSTED REDUCTION RECOMMENDED\n\n"
        "[MACRO ANALYSIS]\n"
        "Q3 macro headwinds remain elevated. The Fed's 'higher-for-longer' commitment\n"
        "compresses multiples for high-beta tech names. TSLA is the highest-risk node\n"
        "given demand elasticity and margin compression risk.\n\n"
        "[SIGNAL SYNTHESIS]\n"
        "→ AAPL     : HOLD  — Services segment buffers rate sensitivity\n"
        "→ MSFT     : HOLD  — Copilot monetisation offsets multiple compression\n"
        "→ TSLA     : SELL  — Demand destruction in EV cycle; reduce exposure -12%\n"
        "→ 삼성전자  : BUY   — HBM3E ramp driven by NVDA supply chain surge\n"
        "→ SK하이닉스: BUY   — Best-positioned for AI memory tailwinds in H2\n\n"
        "[RECOMMENDATION]\n"
        "Rotate TSLA allocation into KR semiconductor. Maintain AAPL/MSFT as\n"
        "defensive tech anchors. Net tech beta reduction target: -12%."
    ),
    "risk_matrix": [
        {"ticker": "AAPL",   "momentum": "STABLE", "regime": "WATCH", "rates": "WATCH", "sentiment": "STABLE", "sig_score": "HOLD"},
        {"ticker": "MSFT",   "momentum": "STABLE", "regime": "WATCH", "rates": "WATCH", "sentiment": "STABLE", "sig_score": "HOLD"},
        {"ticker": "TSLA",   "momentum": "WATCH",  "regime": "WATCH", "rates": "WATCH", "sentiment": "WATCH",  "sig_score": "SELL"},
        {"ticker": "삼성전자",  "momentum": "WATCH",  "regime": "STABLE","rates": "STABLE","sentiment": "STABLE","sig_score": "BUY"},
        {"ticker": "SK하이닉스","momentum": "WATCH",  "regime": "STABLE","rates": "STABLE","sentiment": "STABLE","sig_score": "BUY"},
    ],
}

_SCENARIO_KR_SEMI: dict[str, Any] = {
    "report": (
        "▌ ALEPH-ONE KR SEMICONDUCTOR DEEP ANALYSIS\n"
        "═══════════════════════════════════════════\n\n"
        "REGIME  : EXPANSION / EARLY_CYCLE (KR domestic)\n"
        "VECTOR  : ACCUMULATE KR SEMI ON AI MEMORY CYCLE\n\n"
        "[ANALYSIS]\n"
        "HBM3/HBM3E demand from hyperscalers (NVDA, AMD, Google) is driving\n"
        "a structural memory supercycle. Both Samsung and SK Hynix are at\n"
        "capacity constraints — pricing power is exceptionally strong.\n\n"
        "[SIGNALS]\n"
        "→ 삼성전자  : BUY   — HBM market share recovery, foundry TSMC gap narrowing\n"
        "→ SK하이닉스: BUY   — #1 HBM3E supplier; sold out through H1 next year\n\n"
        "[RISK FACTORS]\n"
        "⚠ KRW/USD exposure; China restriction escalation; geopolitical premium\n\n"
        "[RECOMMENDATION]\n"
        "Overweight KR semi 8-15% of portfolio. Hedge FX with KRW/USD forward."
    ),
    "risk_matrix": [
        {"ticker": "AAPL",   "momentum": "STABLE", "regime": "STABLE","rates": "WATCH", "sentiment": "STABLE","sig_score": "HOLD"},
        {"ticker": "MSFT",   "momentum": "STABLE", "regime": "STABLE","rates": "WATCH", "sentiment": "STABLE","sig_score": "HOLD"},
        {"ticker": "TSLA",   "momentum": "WATCH",  "regime": "WATCH", "rates": "WATCH", "sentiment": "WATCH", "sig_score": "HOLD"},
        {"ticker": "삼성전자",  "momentum": "WATCH",  "regime": "STABLE","rates": "STABLE","sentiment": "STABLE","sig_score": "BUY"},
        {"ticker": "SK하이닉스","momentum": "WATCH",  "regime": "STABLE","rates": "STABLE","sentiment": "STABLE","sig_score": "BUY"},
    ],
}

_SCENARIO_REGIME: dict[str, Any] = {
    "report": (
        "▌ ALEPH-ONE REGIME SHIFT ALERT\n"
        "════════════════════════════════\n\n"
        "CURRENT REGIME : POLICY_TIGHTENING → TRANSITIONING\n"
        "NEW REGIME     : RISK_OFF / CONTRACTION (probability: 67%)\n\n"
        "[REGIME ANALYSIS]\n"
        "Leading indicators signal early contraction: PMI sub-50, yield curve\n"
        "inversion deepening, credit spreads widening. The tightening cycle\n"
        "is creating lagged demand destruction across rate-sensitive sectors.\n\n"
        "[DEFENSIVE ROTATION]\n"
        "→ Reduce high-beta cyclicals (TSLA, growth tech)\n"
        "→ Increase defensive allocation: healthcare, utilities, cash equivalents\n"
        "→ Duration extension: long-end bonds attractive at peak rates\n\n"
        "[ALL SIGNALS DEFENSIVE]\n"
        "→ AAPL : HOLD  → MSFT : HOLD  → TSLA : SELL\n"
        "→ 삼성  : HOLD  → SK하이: HOLD\n\n"
        "[RECOMMENDATION]\n"
        "Reduce equity beta 20%. Shift 15% to fixed income duration play.\n"
        "Set volatility alerts on all positions at 2σ from current levels."
    ),
    "risk_matrix": [
        {"ticker": "AAPL",   "momentum": "WATCH", "regime": "WATCH","rates": "WATCH","sentiment": "STABLE","sig_score": "HOLD"},
        {"ticker": "MSFT",   "momentum": "WATCH", "regime": "WATCH","rates": "WATCH","sentiment": "STABLE","sig_score": "HOLD"},
        {"ticker": "TSLA",   "momentum": "WATCH", "regime": "WATCH","rates": "WATCH","sentiment": "WATCH", "sig_score": "SELL"},
        {"ticker": "삼성전자",  "momentum": "WATCH", "regime": "WATCH","rates": "WATCH","sentiment": "STABLE","sig_score": "HOLD"},
        {"ticker": "SK하이닉스","momentum": "WATCH", "regime": "WATCH","rates": "WATCH","sentiment": "STABLE","sig_score": "HOLD"},
    ],
}

_OMNI_SCENARIOS: list[tuple[frozenset[str], dict[str, Any], list[dict[str, Any]]]] = [
    (
        frozenset({"tech", "q3", "exposure", "reduce", "trim"}),
        _SCENARIO_TECH_Q3,
        _twist_nodes_tech_reduce(),
    ),
    (
        frozenset({"korea", "kr", "semiconductor", "hbm", "samsung", "hynix", "memory"}),
        _SCENARIO_KR_SEMI,
        _twist_nodes_kr_focus(),
    ),
    (
        frozenset({"regime", "cycle", "tightening", "contraction", "recession", "rate", "rates"}),
        _SCENARIO_REGIME,
        _twist_nodes_defensive(),
    ),
]

_DEFAULT_RESPONSE: dict[str, Any] = {
    "report": (
        "▌ ALEPH-ONE GENERAL PORTFOLIO HEALTH CHECK\n"
        "════════════════════════════════════════════\n\n"
        "SYSTEM ONLINE — All engines nominal.\n\n"
        "Current regime: POLICY_TIGHTENING / LATE_CYCLE\n"
        "Portfolio status: MONITORING — no immediate action required.\n\n"
        "Type a specific command to activate scenario analysis.\n"
        "Examples: 'tech exposure Q3', 'KR semiconductor', 'regime shift'"
    ),
    "risk_matrix": None,
}


def _match_scenario(
    query: str,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    words = frozenset(query.lower().split())
    for keywords, scenario, nodes in _OMNI_SCENARIOS:
        if keywords & words:
            return scenario, nodes
    return _DEFAULT_RESPONSE, None


# ── LangChain Agent — Tools, Builder, Runner ──────────────────────────────────

_AGENT_SYSTEM_PROMPT: str = (
    "You are ALEPH-ONE — a J.A.R.V.I.S.-style hyper-professional financial "
    "intelligence synchronizer. You operate with the precision of a top-tier "
    "quantitative hedge fund. Your universe: AAPL · MSFT · TSLA · 005930(삼성전자) · "
    "000660(SK하이닉스).\n\n"
    "Core analytical framework embedded in your engines:\n"
    "• Ray Dalio — Volatility Targeting: vol_spike (recent 5-day σ > 1.5× 20-day σ) "
    "forces status WATCH + applies momentum penalty\n"
    "• James Simons — Regime Switching: crisis keyword frequency "
    "(inflation/hawkish/tightening/crisis ≥ 3 occurrences) → CRISIS_MODE\n"
    "• Warren Buffett — Margin of Safety: RSI ≥ 70 locks BUY → HOLD for CONSERVATIVE\n\n"
    "Operational protocol (analysis queries):\n"
    "1. Call search_news_database with the user query to retrieve the most relevant\n"
    "   real news articles from the Milvus vector store for RAG context\n"
    "2. Call get_quant_intelligence for each relevant ticker (momentum, RSI, vol_spike)\n"
    "3. Call get_sentiment_intelligence for each relevant ticker (sentiment, regime_switch)\n"
    "4. Synthesize findings — real news context + quant signals — into a sharp briefing\n"
    "5. Cite specific headlines from search_news_database when making claims\n"
    "6. Lead with actionable signals and quantitative evidence\n"
    "7. Concise and data-driven — no vague commentary\n"
    "8. Format like a top-tier hedge fund quant report with clear sections\n\n"
    "Virtual Broker protocol (when the user asks you to trade, rebalance, or\n"
    "execute a position — this is paper trading against a simulated KRW/USD\n"
    "account, never real money):\n"
    "1. Call get_portfolio_summary_tool FIRST to see current cash and holdings\n"
    "2. Call get_quant_intelligence (and run_backtest_tool if validating a\n"
    "   strategy) for every ticker under consideration before sizing an order\n"
    "3. Size each order against the cash actually available in that ticker's\n"
    "   currency account (KRW for 6-digit KR tickers, USD otherwise) — never\n"
    "   assume unlimited cash\n"
    "4. Call execute_virtual_order_tool per ticker; if a status is REJECTED,\n"
    "   report the exact reason — do not retry blindly or claim it succeeded\n"
    "5. After all orders, call get_portfolio_summary_tool again and report the\n"
    "   resulting position sizes, cash remaining, and rationale per trade"
)

# Lazy-initialised AgentExecutor singleton — built on first OMNI command
_AGENT_EXECUTOR: Any = None


@tool
def get_quant_intelligence(ticker: str) -> str:
    """Run the Aleph-One QuantEngine on a specific equity ticker.

    Returns SMA-5/20 golden/dead-cross momentum analysis, Ray Dalio volatility
    targeting spike detection, and Warren Buffett Margin of Safety RSI(14) status.
    Use this tool to obtain quantitative market signals for a specific ticker.

    Args:
        ticker: Internal ticker ID. Valid values: AAPL, MSFT, TSLA, 005930, 000660
    """
    price_df = _fetch_price_df_from_db(ticker, n_rows=20)
    if price_df is None or price_df.empty:
        return json.dumps({"error": f"no_price_data_for_{ticker}", "ticker": ticker})

    live_price = _PRICE_STATE.get(ticker)
    if live_price:
        price_df = pd.concat(
            [price_df, pd.DataFrame({"close_price": [live_price]})],
            ignore_index=True,
        )

    q = QuantEngine().analyze(ticker, price_df, [])
    rsi_val = _compute_rsi(price_df["close_price"].astype(float))

    return json.dumps({
        "ticker":            ticker,
        "display_name":      DISPLAY_NAMES.get(ticker, ticker),
        "momentum_score":    round(q["momentum_score"], 3),
        "status":            q["status"],
        "golden_cross":      q["golden_cross"],
        "dead_cross":        q["dead_cross"],
        "vol_spike":         q["vol_spike"],
        "vol_spike_penalty": round(q["vol_spike_penalty"], 3),
        "vol_ratio_pct":     f"{q['vol_ratio']:.2%}",
        "sma5":              round(q["sma5_last"], 2),
        "sma20":             round(q["sma20_last"], 2),
        "rsi":               round(rsi_val, 2),
        "margin_of_safety":  "UNSAFE_OVERBOUGHT" if rsi_val >= 70.0 else "SAFE",
    })


@tool
def get_sentiment_intelligence(ticker: str) -> str:
    """Run the Aleph-One SentimentEngine on the latest news for a specific equity ticker.

    Applies weighted financial lexicon scoring and James Simons Regime Switching
    (crisis keyword frequency → regime_switch flag) to Yahoo Finance news headlines.
    Use this tool to assess news sentiment and macro regime signals for a specific ticker.

    Args:
        ticker: Internal ticker ID. Valid values: AAPL, MSFT, TSLA, 005930, 000660
    """
    news = _LIVE_NEWS_CACHE.get(ticker) or _TICKER_NEWS.get(ticker, [])
    if not news:
        return json.dumps({"error": f"no_news_for_{ticker}", "ticker": ticker})

    dummy_df = pd.DataFrame({"close_price": [100.0] * 5})
    s = SentimentEngine().analyze(ticker, dummy_df, news)

    return json.dumps({
        "ticker":               ticker,
        "display_name":         DISPLAY_NAMES.get(ticker, ticker),
        "sentiment_score":      round(s["sentiment_score"], 3),
        "positive_ratio":       f"{s['positive_ratio']:.2%}",
        "negative_ratio":       f"{s['negative_ratio']:.2%}",
        "regime_switch":        s["regime_switch"],
        "crisis_keyword_count": s["crisis_keyword_count"],
        "news_count":           s["sample_size"],
        "macro_regime_signal":  "CRISIS_MODE" if s["regime_switch"] else "NORMAL",
        "top_headlines":        news[:3],
    })


@tool
def search_news_database(query: str, ticker: str = "") -> str:
    """Search the Milvus vector database for real news most semantically similar to the query.

    Uses sentence-transformers/all-MiniLM-L6-v2 to embed the query and retrieves
    the top-3 most relevant Yahoo Finance headlines ingested by the live collector.
    Call this FIRST to ground your analysis in real, timestamped market news.

    Args:
        query:  Natural-language query (e.g. "AI chip demand outlook", "Fed rate hike impact")
        ticker: Optional ticker filter: AAPL, MSFT, TSLA, 005930, 000660 — or "" for all tickers
    """
    hits = search_milvus_news(query, ticker=ticker or None, top_k=3)
    if not hits:
        fallback = _LIVE_NEWS_CACHE or _TICKER_NEWS
        sample   = []
        for t, headlines in fallback.items():
            if not ticker or t == ticker:
                sample.extend(headlines[:2])
        if sample:
            return json.dumps({
                "source":   "in_memory_fallback",
                "note":     "Milvus unavailable — returning cached headlines",
                "results":  [{"title": h, "score": 0.0} for h in sample[:3]],
            })
        return json.dumps({"source": "empty", "results": []})

    return json.dumps({
        "source":  "milvus_vector_db",
        "query":   query,
        "ticker":  ticker or "all",
        "results": hits,
    })


@tool
def execute_virtual_order_tool(ticker: str, side: str, quantity: float) -> str:
    """Place an immediate-fill virtual order against the live Aleph-One paper-trading book.

    Fills at the current live tick price (``_PRICE_STATE``) — there is no real
    brokerage involved. BUY debits the ticker's currency account (KRW for
    6-digit KR tickers, USD otherwise) and increases the held position at a
    blended average cost. SELL credits cash and reduces the position. Orders
    are rejected (not raised as errors) on insufficient cash or insufficient
    holdings — always report the ``status`` field back to the user verbatim.

    Args:
        ticker:   Internal ticker ID. Valid values: AAPL, MSFT, TSLA, QQQ, BND,
                   GLD, 005930, 000660, 035420, 051910, 006400, 122630
        side:     "BUY" or "SELL"
        quantity: Number of shares/units to trade. Must be positive.
    """
    side_upper = side.upper()
    if side_upper not in ("BUY", "SELL"):
        return json.dumps({"status": "REJECTED", "reason": f"invalid_side_{side}"})

    live_price = _PRICE_STATE.get(ticker)
    if not live_price:
        return json.dumps({"status": "REJECTED", "reason": f"no_live_price_for_{ticker}"})

    result = execute_virtual_order(ticker, side_upper, quantity, live_price)  # type: ignore[arg-type]
    if result.get("status") == "FILLED":
        _build_portfolio_summary(force_refresh=True)
    return json.dumps(result)


@tool
def get_portfolio_summary_tool() -> str:
    """Return the current virtual-broker state: cash balances, holdings, and P&L.

    Reports both the KRW and USD paper-trading accounts separately (cash,
    mark-to-market holding value, total value, and unrealized P&L vs the
    initial seed balance), plus a per-position breakdown. Call this before
    sizing a new order (to check available cash) and after executing trades
    (to confirm the result).
    """
    return json.dumps(_build_portfolio_summary())


@tool
def run_backtest_tool(ticker: str) -> str:
    """Backtest the SMA(5/20) crossover strategy on a ticker's recent price history.

    Vectorized walk-forward simulation: long when the 5-day SMA crosses above
    the 20-day SMA, flat otherwise. Returns total return %, max drawdown %, and
    trade count — use this to validate a strategy BEFORE recommending or
    executing a virtual order on a ticker.

    Args:
        ticker: Internal ticker ID. Valid values: AAPL, MSFT, TSLA, QQQ, BND,
                 GLD, 005930, 000660, 035420, 051910, 006400, 122630
    """
    price_df = _fetch_price_df_from_db(ticker, n_rows=60)
    if price_df is None or len(price_df) < 20:
        price_df = pd.DataFrame({"close_price": _PRICE_HISTORY.get(ticker, [])})
    if price_df.empty or len(price_df) < 20:
        return json.dumps({"error": f"insufficient_price_history_for_{ticker}", "ticker": ticker})

    try:
        result = BacktestEngine().run(ticker, price_df)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "ticker": ticker})

    return json.dumps({
        "ticker":           result.ticker,
        "display_name":     DISPLAY_NAMES.get(ticker, ticker),
        "strategy":         result.strategy,
        "bars":             result.bars,
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "num_trades":       result.num_trades,
        "final_value":      round(result.final_value, 2),
    })


def _build_lc_agent() -> Any:  # noqa: ANN401
    """Construct a LangChain 1.x tool-calling agent (provider from config).

    Imports are deferred so the module loads even without the provider packages
    installed. Raises RuntimeError (caught by intelligence_command → fallback)
    if required packages are absent.
    """
    try:
        from langgraph.prebuilt import create_react_agent
    except ImportError as exc:
        raise RuntimeError(
            f"LangGraph packages unavailable: {exc}. "
            "Ensure langgraph>=0.2.0 is installed."
        ) from exc

    llm = config.get_llm()
    tools = [
        search_news_database,
        get_quant_intelligence,
        get_sentiment_intelligence,
        run_backtest_tool,
        get_portfolio_summary_tool,
        execute_virtual_order_tool,
    ]
    agent = create_react_agent(llm, tools, prompt=_AGENT_SYSTEM_PROMPT)
    logger.info("lc_agent_built", extra={"tools": len(tools)})
    return agent


async def _run_agent_async(query: str, persona: PersonaProfile) -> dict[str, Any]:
    """Invoke the LangChain agent and assemble a full UI-contract response.

    Pipeline:
    1. Run the agent (uses tools to fetch real engine data) → briefing text.
    2. Execute the full engine pipeline for all tickers → live risk_matrix.
    3. Combine into the UI-contract JSON shape (same schema as SSE stream).
    """
    global _AGENT_EXECUTOR
    if _AGENT_EXECUTOR is None:
        _AGENT_EXECUTOR = _build_lc_agent()

    # Run agent in thread pool — LangChain sync invoke blocks the event loop otherwise
    agent_result: dict[str, Any] = await asyncio.to_thread(
        _AGENT_EXECUTOR.invoke,
        {"messages": [{"role": "user", "content": query}]},
    )
    # LangChain 1.x returns {"messages": [...]}; walk backwards to find the last
    # AIMessage (not a ToolMessage which has tool_call_id and no synthesis content).
    messages: list[Any] = agent_result.get("messages", [])
    logger.info(
        "agent_pipeline_trace",
        extra={
            "message_count": len(messages),
            "message_types":  [type(m).__name__ for m in messages],
        },
    )
    briefing: str = "Analysis complete."
    for msg in reversed(messages):
        content      = getattr(msg, "content", None)
        tool_call_id = getattr(msg, "tool_call_id", None)
        if content and not tool_call_id:
            briefing = str(content)
            break

    # Rebuild risk_matrix from the live engine pipeline for this cycle
    rng = random.Random()
    _tick(rng)
    macro_phase = _REGIME_CACHE.get("market_phase", "LATE_CYCLE")
    risk_matrix: list[dict[str, Any]] = []
    confidences: list[float]           = []

    for ticker in TICKERS:
        db_df = _fetch_price_df_from_db(ticker, n_rows=20)
        if db_df is not None and len(db_df) >= 5:
            live_row = pd.DataFrame({"close_price": [_PRICE_STATE[ticker]]})
            price_df = pd.concat([db_df, live_row], ignore_index=True)
        else:
            price_df = pd.DataFrame({"close_price": _PRICE_HISTORY[ticker]})

        news = _LIVE_NEWS_CACHE.get(ticker) or _TICKER_NEWS.get(ticker, [])
        row  = build_intelligence_row(ticker, price_df, news, macro_phase, persona)
        risk_matrix.append(row)
        confidences.append(float(row.get("_confidence", 0.5)))

    health_score      = round(float(np.mean(confidences)) * 100, 1)
    any_regime_switch = any(r.get("_regime_switch", False) for r in risk_matrix)
    any_vol_spike     = any(r.get("_vol_spike", False)     for r in risk_matrix)
    live_regime_name  = (
        "CRISIS_MODE"       if any_regime_switch else
        "VOLATILITY_REGIME" if any_vol_spike     else
        _REGIME_CACHE.get("regime_name", "POLICY_TIGHTENING")
    )

    sorted_rows = sorted(
        zip(TICKERS, risk_matrix, confidences, strict=False),
        key=lambda t: t[2],
        reverse=True,
    )
    active_signals = [
        {
            "action":      row["sig_score"],
            "strategy":    f"{DISPLAY_NAMES.get(t, t)}: Agent-synthesised signal",
            "probability": round(conf, 3),
        }
        for t, row, conf in sorted_rows[:3]
    ]
    clean_matrix = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in risk_matrix
    ]

    logger.info("agent_response_assembled", extra={"health": health_score})
    return {
        "timestamp": datetime.now(tz=_KST).isoformat(),
        "status":    "ANALYZED",
        "portfolio_health": {
            "score":  health_score,
            "source": "LANGCHAIN_AGENT",
        },
        "macro_regime": {
            "regime_name":      live_regime_name,
            "market_phase":     _REGIME_CACHE.get("market_phase", "LATE_CYCLE"),
            "confidence_score": _REGIME_CACHE.get("confidence_score", 0.85),
        },
        "active_signals": active_signals,
        "intelligence_synthesis": {
            "assets_count":  len(TICKERS),
            "vector_mode":   "LANGCHAIN-AGENT VECTORS",
            "network_nodes": _perturb_nodes(_BASE_NODES, sigma=0.03, rng=rng),
            "risk_matrix":   clean_matrix,
        },
        "omni_report":       briefing,
        "virtual_portfolio": _build_portfolio_summary(force_refresh=True),
    }


# ── FastAPI application ───────────────────────────────────────────────────────

async def _macro_collector_loop() -> None:
    """Hourly background task: fetch FRED/yfinance macro indicators → _MACRO_CACHE.

    Runs once immediately at startup (so the cache is warm on first SSE request),
    then every 3600 seconds thereafter.  Errors are logged and swallowed so the
    loop never crashes the server.
    """
    logger.info("macro_collector_started")
    while True:
        try:
            data = await asyncio.to_thread(fetch_macro_indicators)
            if data:
                _MACRO_CACHE.update(data)
                logger.info("macro_cache_updated", extra={"keys": list(data.keys())})
        except asyncio.CancelledError:
            logger.info("macro_collector_stopped")
            raise
        except Exception as exc:
            logger.warning("macro_collector_error", extra={"error": str(exc)})
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("macro_collector_stopped")
            raise


async def _fund_nav_collector_loop() -> None:
    """Daily background task: fetch KOFIA fund NAV → _FUND_NAV_CACHE.

    NAV (기준가) is published once per trading day, so this runs every 86400
    seconds. fetch_fund_nav() is a no-op while KOFIA_API_KEY/FUND_NAV_TARGETS
    are unconfigured (default), so this loop is dormant until a real KOFIA
    adapter is implemented. Errors are logged and swallowed so the loop never
    crashes the server.
    """
    logger.info("fund_nav_collector_started")
    while True:
        try:
            data = await asyncio.to_thread(fetch_fund_nav)
            if data:
                _FUND_NAV_CACHE.update(data)
                logger.info("fund_nav_cache_updated", extra={"keys": list(data.keys())})
        except asyncio.CancelledError:
            logger.info("fund_nav_collector_stopped")
            raise
        except Exception as exc:
            logger.warning("fund_nav_collector_error", extra={"error": str(exc)})
        try:
            await asyncio.sleep(86400)
        except asyncio.CancelledError:
            logger.info("fund_nav_collector_stopped")
            raise


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: DB init → seed → load history → cache regime. Shutdown: close pool."""
    global _MACRO_COLLECTOR_TASK, _FUND_NAV_COLLECTOR_TASK

    logger.info("aleph_one_startup")
    try:
        await asyncio.to_thread(init_db)
        await asyncio.to_thread(seed_mock_data)
    except Exception as exc:
        logger.warning("db_startup_partial", extra={"error": str(exc)})

    _init_price_history()

    # Fetch real OHLCV on startup so the SSE stream never shows stale GBM prices.
    try:
        rows = await asyncio.to_thread(fetch_live_market_data)
        logger.info("startup_market_fetch_complete", extra={"rows": rows})
        _sync_price_state_from_db()
    except Exception as exc:
        logger.warning("startup_market_fetch_failed", extra={"error": str(exc)})

    try:
        await asyncio.to_thread(_load_regime_from_db)
    except Exception as exc:
        logger.warning("regime_cache_fallback", extra={"error": str(exc)})

    # Milvus vector store — optional; app boots normally if Milvus is unavailable
    try:
        await asyncio.to_thread(init_milvus)
    except Exception as exc:
        logger.warning("milvus_startup_skipped", extra={"error": str(exc)})

    # Start hourly macro indicator collector (runs independently of SSE connections)
    _MACRO_COLLECTOR_TASK = asyncio.create_task(_macro_collector_loop())

    # Start daily fund NAV collector (dormant no-op until KOFIA adapter is real)
    _FUND_NAV_COLLECTOR_TASK = asyncio.create_task(_fund_nav_collector_loop())

    logger.info("aleph_one_ready")
    yield

    if _MACRO_COLLECTOR_TASK is not None:
        _MACRO_COLLECTOR_TASK.cancel()
    if _FUND_NAV_COLLECTOR_TASK is not None:
        _FUND_NAV_COLLECTOR_TASK.cancel()
    _PoolManager.close()
    logger.info("aleph_one_shutdown")


app = FastAPI(
    title="Aleph-One Intelligence API",
    version="2.0.0",
    description=(
        "J.A.R.V.I.S.-style polymorphic financial intelligence synchronizer. "
        "SSE streaming + OMNI:// command terminal."
    ),
    docs_url="/docs",
    redoc_url=None,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/events/recent", tags=["intelligence"])
async def events_recent(limit: int = 15) -> dict[str, Any]:
    """Return the most recently cached news headlines from the live collector.

    Consumed by the frontend ``useNewsStream`` hook (SWR 30-second polling).
    Falls back to the static seed corpus when the live collector has not yet
    populated the cache.
    """
    events: list[dict[str, Any]] = []
    source = _LIVE_NEWS_CACHE if _LIVE_NEWS_CACHE else _TICKER_NEWS
    for ticker, headlines in source.items():
        for headline in headlines:
            events.append({
                "title":        headline,
                "ticker":       ticker,
                "published_at": datetime.now(tz=_KST).isoformat(),
                "source":       "live" if _LIVE_NEWS_CACHE else "seed",
            })
    return {"events": events[:limit], "total": len(events)}


@app.get("/api/regimes/latest", tags=["intelligence"])
async def regimes_latest() -> dict[str, Any]:
    """Latest macro regime for the StatusBar and dashboard regime badge.

    Returns the current in-memory regime derived from the live engine.
    """
    regime_name  = _REGIME_CACHE.get("regime_name",      "POLICY_TIGHTENING")
    market_phase = _REGIME_CACHE.get("market_phase",     "LATE_CYCLE")
    confidence   = _REGIME_CACHE.get("confidence_score", 0.85)
    now          = datetime.now(tz=_KST)
    return {
        "as_of_date":              now.date().isoformat(),
        "regime_id":               f"live_{now.strftime('%Y%m%d')}",
        "regime_timestamp":        now.isoformat(),
        "regime_label":            regime_name,
        "regime_family":           market_phase,
        "confidence":              f"{confidence:.2f}",
        "freshness_status":        "fresh",
        "degraded_status":         "ok",
        "missing_inputs":          [],
        "supporting_snapshot_id":  "",
        "supporting_states":       {},
        "transition": {
            "transition_from_prior": None,
            "transition_type":       "no_change",
            "changed":               False,
        },
        "rationale_summary": f"Live engine: {regime_name} / {market_phase}",
        "warnings":          [],
        "status":            "success",
        "is_seeded":         False,
        "data_source":       "aleph_one_live_engine",
    }


@app.get("/api/signals/latest", tags=["intelligence"])
async def signals_latest(country: str = "US") -> dict[str, Any]:
    """Latest signal summary with trust metadata for the dashboard.

    Full per-ticker signals are served via the SSE stream; this endpoint
    exposes the trust envelope (freshness, availability) consumed by
    dashboard trust indicators and the useSignals hook.
    """
    now         = datetime.now(tz=_KST)
    regime_name = _REGIME_CACHE.get("regime_name", "POLICY_TIGHTENING")
    macro_fresh = bool(_MACRO_CACHE)

    trust: dict[str, Any] = {
        "snapshot_timestamp":          now.isoformat(),
        "previous_snapshot_timestamp": None,
        "freshness_status":            "fresh"   if macro_fresh else "unknown",
        "availability":                "full"    if macro_fresh else "partial",
        "is_degraded":                 not macro_fresh,
        "sources": [
            {
                "source_id":           "aleph_one_live",
                "source_label":        "Aleph-One Live Engine",
                "retrieval_timestamp": now.isoformat(),
            },
        ],
        "changed_indicators_count": None,
        "degraded_reason":          None if macro_fresh else "macro_cache_empty",
    }
    return {
        "country":             country,
        "run_id":              f"run_{now.strftime('%Y%m%d_%H%M')}",
        "signals":             [],
        "signals_count":       0,
        "buy_count":           0,
        "sell_count":          0,
        "hold_count":          0,
        "strongest_signal_id": None,
        "trust":               trust,
        "regime_label":        regime_name,
        "as_of_date":          now.date().isoformat(),
        "is_regime_grounded":  True,
        "status":              "success",
    }


@app.post("/api/v1/finance/macro/sync", tags=["finance"])
async def finance_macro_sync() -> dict[str, Any]:
    """Force-sync macro indicators from FRED (or yfinance proxy) into TimescaleDB.

    Triggers the same pipeline as the hourly background task immediately.
    Use from Swagger UI (/docs) to verify the macro data pipeline end-to-end:
    the response shows which values were fetched, from which source, and the
    current state of ``_MACRO_CACHE`` that feeds every SSE tick.
    """
    data = await asyncio.to_thread(fetch_macro_indicators)
    if data:
        _MACRO_CACHE.update(data)
    return {
        "status":            "ok",
        "source":            "FRED" if FRED_API_KEY else "yfinance_proxy",
        "indicators_synced": len(data),
        "values":            data,
        "macro_cache":       dict(_MACRO_CACHE),
        "timestamp":         datetime.now(tz=_KST).isoformat(),
    }


@app.get("/api/v1/finance/prices", tags=["finance"])
async def finance_prices(tickers: str = "") -> dict[str, Any]:
    """Return the latest close price for all tracked tickers.

    Price source per ticker (priority order):

    1. TimescaleDB ``market_ticks`` — real yfinance data, updated every 60 s
    2. In-memory ``_PRICE_STATE`` — GBM walk fallback when DB has no rows yet

    Query params:

    - ``tickers``: comma-separated internal IDs, e.g. ``AAPL,005930,QQQ``.
      Omit to return all 12 tickers.

    Use from Swagger UI to verify:

    - KR tickers (6-digit codes) show ``.KS``-resolved prices from Yahoo Finance
    - ``source: timescaledb`` confirms data is flowing through the live collector
    - Market-closed sessions should still return the last known close from DB
    """
    db_prices     = await asyncio.to_thread(get_latest_prices)
    ticker_filter = {t.strip() for t in tickers.split(",") if t.strip()} if tickers else set()

    merged: dict[str, Any] = {}
    for ticker in TICKERS:
        if ticker_filter and ticker not in ticker_filter:
            continue
        db_entry   = db_prices.get(ticker)
        live_price = round(_PRICE_STATE.get(ticker, 0.0), 4)
        if db_entry:
            merged[ticker] = {
                "display_name": DISPLAY_NAMES.get(ticker, ticker),
                "price":        db_entry["price"],
                "live_tick":    live_price,
                "timestamp":    db_entry["timestamp"],
                "source":       "timescaledb",
            }
        else:
            merged[ticker] = {
                "display_name": DISPLAY_NAMES.get(ticker, ticker),
                "price":        live_price,
                "live_tick":    live_price,
                "timestamp":    None,
                "source":       "in_memory_gbm",
            }

    return {
        "timestamp": datetime.now(tz=_KST).isoformat(),
        "total":     len(merged),
        "prices":    merged,
    }


@app.get("/api/v1/portfolio/summary", tags=["portfolio"])
async def portfolio_summary() -> dict[str, Any]:
    """Return the current virtual-broker state: cash, holdings, and P&L by currency.

    Same shape as the ``virtual_portfolio`` field on the SSE intelligence stream
    and OMNI command responses — exposed standalone for direct polling (e.g. a
    dashboard panel that doesn't need the full intelligence payload).
    """
    try:
        summary = await asyncio.to_thread(_build_portfolio_summary, force_refresh=True)
        return {
            "timestamp": datetime.now(tz=_KST).isoformat(),
            "status":    "ok",
            **summary,
        }
    except Exception as exc:
        logger.error("portfolio_summary_failed", extra={"error": str(exc)})
        return {
            "timestamp": datetime.now(tz=_KST).isoformat(),
            "status":    "ERROR",
            "error":     str(exc),
        }


@app.get("/api/v1/intelligence/stream", tags=["intelligence"])
async def intelligence_stream(
    request:  Request,
    persona:  PersonaProfile = "AGGRESSIVE",
) -> EventSourceResponse:
    """SSE stream — emits full UI-contract JSON every second.

    On first connect: starts a background asyncio task (_live_collector_loop)
    that fetches real OHLCV + news from Yahoo Finance every 60 seconds and
    refreshes the TimescaleDB market_ticks table. The task is cancelled when
    the last client disconnects, conserving server resources.

    Connect from the frontend::

        const es = new EventSource('/api/v1/intelligence/stream?persona=AGGRESSIVE')
        es.onmessage = (e) => update(JSON.parse(e.data))
    """
    global _LIVE_COLLECTOR_TASK, _SSE_CONNECTION_COUNT

    _SSE_CONNECTION_COUNT += 1
    if _LIVE_COLLECTOR_TASK is None or _LIVE_COLLECTOR_TASK.done():
        _LIVE_COLLECTOR_TASK = asyncio.create_task(_live_collector_loop())
        logger.info(
            "live_collector_task_created",
            extra={"connections": _SSE_CONNECTION_COUNT},
        )

    rng = random.Random()

    async def _generator() -> AsyncGenerator[dict[str, str], None]:
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("sse_client_disconnected")
                    break
                try:
                    _tick(rng)
                    payload = _build_payload(rng, persona)
                    yield {"data": json.dumps(payload, ensure_ascii=False), "event": "intelligence"}
                except Exception as exc:
                    logger.error("sse_tick_error", extra={"error": str(exc)})
                    yield {
                        "data":  json.dumps({"status": "ERROR", "error": str(exc)}),
                        "event": "error",
                    }
                await asyncio.sleep(1.0)
        finally:
            await _on_sse_disconnect()

    return EventSourceResponse(_generator())


# ── OMNI command ──────────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    query:   str
    persona: PersonaProfile = "AGGRESSIVE"


@app.post("/api/v1/intelligence/command", tags=["intelligence"])
async def intelligence_command(body: CommandRequest) -> dict[str, Any]:
    """OMNI:// terminal — LangChain agent response with static-scenario fallback.

    Attempts to run the full LangChain agent pipeline. If langchain /
    langchain-groq are not installed, or the agent raises, falls back to
    keyword-matched scenario responses.

    Example::

        POST /api/v1/intelligence/command
        {"query": "How should I adjust my tech exposure for Q3?", "persona": "AGGRESSIVE"}
    """
    logger.info("omni_command_received", extra={"query": body.query[:80]})

    try:
        response = await _run_agent_async(body.query, body.persona)
        logger.info("omni_agent_dispatched")
        return response
    except Exception as exc:
        logger.warning("omni_agent_fallback", extra={"error": str(exc)})

    # Static keyword-scenario fallback
    scenario, twisted_nodes = _match_scenario(body.query)
    matched = twisted_nodes is not None
    fallback: dict[str, Any] = {
        "timestamp": datetime.now(tz=_KST).isoformat(),
        "status":    "ANALYZED" if matched else "SYNCING",
        "portfolio_health": {
            "score":  75.0,
            "source": "COMMAND_ANALYSIS",
        },
        "macro_regime": {
            "regime_name":      _REGIME_CACHE.get("regime_name",      "POLICY_TIGHTENING"),
            "market_phase":     _REGIME_CACHE.get("market_phase",     "LATE_CYCLE"),
            "confidence_score": _REGIME_CACHE.get("confidence_score", 0.85),
        },
        "active_signals": [
            {
                "action":      "HOLD",
                "strategy":    "Scenario analysis complete. Review risk matrix for guidance.",
                "probability": 0.72,
            }
        ],
        "intelligence_synthesis": {
            "assets_count":  len(TICKERS),
            "vector_mode":   "SCENARIO-OVERRIDE VECTORS",
            "network_nodes": twisted_nodes if twisted_nodes else _BASE_NODES,
            "risk_matrix":   scenario.get("risk_matrix") or [],
        },
        "omni_report": scenario.get("report", ""),
    }
    logger.info("omni_command_dispatched", extra={"matched": matched, "mode": "fallback"})
    return fallback


@app.post("/api/v1/intelligence/command/stream", tags=["intelligence"])
async def intelligence_command_stream(body: CommandRequest) -> EventSourceResponse:
    """OMNI:// streaming terminal — SSE token stream.

    Runs the LangChain agent (or keyword-scenario fallback), then streams the
    response as SSE events so the frontend ResearchPanel can render tokens
    progressively without waiting for the full agent response.

    Event types::

        {"type": "meta",  "macro_regime": {...}, "portfolio_health": {...}, ...}
        {"type": "token", "content": "<word> "}
        {"type": "done"}
    """
    async def _stream() -> AsyncGenerator[dict[str, str], None]:
        try:
            response = await _run_agent_async(body.query, body.persona)
        except Exception as exc:
            logger.warning("omni_stream_fallback", extra={"error": str(exc)})
            scenario, _ = _match_scenario(body.query)
            response = {
                "omni_report":      scenario.get("report", "ANALYSIS UNAVAILABLE"),
                "macro_regime":     {
                    "regime_name":      _REGIME_CACHE.get("regime_name",      "POLICY_TIGHTENING"),
                    "market_phase":     _REGIME_CACHE.get("market_phase",     "LATE_CYCLE"),
                    "confidence_score": _REGIME_CACHE.get("confidence_score", 0.85),
                },
                "portfolio_health": {"score": 75.0, "source": "FALLBACK"},
                "active_signals":   [],
            }

        meta: dict[str, Any] = {
            "type":             "meta",
            "timestamp":        datetime.now(tz=_KST).isoformat(),
            "macro_regime":     response.get("macro_regime",     {}),
            "portfolio_health": response.get("portfolio_health", {}),
            "active_signals":   response.get("active_signals",   []),
        }
        yield {"data": json.dumps(meta, ensure_ascii=False), "event": "message"}

        report: str = response.get("omni_report") or response.get("briefing") or ""
        words = report.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield {
                "data":  json.dumps({"type": "token", "content": chunk}, ensure_ascii=False),
                "event": "message",
            }
            await asyncio.sleep(0.025)

        yield {"data": json.dumps({"type": "done"}, ensure_ascii=False), "event": "message"}

    return EventSourceResponse(_stream())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    uvicorn.run("src.main:app", host="0.0.0.0", port=8001, reload=True)
