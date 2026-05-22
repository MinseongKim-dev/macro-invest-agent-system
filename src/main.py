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
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.tools import tool  # type: ignore[import-not-found]
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.database import (
    _PoolManager,
    fetch_live_market_data,
    fetch_live_news,
    get_connection,
    init_db,
    seed_mock_data,
)
from src.engines import (
    DISPLAY_NAMES,
    TICKER_GROUPS,
    TICKERS,
    PersonaProfile,
    QuantEngine,
    SentimentEngine,
    _compute_rsi,
    build_intelligence_row,
)

logger = logging.getLogger(__name__)

# ── In-memory live state ──────────────────────────────────────────────────────

_BASELINE_PRICES: dict[str, float] = {
    "AAPL":  195.0,
    "MSFT":  415.0,
    "TSLA":  245.0,
    "005930": 72_000.0,
    "000660": 195_000.0,
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

        try:
            await asyncio.sleep(60)
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
        "timestamp": datetime.now(tz=UTC).isoformat(),
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
    "Operational protocol:\n"
    "1. Call get_quant_intelligence for each relevant ticker (momentum, RSI, vol_spike)\n"
    "2. Call get_sentiment_intelligence for each relevant ticker (sentiment, regime_switch)\n"
    "3. Synthesize findings into a sharp, structured investment briefing\n"
    "4. Lead with actionable signals and quantitative evidence\n"
    "5. Concise and data-driven — no vague commentary\n"
    "6. Format like a top-tier hedge fund quant report with clear sections"
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


def _build_lc_agent() -> Any:  # noqa: ANN401
    """Construct a LangChain tool-calling AgentExecutor backed by Claude.

    Imports are deferred so the module loads even without langchain-anthropic
    installed. Raises RuntimeError (caught by intelligence_command → fallback)
    if required packages are absent.
    """
    try:
        from langchain.agents import (  # type: ignore[import-not-found]
            AgentExecutor,
            create_tool_calling_agent,
        )
        from langchain_anthropic import ChatAnthropic  # type: ignore[import-not-found]
        from langchain_core.prompts import (  # type: ignore[import-not-found]
            ChatPromptTemplate,
            MessagesPlaceholder,
        )
    except ImportError as exc:
        raise RuntimeError(
            f"LangChain agent packages unavailable: {exc}. "
            "Ensure langchain>=0.3.0 and langchain-anthropic>=0.3.0 are installed."
        ) from exc

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        temperature=0.1,
        max_tokens=2048,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", _AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    tools = [get_quant_intelligence, get_sentiment_intelligence]
    agent = create_tool_calling_agent(llm, tools, prompt)
    logger.info("lc_agent_built", extra={"model": "claude-sonnet-4-6", "tools": len(tools)})
    return AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=6)


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
        {"input": query, "chat_history": []},
    )
    briefing: str = str(agent_result.get("output", "Analysis complete."))

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
        "timestamp": datetime.now(tz=UTC).isoformat(),
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
        "omni_report": briefing,
    }


# ── FastAPI application ───────────────────────────────────────────────────────

@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: DB init → seed → load history → cache regime. Shutdown: close pool."""
    logger.info("aleph_one_startup")
    try:
        await asyncio.to_thread(init_db)
        await asyncio.to_thread(seed_mock_data)
    except Exception as exc:
        logger.warning("db_startup_partial", extra={"error": str(exc)})

    _init_price_history()

    try:
        await asyncio.to_thread(_load_regime_from_db)
    except Exception as exc:
        logger.warning("regime_cache_fallback", extra={"error": str(exc)})

    logger.info("aleph_one_ready")
    yield

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
    langchain-anthropic are not installed, or the agent raises, falls back to
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
        "timestamp": datetime.now(tz=UTC).isoformat(),
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    uvicorn.run("src.main:app", host="0.0.0.0", port=8001, reload=True)
