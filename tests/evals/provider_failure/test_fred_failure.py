"""Eval: FredMacroDataSource.fetch_raw raising ProviderError propagates through ingestion.

Verifies that when the FRED adapter raises ProviderError (or RuntimeError for
backward compat), the error surfaces from MacroIngestionService with the original
message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from adapters.repositories.in_memory_feature_store import InMemoryFeatureStore
from adapters.sources.fred import FredMacroDataSource
from core.exceptions.base import ProviderError, ProviderHTTPError
from pipelines.ingestion.macro_ingestion_service import MacroIngestionService


@pytest.mark.asyncio
class TestFredFailureEval:
    """FRED RuntimeError/ProviderError surfaces through the full ingestion service."""

    async def test_fred_unavailable_raises_runtime_error(self) -> None:
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        with patch.object(
            src,
            "fetch_raw",
            new=AsyncMock(side_effect=RuntimeError("FRED unavailable")),
        ), pytest.raises(RuntimeError, match="FRED unavailable"):
            await svc.ingest("US")

    async def test_fred_provider_http_error_propagates(self) -> None:
        """ProviderHTTPError (typed) also surfaces from the ingestion service."""
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        exc = ProviderHTTPError(
            "FRED API HTTP error 503",
            provider_id="fred",
            http_status=503,
        )
        with patch.object(src, "fetch_raw", new=AsyncMock(side_effect=exc)), pytest.raises(ProviderError):
                await svc.ingest("US")

    async def test_fred_error_message_preserved(self) -> None:
        """The original RuntimeError message is not swallowed or wrapped."""
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        original_msg = "FRED API HTTP error 503 for series='GDPC1': Service Unavailable."
        with patch.object(
            src,
            "fetch_raw",
            new=AsyncMock(side_effect=RuntimeError(original_msg)),
        ), pytest.raises(RuntimeError, match="503"):
            await svc.ingest("US")

    async def test_snapshot_not_persisted_on_fred_failure(self) -> None:
        """When FRED raises, no snapshot should be saved to the store."""
        src = FredMacroDataSource(api_key="test-key")
        store = InMemoryFeatureStore()
        svc = MacroIngestionService(source=src, repository=store)

        with patch.object(
            src,
            "fetch_raw",
            new=AsyncMock(side_effect=RuntimeError("FRED unavailable")),
        ), pytest.raises(RuntimeError):
            await svc.ingest("US")

        # Nothing should have been persisted
        latest = await store.get_latest_snapshot("US")
        assert latest is None
