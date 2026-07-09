"""Market data adapters — coexist alongside yfinance as the primary data source.

Each adapter activates only when its env var(s) are configured. When
unavailable (unconfigured or network error), the caller falls back to
yfinance. No adapter is required for the system to function.

Supported adapters:
  - Alpaca Markets (ALPACA_API_KEY + ALPACA_API_SECRET) — US stocks / ETFs
  - Finnhub        (FINNHUB_API_KEY)                    — US real-time quotes
  - KIS            (KIS_APP_KEY + KIS_APP_SECRET)        — KR stocks [STUB]

Row tuple format matches the market_ticks COPY schema:
    (timestamp_kst, internal_id, open, high, low, close, volume, source)
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytz

logger = logging.getLogger(__name__)

_KST = pytz.timezone("Asia/Seoul")

# ── env-var gates ─────────────────────────────────────────────────────────────

_ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
_ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
_FINNHUB_API_KEY   = os.getenv("FINNHUB_API_KEY", "")
_KIS_APP_KEY       = os.getenv("KIS_APP_KEY", "")
_KIS_APP_SECRET    = os.getenv("KIS_APP_SECRET", "")

# Row format: (timestamp_kst, internal_id, open, high, low, close, volume, source)
OHLCVRow = tuple[datetime, str, float, float, float, float, int, str]


def alpaca_available() -> bool:
    return bool(_ALPACA_API_KEY and _ALPACA_API_SECRET)


def finnhub_available() -> bool:
    return bool(_FINNHUB_API_KEY)


def kis_available() -> bool:
    return bool(_KIS_APP_KEY and _KIS_APP_SECRET)


# ── Alpaca Markets ────────────────────────────────────────────────────────────

_ALPACA_BASE = "https://data.alpaca.markets/v2"


def fetch_alpaca_bars(
    internal_id: str,
    us_symbol: str,
    days: int = 7,
) -> list[OHLCVRow] | None:
    """Fetch daily OHLCV bars from Alpaca Markets (IEX free feed).

    Targets US-listed symbols (AAPL, MSFT, TSLA, QQQ, BND, GLD, …).
    Returns None when unconfigured or the request fails (caller falls back
    to yfinance). Returns [] for valid symbol with no recent bars.
    """
    if not alpaca_available():
        return None

    start_date = (datetime.now(tz=UTC) - timedelta(days=days + 4)).strftime("%Y-%m-%d")

    try:
        resp = httpx.get(
            f"{_ALPACA_BASE}/stocks/{us_symbol}/bars",
            params={
                "timeframe":  "1Day",
                "start":      start_date,
                "limit":      days,
                "feed":       "iex",   # free tier: IEX feed
                "adjustment": "all",   # split + dividend adjusted
            },
            headers={
                "APCA-API-KEY-ID":     _ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": _ALPACA_API_SECRET,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "alpaca_http_error",
            extra={"ticker": internal_id, "status": exc.response.status_code},
        )
        return None
    except Exception as exc:
        logger.warning("alpaca_fetch_failed", extra={"ticker": internal_id, "error": str(exc)})
        return None

    bars: list[dict[str, Any]] = resp.json().get("bars") or []
    rows: list[OHLCVRow] = []
    for bar in bars:
        ts_utc = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
        ts_kst = ts_utc.astimezone(_KST)
        rows.append((
            ts_kst,
            internal_id,
            float(bar["o"]),
            float(bar["h"]),
            float(bar["l"]),
            float(bar["c"]),
            int(bar["v"]),
            "alpaca",
        ))

    if rows:
        logger.debug("alpaca_bars_fetched", extra={"ticker": internal_id, "rows": len(rows)})
    return rows


# ── Finnhub ───────────────────────────────────────────────────────────────────

_FINNHUB_BASE = "https://finnhub.io/api/v1"


def fetch_finnhub_quote(
    internal_id: str,
    finnhub_symbol: str,
) -> OHLCVRow | None:
    """Fetch the current-day OHLCV snapshot from Finnhub.

    Useful as a real-time supplement to historical bars (e.g. today's
    intraday snapshot when the market is open). Finnhub free tier covers
    US exchanges; Korean stocks (XKRX) require a premium plan.

    Returns None when unconfigured, market is closed/symbol not found,
    or the request fails.
    """
    if not finnhub_available():
        return None

    try:
        resp = httpx.get(
            f"{_FINNHUB_BASE}/quote",
            params={"symbol": finnhub_symbol, "token": _FINNHUB_API_KEY},
            timeout=8.0,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
    except Exception as exc:
        logger.warning("finnhub_fetch_failed", extra={"ticker": internal_id, "error": str(exc)})
        return None

    # Finnhub returns 0s for closed / unknown symbols
    if not data.get("c") or data["c"] == 0:
        return None

    # Represent as today 00:00 KST (daily bar convention)
    ts_kst = datetime.now(tz=_KST).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        ts_kst,
        internal_id,
        float(data.get("o", data["c"])),
        float(data.get("h", data["c"])),
        float(data.get("l", data["c"])),
        float(data["c"]),
        int(data.get("v", 0)),
        "finnhub",
    )


# ── KIS (Korea Investment Securities) — STUB ──────────────────────────────────


def fetch_kis_bars(
    internal_id: str,
    kr_symbol: str,  # noqa: ARG001
    days: int = 7,   # noqa: ARG001
) -> list[OHLCVRow] | None:
    """Fetch daily OHLCV bars from KIS Developers API for KR-listed stocks.

    Not yet implemented — requires a KIS account and API key from
    https://apiportal.koreainvestment.com/. Returns None (yfinance fallback)
    until the real adapter is built.
    """
    if not kis_available():
        return None
    logger.debug("kis_adapter_stub_called", extra={"ticker": internal_id})
    return None  # stub: caller falls through to yfinance
