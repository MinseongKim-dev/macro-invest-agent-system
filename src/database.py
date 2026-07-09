"""Aleph-One database layer — connection pool, schema init, mock data seeding,
live market data fetch (yfinance + optional Alpaca/Finnhub/KIS adapters), Milvus news vector store.

Tri-File Architecture — this file owns:
  - DatabaseConfig            : env-var backed config dataclass
  - _PoolManager              : thread-safe connection pool singleton
  - get_pool()                : pool accessor
  - get_connection()          : context manager (lease → auto-return)
  - init_db()                 : DDL — market_ticks hypertable + macro_regimes
  - seed_mock_data()          : pandas GBM OHLCV + dummy regimes via COPY (bulk)
  - LIVE_TICKERS              : internal ticker ID → yfinance symbol mapping
  - _US_TICKERS               : US-listed ticker IDs eligible for Alpaca / Finnhub adapters
  - fetch_live_market_data()  : OHLCV → market_ticks (Alpaca for US, yfinance fallback)
  - fetch_live_news()         : yfinance .news → headlines per ticker + Milvus upsert
  - init_milvus()             : Milvus connection + news_collection schema + HNSW index
  - search_milvus_news()      : semantic ANN search over ingested news headlines
  - fetch_fund_nav()          : KOFIA fund NAV scaffold → fund_nav_ticks (adapter call TODO)
  - execute_virtual_order()   : virtual broker BUY/SELL transaction (cash + holdings + order log)
  - get_portfolio_holdings()  : current portfolio_holdings rows
  - get_virtual_accounts()    : current KRW/USD virtual_accounts cash balances

Run standalone::

    python -m src.database
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import httpx
import numpy as np
import pandas as pd
import psycopg
import psycopg_pool
import pytz
import yfinance as yf
from psycopg.rows import TupleRow

from src.adapters import alpaca_available, fetch_alpaca_bars, fetch_kis_bars, kis_available

logger = logging.getLogger(__name__)

_KST = pytz.timezone("Asia/Seoul")

# ── Config ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DatabaseConfig:
    host: str     = field(default_factory=lambda: os.environ.get("DB_HOST", "localhost"))
    port: int     = field(default_factory=lambda: int(os.environ.get("DB_PORT", "5432")))
    name: str     = field(default_factory=lambda: os.environ.get("DB_NAME", "aleph_core"))
    user: str     = field(default_factory=lambda: os.environ.get("DB_USER", "aleph_admin"))
    password: str = field(default_factory=lambda: os.environ.get("DB_PASSWORD", "aleph_secure_pass"))
    pool_min: int = 2
    pool_max: int = 10

    @property
    def conninfo(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.name} "
            f"user={self.user} password={self.password}"
        )


# ── Connection Pool Singleton ─────────────────────────────────────────────────


class _PoolManager:
    """Thread-safe connection pool singleton (double-checked locking).

    One pool is created per process lifetime. Call `close()` only on shutdown.
    """

    _instance: psycopg_pool.ConnectionPool | None = None
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get(cls, config: DatabaseConfig | None = None) -> psycopg_pool.ConnectionPool:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cfg = config or DatabaseConfig()
                    try:
                        cls._instance = psycopg_pool.ConnectionPool(
                            conninfo=cfg.conninfo,
                            min_size=cfg.pool_min,
                            max_size=cfg.pool_max,
                            open=True,
                        )
                        logger.info(
                            "db_pool_created",
                            extra={"host": cfg.host, "min": cfg.pool_min, "max": cfg.pool_max},
                        )
                    except Exception as exc:
                        logger.error("db_pool_creation_failed", extra={"error": str(exc)})
                        raise
        return cls._instance

    @classmethod
    def close(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None
                logger.info("db_pool_closed")


def get_pool(config: DatabaseConfig | None = None) -> psycopg_pool.ConnectionPool:
    """Return the process-wide connection pool, creating it on first call."""
    return _PoolManager.get(config)


@contextmanager
def get_connection(config: DatabaseConfig | None = None) -> Iterator[psycopg.Connection[TupleRow]]:
    """Lease a connection from the pool; return it automatically on exit."""
    pool = get_pool(config)
    with pool.connection() as conn:
        yield conn


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL_MARKET_TICKS = """
CREATE TABLE IF NOT EXISTS market_ticks (
    timestamp   TIMESTAMPTZ   NOT NULL,
    ticker      VARCHAR(10)   NOT NULL,
    open_price  NUMERIC(15,4) NOT NULL,
    high_price  NUMERIC(15,4) NOT NULL,
    low_price   NUMERIC(15,4) NOT NULL,
    close_price NUMERIC(15,4) NOT NULL,
    volume      BIGINT        NOT NULL
);
"""

_DDL_HYPERTABLE = """
SELECT create_hypertable(
    'market_ticks',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);
"""

_DDL_MACRO_REGIMES = """
CREATE TABLE IF NOT EXISTS macro_regimes (
    id               SERIAL       PRIMARY KEY,
    updated_at       TIMESTAMPTZ  DEFAULT NOW(),
    regime_name      VARCHAR(50)  NOT NULL,
    market_phase     VARCHAR(30)  NOT NULL,
    confidence_score NUMERIC(3,2) NOT NULL
);
"""

_DDL_INDEX_TICKS = """
CREATE TABLE IF NOT EXISTS index_ticks (
    timestamp   TIMESTAMPTZ   NOT NULL,
    index_id    VARCHAR(10)   NOT NULL,
    close_value NUMERIC(15,4) NOT NULL
);
"""

_DDL_INDEX_HYPERTABLE = """
SELECT create_hypertable(
    'index_ticks',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);
"""

_DDL_MACRO_INDICATORS = """
CREATE TABLE IF NOT EXISTS macro_indicators (
    snapshot_time TIMESTAMPTZ   NOT NULL,
    series_id     VARCHAR(20)   NOT NULL,
    value         NUMERIC(15,6) NOT NULL,
    source        VARCHAR(20)   NOT NULL DEFAULT 'yfinance',
    country       VARCHAR(5)    NOT NULL DEFAULT 'US'
);
"""

# Idempotent backfill for tables created before this schema revision.
# DO blocks swallow duplicate_object so repeated startups are safe.
_DDL_MACRO_BACKFILL = """
DO $$ BEGIN
    ALTER TABLE macro_indicators
        ADD COLUMN IF NOT EXISTS country VARCHAR(5) NOT NULL DEFAULT 'US';
