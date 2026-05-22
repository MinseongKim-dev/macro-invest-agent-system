"""Turn trimming and bounding rules for conversation context.

All functions in this module are **pure**: they accept a list of
:class:`~agent.context.models.ConversationTurn` objects and return a new
list without mutating the input.

Trimming strategy
-----------------
The primary trimming rule is a simple max-turns cap using FIFO eviction
(oldest turns first).  Additional rules can be layered on top without
touching the core :class:`~agent.context.models.ConversationContext` class.

Design notes
------------
* No token-budget trimming in Phase 3 — FIFO is sufficient for bounded
  recent-turn carryover.
* Staleness eviction is provided as a utility but not enforced by default.
"""

from __future__ import annotations

from agent.context.models import ConversationTurn


def trim_to_max_turns(
    turns: list[ConversationTurn],
    max_turns: int,
) -> list[ConversationTurn]:
    """Trim a turn list to at most *max_turns* by dropping the oldest turns.

    If ``len(turns) <= max_turns`` the original list is returned unchanged.

    Args:
        turns: Chronologically ordered list of turns (oldest first).
        max_turns: Maximum number of turns to retain.

    Returns:
        A new list containing the *max_turns* most-recent turns.

    Raises:
        ValueError: If *max_turns* is less than 1.

    Example::

        trimmed = trim_to_max_turns(turns, max_turns=3)
        assert len(trimmed) <= 3
    """
    if max_turns < 1:
        raise ValueError(f"max_turns must be >= 1, got {max_turns}")
    if len(turns) <= max_turns:
        return turns
    return turns[-max_turns:]


def keep_successful_only(
    turns: list[ConversationTurn],
) -> list[ConversationTurn]:
    """Return only the successful turns from *turns*.

    Useful when injecting context into prompts and failed turns carry no
    useful signal for the next request.

    Args:
        turns: List of turns (may contain successes and failures).

    Returns:
        A new list containing only turns where ``success is True``.
    """
    return [t for t in turns if t.success]


def extract_recent_summaries(
    turns: list[ConversationTurn],
    limit: int = 3,
) -> list[str]:
    """Extract the *limit* most-recent non-empty response summaries.

    Args:
        turns: Chronologically ordered turn list (oldest first).
        limit: Maximum number of summaries to return.

    Returns:
        A list of non-empty ``response_summary`` strings from the most recent
        turns, newest-last.

    Raises:
        ValueError: If *limit* is less than 1.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    summaries = [t.response_summary for t in turns if t.response_summary]
    return summaries[-limit:]
