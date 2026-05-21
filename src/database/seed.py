"""Market data seeder.

Fetches 30 days of daily OHLCV data for AAPL and MSFT via yfinance and
upserts it into the `market_ticks` TimescaleDB table.

Usage::

    python -m src.database.seed

Environment variables (all optional, defaults match docker-compose):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import yfinance as yf

from src.database.connection import DatabaseConfig, DatabaseConnection

logger = logging.getLogger(__name__)

_TICKERS = ["AAPL", "MSFT"]
_HISTORY_DAYS = 30

_UPSERT_TICK = """
INSERT INTO market_ticks (timestamp, ticker, open_price, high_price, low_price, close_price, volume)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING;
"""


@dataclass(frozen=True)
class OHLCVRow:
    timestamp: date
    ticker: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int


class YFinanceFetcher:
    """Downloads daily OHLCV rows from Yahoo Finance for the given tickers."""

    def fetch(self, tickers: list[str], days: int = _HISTORY_DAYS) -> list[OHLCVRow]:
        end = date.today()
        start = end - timedelta(days=days)
        rows: list[OHLCVRow] = []

        for ticker in tickers:
            logger.info("yfinance_fetch_start", extra={"ticker": ticker, "start": str(start), "end": str(end)})
            try:
                df = yf.download(
                    ticker,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    progress=False,
                    auto_adjust=True,
                )
            except Exception as exc:
                logger.error("yfinance_fetch_error", extra={"ticker": ticker, "error": str(exc)})
                continue

            if df.empty:
                logger.warning("yfinance_no_data", extra={"ticker": ticker})
                continue

            for idx, row in df.iterrows():
                rows.append(
                    OHLCVRow(
                        timestamp=idx.date(),  # type: ignore[union-attr]
                        ticker=ticker,
                        open_price=float(row["Open"]),
                        high_price=float(row["High"]),
                        low_price=float(row["Low"]),
                        close_price=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )

            logger.info("yfinance_fetch_complete", extra={"ticker": ticker, "rows": len(df)})

        return rows


class MarketDataSeeder:
    """Upserts OHLCV rows from `YFinanceFetcher` into `market_ticks`."""

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self._db = DatabaseConnection(config)
        self._fetcher = YFinanceFetcher()

    def run(self, tickers: list[str] = _TICKERS, days: int = _HISTORY_DAYS) -> None:
        rows = self._fetcher.fetch(tickers, days)
        if not rows:
            logger.warning("seed_no_rows_fetched")
            return

        logger.info("seed_insert_start", extra={"rows": len(rows)})
        inserted = 0

        with self._db.connect() as conn:
            for row in rows:
                conn.execute(
                    _UPSERT_TICK,
                    (
                        row.timestamp,
                        row.ticker,
                        row.open_price,
                        row.high_price,
                        row.low_price,
                        row.close_price,
                        row.volume,
                    ),
                )
                inserted += 1
            conn.commit()

        logger.info("seed_insert_complete", extra={"rows_inserted": inserted})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    MarketDataSeeder().run()