EXCEPTION WHEN OTHERS THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE macro_indicators
        ADD CONSTRAINT macro_indicators_ts_series_uq
            UNIQUE (snapshot_time, series_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
"""

_DDL_MACRO_INDICATORS_HYPERTABLE = """
SELECT create_hypertable(
    'macro_indicators',
    'snapshot_time',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists       => TRUE
);
"""

_DDL_FUND_NAV_TICKS = """
CREATE TABLE IF NOT EXISTS fund_nav_ticks (
    snapshot_time TIMESTAMPTZ   NOT NULL,
    fund_code     VARCHAR(20)   NOT NULL,
    nav           NUMERIC(15,4) NOT NULL,
    source        VARCHAR(20)   NOT NULL DEFAULT 'KOFIA',
    UNIQUE (snapshot_time, fund_code)
);
"""

_DDL_FUND_NAV_HYPERTABLE = """
SELECT create_hypertable(
    'fund_nav_ticks',
    'snapshot_time',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists       => TRUE
);
"""

# Virtual broker — current-state tables, not hypertables (one row per
# currency/ticker, mutated in place; virtual_orders is an append-only log
# but at simulation order volumes a plain SERIAL PK table is sufficient).
_DDL_VIRTUAL_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS virtual_accounts (
    currency        VARCHAR(3)    PRIMARY KEY,
    cash_balance    NUMERIC(20,4) NOT NULL,
    initial_balance NUMERIC(20,4) NOT NULL,
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
"""

_DDL_VIRTUAL_ORDERS = """
CREATE TABLE IF NOT EXISTS virtual_orders (
    id            SERIAL        PRIMARY KEY,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    ticker        VARCHAR(10)   NOT NULL,
    side          VARCHAR(4)    NOT NULL,
    quantity      NUMERIC(20,6) NOT NULL,
    fill_price    NUMERIC(20,4) NOT NULL,
    currency      VARCHAR(3)    NOT NULL,
    status        VARCHAR(10)   NOT NULL DEFAULT 'FILLED',
    reject_reason VARCHAR(100)
);
"""

_DDL_PORTFOLIO_HOLDINGS = """
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    ticker     VARCHAR(10)   PRIMARY KEY,
    quantity   NUMERIC(20,6) NOT NULL,
    avg_cost   NUMERIC(20,4) NOT NULL,
    currency   VARCHAR(3)    NOT NULL,
    updated_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
"""

# Append-only audit trail for every action taken by the Virtual Broker.
# user_id is NULL until Supabase Auth is wired in (Phase B-1).
_DDL_AUDIT_LOG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGSERIAL    PRIMARY KEY,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    action     VARCHAR(64)  NOT NULL,
    user_id    UUID,
    payload    JSONB        NOT NULL DEFAULT '{}'
);
"""

# Starting paper-trading balances, seeded once per currency on first init_db().
_VIRTUAL_ACCOUNT_SEED: dict[str, float] = {
    "KRW": 100_000_000.0,
    "USD": 100_000.0,
}


def init_db(config: DatabaseConfig | None = None) -> None:
    """Create market_ticks (hypertable, 7-day chunks) and macro_regimes.

    Idempotent — safe to call on every startup.
    """
    logger.info("db_init_start")
    try:
        with get_connection(config) as conn:
            conn.execute(_DDL_MARKET_TICKS)
            logger.debug("db_table_ensured", extra={"table": "market_ticks"})
            conn.execute(_DDL_HYPERTABLE)
            logger.debug("db_hypertable_ensured")
            conn.execute(_DDL_MACRO_REGIMES)
            logger.debug("db_table_ensured", extra={"table": "macro_regimes"})
            conn.execute(_DDL_INDEX_TICKS)
            conn.execute(_DDL_INDEX_HYPERTABLE)
            logger.debug("db_table_ensured", extra={"table": "index_ticks"})
            conn.execute(_DDL_MACRO_INDICATORS)
            conn.execute(_DDL_MACRO_INDICATORS_HYPERTABLE)
            conn.execute(_DDL_MACRO_BACKFILL)
            logger.debug("db_table_ensured", extra={"table": "macro_indicators"})
            conn.execute(_DDL_FUND_NAV_TICKS)
            conn.execute(_DDL_FUND_NAV_HYPERTABLE)
            logger.debug("db_table_ensured", extra={"table": "fund_nav_ticks"})
            conn.execute(_DDL_VIRTUAL_ACCOUNTS)
            conn.execute(_DDL_VIRTUAL_ORDERS)
            conn.execute(_DDL_PORTFOLIO_HOLDINGS)
            conn.execute(_DDL_AUDIT_LOG)
            logger.debug("db_table_ensured", extra={"table": "audit_log"})
            for currency, balance in _VIRTUAL_ACCOUNT_SEED.items():
                conn.execute(
                    "INSERT INTO virtual_accounts (currency, cash_balance, initial_balance) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (currency) DO NOTHING",
                    (currency, balance, balance),
                )
            logger.debug("db_table_ensured", extra={"table": "virtual_accounts"})
            conn.commit()
        logger.info("db_init_complete")
    except Exception as exc:
        logger.error("db_init_failed", extra={"error": str(exc)})
        raise


# ── Mock Data Generators ──────────────────────────────────────────────────────

_OHLCV_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":   {"start": 195.0,     "mu": 0.10, "sigma": 0.22},
    "MSFT":   {"start": 415.0,     "mu": 0.12, "sigma": 0.20},
    "TSLA":   {"start": 245.0,     "mu": 0.08, "sigma": 0.48},
    "005930": {"start": 72_000.0,  "mu": 0.09, "sigma": 0.28},
    "000660": {"start": 195_000.0, "mu": 0.11, "sigma": 0.32},
}

_MOCK_REGIMES: list[dict[str, Any]] = [
    {"regime_name": "POLICY_TIGHTENING", "market_phase": "LATE_CYCLE",  "confidence_score": 0.85},
    {"regime_name": "RISK_OFF",          "market_phase": "CONTRACTION", "confidence_score": 0.72},
    {"regime_name": "EXPANSION",         "market_phase": "MID_CYCLE",   "confidence_score": 0.91},
    {"regime_name": "REFLATION",         "market_phase": "EARLY_CYCLE", "confidence_score": 0.78},
    {"regime_name": "STAGFLATION",       "market_phase": "LATE_CYCLE",  "confidence_score": 0.65},
]


def _generate_ohlcv(n_days: int = 30) -> pd.DataFrame:
    """Generate synthetic OHLCV for every ticker via Geometric Brownian Motion.

    Deterministic per ticker (seeded RNG) so repeated calls produce the same
    price path — useful for reproducible integration tests.
    """
    frames: list[pd.DataFrame] = []
    today = date.today()

    for ticker, params in _OHLCV_PARAMS.items():
        rng = np.random.default_rng(hash(ticker) % (2**31))
        dt = 1.0 / 252.0

        # GBM: S(t+dt) = S(t) * exp((μ - σ²/2)dt + σ√dt · Z)
        z = rng.standard_normal(n_days)
        log_ret = (params["mu"] - 0.5 * params["sigma"] ** 2) * dt + params["sigma"] * np.sqrt(dt) * z
        closes = params["start"] * np.exp(np.cumsum(log_ret))

        noise = rng.uniform(0.002, 0.015, n_days)
        highs = closes * (1.0 + noise)
        lows  = closes * (1.0 - noise)
        opens = np.roll(closes, 1)
        opens[0] = closes[0]
        volumes = rng.integers(1_000_000, 10_000_000, n_days)
        dates = [today - timedelta(days=n_days - 1 - i) for i in range(n_days)]

        frames.append(pd.DataFrame({
            "timestamp":   dates,
            "ticker":      ticker,
            "open_price":  np.round(opens, 4),
            "high_price":  np.round(highs, 4),
            "low_price":   np.round(lows, 4),
            "close_price": np.round(closes, 4),
            "volume":      volumes.astype(np.int64),
        }))

    return pd.concat(frames, ignore_index=True)


# ── Seeder ────────────────────────────────────────────────────────────────────


def seed_mock_data(config: DatabaseConfig | None = None, n_days: int = 30) -> None:
    """Bulk-insert synthetic OHLCV and dummy macro-regime rows.

    market_ticks  — PostgreSQL COPY protocol (maximum throughput).
    macro_regimes — executemany INSERT, skipped if table already populated.
    """
    logger.info("seed_mock_data_start", extra={"n_days": n_days})
    ohlcv_df = _generate_ohlcv(n_days)

    try:
        with get_connection(config) as conn:

            # ── market_ticks: COPY FROM STDIN (bulk, ~10× faster than INSERT) ──
            with conn.cursor() as cur, cur.copy(
                "COPY market_ticks "
                "(timestamp, ticker, open_price, high_price, low_price, close_price, volume) "
                "FROM STDIN"
            ) as copy:
                    for row in ohlcv_df.itertuples(index=False):
                        copy.write_row((
                            row.timestamp,
                            row.ticker,
                            float(row.open_price),
                            float(row.high_price),
                            float(row.low_price),
                            float(row.close_price),
                            int(row.volume),
                        ))
            logger.info("seed_market_ticks_done", extra={"rows": len(ohlcv_df)})

            # ── macro_regimes: INSERT only if table is empty ──────────────────
            row_count = conn.execute("SELECT COUNT(*) FROM macro_regimes").fetchone()
            if row_count is not None and int(row_count[0]) == 0:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO macro_regimes (regime_name, market_phase, confidence_score) "
                        "VALUES (%s, %s, %s)",
                        [
                            (r["regime_name"], r["market_phase"], r["confidence_score"])
                            for r in _MOCK_REGIMES
                        ],
                    )
                logger.info("seed_macro_regimes_done", extra={"rows": len(_MOCK_REGIMES)})
            else:
                logger.info("seed_macro_regimes_skipped", extra={"reason": "table not empty"})

            conn.commit()

        logger.info("seed_mock_data_complete", extra={"tickers": list(_OHLCV_PARAMS.keys())})

    except Exception as exc:
        logger.error("seed_mock_data_failed", extra={"error": str(exc)})
        raise


# ── Live Data Domain Map ──────────────────────────────────────────────────────

# Maps Aleph-One internal ticker IDs to Yahoo Finance symbols.
# Internal IDs match market_ticks.ticker and engines.TICKERS exactly.
LIVE_TICKERS: dict[str, str] = {
    "AAPL":   "AAPL",
    "MSFT":   "MSFT",
    "TSLA":   "TSLA",
    "005930": "005930.KS",   # 삼성전자 — KRX listed on Yahoo Finance
    "000660": "000660.KS",   # SK하이닉스 — KRX listed on Yahoo Finance
    "QQQ":    "QQQ",         # Invesco QQQ Trust (Nasdaq 100 ETF)
    "BND":    "BND",         # Vanguard Total Bond Market ETF
    "GLD":    "GLD",         # SPDR Gold Shares ETF
    "035420": "035420.KS",   # NAVER
    "051910": "051910.KS",   # LG화학
    "006400": "006400.KS",   # 삼성SDI
    "122630": "122630.KS",   # KODEX 레버리지 ETF
    "005380": "005380.KS",   # 현대차
    "207940": "207940.KS",   # 삼성바이오로직스
    "005490": "005490.KS",   # POSCO홀딩스
    "105560": "105560.KS",   # KB금융
}

# US-listed tickers eligible for Alpaca / Finnhub adapters.
# KR tickers (.KS suffix) use yfinance or KIS as primary source.
_US_TICKERS: frozenset[str] = frozenset({
    "AAPL", "MSFT", "TSLA", "QQQ", "BND", "GLD",
})

def _normalize_yf_symbol(ticker: str) -> str:
    """Map any internal ticker ID to its Yahoo Finance symbol.

    Resolution order:
    1. ``LIVE_TICKERS`` dict — known tickers with exact Yahoo Finance symbols.
    2. 6-digit numeric codes (KRX / KOSDAQ) — auto-append ``.KS`` (KRX default).
    3. Everything else — returned unchanged.

    Examples::

        _normalize_yf_symbol("005930") -> "005930.KS"
        _normalize_yf_symbol("AAPL")   -> "AAPL"
        _normalize_yf_symbol("QQQ")    -> "QQQ"
    """
    if ticker in LIVE_TICKERS:
        return LIVE_TICKERS[ticker]
    if re.fullmatch(r"\d{6}", ticker):
        return f"{ticker}.KS"
    return ticker


# Market index symbols — used by the index collector (not stored in market_ticks)
INDEX_TICKERS: dict[str, str] = {
    "KOSPI":  "^KS11",
    "SP500":  "^GSPC",
    "USDKRW": "KRW=X",
}

# ── Macro Indicators ──────────────────────────────────────────────────────────

# Optional FRED API key — set FRED_API_KEY to enable. Falls back to yfinance proxies.
FRED_API_KEY: str = os.environ.get("FRED_API_KEY", "")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED series for authoritative macro data (requires FRED_API_KEY)
MACRO_FRED_SERIES: dict[str, str] = {
    "FED_RATE": "FEDFUNDS",         # Effective federal funds rate (%)
    "CPI_YOY":  "CPIAUCSL",         # CPI All Urban Consumers (index)
    "GDP_QOQ":  "A191RL1Q225SBEA",  # Real GDP % change, annualised
    "UNRATE":   "UNRATE",           # US unemployment rate (%)
}

# yfinance proxies used when FRED_API_KEY is absent (real-time market rates)
MACRO_YF_PROXIES: dict[str, str] = {
    "T10Y":  "^TNX",   # 10-year US Treasury yield
    "T3M":   "^IRX",   # 3-month T-bill rate
    "VIX":   "^VIX",   # CBOE Volatility Index
}

# Minimal mock values — used when both FRED and yfinance are unavailable.
# Keeps dashboard layout coherent without throwing KeyErrors.
_MACRO_MOCK_FALLBACK: dict[str, float] = {
    "T10Y":     4.35,
    "T3M":      5.28,
    "VIX":      18.5,
    "FED_RATE": 5.33,
}

# Optional BLS API key — raises daily request limit from 25 to 500.
# Free registration: https://www.bls.gov/developers/api_signature_v2.htm
BLS_API_KEY: str = os.environ.get("BLS_API_KEY", "")

# Optional 한국은행 ECOS Open API key — required for KR macro data.
# Free registration: https://ecos.bok.or.kr/
BOK_API_KEY: str = os.environ.get("BOK_API_KEY", "")

# ── BLS helper ────────────────────────────────────────────────────────────────

def _fetch_bls_macro() -> dict[str, float]:
    """Fetch US macro from BLS Data API v2 (free; ≤25 req/day without key).

    Series fetched:
      CUUR0000SA0 → US_CPI_BLS  (CPI-U All Items, not seasonally adjusted)
      LNS14000000 → US_UNRATE_BLS  (civilian unemployment rate)

    Returns {} on any failure — caller falls back to FRED / yfinance proxies.
    """
    now_yr = str(datetime.now(_KST).year)
    body: dict[str, Any] = {
        "seriesid":  ["CUUR0000SA0", "LNS14000000"],
        "startyear": str(int(now_yr) - 1),
        "endyear":   now_yr,
    }
    if BLS_API_KEY:
        body["registrationkey"] = BLS_API_KEY

    try:
        with httpx.Client(timeout=12.0) as http:
            data = http.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                json=body,
            ).raise_for_status().json()
    except Exception as exc:
        logger.warning("bls_fetch_failed", extra={"error": str(exc)})
        return {}

    bls_map: dict[str, str] = {
        "CUUR0000SA0": "US_CPI_BLS",
        "LNS14000000": "US_UNRATE_BLS",
    }
    results: dict[str, float] = {}
    for series in data.get("Results", {}).get("series", []):
        sid   = series.get("seriesID", "")
        items = series.get("data", [])
        if items and sid in bls_map:
            with contextlib.suppress(ValueError, KeyError, IndexError):
                results[bls_map[sid]] = round(float(items[0]["value"]), 4)

    if results:
        logger.debug("bls_macro_fetched", extra={"series": list(results.keys())})
    return results


# ── ECB helper ────────────────────────────────────────────────────────────────

_ECB_BASE = "https://data-api.ecb.europa.eu/service/data"

# ECB SDMX-REST series keys → internal series_id
_ECB_SERIES: dict[str, str] = {
    "ICP/M.U2.N.000000.4.ANR": "EU_HICP",  # Euro area HICP annual inflation %
}


def _fetch_ecb_macro() -> dict[str, float]:
    """Fetch Eurozone macro from ECB Data Portal (public SDMX-REST, no key needed).

    Returns {} on any failure.
    """
    results: dict[str, float] = {}
    for ecb_key, series_id in _ECB_SERIES.items():
        try:
            with httpx.Client(timeout=12.0) as http:
                resp = http.get(
                    f"{_ECB_BASE}/{ecb_key}",
                    params={"format": "csvdata", "lastNObservations": "1"},
                    headers={"Accept": "text/csv"},
                ).raise_for_status()
            # CSV layout: optional comment lines (#), then header, then data rows
            lines = [ln for ln in resp.text.splitlines() if ln and not ln.startswith("#")]
            if len(lines) < 2:
                continue
            header = [h.strip() for h in lines[0].split(",")]
            row    = [v.strip() for v in lines[-1].split(",")]
            col = header.index("OBS_VALUE") if "OBS_VALUE" in header else 8
            results[series_id] = round(float(row[col]), 4)
        except Exception as exc:
            logger.warning("ecb_fetch_failed", extra={"series": series_id, "error": str(exc)})

    if results:
        logger.debug("ecb_macro_fetched", extra={"series": list(results.keys())})
    return results


# ── BOK helper ────────────────────────────────────────────────────────────────

_BOK_BASE = "https://ecos.bok.or.kr/api"

# (series_id, stat_table, cycle, item_code)
# BOK ECOS stat tables: 722Y001 = 기준금리, 901Y062 = 소비자물가지수(2020=100)
_BOK_QUERIES: list[tuple[str, str, str, str]] = [
    ("KR_BASE_RATE", "722Y001", "D", "0101000"),   # 한국은행 기준금리 (daily)
    ("KR_CPI",       "901Y062", "M", "0"),          # 소비자물가지수 총지수 (monthly)
]


def _fetch_bok_macro() -> dict[str, float]:
    """Fetch Korean macro from 한국은행 ECOS Open API (requires BOK_API_KEY).

    Free API key registration: https://ecos.bok.or.kr/

    Series fetched:
      722Y001 / 0101000 → KR_BASE_RATE  (한국은행 기준금리 %)
      901Y062 / 0       → KR_CPI        (소비자물가지수, 2020=100)

    Returns {} when BOK_API_KEY is unset or all fetches fail.
    """
    if not BOK_API_KEY:
        return {}

    now   = datetime.now(_KST)
    today = now.strftime("%Y%m%d")
    last_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y%m")

    # Map cycle → (start, end) dates
    _dates: dict[str, tuple[str, str]] = {
        "D": (today, today),
        "M": (last_month, last_month),
    }

    results: dict[str, float] = {}
    for series_id, table, cycle, item in _BOK_QUERIES:
        start, end = _dates.get(cycle, (today, today))
        url = (
            f"{_BOK_BASE}/StatisticSearch/{BOK_API_KEY}/json/kr"
            f"/1/1/{table}/{cycle}/{start}/{end}/{item}"
        )
        try:
            with httpx.Client(timeout=12.0) as http:
                payload = http.get(url).raise_for_status().json()
            rows = payload.get("StatisticSearch", {}).get("row", [])
            if rows:
                results[series_id] = round(float(rows[0]["DATA_VALUE"]), 4)
        except Exception as exc:
            logger.warning("bok_fetch_failed", extra={"series": series_id, "error": str(exc)})

    if results:
        logger.debug("bok_macro_fetched", extra={"series": list(results.keys())})
    return results

# ── Price-change tracking for Milvus sync bridge ──────────────────────────────
# Stores the most recent close price per ticker; used to detect significant moves.
_PREV_CLOSE: dict[str, float] = {}
_PRICE_ALERT_THRESHOLD = 0.02  # 2% absolute price change triggers Milvus embed


def _to_kst(ts: int | float | pd.Timestamp | datetime | str) -> datetime:
    """Convert any timestamp to KST (Asia/Seoul) aware datetime."""
    if isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts, tz=UTC)
    elif isinstance(ts, pd.Timestamp):
        dt = ts.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    elif isinstance(ts, datetime):
        dt = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    else:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_KST)

# ── Milvus Vector Store (Lite — embedded file mode) ──────────────────────────
#
# Uses pymilvus MilvusClient with a local file path instead of Docker Milvus.
# This eliminates the ~1 GB Milvus standalone Docker overhead on the VPS.
# File path is configurable via MILVUS_LITE_PATH (default: ./data/milvus_lite.db).

_NEWS_COLLECTION: str = "news_collection"
_EMBEDDING_DIM:   int = 384   # sentence-transformers/all-MiniLM-L6-v2
_MILVUS_LITE_PATH: str = os.environ.get("MILVUS_LITE_PATH", "./data/milvus_lite.db")

# Module-level singletons
_milvus_ready:  bool = False
_milvus_client: Any  = None   # pymilvus.MilvusClient
_embedder:      Any  = None   # HuggingFaceEmbeddings


def _get_embedder() -> Any:  # noqa: ANN401
    """Lazy-load HuggingFaceEmbeddings on first call (defers ~2 s model download)."""
    global _embedder
    if _embedder is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        logger.info("embedder_loading", extra={"model": "all-MiniLM-L6-v2"})
        _embedder = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("embedder_ready")
    return _embedder


def _news_hash(title: str) -> str:
    """Return a 16-char hex SHA-256 fingerprint for deduplication."""
    return hashlib.sha256(title.encode()).hexdigest()[:16]


def _news_hash_int(title: str) -> int:
    """Return a stable INT64 primary key derived from the title SHA-256."""
    return int(hashlib.sha256(title.encode()).hexdigest(), 16) % (2**63)


def init_milvus() -> None:
    """Initialise Milvus Lite (embedded, file-based) vector store.

    Creates ``news_collection`` with COSINE HNSW index if absent.
    Sets ``_milvus_ready = True`` on success; logs a warning and returns
    without raising on failure so the application boots even when the
    embedder or milvus-lite package is absent.

    File path: MILVUS_LITE_PATH env var (default ./data/milvus_lite.db).
    """
    global _milvus_ready, _milvus_client
    try:
        from pymilvus import DataType, MilvusClient

        os.makedirs(os.path.dirname(_MILVUS_LITE_PATH) or ".", exist_ok=True)
        _milvus_client = MilvusClient(_MILVUS_LITE_PATH)

        if _NEWS_COLLECTION not in _milvus_client.list_collections():
            schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("id",           DataType.INT64,         is_primary=True)
            schema.add_field("vector",       DataType.FLOAT_VECTOR,  dim=_EMBEDDING_DIM)
            schema.add_field("news_hash",    DataType.VARCHAR,       max_length=32)
            schema.add_field("ticker",       DataType.VARCHAR,       max_length=16)
            schema.add_field("title",        DataType.VARCHAR,       max_length=512)
            schema.add_field("published_at", DataType.INT64)

            idx = MilvusClient.prepare_index_params()
            idx.add_index(
                field_name="vector",
                metric_type="COSINE",
                index_type="HNSW",
                params={"M": 8, "efConstruction": 64},
            )

            _milvus_client.create_collection(
                collection_name=_NEWS_COLLECTION,
                schema=schema,
                index_params=idx,
            )
            logger.info("milvus_lite_collection_created", extra={"collection": _NEWS_COLLECTION})
        else:
            _milvus_client.load_collection(_NEWS_COLLECTION)

        _milvus_ready = True
        logger.info("milvus_lite_ready", extra={"path": _MILVUS_LITE_PATH})

    except Exception as exc:
        logger.warning("milvus_lite_init_skipped", extra={"error": str(exc), "path": _MILVUS_LITE_PATH})
        _milvus_ready = False


def _upsert_news_to_milvus(news_map: dict[str, list[str]]) -> int:
    """Embed headlines and upsert into Milvus Lite, deduplicating by title hash.

    Uses INT64 primary keys derived from SHA-256 so identical titles are
    idempotent. Returns number of newly written vectors (0 when unavailable).
    """
    if not _milvus_ready or _milvus_client is None:
        return 0

    try:
        rows: list[dict[str, Any]] = []
        for ticker, headlines in news_map.items():
            for title in headlines:
                if not title:
                    continue
                rows.append({
                    "id":           _news_hash_int(title),
                    "news_hash":    _news_hash(title),
                    "ticker":       ticker[:16],
                    "title":        title[:512],
                    "published_at": int(time.time()),
                    "vector":       [],   # placeholder — filled after batched embed
                })

        if not rows:
            return 0

        embedder = _get_embedder()
        embeddings: list[list[float]] = embedder.embed_documents([r["title"] for r in rows])
        for row, vec in zip(rows, embeddings, strict=True):
            row["vector"] = vec

        _milvus_client.upsert(collection_name=_NEWS_COLLECTION, data=rows)
        logger.info("milvus_lite_upserted", extra={"inserted": len(rows)})
        return len(rows)

    except Exception as exc:
        logger.warning("milvus_lite_upsert_failed", extra={"error": str(exc)})
        return 0


def search_milvus_news(
    query: str,
    ticker: str | None = None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Embed *query* and return the top_k semantically closest news items.

    Args:
        query:  Natural-language query string.
        ticker: Optional internal ticker ID filter.
        top_k:  Maximum results.

    Returns a list of dicts with keys ``ticker``, ``title``, ``published_at``,
    ``score``.  Returns ``[]`` when Milvus Lite is not available.
    """
    if not _milvus_ready or _milvus_client is None:
        return []

    try:
        embedder = _get_embedder()
        query_vec: list[float] = embedder.embed_query(query)

        filter_expr = f'ticker == "{ticker}"' if ticker else ""

        results = _milvus_client.search(
            collection_name=_NEWS_COLLECTION,
            data=[query_vec],
            limit=top_k,
            filter=filter_expr or None,
            output_fields=["ticker", "title", "published_at"],
        )

        hits: list[dict[str, Any]] = []
        for hit in (results[0] if results else []):
            entity = hit.get("entity", {})
            hits.append({
                "ticker":       entity.get("ticker", ""),
                "title":        entity.get("title", ""),
                "published_at": entity.get("published_at", 0),
                "score":        round(float(hit.get("distance", 0.0)), 4),
            })

        logger.debug("milvus_lite_search_done", extra={"query": query[:60], "hits": len(hits)})
        return hits

    except Exception as exc:
        logger.warning("milvus_lite_search_failed", extra={"error": str(exc)})
        return []
