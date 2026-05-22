"""Macro ingestion service.

Orchestrates the full ingestion cycle:

1. Fetch raw macro features from a :class:`~core.contracts.macro_data_source.MacroDataSourceContract`.
2. Compute deterministic derived fields (``features_count``, ``ingested_at``).
3. Wrap the features in a :class:`~pipelines.ingestion.models.FeatureSnapshot`.
4. Persist the snapshot via a :class:`~core.contracts.feature_store_repository.FeatureStoreRepositoryContract`.
5. Return the persisted snapshot to the caller.

Design principles
-----------------
* **No side effects beyond the repository**: the service fetches from the
  source and writes to the repository only.
* **Deterministic features**: given the same source data, the output snapshot
  is always structurally identical (same field values).
* **Error-safe**: ``RuntimeError`` is raised (not swallowed) when the source
  returns no features, so callers can handle empty-data scenarios explicitly.
* **No direct pipeline dependencies**: this service does not import from the
  ``agent`` or ``mcp`` layers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.contracts.feature_store_repository import FeatureStoreRepositoryContract
from core.contracts.macro_data_source import MacroDataSourceContract
from core.exceptions.base import ProviderError
from core.logging.logger import get_logger
from core.metrics import INGESTION_OBSERVATIONS_TOTAL, PIPELINE_RUN_DURATION, PIPELINE_RUNS_TOTAL
from core.tracing import get_tracer
from core.tracing.span_attributes import (
    COUNTRY,
    FEATURES_COUNT,
    INDICATOR_COUNT,
    PIPELINE_RUN_ID,
    SOURCE_ID,
)
from pipelines.ingestion.indicator_catalog import PRIORITY_INDICATORS
from pipelines.ingestion.models import (
    FeatureSnapshot,
    IngestionRunRecord,
    RawFeatureRecord,
    build_normalized_observation,
)

_log = get_logger(__name__)
_tracer = get_tracer(__name__)

# Default set of indicators fetched when the caller does not specify any.
DEFAULT_INDICATORS: list[str] = [i.value for i in PRIORITY_INDICATORS]


class MacroIngestionService:
    """Orchestrates macro feature ingestion and persistence.

    Fetches raw macro features from a configured data source, wraps them in a
    :class:`~pipelines.ingestion.models.FeatureSnapshot`, and persists them via
    the feature-store repository.

    Args:
        source: A :class:`~core.contracts.macro_data_source.MacroDataSourceContract`
            implementation (e.g. :class:`~adapters.sources.fixture_macro_data_source.FixtureMacroDataSource`).
        repository: A :class:`~core.contracts.feature_store_repository.FeatureStoreRepositoryContract`
            implementation (e.g. :class:`~adapters.repositories.in_memory_feature_store.InMemoryFeatureStore`).

    Example::

        from adapters.sources.fixture_macro_data_source import FixtureMacroDataSource
        from adapters.repositories.in_memory_feature_store import InMemoryFeatureStore
        from pipelines.ingestion.macro_ingestion_service import MacroIngestionService

        service = MacroIngestionService(
            source=FixtureMacroDataSource(),
            repository=InMemoryFeatureStore(),
        )
        snapshot = await service.ingest(country="US")
    """

    def __init__(
        self,
        source: MacroDataSourceContract,
        repository: FeatureStoreRepositoryContract,
    ) -> None:
        self._source = source
        self._repository = repository

    async def ingest(
        self,
        country: str,
        indicators: list[str] | None = None,
    ) -> FeatureSnapshot:
        """Fetch, snapshot, and persist macro features for a country.

        Args:
            country: ISO 3166-1 alpha-2 country code (e.g. ``"US"``).
            indicators: Indicator names to fetch.  Defaults to
                :data:`DEFAULT_INDICATORS` when ``None``.

        Returns:
            The persisted :class:`~pipelines.ingestion.models.FeatureSnapshot`.

        Raises:
            RuntimeError: If the data source returns no features for the
                requested indicators.
        """
        effective_indicators = indicators if indicators is not None else DEFAULT_INDICATORS
        source_id = self._source.source_id
        _log.info(
            "ingestion_started",
            country=country,
            source=source_id,
            indicator_count=len(effective_indicators),
        )

        run_started_at = datetime.now(UTC)
        with _tracer.start_as_current_span("pipeline.ingest") as span:
            span.set_attribute(COUNTRY, country)
            span.set_attribute(SOURCE_ID, source_id)
            span.set_attribute(INDICATOR_COUNT, len(effective_indicators))

            with PIPELINE_RUN_DURATION.labels(source=source_id).time():
                try:
                    raw_features = await self._source.fetch_raw(
                        country=country, indicators=effective_indicators
                    )
                except ProviderError as exc:
                    _log.warning(
                        "ingestion_provider_error",
                        country=country,
                        source=source_id,
                        failure_category=exc.error_code,
                        error=str(exc),
                    )
                    PIPELINE_RUNS_TOTAL.labels(source=source_id, result="failure").inc()
                    raise

                if not raw_features:
                    PIPELINE_RUNS_TOTAL.labels(source=source_id, result="failure").inc()
                    raise RuntimeError(
                        f"No macro features returned for country={country!r} "
                        f"from source={source_id!r}. "
                        f"Requested indicators: {effective_indicators}"
                    )

                snapshot = FeatureSnapshot(
                    country=country,
                    source_id=source_id,
                    features=raw_features,
                )

                raw_records = [
                    RawFeatureRecord(
                        snapshot_id=snapshot.snapshot_id,
                        indicator_type=f.indicator_type,
                        source_id=source_id,
                        raw_payload={k: str(v) for k, v in f.metadata.items()},
                    )
                    for f in raw_features
                ]
                normalized_records = [
                    build_normalized_observation(snapshot_id=snapshot.snapshot_id, feature=f)
                    for f in raw_features
                ]

                INGESTION_OBSERVATIONS_TOTAL.labels(source=source_id, layer="raw").inc(
                    len(raw_records)
                )
                INGESTION_OBSERVATIONS_TOTAL.labels(source=source_id, layer="normalized").inc(
                    len(normalized_records)
                )

                await self._repository.save_snapshot(snapshot)
                if hasattr(self._repository, "save_raw_records"):
                    await self._repository.save_raw_records(snapshot.snapshot_id, raw_records)
                if hasattr(self._repository, "save_normalized_records"):
                    await self._repository.save_normalized_records(
                        snapshot.snapshot_id, normalized_records
                    )
                if hasattr(self._repository, "save_ingestion_run"):
                    run_record = IngestionRunRecord(
                        snapshot_id=snapshot.snapshot_id,
                        source_id=source_id,
                        country=country,
                        started_at=run_started_at,
                        finished_at=datetime.now(UTC),
                        requested_indicators=effective_indicators,
                        fetched_count=len(raw_features),
                        normalized_count=len(normalized_records),
                        failed_count=0,
                        success=True,
                    )
                    await self._repository.save_ingestion_run(run_record)

            span.set_attribute(PIPELINE_RUN_ID, snapshot.snapshot_id)
            span.set_attribute(FEATURES_COUNT, snapshot.features_count)

        PIPELINE_RUNS_TOTAL.labels(source=source_id, result="success").inc()
        _log.info(
            "ingestion_complete",
            country=country,
            features_count=snapshot.features_count,
            snapshot_id=snapshot.snapshot_id,
        )

        return snapshot
