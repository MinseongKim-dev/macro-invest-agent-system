"""Unit tests for agent.formatting.comparison.

Covers:
- format_comparison_summary: header, detail lines, all directions, no-prior suffix
- format_comparison_error: error message structure
- format_prior_missing_error: prior missing message structure
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.agent.formatting.comparison import (
    format_comparison_error,
    format_comparison_summary,
    format_prior_missing_error,
)
from src.domain.macro.comparison import FeatureDelta, SnapshotComparison

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comparison(
    country: str = "US",
    prior_snapshot_label: str = "Q1-2026",
    deltas: list[FeatureDelta] | None = None,
    changed: int = 0,
    unchanged: int = 0,
    no_prior: int = 0,
    ts: datetime | None = None,
) -> SnapshotComparison:
    return SnapshotComparison(
        country=country,
        prior_snapshot_label=prior_snapshot_label,
        current_snapshot_timestamp=ts or datetime.now(UTC),
        deltas=deltas or [],
        changed_count=changed,
        unchanged_count=unchanged,
        no_prior_count=no_prior,
    )


def _delta(
    indicator: str,
    current: float,
    prior: float | None = None,
    delta: float | None = None,
    direction: str = "unchanged",
) -> FeatureDelta:
    return FeatureDelta(
        indicator_type=indicator,
        current_value=current,
        prior_value=prior,
        delta=delta,
        direction=direction,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# format_comparison_summary
# ---------------------------------------------------------------------------


class TestFormatComparisonSummary:
    def test_header_contains_country(self) -> None:
        c = _comparison(country="JP")
        summary = format_comparison_summary(c)
        assert "country=JP" in summary

    def test_header_contains_prior_label(self) -> None:
        c = _comparison(prior_snapshot_label="Q1-2026")
        summary = format_comparison_summary(c)
        assert "Q1-2026" in summary

    def test_header_contains_changed_count(self) -> None:
        c = _comparison(changed=2, unchanged=1)
        summary = format_comparison_summary(c)
        assert "2 indicator(s) changed" in summary

    def test_header_contains_unchanged_count(self) -> None:
        c = _comparison(changed=0, unchanged=3)
        summary = format_comparison_summary(c)
        assert "3 unchanged" in summary

    def test_no_prior_suffix_present_when_positive(self) -> None:
        c = _comparison(no_prior=2)
        summary = format_comparison_summary(c)
        assert "with no prior data" in summary

    def test_no_prior_suffix_absent_when_zero(self) -> None:
        c = _comparison(no_prior=0)
        summary = format_comparison_summary(c)
        assert "with no prior data" not in summary

    def test_increased_direction_line(self) -> None:
        d = _delta("gdp", 3.7, prior=3.2, delta=0.5, direction="increased")
        c = _comparison(deltas=[d], changed=1)
        summary = format_comparison_summary(c)
        assert "gdp" in summary
        assert "increased" in summary

    def test_decreased_direction_line(self) -> None:
        d = _delta("inflation", 3.9, prior=4.1, delta=-0.2, direction="decreased")
        c = _comparison(deltas=[d], changed=1)
        summary = format_comparison_summary(c)
        assert "inflation" in summary
        assert "decreased" in summary

    def test_unchanged_direction_line(self) -> None:
        d = _delta("unemployment", 5.0, prior=5.0, delta=0.0, direction="unchanged")
        c = _comparison(deltas=[d], unchanged=1)
        summary = format_comparison_summary(c)
        assert "unemployment" in summary
        assert "unchanged" in summary

    def test_no_prior_direction_line(self) -> None:
        d = _delta("pmi", 52.0, direction="no_prior")
        c = _comparison(deltas=[d], no_prior=1)
        summary = format_comparison_summary(c)
        assert "pmi" in summary
        assert "no prior" in summary

    def test_no_deltas_returns_header_only(self) -> None:
        c = _comparison(deltas=[])
        summary = format_comparison_summary(c)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_timestamp_in_header(self) -> None:
        ts = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
        c = _comparison(ts=ts)
        summary = format_comparison_summary(c)
        assert "2026-04-01" in summary

    def test_timestamp_none_shows_unknown(self) -> None:
        c = SnapshotComparison(
            country="US",
            prior_snapshot_label="Q1",
            current_snapshot_timestamp=None,
        )
        summary = format_comparison_summary(c)
        assert "unknown" in summary

    def test_delta_sign_present_for_increase(self) -> None:
        d = _delta("gdp", 3.7, prior=3.2, delta=0.5, direction="increased")
        summary = format_comparison_summary(_comparison(deltas=[d]))
        assert "+0.5" in summary

    def test_returns_string(self) -> None:
        summary = format_comparison_summary(_comparison())
        assert isinstance(summary, str)


# ---------------------------------------------------------------------------
# format_comparison_error
# ---------------------------------------------------------------------------


class TestFormatComparisonError:
    def test_contains_country(self) -> None:
        msg = format_comparison_error("feed down", "req-1", "JP")
        assert "country=JP" in msg

    def test_contains_request_id(self) -> None:
        msg = format_comparison_error("feed down", "req-trace-42", "US")
        assert "req-trace-42" in msg

    def test_contains_raw_error(self) -> None:
        msg = format_comparison_error("feed down", "req-1", "US")
        assert "feed down" in msg

    def test_returns_string(self) -> None:
        assert isinstance(format_comparison_error("err", "id", "US"), str)


# ---------------------------------------------------------------------------
# format_prior_missing_error
# ---------------------------------------------------------------------------


class TestFormatPriorMissingError:
    def test_contains_prior_label(self) -> None:
        msg = format_prior_missing_error("Q1-2026", "req-1", "US")
        assert "Q1-2026" in msg

    def test_contains_request_id(self) -> None:
        msg = format_prior_missing_error("Q1-2026", "req-999", "US")
        assert "req-999" in msg

    def test_contains_country(self) -> None:
        msg = format_prior_missing_error("Q1-2026", "req-1", "JP")
        assert "country=JP" in msg

    def test_mentions_prior_features(self) -> None:
        msg = format_prior_missing_error("Q1-2026", "req-1", "US")
        assert "prior_features" in msg

    def test_returns_string(self) -> None:
        assert isinstance(format_prior_missing_error("label", "id", "US"), str)
