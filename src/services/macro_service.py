"""Macroeconomic data service implementation.

Provides :class:`MacroService`, which wraps an optional
:class:`~core.contracts.macro_data_source.MacroDataSourceContract` to delegate
data fetching to a real or stub adapter.  When no source is provided, synthetic
placeholder data is returned so that the service layer is always operational.
"""

from datetime import UTC, datetime

from core.contracts.macro_data_source import MacroDataSourceContract
from core.logging.logger import get_logger
from core.tracing import get_tracer
from core.tracing.span_attributes import COUNTRY, FEATURES_COUNT, INDICATOR_COUNT, SOURCE_ID
from domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from domain.macro.models import MacroFeature, MacroSnapshot
from services.interfaces import MacroServiceInterface

_log = get_logger(__name__)
_tracer = get_tracer(__name__)


class MacroService(MacroServiceInterface):
    """Implementation of the macro data service.

    When a :class:`~core.contracts.macro_data_source.MacroDataSourceContract`
    is injected at construction time, :meth:`fetch_features` and
    :meth:`get_snapshot` delegate to it.  When no source is provided, synthetic
    placeholder data is returned (backward-compatible default).

    Args:
        source: Optional data source adapter.  When ``None`` (the default),
            the service falls back to synthetic data.
    """

    def __init__(self, source: MacroDataSourceContract | None = None) -> None:
        self._source = source

    async def fetch_features(
        self, indicator_types: list[str], country: str = "US"
    ) -> list[MacroFeature]:
        """Fetch macro features for given indicators.

        When a source is configured, delegates to
        :meth:`~core.contracts.macro_data_source.MacroDataSourceContract.fetch_raw`.
        Otherwise returns synthetic placeholder data.

        Args:
            indicator_types: List of indicator types to fetch
            country: Country code (default: "US")

        Returns:
            List of MacroFeature objects

        Raises:
            ValueError: If indicator_types is empty
            ProviderTimeoutError: If the upstream source times out.
            ProviderHTTPError: If the upstream source returns a non-2xx status.
            ProviderNetworkError: On network I/O failure.
        """
        if not indicator_types:
            raise ValueError("At least one indicator type must be specified")

        _log.debug(
            "service_fetch_started",
            operation="fetch_features",
            country=country,
            indicator_count=len(indicator_types),
            source=self._source.source_id if self._source else "synthetic",
        )

        with _tracer.start_as_current_span("service.fetch_features") as span:
            span.set_attribute(COUNTRY, country)
            span.set_attribute(INDICATOR_COUNT, len(indicator_types))
            span.set_attribute(SOURCE_ID, self._source.source_id if self._source else "synthetic")

            if self._source is not None:
                _log.debug("source_selected", source=self._source.source_id, country=country)
                features = await self._source.fetch_raw(country=country, indicators=indicator_types)
                span.set_attribute(FEATURES_COUNT, len(features))
                _log.debug(
                    "service_fetch_complete",
                    operation="fetch_features",
                    country=country,
                    features_returned=len(features),
                )
                return features

            # Synthetic fallback (no source configured)
            features_list: list[MacroFeature] = []
            for indicator_name in indicator_types:
                try:
                    indicator = MacroIndicatorType(indicator_name)
                    feature = MacroFeature(
                        indicator_type=indicator,
                        source=MacroSourceType.MARKET_DATA,
                        value=50.0,  # Placeholder value
                        timestamp=datetime.now(UTC),
                        frequency=DataFrequency.MONTHLY,
                        country=country,
                        metadata={"status": "placeholder"},
                    )
                    features_list.append(feature)
                except ValueError:
                    # Invalid indicator type, skip
                    continue

            span.set_attribute(FEATURES_COUNT, len(features_list))
            _log.debug(
                "service_fetch_complete",
                operation="fetch_features",
                country=country,
                features_returned=len(features_list),
            )
            return features_list

    async def get_snapshot(self, country: str = "US") -> MacroSnapshot:
        """Get a complete macro snapshot at current time.

        When a source is configured, fetches all indicators via
        :meth:`fetch_features`.  Otherwise returns a synthetic snapshot.

        Args:
            country: Country code (default: "US")

        Returns:
            MacroSnapshot containing all available features

        Raises:
            RuntimeError: If snapshot cannot be created
        """
        _log.debug("service_fetch_started", operation="get_snapshot", country=country)

        with _tracer.start_as_current_span("service.get_snapshot") as span:
            span.set_attribute(COUNTRY, country)
            span.set_attribute(SOURCE_ID, self._source.source_id if self._source else "synthetic")

            if self._source is not None:
                # Fetch all indicators the source supports
                source_meta = self._source.metadata
                if source_meta and source_meta.supported_indicators:
                    all_indicators = list(source_meta.supported_indicators)
                else:
                    # Source has no metadata or empty indicator set — use common defaults
                    all_indicators = [
                        MacroIndicatorType.GDP.value,
                        MacroIndicatorType.INFLATION.value,
                        MacroIndicatorType.UNEMPLOYMENT.value,
                    ]
                try:
                    features = await self.fetch_features(all_indicators, country)
                except ValueError as exc:
                    raise RuntimeError(f"Could not fetch macro data for {country}") from exc
            else:
                # Synthetic fallback — fetch common indicators
                common_indicators = [
                    MacroIndicatorType.GDP.value,
                    MacroIndicatorType.INFLATION.value,
                    MacroIndicatorType.UNEMPLOYMENT.value,
                ]
                features = await self.fetch_features(common_indicators, country)

            if not features:
                raise RuntimeError(f"Could not fetch macro data for {country}")

            span.set_attribute(FEATURES_COUNT, len(features))
            _log.debug(
                "service_fetch_complete",
                operation="get_snapshot",
                country=country,
                features_count=len(features),
            )
            return MacroSnapshot(
                features=features,
                snapshot_time=datetime.now(UTC),
                version=1,
            )
