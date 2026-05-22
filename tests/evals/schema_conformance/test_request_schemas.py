"""Schema conformance eval: all AgentRequest subclasses.

Verifies:
- Extra fields are rejected where appropriate.
- Required fields must be non-empty.
- Valid requests construct cleanly.
- ``model_dump()`` round-trips work correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.schemas import (
    MacroSnapshotSummaryRequest,
    PriorFeatureInput,
    SignalReviewRequest,
    SnapshotComparisonRequest,
)

# ---------------------------------------------------------------------------
# SignalReviewRequest
# ---------------------------------------------------------------------------


class TestSignalReviewRequestSchema:
    """Conformance tests for SignalReviewRequest."""

    def test_valid_request_constructs(self) -> None:
        req = SignalReviewRequest(
            request_id="req-1",
            signal_ids=["bull_market"],
            country="US",
        )
        assert req.signal_ids == ["bull_market"]

    def test_empty_signal_ids_raises(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewRequest(request_id="req-1", signal_ids=[])

    def test_empty_string_signal_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewRequest(request_id="req-1", signal_ids=[""])

    def test_model_dump_round_trip(self) -> None:
        req = SignalReviewRequest(
            request_id="req-1",
            signal_ids=["bull_market", "bear_market"],
            country="JP",
        )
        data = req.model_dump()
        reparsed = SignalReviewRequest.model_validate(data)
        assert reparsed.signal_ids == ["bull_market", "bear_market"]
        assert reparsed.country == "JP"

    def test_session_id_defaults_to_none(self) -> None:
        req = SignalReviewRequest(request_id="req-1", signal_ids=["bull_market"])
        assert req.session_id is None

    def test_session_id_can_be_set(self) -> None:
        req = SignalReviewRequest(
            request_id="req-1",
            signal_ids=["bull_market"],
            session_id="sess-abc",
        )
        assert req.session_id == "sess-abc"


# ---------------------------------------------------------------------------
# MacroSnapshotSummaryRequest
# ---------------------------------------------------------------------------


class TestMacroSnapshotSummaryRequestSchema:
    """Conformance tests for MacroSnapshotSummaryRequest."""

    def test_valid_request_constructs(self) -> None:
        req = MacroSnapshotSummaryRequest(request_id="req-2", country="US")
        assert req.country == "US"

    def test_default_country_is_us(self) -> None:
        req = MacroSnapshotSummaryRequest(request_id="req-2")
        assert req.country == "US"

    def test_model_dump_round_trip(self) -> None:
        req = MacroSnapshotSummaryRequest(request_id="req-2", country="GB")
        data = req.model_dump()
        reparsed = MacroSnapshotSummaryRequest.model_validate(data)
        assert reparsed.country == "GB"

    def test_session_id_is_optional(self) -> None:
        req = MacroSnapshotSummaryRequest(request_id="req-2")
        assert req.session_id is None


# ---------------------------------------------------------------------------
# SnapshotComparisonRequest
# ---------------------------------------------------------------------------


class TestSnapshotComparisonRequestSchema:
    """Conformance tests for SnapshotComparisonRequest."""

    def test_valid_request_with_prior_features_constructs(self) -> None:
        req = SnapshotComparisonRequest(
            request_id="req-3",
            country="US",
            prior_snapshot_label="Q1-2026",
            prior_features=[PriorFeatureInput(indicator_type="gdp", value=25000.0)],
        )
        assert len(req.prior_features) == 1

    def test_empty_prior_features_allowed(self) -> None:
        req = SnapshotComparisonRequest(
            request_id="req-3",
            country="US",
            prior_snapshot_label="Q1-2026",
            prior_features=[],
        )
        assert req.prior_features == []

    def test_missing_prior_snapshot_label_raises(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotComparisonRequest(
                request_id="req-3",
                country="US",
            )  # type: ignore[call-arg]

    def test_model_dump_round_trip(self) -> None:
        req = SnapshotComparisonRequest(
            request_id="req-3",
            country="FR",
            prior_snapshot_label="Q2-2026",
            prior_features=[PriorFeatureInput(indicator_type="inflation", value=3.2)],
        )
        data = req.model_dump()
        reparsed = SnapshotComparisonRequest.model_validate(data)
        assert reparsed.prior_snapshot_label == "Q2-2026"
        assert len(reparsed.prior_features) == 1


# ---------------------------------------------------------------------------
# PriorFeatureInput
# ---------------------------------------------------------------------------


class TestPriorFeatureInputSchema:
    """Conformance tests for PriorFeatureInput."""

    def test_valid_constructs(self) -> None:
        f = PriorFeatureInput(indicator_type="gdp", value=25000.0)
        assert f.indicator_type == "gdp"
        assert f.value == 25000.0

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PriorFeatureInput(indicator_type="gdp", value=100.0, extra="x")  # type: ignore[call-arg]

    def test_model_dump_round_trip(self) -> None:
        f = PriorFeatureInput(indicator_type="unemployment", value=4.1)
        data = f.model_dump()
        reparsed = PriorFeatureInput.model_validate(data)
        assert reparsed.value == 4.1
