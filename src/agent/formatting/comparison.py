"""Deterministic comparison summary and error formatters.

All functions in this module produce deterministic, human-readable strings
from :class:`~domain.macro.comparison.SnapshotComparison` results.  No LLM
or external I/O is involved.

Design notes
------------
* Each formatter is a pure function: same inputs always produce the same output.
* Comparison logic lives in :mod:`domain.macro.comparison`, not here.
* The output describes *what changed* (counts, indicator directions) and
  never makes speculative investment conclusions.
"""

from __future__ import annotations

from domain.macro.comparison import SnapshotComparison


def format_comparison_summary(comparison: SnapshotComparison) -> str:
    """Build a deterministic "what changed" summary for a snapshot comparison.

    The summary covers:
    * Overall change counts (changed / unchanged / no-prior).
    * Per-indicator direction lines for indicators that changed.

    Indicators with ``direction="no_prior"`` are listed separately.

    Args:
        comparison: A :class:`~domain.macro.comparison.SnapshotComparison`
            produced by :func:`~domain.macro.comparison.compare_snapshots`.

    Returns:
        A concise, human-readable summary string.

    Example::

        summary = format_comparison_summary(comparison)
        # "Snapshot comparison for country=US vs prior (Q1-2026): ..."
    """
    ts_str = (
        comparison.current_snapshot_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        if comparison.current_snapshot_timestamp is not None
        else "unknown"
    )

    header = (
        f"Snapshot comparison for country={comparison.country} "
        f"vs prior ({comparison.prior_snapshot_label}) as of {ts_str}: "
        f"{comparison.changed_count} indicator(s) changed, "
        f"{comparison.unchanged_count} unchanged"
        + (
            f", {comparison.no_prior_count} with no prior data"
            if comparison.no_prior_count > 0
            else ""
        )
        + "."
    )

    detail_lines: list[str] = []
    for delta in comparison.deltas:
        if delta.direction == "no_prior":
            detail_lines.append(
                f"  {delta.indicator_type}: no prior value available "
                f"(current={delta.current_value:.4g})."
            )
        elif delta.direction == "unchanged":
            detail_lines.append(
                f"  {delta.indicator_type}: unchanged "
                f"(value={delta.current_value:.4g})."
            )
        else:
            sign = "+" if delta.direction == "increased" else ""
            detail_lines.append(
                f"  {delta.indicator_type}: {delta.direction} "
                f"({delta.prior_value:.4g} → {delta.current_value:.4g}, "
                f"delta={sign}{delta.delta:.4g})."
            )

    if detail_lines:
        return header + "\n" + "\n".join(detail_lines)
    return header


def format_comparison_error(raw_error: str, request_id: str, country: str) -> str:
    """Return a user-facing error string for a failed snapshot comparison.

    Args:
        raw_error: The raw error description.
        request_id: The tracing ID from the original request.
        country: The country code that was requested.

    Returns:
        A concise, user-friendly error message.
    """
    return (
        f"Snapshot comparison for country={country} could not be completed "
        f"(request_id={request_id}). "
        f"Detail: {raw_error}"
    )


def format_prior_missing_error(
    prior_snapshot_label: str,
    request_id: str,
    country: str,
) -> str:
    """Return a user-facing error string for a missing prior snapshot.

    Args:
        prior_snapshot_label: The label of the prior snapshot that was
            requested but not provided.
        request_id: The tracing ID from the original request.
        country: The country code for the comparison.

    Returns:
        A concise, user-friendly error message.
    """
    return (
        f"Snapshot comparison for country={country} could not be completed: "
        f"no prior snapshot data provided for label '{prior_snapshot_label}' "
        f"(request_id={request_id}). "
        f"Supply prior_features to enable comparison."
    )
