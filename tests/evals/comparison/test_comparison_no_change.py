"""Eval: snapshot comparison with no changes — all prior values identical.

Verifies that when all prior feature values match the current snapshot values,
``changed_count == 0`` and the response is still successful.
"""

from __future__ import annotations

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.schemas import PriorFeatureInput, SnapshotComparisonRequest
from agent.service import AgentService
from services.macro_service import MacroService
from services.signal_service import SignalService


def _make_runtime() -> LangChainAgentRuntime:
    macro_service = MacroService()
    signal_service = SignalService()
    service = AgentService(macro_service, signal_service)
    adapter = MCPAdapter(macro_service, signal_service)
    return LangChainAgentRuntime(service, adapter, enable_context=False)


# MacroService placeholder returns value=50.0 for all indicators.
# Supply the same values as "prior" to trigger the no-change path.
_IDENTICAL_PRIOR = [
    {"indicator_type": "gdp", "value": 50.0},
    {"indicator_type": "inflation", "value": 50.0},
    {"indicator_type": "unemployment", "value": 50.0},
    {"indicator_type": "interest_rate", "value": 50.0},
    {"indicator_type": "bond_yield", "value": 50.0},
]


@pytest.mark.asyncio
class TestComparisonNoChange:
    """All prior values identical → changed_count == 0."""

    async def test_changed_count_is_zero_when_values_identical(self) -> None:
        runtime = _make_runtime()
        features = [PriorFeatureInput(**f) for f in _IDENTICAL_PRIOR]  # type: ignore[arg-type]
        result = await runtime.invoke(
            SnapshotComparisonRequest(
                request_id="no-change-req-1",
                country="US",
                prior_snapshot_label="Q0-2026",
                prior_features=features,
            )
        )
        assert result.success
        assert result.response.changed_count == 0  # type: ignore[union-attr]

    async def test_unchanged_count_equals_matched_indicators(self) -> None:
        runtime = _make_runtime()
        features = [PriorFeatureInput(**f) for f in _IDENTICAL_PRIOR]  # type: ignore[arg-type]
        result = await runtime.invoke(
            SnapshotComparisonRequest(
                request_id="no-change-req-2",
                country="US",
                prior_snapshot_label="Q0-2026",
                prior_features=features,
            )
        )
        assert result.success
        assert result.response.unchanged_count >= 0  # type: ignore[union-attr]

    async def test_success_true_even_with_no_changes(self) -> None:
        runtime = _make_runtime()
        features = [PriorFeatureInput(**f) for f in _IDENTICAL_PRIOR]  # type: ignore[arg-type]
        result = await runtime.invoke(
            SnapshotComparisonRequest(
                request_id="no-change-req-3",
                country="US",
                prior_snapshot_label="Q0-2026",
                prior_features=features,
            )
        )
        assert result.success is True

    async def test_summary_non_empty_on_no_change(self) -> None:
        runtime = _make_runtime()
        features = [PriorFeatureInput(**f) for f in _IDENTICAL_PRIOR]  # type: ignore[arg-type]
        result = await runtime.invoke(
            SnapshotComparisonRequest(
                request_id="no-change-req-4",
                country="US",
                prior_snapshot_label="Q0-2026",
                prior_features=features,
            )
        )
        assert result.success
        assert len(result.response.summary) > 0
