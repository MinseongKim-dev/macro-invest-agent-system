"""Unit tests for Level 2-3 historical data ingestion in src/database.py.

All tests mock yfinance and DB calls — no live API requests or DB writes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd


def _make_yf_history(closes: list[float]) -> pd.DataFrame:
    """Build a minimal yfinance-style .history() DataFrame."""
    idx = pd.date_range("2024-01-02", periods=len(closes), freq="B", tz="UTC")
    return pd.DataFrame({"Close": closes}, index=idx)


# ── fetch_historical_data ─────────────────────────────────────────────────────


def test_fetch_historical_data_happy_path() -> None:
    """Happy path: 3 close prices → 3 upserted rows, returns count."""
    from src.database import fetch_historical_data

    closes = [100.0, 101.5, 102.3]
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_yf_history(closes)

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.database.yf.Ticker", return_value=mock_ticker),
        patch("src.database.get_connection", return_value=mock_conn),
    ):
        result = fetch_historical_data(tickers={"AAPL": "AAPL"}, years=1)

    assert result == 3
    assert mock_conn.execute.call_count == 3
    mock_conn.commit.assert_called_once()


def test_fetch_historical_data_empty_history() -> None:
    """Empty yfinance result → 0 rows, no DB writes."""
    from src.database import fetch_historical_data

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.database.yf.Ticker", return_value=mock_ticker),
        patch("src.database.get_connection", return_value=mock_conn),
    ):
        result = fetch_historical_data(tickers={"AAPL": "AAPL"}, years=1)

    assert result == 0
    mock_conn.execute.assert_not_called()


def test_fetch_historical_data_yfinance_error_skips_ticker() -> None:
    """yfinance failure for one ticker is logged and swallowed; returns 0."""
    from src.database import fetch_historical_data

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.database.yf.Ticker", side_effect=Exception("network error")),
        patch("src.database.get_connection", return_value=mock_conn),
    ):
        result = fetch_historical_data(tickers={"AAPL": "AAPL"}, years=1)

    assert result == 0
    mock_conn.execute.assert_not_called()


def test_fetch_historical_data_multiple_tickers() -> None:
    """Two tickers → rows from both are summed in return value."""
    from src.database import fetch_historical_data

    def _ticker_factory(symbol: str) -> MagicMock:
        m = MagicMock()
        m.history.return_value = _make_yf_history([50.0, 51.0])
        return m

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.database.yf.Ticker", side_effect=_ticker_factory),
        patch("src.database.get_connection", return_value=mock_conn),
    ):
        result = fetch_historical_data(
            tickers={"AAPL": "AAPL", "MSFT": "MSFT"}, years=1
        )

    assert result == 4  # 2 tickers × 2 bars


def test_fetch_historical_data_partial_ticker_failure() -> None:
    """One ticker errors, the other succeeds — partial result returned."""
    from src.database import fetch_historical_data

    good_ticker = MagicMock()
    good_ticker.history.return_value = _make_yf_history([200.0, 202.0, 204.0])
    bad_ticker = MagicMock()
    bad_ticker.history.side_effect = Exception("rate limit")

    call_count = 0

    def _ticker_factory(symbol: str) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return good_ticker if call_count == 1 else bad_ticker

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.database.yf.Ticker", side_effect=_ticker_factory),
        patch("src.database.get_connection", return_value=mock_conn),
    ):
        result = fetch_historical_data(
            tickers={"AAPL": "AAPL", "MSFT": "MSFT"}, years=1
        )

    assert result == 3


def test_fetch_historical_data_uses_live_tickers_by_default() -> None:
    """When tickers=None, all LIVE_TICKERS are processed."""
    from src.database import LIVE_TICKERS, fetch_historical_data

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.database.yf.Ticker", return_value=mock_ticker) as mock_yf,
        patch("src.database.get_connection", return_value=mock_conn),
    ):
        fetch_historical_data(years=1)

    assert mock_yf.call_count == len(LIVE_TICKERS)
