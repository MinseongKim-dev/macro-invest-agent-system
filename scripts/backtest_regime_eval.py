"""Regime classification accuracy eval harness (PRD Phase D-2 groundwork).

Replays a sequence of synthetic macro snapshots — one per scenario, each
built to deterministically exercise one rule branch of
``map_snapshot_to_regime_label()`` — through the real snapshot/regime build
pipeline (the same ``MacroSnapshotService`` / ``MacroRegimeService`` used by
the API and the startup seeder) and checks that the resulting regime label
matches the expected label for that scenario.

This is NOT a historical backtest against real market data — no verified
2-year historical macro data source/loader exists yet (see CLAUDE.md v0.4.0
notes on the KOFIA adapter blocker for the analogous problem on the fund-NAV
side). This harness instead validates that the deterministic regime engine
classifies known, hand-derived indicator combinations correctly — i.e. it
guards against regressions in ``regime_mapping.py`` rule order/logic.

Usage::

    uv run python -m scripts.backtest_regime_eval

Exit code is 0 when every scenario's actual label matches its expected
label, 1 otherwise.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

from src.agent.adapters.repositories.in_memory_macro_regime_store import (
    InMemoryMacroRegimeStore,
)
from src.agent.adapters.repositories.in_memory_macro_snapshot_store import (
    InMemoryMacroSnapshotStore,
)
from src.domain.macro.enums import DataFrequency, MacroIndicatorType, MacroSourceType
from src.domain.macro.regime import RegimeLabel
from src.pipelines.ingestion.models import (
    FreshnessMetadata,
    FreshnessStatus,
    NormalizedMacroObservation,
    RevisionStatus,
)
from src.services.macro_regime_service import MacroRegimeService
from src.services.macro_snapshot_service import MacroSnapshotService


@dataclass(frozen=True)
class Scenario:
    """One synthetic macro period with a hand-derived expected regime label."""

    name: str
    as_of_date: date
    expected_label: RegimeLabel
    values: dict[MacroIndicatorType, float]


# Each scenario's indicator values are chosen so exactly one branch of
# map_snapshot_to_regime_label() fires, in rule-evaluation order. See
# src/domain/macro/snapshot.py for the raw-value → category-state thresholds
# and src/domain/macro/regime_mapping.py for the state → label rules.
SCENARIOS: list[Scenario] = [
    Scenario(
        name="goldilocks",
        as_of_date=date(2025, 1, 1),
        expected_label=RegimeLabel.GOLDILOCKS,
        values={
            MacroIndicatorType.PMI: 54.0,
            MacroIndicatorType.RETAIL_SALES: 1.0,
            MacroIndicatorType.INFLATION: 2.0,
            MacroIndicatorType.UNEMPLOYMENT: 3.8,
            MacroIndicatorType.YIELD_10Y: 3.5,
        },
    ),
    Scenario(
        name="disinflation",
        as_of_date=date(2025, 2, 1),
        expected_label=RegimeLabel.DISINFLATION,
        values={
            MacroIndicatorType.PMI: 48.0,
            MacroIndicatorType.RETAIL_SALES: -0.5,
            MacroIndicatorType.INFLATION: 2.0,
            MacroIndicatorType.UNEMPLOYMENT: 5.0,
            MacroIndicatorType.YIELD_10Y: 3.5,
        },
    ),
    Scenario(
        name="contraction",
        as_of_date=date(2025, 3, 1),
        expected_label=RegimeLabel.CONTRACTION,
        values={
            MacroIndicatorType.PMI: 45.0,
            MacroIndicatorType.RETAIL_SALES: -2.0,
            MacroIndicatorType.INFLATION: 3.0,
            MacroIndicatorType.UNEMPLOYMENT: 6.5,
            MacroIndicatorType.YIELD_10Y: 5.0,
        },
    ),
    Scenario(
        name="policy_tightening_drag",
        as_of_date=date(2025, 4, 1),
        expected_label=RegimeLabel.POLICY_TIGHTENING_DRAG,
        values={
            MacroIndicatorType.PMI: 50.5,
            MacroIndicatorType.RETAIL_SALES: 0.0,
            MacroIndicatorType.INFLATION: 3.0,
            MacroIndicatorType.UNEMPLOYMENT: 4.5,
            MacroIndicatorType.YIELD_10Y: 5.0,
        },
    ),
    Scenario(
        name="policy_tightening_drag (seeder baseline)",
        as_of_date=date(2025, 5, 1),
        expected_label=RegimeLabel.POLICY_TIGHTENING_DRAG,
        values={
            MacroIndicatorType.PMI: 48.2,
            MacroIndicatorType.RETAIL_SALES: -0.5,
            MacroIndicatorType.INFLATION: 3.1,
            MacroIndicatorType.UNEMPLOYMENT: 4.4,
            MacroIndicatorType.YIELD_10Y: 4.6,
        },
    ),
    Scenario(
        name="stagflation_risk",
        as_of_date=date(2025, 6, 1),
        expected_label=RegimeLabel.STAGFLATION_RISK,
        values={
            MacroIndicatorType.PMI: 45.0,
            MacroIndicatorType.RETAIL_SALES: -1.0,
            MacroIndicatorType.INFLATION: 4.0,
            MacroIndicatorType.UNEMPLOYMENT: 5.0,
            MacroIndicatorType.YIELD_10Y: 3.5,
        },
    ),
    Scenario(
        name="reflation",
        as_of_date=date(2025, 7, 1),
        expected_label=RegimeLabel.REFLATION,
        values={
            MacroIndicatorType.PMI: 54.0,
            MacroIndicatorType.RETAIL_SALES: 1.0,
            MacroIndicatorType.INFLATION: 4.0,
            MacroIndicatorType.UNEMPLOYMENT: 4.5,
            MacroIndicatorType.YIELD_10Y: 2.5,
        },
    ),
    Scenario(
        name="slowdown",
        as_of_date=date(2025, 8, 1),
        expected_label=RegimeLabel.SLOWDOWN,
        values={
            MacroIndicatorType.PMI: 47.0,
            MacroIndicatorType.RETAIL_SALES: -1.0,
            MacroIndicatorType.INFLATION: 3.0,
            MacroIndicatorType.UNEMPLOYMENT: 4.5,
            MacroIndicatorType.YIELD_10Y: 3.5,
        },
    ),
    Scenario(
        name="mixed",
        as_of_date=date(2025, 9, 1),
        expected_label=RegimeLabel.MIXED,
        values={
            MacroIndicatorType.PMI: 50.5,
            MacroIndicatorType.RETAIL_SALES: 0.0,
            MacroIndicatorType.INFLATION: 3.0,
            MacroIndicatorType.UNEMPLOYMENT: 3.5,
            MacroIndicatorType.YIELD_10Y: 3.8,
        },
    ),
]


def _build_observations(
    as_of_date: date,
    snapshot_id: str,
    values: dict[MacroIndicatorType, float],
) -> list[NormalizedMacroObservation]:
    """Build fully-fresh, non-degraded observations for one scenario."""
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
        observations.append(
            NormalizedMacroObservation(
                snapshot_id=snapshot_id,
                indicator_id=indicator,
                observation_date=obs_dt,
                fetched_at=now,
                source=MacroSourceType.FRED,
                value=value,
                release_date=obs_dt,
                unit="index",
                frequency=DataFrequency.MONTHLY,
                source_series_id=f"EVAL_{indicator.value.upper()}",
                region="US",
                freshness=freshness,
                revision_status=RevisionStatus.INITIAL,
                metadata={"eval_harness": "true"},
            )
        )
    return observations


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    actual_label: RegimeLabel
    confidence: str
    matched: bool


async def run_eval(scenarios: list[Scenario] | None = None) -> list[ScenarioResult]:
    """Run every scenario through the real snapshot/regime build pipeline.

    Uses fresh in-memory stores so this harness never touches the live
    application's shared singletons. Scenarios are processed in
    ``as_of_date`` order since each regime build compares against the prior
    persisted regime.
    """
    scenarios = scenarios or SCENARIOS
    snapshot_store = InMemoryMacroSnapshotStore()
    regime_store = InMemoryMacroRegimeStore()
    snapshot_service = MacroSnapshotService(repository=snapshot_store)
    regime_service = MacroRegimeService(
        snapshot_repository=snapshot_store,
        regime_repository=regime_store,
    )

    results: list[ScenarioResult] = []
    for scenario in sorted(scenarios, key=lambda s: s.as_of_date):
        snapshot_id = f"eval-{scenario.name}"
        observations = _build_observations(scenario.as_of_date, snapshot_id, scenario.values)
        await snapshot_service.build_and_save_snapshot(
            observations=observations,
            as_of_date=scenario.as_of_date,
        )
        regime = await regime_service.build_and_save_regime(as_of_date=scenario.as_of_date)
        results.append(
            ScenarioResult(
                scenario=scenario,
                actual_label=regime.regime_label,
                confidence=regime.confidence.value,
                matched=regime.regime_label == scenario.expected_label,
            )
        )
    return results


def _print_report(results: list[ScenarioResult]) -> None:
    hits = sum(1 for r in results if r.matched)
    total = len(results)
    print(f"{'scenario':<42}{'expected':<24}{'actual':<24}{'confidence':<12}{'match'}")
    print("-" * 112)
    for r in results:
        mark = "OK" if r.matched else "MISMATCH"
        print(
            f"{r.scenario.name:<42}"
            f"{r.scenario.expected_label.value:<24}"
            f"{r.actual_label.value:<24}"
            f"{r.confidence:<12}"
            f"{mark}"
        )
    print("-" * 112)
    print(f"Hit rate: {hits}/{total} ({hits / total:.0%})" if total else "No scenarios run.")


def main() -> int:
    results = asyncio.run(run_eval())
    _print_report(results)
    return 0 if all(r.matched for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
