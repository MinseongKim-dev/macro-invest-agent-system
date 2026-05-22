"""Tests for the run_signal_engine MCP tool handler."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.domain.signals.registry import SignalRegistry, default_registry
from src.agent.mcp.schemas.run_signal_engine import RunSignalEngineRequest
from src.agent.mcp.tools.run_signal_engine import handle_run_signal_engine
from src.services.macro_service import MacroService
from src.services.signal_service import SignalService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request(
    signal_ids: list[str],
    country: str = "US",
    request_id: str = "req-engine-001",
) -> RunSignalEngineRequest:
    return RunSignalEngineRequest(
        request_id=request_id,
        signal_ids=signal_ids,
        country=country,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHandleRunSignalEngine:
    """Tests for handle_run_signal_engine."""

    # ------------------------------------------------------------------
    # Success paths
    # ------------------------------------------------------------------

    async def test_success_with_known_signal_id(self) -> None:
        """A request with a valid signal ID returns a successful response."""
        response = await handle_run_signal_engine(
            request=_request(["bull_market"]),
            macro_service=MacroService(),
            signal_service=SignalService(),
            registry=default_registry,
        )

        assert response.success is True
        assert response.engine_run_id != ""
        assert response.signals_generated >= 0
        assert response.error_message is None

    async def test_success_echoes_request_id(self) -> None:
        """Response request_id matches request."""
        response = await handle_run_signal_engine(
            request=_request(["bull_market"], request_id="echo-this"),
            macro_service=MacroService(),
            signal_service=SignalService(),
        )

        assert response.request_id == "echo-this"

    async def test_success_signal_counts_are_non_negative(self) -> None:
        """buy/sell/hold counts are non-negative integers."""
        response = await handle_run_signal_engine(
            request=_request(["bull_market", "recession_warning"]),
            macro_service=MacroService(),
            signal_service=SignalService(),
        )

        assert response.buy_signals >= 0
        assert response.sell_signals >= 0
        assert response.hold_signals >= 0
        assert response.signals_generated == response.buy_signals + response.sell_signals + response.hold_signals

    async def test_success_execution_time_recorded(self) -> None:
        """execution_time_ms is a non-negative float."""
        response = await handle_run_signal_engine(
            request=_request(["hold_neutral"]),
            macro_service=MacroService(),
            signal_service=SignalService(),
        )

        assert isinstance(response.execution_time_ms, float)
        assert response.execution_time_ms >= 0.0

    async def test_success_all_built_in_signals(self) -> None:
        """All three built-in signals can be evaluated together."""
        all_ids = default_registry.list_ids()
        response = await handle_run_signal_engine(
            request=_request(all_ids),
            macro_service=MacroService(),
            signal_service=SignalService(),
        )

        assert response.success is True

    # ------------------------------------------------------------------
    # Validation error paths
    # ------------------------------------------------------------------

    async def test_empty_signal_ids_returns_error(self) -> None:
        """Empty signal_ids returns an error response without calling services."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_signal = AsyncMock(spec=SignalService)

        response = await handle_run_signal_engine(
            request=_request([]),
            macro_service=mock_macro,
            signal_service=mock_signal,
        )

        assert response.success is False
        assert response.engine_run_id == ""
        assert "empty" in response.error_message.lower()  # type: ignore[union-attr]
        mock_macro.get_snapshot.assert_not_called()
        mock_signal.run_engine.assert_not_called()

    async def test_unknown_signal_id_returns_error(self) -> None:
        """A signal ID not in the registry returns an error response."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_signal = AsyncMock(spec=SignalService)

        response = await handle_run_signal_engine(
            request=_request(["does_not_exist"]),
            macro_service=mock_macro,
            signal_service=mock_signal,
            registry=default_registry,
        )

        assert response.success is False
        assert "'does_not_exist'" in response.error_message  # type: ignore[operator]
        mock_macro.get_snapshot.assert_not_called()
        mock_signal.run_engine.assert_not_called()

    async def test_mixed_known_and_unknown_ids_returns_error(self) -> None:
        """Any unknown ID in the list triggers an error (no partial evaluation)."""
        response = await handle_run_signal_engine(
            request=_request(["bull_market", "unknown_signal"]),
            macro_service=MacroService(),
            signal_service=SignalService(),
            registry=default_registry,
        )

        assert response.success is False
        assert "'unknown_signal'" in response.error_message  # type: ignore[operator]

    async def test_custom_registry_overrides_default(self) -> None:
        """A custom registry with different signal IDs is respected."""
        from src.domain.signals.enums import SignalType
        from src.domain.signals.models import SignalDefinition, SignalRule

        custom_def = SignalDefinition(
            signal_id="custom_signal",
            name="Custom Signal",
            signal_type=SignalType.HOLD,
            description="Custom signal for testing",
            rules=[
                SignalRule(
                    name="always_true",
                    description="Always passes",
                    condition="1 == 1",
                )
            ],
        )
        custom_registry = SignalRegistry({"custom_signal": custom_def})

        response = await handle_run_signal_engine(
            request=_request(["custom_signal"]),
            macro_service=MacroService(),
            signal_service=SignalService(),
            registry=custom_registry,
        )

        assert response.success is True

    # ------------------------------------------------------------------
    # Service error paths
    # ------------------------------------------------------------------

    async def test_snapshot_failure_returns_error(self) -> None:
        """RuntimeError from macro service is captured as error response."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_macro.get_snapshot.side_effect = RuntimeError("FRED unavailable")
        mock_signal = AsyncMock(spec=SignalService)

        response = await handle_run_signal_engine(
            request=_request(["bull_market"]),
            macro_service=mock_macro,
            signal_service=mock_signal,
            registry=default_registry,
        )

        assert response.success is False
        assert response.error_message == "Failed to fetch macro snapshot."
        assert response.engine_run_id == ""

    async def test_engine_failure_returns_error(self) -> None:
        """Exception from signal service is captured as error response."""
        mock_signal = AsyncMock(spec=SignalService)
        mock_signal.run_engine.side_effect = RuntimeError("engine crashed")

        response = await handle_run_signal_engine(
            request=_request(["bull_market"]),
            macro_service=MacroService(),
            signal_service=mock_signal,
            registry=default_registry,
        )

        assert response.success is False
        assert response.error_message == "Signal engine execution failed."
        assert response.engine_run_id == ""

    async def test_use_latest_snapshot_false_returns_error(self) -> None:
        """use_latest_snapshot=False is rejected until the alternate path is implemented."""
        mock_macro = AsyncMock(spec=MacroService)
        mock_signal = AsyncMock(spec=SignalService)

        response = await handle_run_signal_engine(
            request=RunSignalEngineRequest(
                request_id="req-no-snap",
                signal_ids=["bull_market"],
                use_latest_snapshot=False,
            ),
            macro_service=mock_macro,
            signal_service=mock_signal,
        )

        assert response.success is False
        assert response.engine_run_id == ""
        assert "use_latest_snapshot=False" in (response.error_message or "")
        mock_macro.get_snapshot.assert_not_called()
        mock_signal.run_engine.assert_not_called()
