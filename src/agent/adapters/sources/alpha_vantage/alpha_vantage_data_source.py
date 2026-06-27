"""Alpha Vantage macro data source adapter.

Uses the Alpha Vantage free API to fetch economic indicator data.
Stdlib-only I/O (urllib.request) to avoid new dependencies.

Free tier limits: 25 requests/day, 5 requests/minute.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from src.agent.adapters.sources.alpha_vantage.normalizer import normalize_av_observation
from src.agent.adapters.sources.alpha_vantage.series_map import (
    ALPHA_VANTAGE_SERIES_MAP,
    AVSeriesConfig,
)
from src.core.contracts.macro_data_source import MacroDataSourceContract, SourceMetadata
from src.core.logging.logger import get_logger
from src.domain.macro.enums import DataFrequency, MacroIndicatorType
from src.domain.macro.models import MacroFeature

_log = get_logger(__name__)

# Alpha Vantage free tier: max 5 requests/minute
_REQUEST_INTERVAL_S = 12.5


class AlphaVantageDataSource(MacroDataSourceContract):
    """Macro data source adapter for Alpha Vantage economic indicators.

    Args:
        api_key: Alpha Vantage API key. Must be non-empty.
            Get one free at https://www.alphavantage.co/support/#api-key
        base_url: API base URL.
        timeout_s: HTTP request timeout in seconds.

    Raises:
        RuntimeError: If api_key is empty or None.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://www.alphavantage.co/query",
        timeout_s: float = 15.0,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "AlphaVantageDataSource requires a non-empty api_key. "
                "Set the ALPHA_VANTAGE_API_KEY environment variable or "
                "get a free key at https://www.alphavantage.co/support/#api-key"
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._last_request_time: float = 0.0

    @property
    def source_id(self) -> str:
        return "alpha_vantage"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="alpha_vantage",
            priority=8,
            supported_indicators=frozenset(
                i.value for i in ALPHA_VANTAGE_SERIES_MAP
            ),
        )

    def _rate_limit_wait(self) -> None:
        """Respect Alpha Vantage free tier rate limits."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _REQUEST_INTERVAL_S:
            time.sleep(_REQUEST_INTERVAL_S - elapsed)
        self._last_request_time = time.monotonic()

    def _build_url(self, config: AVSeriesConfig) -> str:
        """Build the API URL for a given series config."""
        params: dict[str, str] = {
            "function": config.function,
            "apikey": self._api_key,
            "datatype": "json",
        }
        if config.symbol:
            params["symbol"] = config.symbol
        if config.interval:
            params["interval"] = config.interval
        if config.maturity:
            params["maturity"] = config.maturity

        return f"{self._base_url}?{urllib.parse.urlencode(params)}"

    def _fetch_observation(self, url: str) -> dict:  # type: ignore[type-arg]
        """Make a single HTTP request and return parsed JSON."""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ALEPH-ONE/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        f"Alpha Vantage API HTTP error {resp.status}"
                    )
                return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Alpha Vantage API HTTP error {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            if "timed out" in str(exc.reason).lower():
                raise RuntimeError(
                    f"Alpha Vantage API request timed out after {self._timeout_s}s"
                ) from exc
            raise RuntimeError(
                f"Alpha Vantage API network error: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"Alpha Vantage API request timed out after {self._timeout_s}s"
            ) from exc

    def _extract_latest(self, data: dict) -> tuple[str, str] | None:  # type: ignore[type-arg]
        """Extract the latest (date, value) from an AV economic response.

        AV economic endpoints return a "data" array sorted newest-first.
        Returns None if no valid data point is found.
        """
        if "Error Message" in data:
            _log.warning("av_api_error", error=data["Error Message"])
            return None
        if "Note" in data or "Information" in data:
            _log.warning(
                "av_rate_limit",
                note=data.get("Note", data.get("Information", "")),
            )
            return None

        observations = data.get("data", [])
        if not observations:
            return None

        for obs in observations:
            date_str = obs.get("date", "")
            value_str = obs.get("value", "")
            if date_str and value_str and value_str.strip() != ".":
                return date_str, value_str

        return None

    async def fetch_raw(
        self,
        country: str,
        indicators: list[str],
    ) -> list[MacroFeature]:
        """Fetch the latest observation for each indicator from Alpha Vantage.

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
                _log.debug("av_unknown_indicator", indicator=indicator_str)
                continue

            config = ALPHA_VANTAGE_SERIES_MAP.get(indicator)
            if config is None:
                _log.debug("av_indicator_not_mapped", indicator=indicator_str)
                continue

            self._rate_limit_wait()

            url = self._build_url(config)
            _log.debug("av_fetch_start", indicator=indicator_str, function=config.function)

            try:
                data = self._fetch_observation(url)
            except RuntimeError:
                _log.warning("av_fetch_failed", indicator=indicator_str)
                continue

            latest = self._extract_latest(data)
            if latest is None:
                _log.debug("av_no_data", indicator=indicator_str)
                continue

            date_str, value_str = latest
            try:
                timestamp = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                _log.warning("av_bad_date", date=date_str, indicator=indicator_str)
                continue

            freq = DataFrequency.MONTHLY
            if config.interval == "quarterly":
                freq = DataFrequency.QUARTERLY
            elif config.interval == "daily":
                freq = DataFrequency.DAILY

            feature = normalize_av_observation(
                function_name=config.function,
                raw_value_str=value_str,
                country=country,
                timestamp=timestamp,
                indicator=indicator,
                frequency=freq,
            )
            if feature is not None:
                features.append(feature)
                _log.debug(
                    "av_fetch_ok",
                    indicator=indicator_str,
                    value=feature.value,
                    date=date_str,
                )

        return features
