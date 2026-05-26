"""Aleph-One database layer — connection pool, schema init, mock data seeding,
live market data fetch via yfinance, Milvus news vector store.

Tri-File Architecture — this file owns:
  - DatabaseConfig            : env-var backed config dataclass
  - _PoolManager              : thread-safe connection pool singleton
  - get_pool()                : pool accessor
  - get_connection()          : context manager (lease → auto-return)
  - init_db()                 : DDL — market_ticks hypertable + macro_regimes
  - seed_mock_data()          : pandas GBM OHLCV + dummy regimes via COPY (bulk)
  - LIVE_TICKERS              : yfinance symbol → internal ticker ID mapping
  - fetch_live_market_data()  : yfinance OHLCV → market_ticks (DELETE + COPY, retried)
  - fetch_live_news()         : yfinance .news → headlines per ticker + Milvus upsert
  - init_milvus()             : Milvus connection + news_collection schema + HNSW index
  - search_milvus_news()      : semantic ANN search over ingested news headlines

Run standalone::

    python -m src.database
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import psycopg
import psycopg_pool
import pytz
import yfinance as yf
from psycopg.rows import TupleRow

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
}

# Market index symbols — used by the index collector (not stored in market_ticks)
INDEX_TICKERS: dict[str, str] = {
    "KOSPI":  "^KS11",
    "SP500":  "^GSPC",
    "USDKRW": "KRW=X",
}


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
        ts_kst = _to_kst(ts)   # normalise to KST before DB insert
        rows.append((
            ts_kst,
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

    # Best-effort: embed and upsert into Milvus vector store (non-blocking on failure)
    inserted = _upsert_news_to_milvus(news_map)
    if inserted:
        logger.info("live_news_milvus_sync", extra={"inserted": inserted})

    return news_map


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


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    init_db()
    seed_mock_data()
    _PoolManager.close()
