"""Schema conformance eval: all AgentResponse subclasses.

Verifies:
- Extra fields are rejected (``extra="forbid"`` is effective).
- ``success=False`` responses can be constructed without raising.
- ``model_dump()`` round-trips produce consistent results.
- Numeric fields are non-negative.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent.schemas import (
    AgentResponse,
    MacroSnapshotSummaryResponse,
    SignalReviewResponse,
    SnapshotComparisonResponse,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# AgentResponse base
# ---------------------------------------------------------------------------


class TestAgentResponseSchema:
    """Conformance tests for the AgentResponse base schema."""

    def test_success_response_constructs(self) -> None:
        resp = AgentResponse(
            request_id="r1",
            success=True,
            summary="All good.",
        )
        assert resp.success is True

    def test_failure_response_requires_error_message(self) -> None:
        with pytest.raises(ValidationError):
            AgentResponse(request_id="r1", success=False, summary="")

    def test_failure_response_with_message_constructs(self) -> None:
        resp = AgentResponse(
            request_id="r1",
            success=False,
            error_message="Something failed.",
            summary="",
        )
        assert resp.success is False
        assert resp.error_message == "Something failed."

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentResponse(request_id="r1", success=True, unknown_field="x")  # type: ignore[call-arg]

    def test_model_dump_round_trip(self) -> None:
        resp = AgentResponse(request_id="r1", success=True, summary="ok")
        reparsed = AgentResponse.model_validate(resp.model_dump())
        assert reparsed.request_id == resp.request_id
        assert reparsed.success == resp.success


# ---------------------------------------------------------------------------
# SignalReviewResponse
# ---------------------------------------------------------------------------


class TestSignalReviewResponseSchema:
    """Conformance tests for SignalReviewResponse."""

    def test_success_constructs_with_defaults(self) -> None:
        resp = SignalReviewResponse(request_id="s1", success=True, summary="3 signals.")
        assert resp.signals_generated == 0
        assert resp.buy_signals == 0

    def test_failure_constructs(self) -> None:
        resp = SignalReviewResponse(
            request_id="s1",
            success=False,
            error_message="Engine failed.",
        )
        assert resp.success is False

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewResponse(request_id="s1", success=True, hallucinated="x")  # type: ignore[call-arg]

    def test_negative_signal_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalReviewResponse(request_id="s1", success=True, buy_signals=-1)

    def test_model_dump_round_trip(self) -> None:
        resp = SignalReviewResponse(
            request_id="s1",
            success=True,
            summary="done",
            signals_generated=3,
            buy_signals=2,
            sell_signals=1,
            hold_signals=0,
        )
        data = resp.model_dump()
        reparsed = SignalReviewResponse.model_validate(data)
        assert reparsed.signals_generated == 3


# ---------------------------------------------------------------------------
# MacroSnapshotSummaryResponse
# ---------------------------------------------------------------------------


class TestMacroSnapshotSummaryResponseSchema:
    """Conformance tests for MacroSnapshotSummaryResponse."""

    def test_success_constructs(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="m1",
            success=True,
            summary="5 features.",
            country="US",
            features_count=5,
        )
        assert resp.features_count == 5

    def test_failure_constructs_without_snapshot_time(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="m1",
            success=False,
            error_message="Snapshot unavailable.",
        )
        assert resp.snapshot_timestamp is None

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroSnapshotSummaryResponse(request_id="m1", success=True, extra_xyz=1)  # type: ignore[call-arg]

    def test_negative_features_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MacroSnapshotSummaryResponse(
                request_id="m1", success=True, features_count=-1
            )

    def test_model_dump_round_trip(self) -> None:
        resp = MacroSnapshotSummaryResponse(
            request_id="m1",
            success=True,
            summary="ok",
            country="JP",
            features_count=3,
            snapshot_timestamp=_now(),
        )
        data = resp.model_dump()
        reparsed = MacroSnapshotSummaryResponse.model_validate(data)
        assert reparsed.country == "JP"
        assert reparsed.features_count == 3


# ---------------------------------------------------------------------------
# SnapshotComparisonResponse
# ---------------------------------------------------------------------------


class TestSnapshotComparisonResponseSchema:
    """Conformance tests for SnapshotComparisonResponse."""

    def test_success_constructs(self) -> None:
        resp = SnapshotComparisonResponse(
            request_id="c1",
            success=True,
            summary="3 changed.",
            country="US",
            prior_snapshot_label="Q1-2026",
            changed_count=3,
            unchanged_count=2,
            no_prior_count=0,
        )
        assert resp.changed_count == 3

    def test_failure_constructs_without_raising(self) -> None:
        resp = SnapshotComparisonResponse(
            request_id="c1",
            success=False,
            error_message="Prior missing.",
        )
        assert resp.success is False

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotComparisonResponse(request_id="c1", success=True, bogus="x")  # type: ignore[call-arg]

    def test_negative_changed_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotComparisonResponse(
                request_id="c1", success=True, changed_count=-1
            )

    def test_model_dump_round_trip(self) -> None:
        resp = SnapshotComparisonResponse(
            request_id="c1",
            success=True,
            summary="ok",
            country="DE",
            prior_snapshot_label="Q2",
            changed_count=1,
            unchanged_count=4,
            no_prior_count=0,
        )
        data = resp.model_dump()
        reparsed = SnapshotComparisonResponse.model_validate(data)
        assert reparsed.changed_count == 1
        assert reparsed.unchanged_count == 4
