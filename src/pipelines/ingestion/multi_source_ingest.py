"""Multi-source ingestion orchestrator.

Coordinates data collection from all available sources (FRED, Alpha Vantage,
Yahoo Finance) into a single unified snapshot.  Handles partial failures
gracefully: if one source fails, data from other sources is still persisted.

Usage:
    python -m src.pipelines.ingestion.multi_source_ingest

Or import and call programmatically:
    from src.pipelines.ingestion.multi_source_ingest import run_multi_source_ingest
    summary = await run_multi_source_ingest()
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from src.core.logging.logger import get_logger
from src.domain.macro.enums import MacroIndicatorType
from src.domain.macro.models import MacroFeature

_log = get_logger(__name__)

# Indicator assignments per source.
# Each indicator is assigned to exactly one primary source to avoid conflicts.

FRED_INDICATORS: list[str] = [
    MacroIndicatorType.INFLATION.value,
    MacroIndicatorType.UNEMPLOYMENT.value,
    MacroIndicatorType.PMI.value,
    MacroIndicatorType.RETAIL_SALES.value,
]

ALPHA_VANTAGE_INDICATORS: list[str] = [
    MacroIndicatorType.GDP.value,
    MacroIndicatorType.INTEREST_RATE.value,
]

YAHOO_INDICATORS: list[str] = [
    MacroIndicatorType.YIELD_10Y.value,
    MacroIndicatorType.STOCK_INDEX.value,
    MacroIndicatorType.VOLATILITY_PROXY.value,
    MacroIndicatorType.DOLLAR_STRENGTH.value,
    MacroIndicatorType.EXCHANGE_RATE.value,
    MacroIndicatorType.COMMODITY_PRICE.value,
]


async def _fetch_from_source(
    source_name: str,
    source: object,
    country: str,
    indicators: list[str],
) -> list[MacroFeature]:
    """Fetch from a single source with error isolation."""
    try:
        _log.info(
            "source_fetch_start",
            source=source_name,
            indicator_count=len(indicators),
        )
        features = await source.fetch_raw(country, indicators)  # type: ignore[union-attr]
        _log.info(
            "source_fetch_complete",
            source=source_name,
            features_returned=len(features),
            indicators_requested=len(indicators),
        )
        return features  # type: ignore[return-value]
    except Exception as exc:
        _log.error("source_fetch_failed", source=source_name, error=str(exc))
        return []


async def run_multi_source_ingest(country: str = "US") -> dict:  # type: ignore[type-arg]
    """Run ingestion from all configured sources.

    Returns a summary dict with counts and status per source.
    Sources without API keys are skipped gracefully.
    """
    all_features: list[MacroFeature] = []
    source_status: dict[str, dict] = {}  # type: ignore[type-arg]

    # --- FRED ---
    fred_api_key = os.environ.get("FRED_API_KEY", "")
    if fred_api_key:
        from src.agent.adapters.sources.fred import FredMacroDataSource

        fred = FredMacroDataSource(api_key=fred_api_key)
        features = await _fetch_from_source("fred", fred, country, FRED_INDICATORS)
        all_features.extend(features)
        source_status["fred"] = {
            "requested": len(FRED_INDICATORS),
            "received": len(features),
            "status": "ok" if features else "empty",
        }
    else:
        _log.warning("fred_skipped", reason="FRED_API_KEY not set")
        source_status["fred"] = {"status": "skipped", "reason": "no_api_key"}

    # --- Alpha Vantage ---
    av_api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if av_api_key:
        from src.agent.adapters.sources.alpha_vantage import AlphaVantageDataSource

        av = AlphaVantageDataSource(api_key=av_api_key)
        features = await _fetch_from_source(
            "alpha_vantage", av, country, ALPHA_VANTAGE_INDICATORS
        )
        all_features.extend(features)
        source_status["alpha_vantage"] = {
            "requested": len(ALPHA_VANTAGE_INDICATORS),
            "received": len(features),
            "status": "ok" if features else "empty",
        }
    else:
        _log.warning("av_skipped", reason="ALPHA_VANTAGE_API_KEY not set")
        source_status["alpha_vantage"] = {"status": "skipped", "reason": "no_api_key"}

    # --- Yahoo Finance (no API key needed) ---
    from src.agent.adapters.sources.yahoo import YahooFinanceDataSource

    yahoo = YahooFinanceDataSource()
    features = await _fetch_from_source(
        "yahoo_finance", yahoo, country, YAHOO_INDICATORS
    )
    all_features.extend(features)
    source_status["yahoo_finance"] = {
        "requested": len(YAHOO_INDICATORS),
        "received": len(features),
        "status": "ok" if features else "empty",
    }

    summary = {
        "country": country,
        "timestamp": datetime.now(UTC).isoformat(),
        "total_features": len(all_features),
        "sources": source_status,
        "indicators": [f.indicator_type.value for f in all_features],
    }

    _log.info(
        "multi_source_ingest_complete",
        total_features=len(all_features),
        sources_ok=sum(1 for s in source_status.values() if s.get("status") == "ok"),
        sources_skipped=sum(
            1 for s in source_status.values() if s.get("status") == "skipped"
        ),
    )

    return summary


if __name__ == "__main__":
    import json

    result = asyncio.run(run_multi_source_ingest())
    print(json.dumps(result, indent=2))
