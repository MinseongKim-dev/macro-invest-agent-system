"""Tests for MCP schemas."""

from src.agent.mcp.schemas.common import MCPRequest, MCPResponse
from src.agent.mcp.schemas.get_macro_features import (
    GetMacroFeaturesRequest,
    GetMacroFeaturesResponse,
    GetMacroSnapshotRequest,
    GetMacroSnapshotResponse,
)
from src.agent.mcp.schemas.run_signal_engine import (
    RunSignalEngineRequest,
    RunSignalEngineResponse,
)


class TestMCPBaseSchemas:
    """Tests for base MCP schemas."""

    def test_mcp_request_creation(self) -> None:
        """Test creating base MCP request."""
        request = MCPRequest(request_id="test-123")
        assert request.request_id == "test-123"
        assert request.timestamp is not None

    def test_mcp_response_creation(self) -> None:
        """Test creating base MCP response."""
        response = MCPResponse(request_id="test-123", success=True)
        assert response.request_id == "test-123"
        assert response.success is True
        assert response.error_message is None

    def test_mcp_response_error(self) -> None:
        """Test creating error response."""
        response = MCPResponse(
            request_id="test-123",
            success=False,
            error_message="Service unavailable",
        )
        assert response.success is False
        assert response.error_message == "Service unavailable"


class TestGetMacroFeaturesSchemas:
    """Tests for macro features request/response."""

    def test_get_macro_features_request(self) -> None:
        """Test creating GetMacroFeaturesRequest."""
        request = GetMacroFeaturesRequest(
            request_id="test-123",
            indicator_types=["gdp", "inflation"],
        )
        assert request.request_id == "test-123"
        assert request.indicator_types == ["gdp", "inflation"]
        assert request.country == "US"

    def test_get_macro_features_response(self) -> None:
        """Test creating GetMacroFeaturesResponse."""
        response = GetMacroFeaturesResponse(
            request_id="test-123",
            success=True,
            features_count=2,
        )
        assert response.request_id == "test-123"
        assert response.features_count == 2

    def test_get_macro_snapshot_request(self) -> None:
        """Test creating GetMacroSnapshotRequest."""
        request = GetMacroSnapshotRequest(request_id="test-123", country="GB")
        assert request.country == "GB"

    def test_get_macro_snapshot_response(self) -> None:
        """Test creating GetMacroSnapshotResponse."""
        response = GetMacroSnapshotResponse(
            request_id="test-123",
            success=True,
            features_count=3,
        )
        assert response.features_count == 3


class TestRunSignalEngineSchemas:
    """Tests for signal engine request/response."""

    def test_run_signal_engine_request(self) -> None:
        """Test creating RunSignalEngineRequest."""
        request = RunSignalEngineRequest(
            request_id="test-123",
            signal_ids=["signal_1", "signal_2"],
        )
        assert request.signal_ids == ["signal_1", "signal_2"]
        assert request.use_latest_snapshot is True

    def test_run_signal_engine_response(self) -> None:
        """Test creating RunSignalEngineResponse."""
        response = RunSignalEngineResponse(
            request_id="test-123",
            engine_run_id="run-456",
            signals_generated=2,
            buy_signals=1,
            sell_signals=1,
            execution_time_ms=15.5,
        )
        assert response.engine_run_id == "run-456"
        assert response.signals_generated == 2
        assert response.execution_time_ms == 15.5
