"""Deterministic summary formatters for the agent layer.

All functions in this module produce deterministic, human-readable strings
from structured MCP responses.  No LLM or external I/O is involved.

Design notes
------------
* Each formatter is a pure function: same inputs always produce the same output.
* Formatters are kept separate from the orchestration logic in
  :mod:`agent.service` so they can be tested and evolved independently.
* The output strings are intentionally conservative — they describe *what
  happened* (signal counts, timestamps, feature counts) and never make
  prescriptive investment recommendations.
"""

from __future__ import annotations

from mcp.schemas.get_macro_features import GetMacroSnapshotResponse
from mcp.schemas.run_signal_engine import RunSignalEngineResponse


def dominant_signal_type(response: RunSignalEngineResponse) -> str:
    """Return the dominant signal type label based on counts.

    Returns the type with the highest count, breaking ties in the order
    BUY > SELL > HOLD.  Returns ``"none"`` if no signals were generated.

    Args:
        response: Successful MCP response from the signal engine.

    Returns:
        One of ``"BUY"``, ``"SELL"``, ``"HOLD"``, or ``"none"``.
    """
    counts = {
        "BUY": response.buy_signals,
        "SELL": response.sell_signals,
        "HOLD": response.hold_signals,
    }
    if not any(counts.values()):
        return "none"
    return max(counts, key=lambda k: counts[k])


def format_signal_review_summary(
    response: RunSignalEngineResponse,
    signal_ids: list[str],
    country: str,
) -> str:
    """Build a deterministic one-paragraph signal review summary.

    Args:
        response: Successful MCP response from the signal engine.
        signal_ids: IDs that were reviewed.
        country: Country code used for the macro snapshot.

    Returns:
        A concise summary string describing the signal review outcome.
    """
    ids_str = ", ".join(signal_ids)
    dominance = dominant_signal_type(response)
    return (
        f"Signal review for [{ids_str}] (country={country}): "
        f"{response.signals_generated} signal(s) generated "
        f"(BUY={response.buy_signals}, SELL={response.sell_signals}, "
        f"HOLD={response.hold_signals}). "
        f"Dominant signal direction: {dominance}. "
        f"Engine run ID: {response.engine_run_id}. "
        f"Execution time: {response.execution_time_ms:.1f}ms."
    )


def format_snapshot_summary(
    response: GetMacroSnapshotResponse,
    country: str,
) -> str:
    """Build a deterministic one-paragraph macro snapshot summary.

    Args:
        response: Successful MCP response from the snapshot tool.
        country: Country code for which the snapshot was fetched.

    Returns:
        A concise summary string describing the snapshot.
    """
    ts_str = (
        response.snapshot_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        if response.snapshot_timestamp is not None
        else "unknown"
    )
    return (
        f"Macro snapshot for country={country}: "
        f"{response.features_count} feature(s) available "
        f"as of {ts_str}."
    )
