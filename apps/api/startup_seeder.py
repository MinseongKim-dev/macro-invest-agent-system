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
# Metadata stamped on every regime produced by this seeder
# ---------------------------------------------------------------------------

SEEDER_METADATA: dict[str, str] = {
    "seeded": "true",
    "source": "synthetic_seed",
    "seed_version": "1",
}

# ---------------------------------------------------------------------------
# Synthetic indicator values
# ---------------------------------------------------------------------------
# These values are chosen to produce a deterministic SLOWDOWN/POLICY_TIGHTENING_DRAG
# regime so that the analyst UI shows a meaningful, non-trivial baseline:
#   PMI=48.2      → growth_state = SLOWING
#   RETAIL_SALES  = -0.5 → growth_state = SLOWING (reinforces)
#   INFLATION=3.1 → inflation_state = STICKY
#   UNEMPLOYMENT=4.4 → labor_state = SOFTENING
#   YIELD_10Y=4.6 → policy_state = RESTRICTIVE, financial_conditions_state = TIGHT

_SYNTHETIC_VALUES: dict[MacroIndicatorType, float] = {
    MacroIndicatorType.PMI: 48.2,
    MacroIndicatorType.RETAIL_SALES: -0.5,
    MacroIndicatorType.INFLATION: 3.1,
    MacroIndicatorType.UNEMPLOYMENT: 4.4,
    MacroIndicatorType.YIELD_10Y: 4.6,
}


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
) -> list[NormalizedMacroObservation]:
    """Build a set of synthetic normalized observations for *as_of_date*."""
    now = datetime.now(UTC)
    obs_dt = datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC)
    observations: list[NormalizedMacroObservation] = []

    for indicator, value in _SYNTHETIC_VALUES.items():
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

    # --- Idempotency check ---------------------------------------------------
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
        # Stamp seeder metadata onto the persisted regime
        regime.metadata.update(SEEDER_METADATA)
        # Re-derive warnings now that is_seeded=True is known
        from src.domain.macro.regime_mapping import derive_regime_warnings
        regime.warnings = derive_regime_warnings(
            snapshot=snapshot,
            label=regime.regime_label,
            confidence=regime.confidence,
            missing_inputs=list(regime.missing_inputs),
            is_seeded=True,
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
