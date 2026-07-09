"""Unit tests for src/adapters.py — market data adapters.

All tests use monkeypatching / mock HTTP responses so no live API calls
are made. Tests cover: availability guards, success paths, error handling,
and KIS stub behaviour.
"""

from __future__ import annotations

import importlib
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_alpaca_bar(
    date_str: str,
    o: float,
    h: float,
    low: float,
    c: float,
    v: int,
) -> dict:
    return {"t": f"{date_str}T00:00:00Z", "o": o, "h": h, "l": low, "c": c, "v": v}


def _mock_alpaca_response(bars: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"bars": bars}
    resp.raise_for_status.return_value = None
    return resp


def _mock_finnhub_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


# ── availability guards ───────────────────────────────────────────────────────


def test_alpaca_not_available_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET", raising=False)
    import src.adapters as mod
    importlib.reload(mod)
    assert mod.alpaca_available() is False


def test_finnhub_not_available_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    import src.adapters as mod
    importlib.reload(mod)
    assert mod.finnhub_available() is False


def test_kis_not_available_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KIS_APP_KEY", raising=False)
    monkeypatch.delenv("KIS_APP_SECRET", raising=False)
    import src.adapters as mod
    importlib.reload(mod)
    assert mod.kis_available() is False


# ── Alpaca adapter ────────────────────────────────────────────────────────────


def test_fetch_alpaca_bars_returns_none_when_unconfigured() -> None:
    """fetch_alpaca_bars returns None (not []) when credentials absent."""
    from src.adapters import fetch_alpaca_bars
    with patch("src.adapters._ALPACA_API_KEY", ""), patch("src.adapters._ALPACA_API_SECRET", ""):
        result = fetch_alpaca_bars("AAPL", "AAPL", days=5)
    assert result is None


def test_fetch_alpaca_bars_success() -> None:
    """Happy path: 2 bars returned, row format matches OHLCVRow spec."""
    bars = [
        _make_alpaca_bar("2024-07-08", 190.0, 195.0, 188.0, 192.0, 50_000_000),
        _make_alpaca_bar("2024-07-09", 192.0, 196.0, 191.0, 194.0, 45_000_000),
    ]
    with (
        patch("src.adapters._ALPACA_API_KEY", "key"),
        patch("src.adapters._ALPACA_API_SECRET", "secret"),
        patch("src.adapters.httpx.get", return_value=_mock_alpaca_response(bars)),
    ):
        from src.adapters import fetch_alpaca_bars
        rows = fetch_alpaca_bars("AAPL", "AAPL", days=5)

    assert rows is not None
    assert len(rows) == 2
    ts, ticker, o, h, low, c, v, source = rows[0]
    assert isinstance(ts, datetime)
    assert ticker == "AAPL"
    assert o == 190.0
    assert h == 195.0
    assert low == 188.0
    assert c == 192.0
    assert v == 50_000_000
    assert source == "alpaca"


def test_fetch_alpaca_bars_returns_none_on_http_error() -> None:
    """Network / HTTP errors cause None return (yfinance fallback triggered)."""
    import httpx

    err_resp = MagicMock()
    err_resp.status_code = 403

    with (
        patch("src.adapters._ALPACA_API_KEY", "key"),
        patch("src.adapters._ALPACA_API_SECRET", "secret"),
        patch(
            "src.adapters.httpx.get",
            side_effect=httpx.HTTPStatusError(
                "Forbidden", request=MagicMock(), response=err_resp
            ),
        ),
    ):
        from src.adapters import fetch_alpaca_bars
        result = fetch_alpaca_bars("AAPL", "AAPL")

    assert result is None


def test_fetch_alpaca_bars_empty_when_no_bars() -> None:
    """Empty bars list → [] (distinguishable from None / adapter-unavailable)."""
    with (
        patch("src.adapters._ALPACA_API_KEY", "key"),
        patch("src.adapters._ALPACA_API_SECRET", "secret"),
        patch("src.adapters.httpx.get", return_value=_mock_alpaca_response([])),
    ):
        from src.adapters import fetch_alpaca_bars
        result = fetch_alpaca_bars("QQQ", "QQQ")

    assert result == []


# ── Finnhub adapter ───────────────────────────────────────────────────────────


def test_fetch_finnhub_quote_returns_none_when_unconfigured() -> None:
    from src.adapters import fetch_finnhub_quote
    with patch("src.adapters._FINNHUB_API_KEY", ""):
        result = fetch_finnhub_quote("AAPL", "AAPL")
    assert result is None


def test_fetch_finnhub_quote_returns_none_for_zero_price() -> None:
    """Finnhub returns 0s for closed market / unknown symbol — expect None."""
    data = {"c": 0, "o": 0, "h": 0, "l": 0, "v": 0}
    with (
        patch("src.adapters._FINNHUB_API_KEY", "token"),
        patch("src.adapters.httpx.get", return_value=_mock_finnhub_response(data)),
    ):
        from src.adapters import fetch_finnhub_quote
        result = fetch_finnhub_quote("AAPL", "AAPL")
    assert result is None


def test_fetch_finnhub_quote_success() -> None:
    """Happy path: valid quote returns a single OHLCVRow with source='finnhub'."""
    data = {"c": 192.5, "o": 190.0, "h": 193.0, "l": 189.5, "v": 30_000_000}
    with (
        patch("src.adapters._FINNHUB_API_KEY", "token"),
        patch("src.adapters.httpx.get", return_value=_mock_finnhub_response(data)),
    ):
        from src.adapters import fetch_finnhub_quote
        row = fetch_finnhub_quote("AAPL", "AAPL")

    assert row is not None
    ts, ticker, o, h, low, c, v, source = row
    assert isinstance(ts, datetime)
    assert ticker == "AAPL"
    assert c == 192.5
    assert source == "finnhub"


# ── KIS stub ─────────────────────────────────────────────────────────────────


def test_fetch_kis_bars_returns_none_when_unconfigured() -> None:
    from src.adapters import fetch_kis_bars
    with patch("src.adapters._KIS_APP_KEY", ""), patch("src.adapters._KIS_APP_SECRET", ""):
        result = fetch_kis_bars("005930", "005930.KS")
    assert result is None


def test_fetch_kis_bars_stub_returns_none_even_when_configured() -> None:
    """Stub always returns None regardless of credentials — triggers yfinance fallback."""
    from src.adapters import fetch_kis_bars
    with patch("src.adapters._KIS_APP_KEY", "key"), patch("src.adapters._KIS_APP_SECRET", "secret"):
        result = fetch_kis_bars("005930", "005930.KS")
    assert result is None
