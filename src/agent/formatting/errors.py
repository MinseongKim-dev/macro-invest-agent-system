"""User-facing error message formatters for the agent layer.

Functions in this module convert low-level tool error strings into concise,
user-friendly messages while preserving enough context for tracing.

Design notes
------------
* Error messages describe *what failed*, not *why* in implementation detail.
* The raw MCP error is forwarded unchanged as ``detail`` so callers that need
  the original message can access it.
* All formatters are pure functions — no side effects, no I/O.
"""

from __future__ import annotations


def format_signal_review_error(raw_error: str, request_id: str) -> str:
    """Return a user-facing error string for a failed signal review.

    Args:
        raw_error: The raw error string surfaced from the MCP tool.
        request_id: The tracing ID from the original request.

    Returns:
        A concise, user-friendly error message that includes the request ID
        for tracing but omits low-level implementation details.
    """
    return (
        f"Signal review could not be completed (request_id={request_id}). "
        f"Detail: {raw_error}"
    )


def format_snapshot_summary_error(raw_error: str, request_id: str, country: str) -> str:
    """Return a user-facing error string for a failed macro snapshot summary.

    Args:
        raw_error: The raw error string surfaced from the MCP tool.
        request_id: The tracing ID from the original request.
        country: The country code that was requested.

    Returns:
        A concise, user-friendly error message that includes the request ID
        and country for tracing but omits low-level implementation details.
    """
    return (
        f"Macro snapshot for country={country} could not be retrieved "
        f"(request_id={request_id}). "
        f"Detail: {raw_error}"
    )
