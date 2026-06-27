"""Yahoo Finance market data source adapter.

Uses Yahoo Finance's public v8 quote endpoint to fetch market data.
No API key required. Stdlib-only I/O (urllib.request).

Best for: indices, yields, FX, volatility, commodities.
Not suitable for: economic indicators (use FRED or Alpha Vantage).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from src.agent.adapters.sources.yahoo.normalizer import normalize_yf_quote
from src.agent.adapters.sources.yahoo.series_map import YAHOO_FINANCE_SERIES_MAP
from src.core.contracts.macro_data_source import MacroDataSourceContract, SourceMetadata
from src.core.logging.logger import get_logger
from src.domain.macro.enums import MacroIndicatorType
from src.domain.macro.models import MacroFeature

_log = get_logger(__name__)

_YF_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (ALEPH-ONE/1.0)",
    "Accept": "application/json",
}


class YahooFinanceDataSource(MacroDataSourceContract):
    """Macro data source adapter for Yahoo Finance market data.

    No API key required. Uses the public v8 chart endpoint.

    Args:
        timeout_s: HTTP request timeout in seconds.
    """

    def __init__(self, timeout_s: float = 10.0) -> None:
        self._timeout_s = timeout_s

    @property
    def source_id(self) -> str:
        return "yahoo_finance"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="yahoo_finance",
            priority=7,
            supported_indicators=frozenset(
                i.value for i in YAHOO_FINANCE_SERIES_MAP
            ),
        )

    def _fetch_quote(self, ticker: str) -> dict | None:  # type: ignore[type-arg]
        """Fetch a single ticker's latest quote from Yahoo Finance."""
        url = _YF_QUOTE_URL.format(ticker=urllib.parse.quote(ticker))
        params = urllib.parse.urlencode({
            "range": "5d",
            "interval": "1d",
            "includePrePost": "false",
        })
        full_url = f"{url}?{params}"

        req = urllib.request.Request(full_url, headers=_YF_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                if resp.status != 200:
                    _log.warning("yf_http_error", ticker=ticker, status=resp.status)
                    return None
                return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            _log.warning("yf_http_error", ticker=ticker, code=exc.code)
            return None
        except (urllib.error.URLError, TimeoutError) as exc:
            _log.warning("yf_network_error", ticker=ticker, error=str(exc))
            return None

    def _extract_latest(self, data: dict) -> tuple[float, datetime] | None:  # type: ignore[type-arg]
        """Extract the latest close price and timestamp from a v8 chart response."""
        try:
            result = data["chart"]["result"][0]
            meta = result["meta"]

            price = meta.get("regularMarketPrice")
            if price is None:
                closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                valid_closes = [c for c in closes if c is not None]
                if not valid_closes:
                    return None
                price = valid_closes[-1]

            ts_unix = meta.get("regularMarketTime", 0)
            timestamp = datetime.fromtimestamp(ts_unix, tz=UTC) if ts_unix else datetime.now(UTC)

            return float(price), timestamp
        except (KeyError, IndexError, TypeError):
            return None

    async def fetch_raw(
        self,
        country: str,
        indicators: list[str],
    ) -> list[MacroFeature]:
        """Fetch the latest quote for each indicator from Yahoo Finance.

        Args:
            country: ISO 3166-1 alpha-2 country code.
            indicators: List of MacroIndicatorType string values to fetch.

        Returns:
            List of MacroFeature instances for successfully fetched indicators.
        """
        features: list[MacroFeature] = []

        for indicator_str in indicators:
            try:
                indicator = MacroIndicatorType(indicator_str)
            except ValueError:
                continue

            config = YAHOO_FINANCE_SERIES_MAP.get(indicator)
            if config is None:
                continue

            _log.debug("yf_fetch_start", indicator=indicator_str, ticker=config.ticker)

            data = self._fetch_quote(config.ticker)
            if data is None:
                _log.debug("yf_no_response", indicator=indicator_str)
                continue

            latest = self._extract_latest(data)
            if latest is None:
                _log.debug("yf_no_data", indicator=indicator_str)
                continue

            value, timestamp = latest
            feature = normalize_yf_quote(
                ticker=config.ticker,
                value=value,
                country=country,
                timestamp=timestamp,
                indicator=indicator,
                frequency=config.frequency,
            )
            if feature is not None:
                features.append(feature)
                _log.debug(
                    "yf_fetch_ok",
                    indicator=indicator_str,
                    value=feature.value,
                    ticker=config.ticker,
                )

        return features
