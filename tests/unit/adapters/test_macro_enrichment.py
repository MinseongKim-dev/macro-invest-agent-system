"""Unit tests for Level 2-2 macro enrichment helpers in src/database.py.

All tests mock HTTP calls — no live API requests are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ── BLS helpers ───────────────────────────────────────────────────────────────


def _bls_response(series_data: list[dict]) -> MagicMock:  # type: ignore[type-arg]
    resp = MagicMock()
    resp.raise_for_status.return_value = resp
    resp.json.return_value = {
        "Results": {
            "series": series_data,
        }
    }
    return resp


def test_fetch_bls_macro_returns_empty_on_http_error() -> None:
    from src.database import _fetch_bls_macro

    with patch("src.database.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.side_effect = Exception("timeout")
        result = _fetch_bls_macro()

    assert result == {}


def test_fetch_bls_macro_happy_path() -> None:
    from src.database import _fetch_bls_macro

    payload = _bls_response([
        {"seriesID": "CUUR0000SA0", "data": [{"value": "315.2", "year": "2024", "period": "M05"}]},
        {"seriesID": "LNS14000000", "data": [{"value": "3.9",   "year": "2024", "period": "M05"}]},
    ])

    with patch("src.database.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = payload
        result = _fetch_bls_macro()

    assert result["US_CPI_BLS"] == pytest.approx(315.2, abs=0.01)
    assert result["US_UNRATE_BLS"] == pytest.approx(3.9, abs=0.01)


def test_fetch_bls_macro_skips_malformed_value() -> None:
    from src.database import _fetch_bls_macro

    payload = _bls_response([
        {"seriesID": "CUUR0000SA0", "data": [{"value": "N/A"}]},
    ])

    with patch("src.database.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = payload
        result = _fetch_bls_macro()

    assert "US_CPI_BLS" not in result


# ── ECB helpers ───────────────────────────────────────────────────────────────


def _ecb_csv_response(value: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = resp
    resp.text = (
        "KEY,FREQ,REF_AREA,ADJUSTMENT,ICP_ITEM,STS_INSTITUTION,ICP_SUFFIX,"
        "TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
        f"ICP.M.U2.N.000000.4.ANR,M,U2,N,000000,4,ANR,2024-05,{value},A\n"
    )
    return resp


def test_fetch_ecb_macro_happy_path() -> None:
    from src.database import _fetch_ecb_macro

    with patch("src.database.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = _ecb_csv_response("2.6")
        result = _fetch_ecb_macro()

    assert result["EU_HICP"] == pytest.approx(2.6, abs=0.01)


def test_fetch_ecb_macro_returns_empty_on_http_error() -> None:
    from src.database import _fetch_ecb_macro

    with patch("src.database.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = Exception("connection refused")
        result = _fetch_ecb_macro()

    assert result == {}


def test_fetch_ecb_macro_returns_empty_on_empty_csv() -> None:
    from src.database import _fetch_ecb_macro

    resp = MagicMock()
    resp.raise_for_status.return_value = resp
    resp.text = ""

    with patch("src.database.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = resp
        result = _fetch_ecb_macro()

    assert result == {}


# ── BOK helpers ───────────────────────────────────────────────────────────────


def test_fetch_bok_macro_returns_empty_without_key() -> None:
    from src.database import _fetch_bok_macro

    with patch("src.database.BOK_API_KEY", ""):
        result = _fetch_bok_macro()

    assert result == {}


def test_fetch_bok_macro_happy_path() -> None:
    from src.database import _fetch_bok_macro

    # Two separate GET calls: first for base rate, second for CPI
    base_rate_resp = MagicMock()
    base_rate_resp.raise_for_status.return_value = base_rate_resp
    base_rate_resp.json.return_value = {
        "StatisticSearch": {"row": [{"DATA_VALUE": "3.50"}]}
    }
    cpi_resp = MagicMock()
    cpi_resp.raise_for_status.return_value = cpi_resp
    cpi_resp.json.return_value = {
        "StatisticSearch": {"row": [{"DATA_VALUE": "112.43"}]}
    }

    with (
        patch("src.database.BOK_API_KEY", "test_key"),
        patch("src.database.httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get.side_effect = [
            base_rate_resp, cpi_resp,
        ]
        result = _fetch_bok_macro()

    assert result["KR_BASE_RATE"] == pytest.approx(3.50, abs=0.01)
    assert result["KR_CPI"] == pytest.approx(112.43, abs=0.01)


def test_fetch_bok_macro_partial_failure() -> None:
    """When one BOK series fails, others still succeed."""
    from src.database import _fetch_bok_macro

    success_resp = MagicMock()
    success_resp.raise_for_status.return_value = success_resp
    success_resp.json.return_value = {
        "StatisticSearch": {"row": [{"DATA_VALUE": "3.50"}]}
    }

    with (
        patch("src.database.BOK_API_KEY", "test_key"),
        patch("src.database.httpx.Client") as mock_client,
    ):
        mock_client.return_value.__enter__.return_value.get.side_effect = [
            success_resp,
            Exception("CPI endpoint unavailable"),
        ]
        result = _fetch_bok_macro()

    assert result.get("KR_BASE_RATE") == pytest.approx(3.50, abs=0.01)
    assert "KR_CPI" not in result
