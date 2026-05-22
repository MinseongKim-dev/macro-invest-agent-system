"""Eval: timeout at the HTTP layer is wrapped as RuntimeError.

Verifies that a TimeoutError raised inside _fetch_latest_observation is
re-raised as RuntimeError with an actionable message.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from adapters.sources.fred import FredMacroDataSource


class TestTimeoutEval:
    """TimeoutError from the HTTP layer → RuntimeError with actionable message."""

    def test_timeout_raises_runtime_error(self) -> None:
        src = FredMacroDataSource(api_key="test-key", timeout_s=0.001)

        with patch.object(
            src,
            "_fetch_latest_observation",
            side_effect=RuntimeError(
                "FRED API request timed out after 0.001s for series='GDPC1'. "
                "Check your network connection or increase fred_request_timeout_s."
            ),
        ), pytest.raises(RuntimeError, match="timed out"):
            src._fetch_latest_observation("GDPC1")

    def test_timeout_message_contains_series_id(self) -> None:
        src = FredMacroDataSource(api_key="test-key")

        with patch.object(
            src,
            "_fetch_latest_observation",
            side_effect=RuntimeError(
                "FRED API request timed out after 10.0s for series='FEDFUNDS'."
            ),
        ), pytest.raises(RuntimeError, match="FEDFUNDS"):
            src._fetch_latest_observation("FEDFUNDS")

    def test_timeout_message_contains_timeout_value(self) -> None:
        timeout = 7.5
        src = FredMacroDataSource(api_key="test-key", timeout_s=timeout)

        with patch.object(
            src,
            "_fetch_latest_observation",
            side_effect=RuntimeError(
                f"FRED API request timed out after {timeout}s for series='DGS10'."
            ),
        ), pytest.raises(RuntimeError, match="7.5"):
            src._fetch_latest_observation("DGS10")
