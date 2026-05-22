"""Aleph-One database layer — connection pool, schema init, mock data seeding,
live market data fetch via yfinance.

Tri-File Architecture — this file owns:
  - DatabaseConfig          : env-var backed config dataclass
  - _PoolManager            : thread-safe connection pool singleton
  - get_pool()              : pool accessor
  - get_connection()        : context manager (lease → auto-return)
  - init_db()               : DDL — market_ticks hypertable + macro_regimes
  - seed_mock_data()        : pandas GBM OHLCV + dummy regimes via COPY (bulk)
  - LIVE_TICKERS            : yfinance symbol → internal ticker ID mapping
  - fetch_live_market_data(): yfinance OHLCV → market_ticks (DELETE + COPY, retried)
  - fetch_live_news()       : yfinance .news → headline strings per ticker (retried)

Run standalone::

    python -m src.database
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import psycopg
import psycopg_pool
import yfinance as yf
from psycopg.rows import TupleRow

logger = logging.getLogger(__name__)

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
}

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


def _fetch_ticker_ohlcv(internal_id: str, yf_symbol: str) -> list[tuple[Any, ...]]:
    """Download the last 5 trading days of daily OHLCV from Yahoo Finance.

    Returns a list of DB row tuples ready for COPY:
        (timestamp_utc, internal_id, open, high, low, close, volume)
    """
    ticker_obj = yf.Ticker(yf_symbol)
    hist: pd.DataFrame = ticker_obj.history(
        period="5d",
        interval="1d",
        auto_adjust=True,
        raise_errors=False,
    )

    if hist.empty:
        logger.warning("yf_history_empty", extra={"ticker": internal_id, "symbol": yf_symbol})
        return []

    hist = hist.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    rows: list[tuple[Any, ...]] = []
    for idx, row in hist.iterrows():
        ts = pd.Timestamp(idx)
        ts_utc = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        rows.append((
            ts_utc.to_pydatetime(),
            internal_id,
            float(row["Open"]),
            float(row["High"]),
            float(row["Low"]),
            float(row["Close"]),
            int(row["Volume"]),
        ))
    return rows


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
                "(timestamp, ticker, open_price, high_price, low_price, close_price, volume) "
                "FROM STDIN"
            ) as copy:
                for r in all_rows:
                    copy.write_row(r)
            conn.commit()

        logger.info("live_market_upsert_done", extra={"rows": len(all_rows)})
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
    return news_map


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    init_db()
    seed_mock_data()
    _PoolManager.close()