# ── Retry Helper ──────────────────────────────────────────────────────────────


def _retry[T](
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 2.0,
    label: str = "",
) -> T:
    """Call *fn* up to *max_attempts* times with exponential back-off on failure.

    Raises the last exception when all attempts are exhausted.
    Uses blocking ``time.sleep`` — safe to call from a thread pool (asyncio.to_thread).
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = base_delay * (2.0 ** attempt)
                logger.warning(
                    "retry_backoff",
                    extra={
                        "label":   label,
                        "attempt": attempt + 1,
                        "delay_s": delay,
                        "error":   str(exc),
                    },
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]  # exhausted — last_exc is always set


# ── yfinance Helpers ──────────────────────────────────────────────────────────


def _extract_news_title(item: dict[str, Any]) -> str:
    """Extract headline string from a yfinance news item dict.

    Handles both the flat format (yfinance < 0.2.50) and the nested
    ``content`` dict format introduced in later releases.
    """
    title: str = str(item.get("title") or "")
    if not title:
        content = item.get("content")
        if isinstance(content, dict):
            title = str(content.get("title") or "")
    return title.strip()


def _extract_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Extract title/url/publisher/published_at from a yfinance news item dict.

    Handles both the flat format (top-level ``link``/``publisher``/
    ``providerPublishTime``) and the nested ``content`` dict format
    (``content.canonicalUrl.url`` or ``content.clickThroughUrl.url``,
    ``content.provider.displayName``, ``content.pubDate`` as ISO-8601),
    mirroring ``_extract_news_title``'s dual-shape handling.

    Returns ``None`` when no usable title is present.
    """
    title = _extract_news_title(item)
    if not title:
        return None

    content_raw = item.get("content")
    content: dict[str, Any] = content_raw if isinstance(content_raw, dict) else {}

    url = item.get("link")
    if not url:
        for key in ("canonicalUrl", "clickThroughUrl"):
            link_obj = content.get(key)
            if isinstance(link_obj, dict) and link_obj.get("url"):
                url = link_obj["url"]
                break

    publisher = item.get("publisher")
    if not publisher:
        provider = content.get("provider")
        if isinstance(provider, dict):
            publisher = provider.get("displayName")

    published_at: str | None = None
    epoch = item.get("providerPublishTime")
    if isinstance(epoch, int | float):
        published_at = datetime.fromtimestamp(epoch, tz=UTC).isoformat()
    elif isinstance(content.get("pubDate"), str):
        published_at = content["pubDate"]

    return {
        "title":        title,
        "url":          url,
        "publisher":    publisher,
        "published_at": published_at,
    }


