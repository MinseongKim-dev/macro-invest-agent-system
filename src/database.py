"""Aleph-One database layer — connection pool, schema init, mock data seeding.

Tri-File Architecture — this file owns:
  - DatabaseConfig        : env-var backed config dataclass
  - _PoolManager          : thread-safe connection pool singleton
  - get_pool()            : pool accessor
  - get_connection()      : context manager (lease → auto-return)
  - init_db()             : DDL — market_ticks hypertable + macro_regimes
  - seed_mock_data()      : pandas GBM OHLCV + dummy regimes via COPY (bulk)

Run standalone::

    python -m src.database
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
import psycopg
import psycopg_pool
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
    "AAPL": {"start": 195.0, "mu": 0.10, "sigma": 0.22},
    "MSFT": {"start": 415.0, "mu": 0.12, "sigma": 0.20},
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


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    init_db()
    seed_mock_data()
    _PoolManager.close()
