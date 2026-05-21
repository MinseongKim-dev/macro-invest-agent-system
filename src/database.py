"""Aleph-One database layer — single-file integration.

Covers: connection management (with exponential-backoff retry), schema
initialisation (TimescaleDB hypertable + macro_regimes), and market-data
seeding from Yahoo Finance.

Quick-start::

    python -m src.database        # init schema + seed AAPL/MSFT

Environment variables (all optional — defaults match docker-compose):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import psycopg
from psycopg.rows import TupleRow

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

_MAX_RETRIES: int = 5
_RETRY_BASE_DELAY: float = 1.0  # doubles on each attempt


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = field(default_factory=lambda: os.environ.get("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.environ.get("DB_PORT", "5432")))
    name: str = field(default_factory=lambda: os.environ.get("DB_NAME", "aleph_core"))
    user: str = field(default_factory=lambda: os.environ.get("DB_USER", "aleph_admin"))
    password: str = field(default_factory=lambda: os.environ.get("DB_PASSWORD", "aleph_secure_pass"))
    max_retries: int = _MAX_RETRIES
    retry_base_delay: float = _RETRY_BASE_DELAY

    @property
    def conninfo(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.name} "
            f"user={self.user} password={self.password}"
        )


# ── Connection ────────────────────────────────────────────────────────────────


class DatabaseConnection:
    """psycopg v3 connection wrapper with exponential-backoff retry.

    Usage::

        db = DatabaseConnection()
        with db.connect() as conn:
            conn.execute("SELECT 1")
    """

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._config = config or DatabaseConfig()

    def open(self) -> psycopg.Connection[TupleRow]:
        """Return an open connection, retrying up to `max_retries` times."""
        cfg = self._config
        delay = cfg.retry_base_delay

        for attempt in range(1, cfg.max_retries + 1):
            try:
                conn: psycopg.Connection[TupleRow] = psycopg.connect(cfg.conninfo)
                logger.info("db_connected", extra={"host": cfg.host, "attempt": attempt})
                return conn
            except psycopg.OperationalError as exc:
                if attempt == cfg.max_retries:
                    logger.error("db_connection_failed", extra={"host": cfg.host, "error": str(exc)})
                    raise
                logger.warning(
                    "db_connection_retry",
                    extra={"attempt": attempt, "retry_in": delay, "error": str(exc)},
                )
                time.sleep(delay)
                delay *= 2

        raise RuntimeError("unreachable")  # pragma: no cover

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection[TupleRow]]:
        """Context manager: open a connection and close it on exit."""
        conn = self.open()
        try:
            yield conn
        finally:
            conn.close()
            logger.debug("db_connection_closed", extra={"host": self._config.host})


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
    id               SERIAL PRIMARY KEY,
    updated_at       TIMESTAMPTZ   DEFAULT NOW(),
    regime_name      VARCHAR(50)   NOT NULL,
    market_phase     VARCHAR(30)   NOT NULL,
    confidence_score NUMERIC(3,2)  NOT NULL
);
"""

# ── Initialiser ───────────────────────────────────────────────────────────────


class DatabaseInitializer:
    """Idempotent schema setup: market_ticks hypertable + macro_regimes."""

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._db = DatabaseConnection(config)

    def run(self) -> None:
        logger.info("db_init_start")
        with self._db.connect() as conn:
            conn.execute(_DDL_MARKET_TICKS)
            logger.debug("db_table_ensured", extra={"table": "market_ticks"})
            conn.execute(_DDL_HYPERTABLE)
            logger.debug("db_hypertable_ensured")
            conn.execute(_DDL_MACRO_REGIMES)
            logger.debug("db_table_ensured", extra={"table": "macro_regimes"})
            conn.commit()
        logger.info("db_init_complete")


# ── Seeder ────────────────────────────────────────────────────────────────────

_SEED_TICKERS: list[str] = ["AAPL", "MSFT"]
_SEED_DAYS: int = 30

_SQL_UPSERT = """
INSERT INTO market_ticks
    (timestamp, ticker, open_price, high_price, low_price, close_price, volume)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING;
"""

_Row = tuple[date, str, float, float, float, float, int]


class MarketDataSeeder:
    """Downloads 30-day daily OHLCV via yfinance and upserts into market_ticks."""

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._db = DatabaseConnection(config)

    def run(
        self,
        tickers: list[str] = _SEED_TICKERS,
        days: int = _SEED_DAYS,
    ) -> None:
        rows = self._fetch(tickers, days)
        if not rows:
            logger.warning("seed_no_rows_fetched")
            return

        logger.info("seed_insert_start", extra={"rows": len(rows)})
        with self._db.connect() as conn:
            for row in rows:
                conn.execute(_SQL_UPSERT, row)
            conn.commit()
        logger.info("seed_insert_complete", extra={"rows": len(rows)})

    def _fetch(self, tickers: list[str], days: int) -> list[_Row]:
        try:
            import yfinance as yf  # optional dependency
        except ImportError:
            logger.error("yfinance_not_installed", extra={"hint": "pip install yfinance"})
            return []

        end = date.today()
        start = end - timedelta(days=days)
        rows: list[_Row] = []

        for ticker in tickers:
            try:
                df = yf.download(
                    ticker,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    progress=False,
                    auto_adjust=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("yfinance_fetch_error", extra={"ticker": ticker, "error": str(exc)})
                continue

            if df.empty:
                logger.warning("yfinance_no_data", extra={"ticker": ticker})
                continue

            # yfinance may return MultiIndex columns for single-ticker downloads
            if hasattr(df.columns, "get_level_values"):
                df.columns = df.columns.get_level_values(0)

            for idx, row in df.iterrows():
                rows.append((
                    idx.date(),  # type: ignore[union-attr]
                    ticker,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    int(row["Volume"]),
                ))

            logger.info("yfinance_fetched", extra={"ticker": ticker, "rows": len(df)})

        return rows


# ── Convenience ───────────────────────────────────────────────────────────────


def init_db(config: DatabaseConfig | None = None) -> None:
    """Run schema initialisation (idempotent)."""
    DatabaseInitializer(config).run()


def seed_db(config: DatabaseConfig | None = None) -> None:
    """Seed AAPL + MSFT 30-day OHLCV data."""
    MarketDataSeeder(config).run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    seed_db()
