"""FRED (Federal Reserve Economic Data) macro data source adapter.

Uses the public FRED REST API to fetch the latest observation for each
requested macro indicator.  All I/O is performed with :mod:`urllib.request`
(stdlib) to avoid adding new dependencies.

Design notes
------------
* ``source_id`` is ``"fred"`` — matches :attr:`~domain.macro.enums.MacroSourceType.FRED`.
* Each fetch call makes one HTTP request per indicator in ``indicators``.
  Indicators not present in :data:`~adapters.sources.fred.series_map.FRED_SERIES_MAP`
  are silently skipped (no feature returned for them).
* Raises :class:`RuntimeError` on HTTP error or network timeout so the
  ingestion service failure path is exercised correctly.
* Raises :class:`RuntimeError` immediately when no API key is configured,
  before any I/O is attempted.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from adapters.sources.fred.normalizer import normalize_fred_observation
from adapters.sources.fred.series_map import FRED_SERIES_MAP
from core.contracts.macro_data_source import MacroDataSourceContract, SourceMetadata
from core.exceptions.base import ProviderHTTPError, ProviderNetworkError, ProviderTimeoutError
from core.logging.logger import get_logger
from core.metrics import PROVIDER_FETCH_DURATION, PROVIDER_FETCH_TOTAL
from domain.macro.enums import MacroIndicatorType
from domain.macro.models import MacroFeature

_log = get_logger(__name__)


class FredMacroDataSource(MacroDataSourceContract):
    """Macro data source adapter that fetches live data from the FRED API.

    Args:
        api_key: FRED API key string.  Must be non-empty.
        base_url: FRED REST API base URL.
            Defaults to ``"https://api.stlouisfed.org/fred"``.
        timeout_s: HTTP request timeout in seconds.  Defaults to ``10.0``.

    Raises:
        RuntimeError: If ``api_key`` is empty or ``None``.

    Example::

        from adapters.sources.fred import FredMacroDataSource

        source = FredMacroDataSource(api_key="your_key_here")
        features = await source.fetch_raw("US", ["gdp", "inflation"])
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.stlouisfed.org/fred",
        timeout_s: float = 10.0,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "FredMacroDataSource requires a non-empty api_key. "
                "Set the FRED_API_KEY environment variable or provide it directly."
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def source_id(self) -> str:
        """Stable identifier for this adapter."""
        return "fred"

    @property
    def metadata(self) -> SourceMetadata:
        """Source metadata for SourceRegistry selection.

        Reports all indicators available in :data:`~adapters.sources.fred.series_map.FRED_SERIES_MAP`.
        The API key is not exposed here.
        """
        return SourceMetadata(
            source_id="fred",
            priority=10,
            supported_indicators=frozenset(i.value for i in FRED_SERIES_MAP),
        )

    async def fetch_raw(
        self,
        country: str,
        indicators: list[str],
    ) -> list[MacroFeature]:
        """Fetch the latest observation for each indicator from FRED.

        For each indicator name in ``indicators``:

        1. Look up the FRED series ID in :data:`~adapters.sources.fred.series_map.FRED_SERIES_MAP`.
           Skip silently if not found.
        2. Call ``/series/observations`` with ``limit=1`` and
           ``sort_order=desc`` to get the most recent observation.
        3. Parse the value and build a :class:`~domain.macro.models.MacroFeature`.

        Args:
            country: ISO 3166-1 alpha-2 country code (e.g. ``"US"``).
            indicators: List of :class:`~domain.macro.enums.MacroIndicatorType`
                string values to fetch.

        Returns:
            List of :class:`~domain.macro.models.MacroFeature` instances —
            one per indicator that is both in the series map and has a valid
            latest observation.

        Raises:
            RuntimeError: On HTTP error (non-200 status) or network timeout.
        """
        features: list[MacroFeature] = []

        for indicator_name in indicators:
            try:
                indicator = MacroIndicatorType(indicator_name)
            except ValueError:
                continue  # unknown indicator type — skip

            series_id = FRED_SERIES_MAP.get(indicator)
            if series_id is None:
                continue  # not in the supported series map — skip

            _log.debug("fred_fetch_started", series_id=series_id, country=country)
            import time as _time
            _start = _time.perf_counter_ns()
            try:
                with PROVIDER_FETCH_DURATION.labels(provider="fred").time():
                    raw_value_str, obs_date = self._fetch_latest_observation(series_id)
            except Exception:
                PROVIDER_FETCH_TOTAL.labels(provider="fred", result="failure").inc()
                raise
            _latency_ms = (_time.perf_counter_ns() - _start) / 1_000_000.0
            if raw_value_str is None:
                _log.debug(
                    "fred_fetch_complete",
                    series_id=series_id,
                    country=country,
                    latency_ms=round(_latency_ms, 3),
                    result="no_observations",
                )
                PROVIDER_FETCH_TOTAL.labels(provider="fred", result="success").inc()
                continue  # FRED returned no observations

            feature = normalize_fred_observation(
                series_id=series_id,
                raw_value_str=raw_value_str,
                country=country,
                timestamp=obs_date,
                indicator=indicator,
            )
            if feature is not None:
                _log.debug(
                    "fred_fetch_complete",
                    series_id=series_id,
                    country=country,
                    latency_ms=round(_latency_ms, 3),
                    result="ok",
                )
                PROVIDER_FETCH_TOTAL.labels(provider="fred", result="success").inc()
                features.append(feature)

        return features

    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    def _fetch_latest_observation(
        self, series_id: str
    ) -> tuple[str | None, datetime]:
        """Fetch the single most recent observation from the FRED API.

        Args:
            series_id: FRED series identifier (e.g. ``"GDPC1"``).

        Returns:
            A ``(value_str, observation_date)`` tuple where ``value_str`` is
            the raw string value returned by FRED (may be ``"."`` for missing
            data) and ``observation_date`` is the UTC observation timestamp.
            Returns ``(None, <now>)`` when the observations list is empty.

        Raises:
            RuntimeError: On HTTP error or timeout.
        """
        params = urllib.parse.urlencode(
            {
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "limit": 1,
                "sort_order": "desc",
            }
        )
        url = f"{self._base_url}/series/observations?{params}"

        try:
            with urllib.request.urlopen(url, timeout=self._timeout_s) as resp:  # noqa: S310
                if resp.status != 200:
                    raise RuntimeError(
                        f"FRED API returned HTTP {resp.status} for series={series_id!r}. "
                        f"Check your API key and series ID."
                    )
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            _log.warning(
                "fred_fetch_failed",
                series_id=series_id,
                error="http_error",
                http_status=exc.code,
            )
            raise ProviderHTTPError(
                f"FRED API HTTP error {exc.code} for series={series_id!r}: {exc.reason}. "
                f"Verify your FRED_API_KEY and network access.",
                provider_id="fred",
                http_status=exc.code,
            ) from exc
        except TimeoutError as exc:
            _log.warning(
                "fred_fetch_failed",
                series_id=series_id,
                error="timeout",
                timeout_s=self._timeout_s,
            )
            raise ProviderTimeoutError(
                f"FRED API request timed out after {self._timeout_s}s for series={series_id!r}. "
                f"Check your network connection or increase fred_request_timeout_s.",
                provider_id="fred",
                timeout_s=self._timeout_s,
            ) from exc
        except OSError as exc:
            _log.warning(
                "fred_fetch_failed",
                series_id=series_id,
                error="network_error",
            )
            raise ProviderNetworkError(
                f"FRED API network error for series={series_id!r}: {exc}. "
                f"Check your network connection.",
                provider_id="fred",
            ) from exc

        observations = payload.get("observations", [])
        if not observations:
            return None, datetime.now(UTC)

        obs = observations[0]
        obs_date_str: str = obs.get("date", "")
        try:
            obs_date = datetime.strptime(obs_date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            obs_date = datetime.now(UTC)

        return obs.get("value"), obs_date
