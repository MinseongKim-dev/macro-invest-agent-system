"""Startup seeder for the analyst-facing product API.

Seeds the shared in-memory stores with a synthetic macro snapshot and a
derived regime so that :func:`GET /api/regimes/latest` returns real data
immediately after startup instead of HTTP 404.

Idempotency
-----------
The seeder checks whether the regime store is already populated before
writing.  If at least one regime is already present the seeder does nothing.
This prevents duplicate bootstrap data from accumulating on repeated
lifespan restarts (e.g. during tests that share a global singleton).

Bootstrap identification
------------------------
All regimes created by this seeder carry the following metadata so that
downstream consumers can distinguish synthetic bootstrap data from
production data::

    metadata = {
        "seeded":       "true",
        "source":       "synthetic_seed",
        "seed_version": "1",
    }

The ``RegimeLatestResponse`` DTO surfaces ``is_seeded`` and ``data_source``
fields derived from this metadata so frontend consumers can render a
"bootstrap data" badge.

Failure handling
----------------
The seeder is designed to never crash the application.  If any step fails
the function returns a :class:`SeedStatus` with ``success=False`` and a
descriptive ``error`` message.  The caller is responsible for logging and
for optionally exposing a degraded readiness state.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from src.core.logging.logger import get_logger
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.pipelines.ingestion.models import (
    FreshnessMetadata,
    FreshnessStatus,
    NormalizedMacroObservation,
    RevisionStatus,
)
from src.services.macro_regime_service import MacroRegimeService
from src.services.macro_snapshot_service import MacroSnapshotService

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# DB series_id → MacroIndicatorType mapping
# PMI and RETAIL_SALES have no real source — kept synthetic.
# ---------------------------------------------------------------------------

_SERIES_TO_INDICATOR: dict[str, MacroIndicatorType] = {
    "CPI":    MacroIndicatorType.INFLATION,
    "UNRATE": MacroIndicatorType.UNEMPLOYMENT,
    "T10Y":   MacroIndicatorType.YIELD_10Y,
}

# ---------------------------------------------------------------------------
# Metadata stamped on every regime produced by this seeder
# ---------------------------------------------------------------------------

SEEDER_METADATA: dict[str, str] = {
    "seeded": "true",
    "source": "synthetic_seed",
    "seed_version": "1",
}

# _SYNTHETIC_VALUES removed (D-01a): all indicator values must come from
# TimescaleDB macro_indicators. If a series is absent, pass None — the
# domain layer returns GrowthState.UNKNOWN rather than a synthetic state.


# ---------------------------------------------------------------------------
# Real-data fetch (best-effort)
# ---------------------------------------------------------------------------


def _fetch_real_values_sync() -> dict[MacroIndicatorType, float]:
    """Query the latest value for each real series from macro_indicators.

    Returns a (possibly partial or empty) dict of indicator → value.
    Never raises — returns {} on any connection or query failure.
    """
    try:
        import psycopg  # noqa: PLC0415  (local import keeps startup cost zero on import)

        conninfo = (
            f"host={os.environ.get('DB_HOST', 'localhost')} "
            f"port={os.environ.get('DB_PORT', '5432')} "
            f"dbname={os.environ.get('DB_NAME', 'aleph_core')} "
            f"user={os.environ.get('DB_USER', 'aleph_admin')} "
            f"password={os.environ.get('DB_PASSWORD', 'aleph_secure_pass')}"
        )
        series_ids = list(_SERIES_TO_INDICATOR.keys())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(series_ids)))
        query = (
            f"SELECT DISTINCT ON (series_id) series_id, value "  # noqa: S608
            f"FROM macro_indicators "
            f"WHERE series_id IN ({placeholders}) "
            f"ORDER BY series_id, snapshot_time DESC"
        )
        result: dict[MacroIndicatorType, float] = {}
        with psycopg.connect(conninfo, connect_timeout=3) as conn:
            rows = conn.execute(query, series_ids).fetchall()
        for series_id, value in rows:
            indicator = _SERIES_TO_INDICATOR.get(series_id)
            if indicator is not None and value is not None:
                result[indicator] = float(value)
        _log.info(
            "startup_seeder_real_values_fetched",
            count=len(result),
            indicators=[ind.value for ind in result],
        )
        return result
    except Exception as exc:  # noqa: BLE001
        _log.warning("startup_seeder_real_values_unavailable", error=str(exc))
        return {}


# ---------------------------------------------------------------------------
# Seed status
# ---------------------------------------------------------------------------


@dataclass
class SeedStatus:
    """Outcome of a seeder invocation."""

    success: bool
    """True when seeding completed without error."""

    skipped: bool = False
    """True when seeding was skipped because the store already contained data."""

    regime_id: str | None = None
    """ID of the created/existing regime, if available."""

    error: str | None = None
    """Human-readable error description when success=False."""

    warnings: list[str] = field(default_factory=list)
    """Non-fatal warnings produced during seeding."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_synthetic_observations(
    as_of_date: date,
    snapshot_id: str,
    indicator_values: dict[MacroIndicatorType, float] | None = None,
) -> list[NormalizedMacroObservation]:
    """Build normalized observations for *as_of_date* from *indicator_values*.

    Only indicators present in *indicator_values* generate observations.
    Absent indicators (e.g. PMI when ISM data is not collected) result in no
    observation, causing the domain to return GrowthState.UNKNOWN — correct
    behaviour per D-01a.
    """
    values = indicator_values if indicator_values is not None else {}
    now = datetime.now(UTC)
    obs_dt = datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC)
    observations: list[NormalizedMacroObservation] = []

    for indicator, value in values.items():
        freshness = FreshnessMetadata(
            expected_max_lag_hours=24 * 45,
            observed_lag_hours=0.0,
            status=FreshnessStatus.FRESH,
            is_late=False,
            is_stale=False,
        )
        obs = NormalizedMacroObservation(
            snapshot_id=snapshot_id,
            indicator_id=indicator,
            observation_date=obs_dt,
            fetched_at=now,
            source=MacroSourceType.FRED,
            value=value,
            release_date=obs_dt,
            unit="index",
            frequency=DataFrequency.MONTHLY,
            source_series_id=f"SYNTHETIC_{indicator.value.upper()}",
            region="US",
            freshness=freshness,
            revision_status=RevisionStatus.INITIAL,
            metadata={"seeded": "true"},
        )
        observations.append(obs)

    return observations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def seed_regime_from_synthetic_observations(
    snapshot_service: MacroSnapshotService,
    regime_service: MacroRegimeService,
    as_of_date: date | None = None,
    force_refresh: bool = False,
) -> SeedStatus:
    """Seed the in-memory stores with a synthetic snapshot and regime.

    **Idempotent**: does nothing if the regime store already contains at
    least one entry for *as_of_date* or any prior date.

    Args:
        snapshot_service: A :class:`~services.macro_snapshot_service.MacroSnapshotService`
            wired to the shared in-memory snapshot store.
        regime_service: A :class:`~services.macro_regime_service.MacroRegimeService`
            wired to the same snapshot store and to the shared regime store.
        as_of_date: Date for the synthetic data.  Defaults to today (UTC).

    Returns:
        :class:`SeedStatus` describing the outcome.  Never raises.
    """
    target_date = as_of_date or date.today()

    # --- Attempt to load real indicator values from TimescaleDB --------------
    loop = __import__("asyncio").get_event_loop()
    real_values = await loop.run_in_executor(None, _fetch_real_values_sync)
    # D-01a: use ONLY real DB values; absent indicators produce UNKNOWN state
    indicator_values = real_values
    used_real_data = bool(real_values)

    # --- Idempotency check (skipped when force_refresh=True) -----------------
    if not force_refresh:
        try:
            if regime_service._regime_repository is not None:  # noqa: SLF001
                existing = await regime_service._regime_repository.get_latest_on_or_before(  # noqa: SLF001
                    target_date
                )
                if existing is not None:
                    _log.info(
                        "startup_seeder_skipped",
                        reason="regime_store_already_populated",
                        existing_regime_id=existing.regime_id,
                        existing_as_of_date=str(existing.as_of_date),
                    )
                    return SeedStatus(
                        success=True,
                        skipped=True,
                        regime_id=existing.regime_id,
                    )
        except Exception as exc:  # noqa: BLE001
            _log.warning("startup_seeder_idempotency_check_failed", error=str(exc))
            # Continue — failure to check idempotency should not block seeding

    # --- Build snapshot -------------------------------------------------------
    snapshot_id = str(uuid.uuid4())
    observations = _build_synthetic_observations(
        as_of_date=target_date,
        snapshot_id=snapshot_id,
        indicator_values=indicator_values,
    )

    _log.info(
        "startup_seeder_building_snapshot",
        as_of_date=str(target_date),
        indicator_count=len(observations),
    )
    try:
        snapshot = await snapshot_service.build_and_save_snapshot(
            observations=observations,
            as_of_date=target_date,
        )
    except Exception as exc:  # noqa: BLE001
        _log.error("startup_seeder_snapshot_failed", error=str(exc))
        return SeedStatus(success=False, error=f"Snapshot build failed: {exc}")

    _log.info(
        "startup_seeder_snapshot_saved",
        snapshot_id=snapshot.snapshot_id,
        growth_state=snapshot.growth_state.value,
        inflation_state=snapshot.inflation_state.value,
        labor_state=snapshot.labor_state.value,
        policy_state=snapshot.policy_state.value,
        financial_conditions_state=snapshot.financial_conditions_state.value,
    )

    # --- Build and persist regime --------------------------------------------
    try:
        regime = await regime_service.build_and_save_regime(as_of_date=target_date)
        # Stamp seeder metadata onto the persisted regime.
        # If real DB values were available, mark as real-data so the frontend
        # does not show the "bootstrap/synthetic" badge (is_seeded = False).
        if used_real_data:
            regime.metadata.update({
                "seeded":       "false",
                "source":       "real_data_seed",
                "seed_version": SEEDER_METADATA["seed_version"],
            })
        else:
            # D-01a: no real data available — all indicator states are UNKNOWN
            regime.metadata.update({
                **SEEDER_METADATA,
                "source": "no_data_available",
            })
        is_seeded_flag = not used_real_data
        # Re-derive warnings with the correct is_seeded flag
        from src.domain.macro.regime_mapping import derive_regime_warnings
        regime.warnings = derive_regime_warnings(
            snapshot=snapshot,
            label=regime.regime_label,
            confidence=regime.confidence,
            missing_inputs=list(regime.missing_inputs),
            is_seeded=is_seeded_flag,
        )
    except Exception as exc:  # noqa: BLE001
        _log.error("startup_seeder_regime_failed", error=str(exc))
        return SeedStatus(success=False, error=f"Regime build failed: {exc}")

    _log.info(
        "startup_seeder_regime_saved",
        regime_id=regime.regime_id,
        regime_label=regime.regime_label.value,
        regime_family=regime.regime_family.value,
        confidence=regime.confidence.value,
        metadata=dict(regime.metadata),
    )

    return SeedStatus(success=True, regime_id=regime.regime_id)
