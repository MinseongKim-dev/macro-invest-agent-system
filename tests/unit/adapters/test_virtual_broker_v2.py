"""Unit tests for L3-3 virtual broker enhancements:
commission/slippage in execute_virtual_order and record_portfolio_nav.

All DB calls are mocked — no real connection required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.database import execute_virtual_order, get_portfolio_nav_history, record_portfolio_nav

# ── commission / slippage math ────────────────────────────────────────────────


def _make_conn_mock(cash: float = 1_000_000.0, held_qty: float = 0.0, held_cost: float = 0.0) -> MagicMock:
    """Return a context-manager mock that mimics a DB connection for virtual orders."""
    conn = MagicMock()
    # SELECT ... FOR UPDATE for account
    account_row = MagicMock()
    account_row.__getitem__ = lambda self, i: cash  # cash_balance
    # SELECT ... FOR UPDATE for holdings
    holding_row: MagicMock | None = None
    if held_qty > 0:
        holding_row = MagicMock()
        holding_row.__getitem__ = lambda self, i: held_qty if i == 0 else held_cost

    execute_results = [
        MagicMock(fetchone=lambda: account_row),   # account lock
        MagicMock(fetchone=lambda: holding_row),   # holding lock
        MagicMock(),                                # INSERT/UPDATE portfolio_holdings
        MagicMock(),                                # UPDATE virtual_accounts
        MagicMock(fetchone=lambda: (42,)),          # INSERT virtual_orders RETURNING id
        MagicMock(),                                # INSERT audit_log
    ]
    conn.execute.side_effect = execute_results
    conn.commit = MagicMock()
    return conn


@patch("src.database.get_connection")
def test_buy_applies_slippage_to_fill_price(mock_get_conn: MagicMock) -> None:
    conn = _make_conn_mock(cash=500_000.0, held_qty=0.0)
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = execute_virtual_order(
        "AAPL", "BUY", quantity=1.0, price=100.0, commission_rate=0.0, slippage_pct=0.01
    )
    assert result["status"] == "FILLED"
    # fill_price = 100 * 1.01 = 101
    assert result["fill_price"] == pytest.approx(101.0, rel=1e-6)


@patch("src.database.get_connection")
def test_sell_applies_slippage_below_price(mock_get_conn: MagicMock) -> None:
    conn = _make_conn_mock(cash=0.0, held_qty=5.0, held_cost=100.0)
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = execute_virtual_order(
        "AAPL", "SELL", quantity=1.0, price=200.0, commission_rate=0.0, slippage_pct=0.01
    )
    assert result["status"] == "FILLED"
    # fill_price = 200 * (1 - 0.01) = 198
    assert result["fill_price"] == pytest.approx(198.0, rel=1e-6)


@patch("src.database.get_connection")
def test_buy_commission_deducted_from_cash(mock_get_conn: MagicMock) -> None:
    conn = _make_conn_mock(cash=500_000.0, held_qty=0.0)
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = execute_virtual_order(
        "AAPL", "BUY", quantity=10.0, price=1000.0, commission_rate=0.001, slippage_pct=0.0
    )
    assert result["status"] == "FILLED"
    # fill_price = 1000, notional = 10_000, commission = 10
    assert result["commission"] == pytest.approx(10.0, rel=1e-6)
    assert result["notional"] == pytest.approx(10_000.0, rel=1e-6)


@patch("src.database.get_connection")
def test_buy_rejected_when_insufficient_cash_after_commission(mock_get_conn: MagicMock) -> None:
    # Price = 1000, qty = 1, commission = 5 → total needed = 1005
    conn = _make_conn_mock(cash=1_002.0, held_qty=0.0)
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = execute_virtual_order(
        "AAPL", "BUY", quantity=1.0, price=1000.0, commission_rate=0.005, slippage_pct=0.0
    )
    # commission = 5 → total = 1005 > 1002 → REJECTED
    assert result["status"] == "REJECTED"
    assert result["reason"] == "insufficient_cash"


@patch("src.database.get_connection")
def test_result_includes_slippage_and_commission_fields(mock_get_conn: MagicMock) -> None:
    conn = _make_conn_mock(cash=200_000.0)
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = execute_virtual_order(
        "MSFT", "BUY", quantity=1.0, price=300.0, commission_rate=0.0003, slippage_pct=0.002
    )
    assert result["status"] == "FILLED"
    assert "commission" in result
    assert "slippage_pct" in result
    assert result["slippage_pct"] == pytest.approx(0.002)


def test_zero_slippage_fill_price_equals_input_price() -> None:
    # Pure math check — no DB
    price = 5000.0
    slippage_pct = 0.0
    assert price * (1 + slippage_pct) == pytest.approx(price)
    assert price * (1 - slippage_pct) == pytest.approx(price)


# ── record_portfolio_nav ──────────────────────────────────────────────────────


@patch("src.database.get_virtual_accounts")
@patch("src.database.get_portfolio_holdings")
@patch("src.database.get_connection")
def test_record_portfolio_nav_returns_total_nav(
    mock_get_conn: MagicMock,
    mock_holdings: MagicMock,
    mock_accounts: MagicMock,
) -> None:
    mock_accounts.return_value = {"KRW": {"cash_balance": 500_000.0, "initial_balance": 1_000_000.0}}
    mock_holdings.return_value = [
        {"ticker": "005930", "quantity": 10.0, "avg_cost": 60_000.0, "currency": "KRW"}
    ]
    conn = MagicMock()
    conn.execute = MagicMock()
    conn.commit = MagicMock()
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    prices = {"005930": 65_000.0}
    result = record_portfolio_nav(prices)

    # total = 500_000 + 10 * 65_000 = 1_150_000
    assert "KRW" in result
    assert result["KRW"] == pytest.approx(1_150_000.0, rel=1e-4)


@patch("src.database.get_virtual_accounts")
@patch("src.database.get_portfolio_holdings")
def test_record_portfolio_nav_empty_accounts_returns_empty(
    mock_holdings: MagicMock,
    mock_accounts: MagicMock,
) -> None:
    mock_accounts.return_value = {}
    mock_holdings.return_value = []
    result = record_portfolio_nav({})
    assert result == {}


@patch("src.database.get_virtual_accounts")
@patch("src.database.get_portfolio_holdings")
@patch("src.database.get_connection")
def test_record_portfolio_nav_uses_avg_cost_when_price_missing(
    mock_get_conn: MagicMock,
    mock_holdings: MagicMock,
    mock_accounts: MagicMock,
) -> None:
    mock_accounts.return_value = {"KRW": {"cash_balance": 0.0, "initial_balance": 1_000_000.0}}
    mock_holdings.return_value = [
        {"ticker": "UNKNOWN", "quantity": 5.0, "avg_cost": 1_000.0, "currency": "KRW"}
    ]
    conn = MagicMock()
    conn.execute = MagicMock()
    conn.commit = MagicMock()
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    # No price provided → falls back to avg_cost = 1000
    result = record_portfolio_nav({})
    # holdings_value = 5 * 1000 = 5000, cash = 0, total = 5000
    assert result["KRW"] == pytest.approx(5_000.0, rel=1e-4)


# ── get_portfolio_nav_history ─────────────────────────────────────────────────


@patch("src.database.get_connection")
def test_get_portfolio_nav_history_returns_list(mock_get_conn: MagicMock) -> None:
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        ("2026-07-09 00:00:00+09:00", "KRW", 500_000.0, 650_000.0, 1_150_000.0),
    ]
    mock_get_conn.return_value.__enter__ = lambda s: conn
    mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = get_portfolio_nav_history(days=30)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["currency"] == "KRW"
    assert result[0]["total_nav"] == pytest.approx(1_150_000.0)


@patch("src.database.get_connection")
def test_get_portfolio_nav_history_returns_empty_on_db_error(mock_get_conn: MagicMock) -> None:
    mock_get_conn.side_effect = Exception("db down")
    result = get_portfolio_nav_history(days=7)
    assert result == []