def _fetch_latest_close_from_db(internal_id: str) -> list[tuple[Any, ...]]:
    """Return the single most recent market_ticks row for a ticker.

    Used as a market-closed / network-error fallback inside ``_fetch_ticker_ohlcv``.
    The row tuple layout matches the COPY schema:
    (timestamp, ticker, open, high, low, close, volume, source).
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT timestamp, ticker, open_price, high_price, low_price, close_price, "
                "volume, source "
                "FROM market_ticks WHERE ticker = %s ORDER BY timestamp DESC LIMIT 1",
                (internal_id,),
            ).fetchone()
        if row:
            logger.info("yf_db_fallback_used", extra={"ticker": internal_id})
            return [tuple(row)]
    except Exception as exc:
        logger.warning("yf_db_fallback_failed", extra={"ticker": internal_id, "error": str(exc)})
    return []


def _fetch_ticker_ohlcv(internal_id: str, yf_symbol: str) -> list[tuple[Any, ...]]:
    """Download the last 5 trading days of daily OHLCV for a ticker.

    Adapter dispatch order (each step falls back to the next on failure):
      1. Alpaca Markets — US-listed tickers when ALPACA_API_KEY is set
      2. KIS Developers — KR-listed tickers when KIS_APP_KEY is set [stub]
      3. yfinance       — always-on fallback for all tickers

    Returns a list of DB row tuples ready for COPY:
        (timestamp_kst, internal_id, open, high, low, close, volume, source)
    """
    # ── 1. Alpaca for US tickers ──────────────────────────────────────────────
    if internal_id in _US_TICKERS and alpaca_available():
        rows = fetch_alpaca_bars(internal_id, yf_symbol, days=5)
        if rows:
            return rows
        logger.info(
            "alpaca_fallback_to_yf",
            extra={"ticker": internal_id, "reason": "empty_or_error"},
        )

    # ── 2. KIS for KR tickers (stub — falls through immediately) ─────────────
    if internal_id not in _US_TICKERS and kis_available():
        rows_kis = fetch_kis_bars(internal_id, yf_symbol, days=5)
        if rows_kis:
            return rows_kis

    # ── 3. yfinance (always-on fallback) ─────────────────────────────────────
    ticker_obj = yf.Ticker(yf_symbol)
    hist: pd.DataFrame = ticker_obj.history(
        period="5d",
        interval="1d",
        auto_adjust=True,
        raise_errors=False,
    )

    if hist.empty:
        logger.warning("yf_history_empty", extra={"ticker": internal_id, "symbol": yf_symbol})
        return _fetch_latest_close_from_db(internal_id)

    hist = hist.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    rows_yf: list[tuple[Any, ...]] = []
    for idx, row in hist.iterrows():
        ts_kst = _to_kst(pd.Timestamp(idx))
        rows_yf.append((
            ts_kst,
            internal_id,
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            int(row["Volume"]),
            "yfinance",
        ))
    return rows_yf


# ── Live Data Fetchers ────────────────────────────────────────────────────────


def fetch_live_market_data(config: DatabaseConfig | None = None) -> int:
    """Fetch latest OHLCV for all 5 tickers from Yahoo Finance and upsert into
    market_ticks.

    Pipeline:
    1. Download last 5 trading days per ticker (retried up to 3× with 2s/4s back-off).
    2. DELETE existing rows in that date window for the affected tickers.
    3. Bulk-insert fresh rows via PostgreSQL COPY (maximum throughput).

    Returns the total number of rows inserted.
    """
    logger.info("live_market_fetch_start", extra={"tickers": list(LIVE_TICKERS.keys())})

    all_rows: list[tuple[Any, ...]] = []

    for internal_id, yf_symbol in LIVE_TICKERS.items():
        try:
            rows = _retry(
                lambda tid=internal_id, sym=yf_symbol: _fetch_ticker_ohlcv(tid, sym),  # type: ignore[misc]
                max_attempts=3,
                base_delay=2.0,
                label=f"ohlcv:{internal_id}",
            )
            all_rows.extend(rows)
            logger.debug("live_ohlcv_fetched", extra={"ticker": internal_id, "rows": len(rows)})
        except Exception as exc:
            logger.error(
                "live_ohlcv_fetch_failed",
                extra={"ticker": internal_id, "error": str(exc)},
            )

    if not all_rows:
        logger.warning("live_market_fetch_no_data")
        return 0

    min_ts          = min(r[0] for r in all_rows)
    tickers_fetched = list({str(r[1]) for r in all_rows})

    try:
        with get_connection(config) as conn:
            conn.execute(
                "DELETE FROM market_ticks WHERE ticker = ANY(%s) AND timestamp >= %s",
                (tickers_fetched, min_ts),
            )
            with conn.cursor() as cur, cur.copy(
                "COPY market_ticks "
                "(timestamp, ticker, open_price, high_price, low_price, close_price, volume, source) "
                "FROM STDIN"
            ) as copy:
                for r in all_rows:
                    copy.write_row(r)
            conn.commit()

        logger.info("live_market_upsert_done", extra={"rows": len(all_rows)})

        # ── Milvus sync bridge: detect ≥2% moves and embed price alerts ────────
        # Build latest close per ticker from the batch we just wrote
        latest_close: dict[str, float] = {}
        for r in all_rows:
            ticker_id = str(r[1])
            close_val = float(r[5])
            # Keep the most recent row per ticker (rows are ordered oldest→newest)
            latest_close[ticker_id] = close_val

        from src.engines import DISPLAY_NAMES as _DISPLAY_NAMES  # local import avoids cycle
        for ticker_id, curr_close in latest_close.items():
            prev_close = _PREV_CLOSE.get(ticker_id)
            if prev_close is not None and prev_close > 0:
                change = abs(curr_close - prev_close) / prev_close
                if change >= _PRICE_ALERT_THRESHOLD:
                    name = _DISPLAY_NAMES.get(ticker_id, ticker_id)
                    embed_price_alert(ticker_id, prev_close, curr_close, name)
            _PREV_CLOSE[ticker_id] = curr_close

        return len(all_rows)

    except Exception as exc:
        logger.error("live_market_upsert_failed", extra={"error": str(exc)})
        raise


def fetch_live_news() -> dict[str, list[str]]:
    """Fetch latest news headlines from Yahoo Finance for each ticker.

    Uses ``yf.Ticker.news`` (JSON feed, no API key required).
    Each ticker is retried up to 3 times with 1-second base back-off.

    Returns a dict mapping internal ticker IDs to lists of headline strings.
    Output is immediately consumable by SentimentEngine (Simons regime-switch
    keyword detection and Buffett margin-of-safety RSI paths).
    """
    logger.info("live_news_fetch_start")
    news_map: dict[str, list[str]] = {}

    for internal_id, yf_symbol in LIVE_TICKERS.items():
        def _fetch_headlines(sym: str = yf_symbol) -> list[str]:
            raw: list[dict[str, Any]] = yf.Ticker(sym).news or []
            headlines = [_extract_news_title(item) for item in raw[:10]]
            return [h for h in headlines if h]

        try:
            headlines = _retry(
                _fetch_headlines,
                max_attempts=3,
                base_delay=1.0,
                label=f"news:{internal_id}",
            )
            news_map[internal_id] = headlines
            logger.debug(
                "live_news_fetched",
                extra={"ticker": internal_id, "count": len(headlines)},
            )
        except Exception as exc:
            logger.warning(
                "live_news_fetch_failed",
                extra={"ticker": internal_id, "error": str(exc)},
            )
            news_map[internal_id] = []

    logger.info("live_news_fetch_done", extra={"tickers": list(news_map.keys())})

    # Best-effort: embed and upsert into Milvus vector store (non-blocking on failure)
    inserted = _upsert_news_to_milvus(news_map)
    if inserted:
        logger.info("live_news_milvus_sync", extra={"inserted": inserted})

    return news_map


def fetch_live_news_items() -> dict[str, list[dict[str, Any]]]:
    """Fetch latest news items (title + url + publisher + published_at) per ticker.

    Same Yahoo Finance source as ``fetch_live_news()`` but preserves the full
    item shape instead of reducing each article to a bare title string.
    Used by the ``/api/events/recent`` endpoint so news detail panels can show
    a real source link and timestamp; ``fetch_live_news()`` is left unchanged
    since SentimentEngine and other callers only want headline strings.
    """
    logger.info("live_news_items_fetch_start")
    news_map: dict[str, list[dict[str, Any]]] = {}

    for internal_id, yf_symbol in LIVE_TICKERS.items():
        def _fetch_items(sym: str = yf_symbol) -> list[dict[str, Any]]:
            raw: list[dict[str, Any]] = yf.Ticker(sym).news or []
            items = [_extract_news_item(item) for item in raw[:10]]
            return [i for i in items if i]

        try:
            items = _retry(
                _fetch_items,
                max_attempts=3,
                base_delay=1.0,
                label=f"news_items:{internal_id}",
            )
            news_map[internal_id] = items
        except Exception as exc:
            logger.warning(
                "live_news_items_fetch_failed",
                extra={"ticker": internal_id, "error": str(exc)},
            )
            news_map[internal_id] = []

    logger.info("live_news_items_fetch_done", extra={"tickers": list(news_map.keys())})
    return news_map


def fetch_ticker_detail(ticker: str) -> dict[str, float | None]:
    """Fetch 52-week high/low and last volume for a single ticker via fast_info.

    Returns ``None`` values on any failure (network error, unknown symbol)
    rather than raising — matches the graceful-degradation pattern used
    throughout this module.
    """
    yf_symbol = _normalize_yf_symbol(ticker)

    def _fetch() -> dict[str, float | None]:
        info = yf.Ticker(yf_symbol).fast_info
        return {
            "week52_high": float(info.year_high) if info.year_high is not None else None,
            "week52_low":  float(info.year_low) if info.year_low is not None else None,
            "volume":      float(info.last_volume) if info.last_volume is not None else None,
        }

    try:
        return _retry(_fetch, max_attempts=3, base_delay=1.0, label=f"ticker_detail:{ticker}")
    except Exception as exc:
        logger.warning("ticker_detail_fetch_failed", extra={"ticker": ticker, "error": str(exc)})
        return {"week52_high": None, "week52_low": None, "volume": None}


def fetch_macro_indicators() -> dict[str, float]:
    """Fetch macro economic indicators from all configured sources.

    Source priority (US):
    1. FRED API (authoritative, monthly cadence) when FRED_API_KEY is set.
    2. yfinance real-time proxies (T10Y, T3M, VIX) as always-on fallback.
    3. BLS Data API (supplement: US_CPI_BLS, US_UNRATE_BLS).

    Additional sources (no US overlap):
    4. ECB Data Portal (EU_HICP — Eurozone inflation, no key required).
    5. 한국은행 ECOS API (KR_BASE_RATE, KR_CPI — requires BOK_API_KEY).

    Each series is stored with its own source and country in macro_indicators.
    Returns a flat dict of series_id → latest value for all collected series.
    """
    # (series_id → value) and (series_id → (source, country))
    results:    dict[str, float]         = {}
    source_map: dict[str, tuple[str, str]] = {}
    now_kst = datetime.now(_KST)

    # ── 1. FRED (US authoritative) ────────────────────────────────────────────
    if FRED_API_KEY:
        for series_id, fred_id in MACRO_FRED_SERIES.items():
            url = (
                f"{FRED_BASE_URL}?series_id={fred_id}"
                f"&api_key={FRED_API_KEY}&file_type=json"
                f"&sort_order=desc&limit=1"
            )
            try:
                with httpx.Client(timeout=10.0) as http:
                    payload = http.get(url).raise_for_status().json()
                obs = payload.get("observations", [])
                if obs and obs[0].get("value", ".") != ".":
                    results[series_id] = round(float(obs[0]["value"]), 4)
                    source_map[series_id] = ("FRED", "US")
            except Exception as exc:
                logger.warning("fred_fetch_failed", extra={"series": fred_id, "error": str(exc)})

    # ── 2. yfinance proxies (US, always-on fallback) ──────────────────────────
    for series_id, yf_symbol in MACRO_YF_PROXIES.items():
        if series_id in results:
            continue
        try:
            df = yf.Ticker(yf_symbol).history(period="2d", interval="1d")
            if not df.empty:
                results[series_id] = round(float(df["Close"].iloc[-1]), 4)
                source_map[series_id] = ("yfinance", "US")
        except Exception as exc:
            logger.warning("macro_yf_fetch_failed", extra={"series": series_id, "error": str(exc)})

    # ── 3. BLS (US supplement — does not override FRED) ──────────────────────
    for series_id, value in _fetch_bls_macro().items():
        if series_id not in results:
            results[series_id] = value
            source_map[series_id] = ("bls", "US")

    # ── 4. ECB (EU — independent series, no overlap with US) ─────────────────
    for series_id, value in _fetch_ecb_macro().items():
        results[series_id] = value
        source_map[series_id] = ("ecb", "EU")

    # ── 5. BOK (KR — independent series) ─────────────────────────────────────
    for series_id, value in _fetch_bok_macro().items():
        results[series_id] = value
        source_map[series_id] = ("bok", "KR")

    # ── Mock fallback — US dashboard stays coherent when all live feeds fail ──
    if not results:
        logger.warning("macro_fetch_all_failed_using_mock")
        results = dict(_MACRO_MOCK_FALLBACK)
        source_map = dict.fromkeys(results, ("mock", "US"))

    # ── Persist to DB ─────────────────────────────────────────────────────────
    try:
        with get_connection() as conn:
            for series_id, value in results.items():
                src, cty = source_map.get(series_id, ("unknown", "US"))
                conn.execute(
                    "INSERT INTO macro_indicators "
                    "    (snapshot_time, series_id, value, source, country) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (snapshot_time, series_id) "
                    "DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source",
                    (now_kst, series_id, value, src, cty),
                )
            conn.commit()
        logger.info("macro_indicators_upserted", extra={"count": len(results)})
    except Exception as exc:
        logger.warning("macro_indicators_db_failed", extra={"error": str(exc)})

    return results


# ── Fund NAV (KOFIA OpenAPI) — scaffold ───────────────────────────────────────
#
# KOFIA(금융투자협회) OpenAPI is the planned source for daily 공모펀드 기준가
# (NAV) data backing the [FUNDS] tab. The exact endpoint path, auth-param
# name, and response field names could NOT be verified for this scaffold —
# openapi.kofia.or.kr and data.go.kr both returned HTTP 403 to documentation
# fetch attempts. Rather than guess a request/response shape for a financial
# data API, _fetch_kofia_fund_nav() is a stub that raises NotImplementedError.
# fetch_fund_nav() degrades gracefully around that stub, mirroring the
# FRED_API_KEY no-key fallback contract in fetch_macro_indicators().

# Optional KOFIA API key — set KOFIA_API_KEY once a real adapter is built.
# Absent key = adapter stays dormant; fetch_fund_nav() returns {}.
KOFIA_API_KEY: str = os.environ.get("KOFIA_API_KEY", "")

# Target funds for the [FUNDS] tab, keyed by KOFIA 펀드표준코드.
# Empty until real fund codes are confirmed — fetch_fund_nav() is a no-op
# while this is empty, so the [FUNDS] tab correctly stays masked
# ("AWAITING FEEDS") in the frontend.
FUND_NAV_TARGETS: dict[str, str] = {}


@dataclass(frozen=True)
class FundNavFact:
    """A single daily NAV (기준가) observation for one fund."""

    fund_code: str
    nav: float
    as_of: date
    source: str = "KOFIA"


def _fetch_kofia_fund_nav(fund_code: str) -> float | None:  # noqa: ARG001
    """Fetch the latest NAV for one fund from KOFIA OpenAPI.

    TODO(kofia-spec): implement the real HTTP call once the registered
    KOFIA_API_KEY's API guide confirms the endpoint path, auth parameter
    name, and response field names. Until then this stub always raises so
    fetch_fund_nav() can detect "adapter not implemented" and degrade
    gracefully instead of silently fabricating data.
    """
    raise NotImplementedError("KOFIA fund NAV API contract not yet verified")


def fetch_fund_nav() -> dict[str, float]:
    """Fetch daily fund NAV (기준가) for each fund in FUND_NAV_TARGETS.

    No-op (returns {}) when KOFIA_API_KEY is unset or FUND_NAV_TARGETS is
    empty — both true by default until a verified KOFIA adapter lands.

    Returns a dict of fund_code → latest NAV.
    Writes each successful fetch to the fund_nav_ticks hypertable.
    """
    results: dict[str, float] = {}

    if not KOFIA_API_KEY or not FUND_NAV_TARGETS:
        logger.debug(
            "fund_nav_fetch_skipped",
            extra={"reason": "no_api_key" if not KOFIA_API_KEY else "no_targets"},
        )
        return results

    for fund_code in FUND_NAV_TARGETS:
        try:
            nav = _fetch_kofia_fund_nav(fund_code)
            if nav is not None:
                results[fund_code] = nav
        except NotImplementedError:
            logger.warning("kofia_adapter_not_implemented", extra={"fund_code": fund_code})
            break  # stub adapter — retrying remaining codes won't help
        except Exception as exc:
            logger.warning("fund_nav_fetch_failed", extra={"fund_code": fund_code, "error": str(exc)})

    if not results:
        return results

    now_kst = datetime.now(_KST)
    try:
        with get_connection() as conn:
            for fund_code, nav in results.items():
                conn.execute(
                    "INSERT INTO fund_nav_ticks "
                    "    (snapshot_time, fund_code, nav, source) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (snapshot_time, fund_code) "
                    "DO UPDATE SET nav = EXCLUDED.nav",
                    (now_kst, fund_code, nav, "KOFIA"),
                )
            conn.commit()
        logger.info("fund_nav_ticks_upserted", extra={"count": len(results)})
    except Exception as exc:
        logger.warning("fund_nav_ticks_db_failed", extra={"error": str(exc)})

    return results


def embed_price_alert(ticker: str, prev: float, curr: float, display_name: str) -> None:
    """Milvus sync bridge — embed a price-alert text when a ticker moves ≥2%.

    Called from fetch_live_market_data() when a significant price change is
    detected. Creates a plain-text event string and inserts it into the
    news_collection so the LangChain RAG agent can reference it immediately.
    """
    if not _milvus_ready or _milvus_client is None:
        return

    pct = (curr - prev) / prev * 100.0
    direction = "급등" if pct > 0 else "급락"
    alert_text = (
        f"{display_name}({ticker}) {abs(pct):.1f}% {direction} "
        f"— {prev:.2f} → {curr:.2f} "
        f"({datetime.now(_KST).strftime('%Y-%m-%d %H:%M KST')})"
    )

    try:
        embedder = _get_embedder()
        vec: list[float] = embedder.embed_documents([alert_text])[0]
        _milvus_client.upsert(
            collection_name=_NEWS_COLLECTION,
            data=[{
                "id":           _news_hash_int(alert_text),
                "news_hash":    _news_hash(alert_text),
                "ticker":       ticker[:16],
                "title":        alert_text[:512],
                "published_at": int(time.time()),
                "vector":       vec,
            }],
        )
        logger.info("price_alert_embedded", extra={"ticker": ticker, "pct": round(pct, 2)})
    except Exception as exc:
        logger.warning("price_alert_embed_failed", extra={"ticker": ticker, "error": str(exc)})


def fetch_live_index_data() -> dict[str, float]:
    """Fetch the latest close price for each market index via yfinance.

    Returns a dict mapping internal index_id (KOSPI / SP500 / USDKRW)
    to the most recent close value.  Missing or errored indices are omitted.
    """
    results: dict[str, float] = {}
    for index_id, yf_symbol in INDEX_TICKERS.items():
        try:
            df = yf.Ticker(yf_symbol).history(period="2d", interval="1d")
            if not df.empty:
                results[index_id] = round(float(df["Close"].iloc[-1]), 4)
        except Exception as exc:
            logger.warning("index_fetch_failed", extra={"index": index_id, "error": str(exc)})
    return results


def get_latest_prices(config: DatabaseConfig | None = None) -> dict[str, dict[str, Any]]:
    """Return the most recent close price per ticker from market_ticks.

    Uses ``DISTINCT ON (ticker)`` — one pass, one row per ticker ordered by
    ``timestamp DESC``.  Returns ``{}`` on any DB failure so callers can fall
    back gracefully to the in-memory ``_PRICE_STATE``.
    """
    try:
        with get_connection(config) as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (ticker) ticker, close_price, timestamp "
                "FROM market_ticks "
                "ORDER BY ticker, timestamp DESC",
            ).fetchall()
        return {
            str(row[0]): {
                "price":     float(row[1]),
                "timestamp": row[2].isoformat() if row[2] else None,
                "source":    "timescaledb",
            }
            for row in rows
        }
    except Exception as exc:
        logger.warning("get_latest_prices_failed", extra={"error": str(exc)})
        return {}


# ── Virtual Broker ────────────────────────────────────────────────────────────


def _ticker_currency(ticker: str) -> str:
    """KR tickers are 6-digit numeric codes (005930); everything else is USD."""
    return "KRW" if ticker.isdigit() else "USD"


def execute_virtual_order(
    ticker: str,
    side: Literal["BUY", "SELL"],
    quantity: float,
    price: float,
    config: DatabaseConfig | None = None,
) -> dict[str, Any]:
    """Execute an immediate-fill virtual order against the given price.

    BUY debits ``virtual_accounts.cash_balance`` for the ticker's currency and
    upserts a weighted-average-cost ``portfolio_holdings`` row. SELL credits
    cash and decrements the holding (deleting the row once quantity reaches
    zero). Insufficient cash or insufficient holdings rejects the order
    (status="REJECTED") without mutating any balance.

    Single DB transaction — rows are locked with SELECT ... FOR UPDATE so
    concurrent orders against the same account/ticker serialize correctly.
    """
    if quantity <= 0:
        return {"status": "REJECTED", "reason": "quantity_must_be_positive"}
    if price <= 0:
        return {"status": "REJECTED", "reason": "invalid_price"}

    currency = _ticker_currency(ticker)
    notional = round(quantity * price, 4)

    try:
        with get_connection(config) as conn:
            account_row = conn.execute(
                "SELECT cash_balance FROM virtual_accounts WHERE currency = %s FOR UPDATE",
                (currency,),
            ).fetchone()
            if account_row is None:
                return {"status": "REJECTED", "reason": f"no_account_for_currency_{currency}"}
            cash_balance = float(account_row[0])

            holding_row = conn.execute(
                "SELECT quantity, avg_cost FROM portfolio_holdings WHERE ticker = %s FOR UPDATE",
                (ticker,),
            ).fetchone()
            held_qty  = float(holding_row[0]) if holding_row else 0.0
            held_cost = float(holding_row[1]) if holding_row else 0.0

            if side == "BUY":
                if notional > cash_balance:
                    return {
                        "status":    "REJECTED",
                        "reason":    "insufficient_cash",
                        "required":  notional,
                        "available": cash_balance,
                    }
                new_qty  = held_qty + quantity
                new_cost = ((held_qty * held_cost) + notional) / new_qty
                conn.execute(
                    "INSERT INTO portfolio_holdings (ticker, quantity, avg_cost, currency, updated_at) "
                    "VALUES (%s, %s, %s, %s, NOW()) "
                    "ON CONFLICT (ticker) DO UPDATE SET "
                    "    quantity = EXCLUDED.quantity, avg_cost = EXCLUDED.avg_cost, updated_at = NOW()",
                    (ticker, new_qty, new_cost, currency),
                )
                conn.execute(
                    "UPDATE virtual_accounts SET cash_balance = cash_balance - %s, updated_at = NOW() "
                    "WHERE currency = %s",
                    (notional, currency),
                )
            else:  # SELL
                if quantity > held_qty:
                    return {
                        "status":    "REJECTED",
                        "reason":    "insufficient_holdings",
                        "requested": quantity,
                        "held":      held_qty,
                    }
                remaining = held_qty - quantity
                if remaining <= 0:
                    conn.execute("DELETE FROM portfolio_holdings WHERE ticker = %s", (ticker,))
                else:
                    conn.execute(
                        "UPDATE portfolio_holdings SET quantity = %s, updated_at = NOW() WHERE ticker = %s",
                        (remaining, ticker),
                    )
                conn.execute(
                    "UPDATE virtual_accounts SET cash_balance = cash_balance + %s, updated_at = NOW() "
                    "WHERE currency = %s",
                    (notional, currency),
                )

            order_row = conn.execute(
                "INSERT INTO virtual_orders (ticker, side, quantity, fill_price, currency, status) "
                "VALUES (%s, %s, %s, %s, %s, 'FILLED') RETURNING id",
                (ticker, side, quantity, price, currency),
            ).fetchone()
            order_id = order_row[0] if order_row else None

            # Append-only audit trail
            import json as _json
            conn.execute(
                "INSERT INTO audit_log (action, payload) VALUES (%s, %s)",
                (
                    "virtual_order_filled",
                    _json.dumps({
                        "order_id":  order_id,
                        "ticker":    ticker,
                        "side":      side,
                        "quantity":  quantity,
                        "price":     price,
                        "currency":  currency,
                        "notional":  notional,
                    }),
                ),
            )
            conn.commit()

        logger.info(
            "virtual_order_filled",
            extra={"ticker": ticker, "side": side, "quantity": quantity, "price": price, "order_id": order_id},
        )
        return {
            "status":     "FILLED",
            "order_id":   order_id,
            "ticker":     ticker,
            "side":       side,
            "quantity":   quantity,
            "fill_price": price,
            "currency":   currency,
            "notional":   notional,
        }
    except Exception as exc:
        logger.error("virtual_order_failed", extra={"ticker": ticker, "error": str(exc)})
        return {"status": "ERROR", "reason": str(exc)}


def get_portfolio_holdings(config: DatabaseConfig | None = None) -> list[dict[str, Any]]:
    """Return every current portfolio_holdings row (cost basis, no live valuation)."""
    try:
        with get_connection(config) as conn:
            rows = conn.execute(
                "SELECT ticker, quantity, avg_cost, currency FROM portfolio_holdings ORDER BY ticker",
            ).fetchall()
        return [
            {
                "ticker":   str(r[0]),
                "quantity": float(r[1]),
                "avg_cost": float(r[2]),
                "currency": str(r[3]),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("get_portfolio_holdings_failed", extra={"error": str(exc)})
        return []


def get_virtual_accounts(config: DatabaseConfig | None = None) -> dict[str, dict[str, float]]:
    """Return {currency: {cash_balance, initial_balance}} for every virtual account."""
    try:
        with get_connection(config) as conn:
            rows = conn.execute(
                "SELECT currency, cash_balance, initial_balance FROM virtual_accounts",
            ).fetchall()
        return {
            str(r[0]): {"cash_balance": float(r[1]), "initial_balance": float(r[2])}
            for r in rows
        }
    except Exception as exc:
        logger.warning("get_virtual_accounts_failed", extra={"error": str(exc)})
        return {}


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    init_db()
    seed_mock_data()
    _PoolManager.close()
