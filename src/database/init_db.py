"""Database schema initializer.

Creates the `market_ticks` TimescaleDB hypertable and the `macro_regimes`
table if they do not already exist.  Safe to run multiple times (idempotent).
"""

from __future__ import annotations

import logging

from src.database.connection import DatabaseConfig, DatabaseConnection

logger = logging.getLogger(__name__)

_CREATE_MARKET_TICKS = """
CREATE TABLE IF NOT EXISTS market_ticks (
    timestamp   TIMESTAMPTZ  NOT NULL,
    ticker      VARCHAR(10)  NOT NULL,
    open_price  NUMERIC(15,4) NOT NULL,
    high_price  NUMERIC(15,4) NOT NULL,
    low_price   NUMERIC(15,4) NOT NULL,
    close_price NUMERIC(15,4) NOT NULL,
    volume      BIGINT       NOT NULL
);
"""

_CREATE_HYPERTABLE = """
SELECT create_hypertable(
    'market_ticks',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);
"""

_CREATE_MACRO_REGIMES = """
CREATE TABLE IF NOT EXISTS macro_regimes (
    id               SERIAL PRIMARY KEY,
    updated_at       TIMESTAMPTZ  DEFAULT NOW(),
    regime_name      VARCHAR(50)  NOT NULL,
    market_phase     VARCHAR(30)  NOT NULL,
    confidence_score NUMERIC(3,2) NOT NULL
);
"""


class DatabaseInitializer:
    """Applies the Aleph-One schema to a TimescaleDB instance.

    All DDL statements are idempotent (`IF NOT EXISTS` / `if_not_exists`),
    so this initializer can be called on every application start without
    risk of data loss or duplicate-object errors.
    """

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._db = DatabaseConnection(config)

    def run(self) -> None:
        """Execute the full schema setup."""
        logger.info("db_init_start")
        with self._db.connect() as conn:
            self._create_market_ticks(conn)
            self._create_hypertable(conn)
            self._create_macro_regimes(conn)
            conn.commit()
        logger.info("db_init_complete")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_market_ticks(self, conn) -> None:  # type: ignore[no-untyped-def]
        conn.execute(_CREATE_MARKET_TICKS)
        logger.debug("db_table_ensured", extra={"table": "market_ticks"})

    def _create_hypertable(self, conn) -> None:  # type: ignore[no-untyped-def]
        conn.execute(_CREATE_HYPERTABLE)
        logger.debug("db_hypertable_ensured", extra={"table": "market_ticks"})

    def _create_macro_regimes(self, conn) -> None:  # type: ignore[no-untyped-def]
        conn.execute(_CREATE_MACRO_REGIMES)
        logger.debug("db_table_ensured", extra={"table": "macro_regimes"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    DatabaseInitializer().run()
