"""Session-scoped conversation context models.

This module provides the data models for lightweight, in-memory conversation
context.  Context is session-scoped and bounded — it never persists beyond the
process lifetime and never carries more than ``max_turns`` recent turns.

Design constraints
------------------
* **Session-scoped only**: context lives at the runtime layer; the service and
  MCP layers remain stateless.
* **In-memory**: no database, file system, or external store is involved.
* **Bounded**: a fixed ``max_turns`` cap prevents unbounded growth.
* **Explicit**: context is represented as typed models, not implicit state.
* **Read-only**: context is never used to override deterministic tool results.

Active analysis parameters
---------------------------
:class:`AnalysisParameters` captures the *current active context* of an
analysis session — which country, timeframe, signal type, and comparison
target the analyst is working on.  When a new request omits a parameter that
was set in a prior turn, the prior value is carried forward automatically via
:meth:`AnalysisParameters.merge`.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Analysis parameters
# ---------------------------------------------------------------------------

_DEFAULT_MAX_TURNS = 10


class AnalysisParameters(BaseModel, extra="forbid"):
    """Active analysis parameters carried across conversation turns.

    All fields are optional.  A ``None`` value means the parameter has not
    been set in this session.  Use :meth:`merge` to produce a new instance
    that inherits values from a prior turn where the new request did not
    supply them.

    Attributes:
        country: ISO 3166-1 alpha-2 country code (e.g. ``"US"``).
        timeframe: Informal timeframe label (e.g. ``"Q1-2026"``).
        signal_type: Signal type label (e.g. ``"BUY"``).
        comparison_target: Prior snapshot label used for comparison.
    """

    country: str | None = Field(default=None, description="Active country code")
    timeframe: str | None = Field(default=None, description="Active analysis timeframe label")
    signal_type: str | None = Field(default=None, description="Active signal type filter")
    comparison_target: str | None = Field(
        default=None,
        description="Prior snapshot label for comparison analysis",
    )

    def merge(self, prior: AnalysisParameters) -> AnalysisParameters:
        """Return a new instance combining *self* with inherited values from *prior*.

        Fields set in *self* take precedence.  Fields that are ``None`` in
        *self* but set in *prior* are inherited.  ``None`` in both → ``None``.

        Args:
            prior: The parameters from the most recent prior turn.

        Returns:
            A new :class:`AnalysisParameters` with inherited values filled in.

        Example::

            prior = AnalysisParameters(country="US", timeframe="Q1-2026")
            current = AnalysisParameters(signal_type="BUY")
            merged = current.merge(prior)
            # merged.country == "US"  (inherited)
            # merged.signal_type == "BUY"  (from current)
        """
        return AnalysisParameters(
            country=self.country if self.country is not None else prior.country,
            timeframe=self.timeframe if self.timeframe is not None else prior.timeframe,
            signal_type=self.signal_type if self.signal_type is not None else prior.signal_type,
            comparison_target=(
                self.comparison_target
                if self.comparison_target is not None
                else prior.comparison_target
            ),
        )

    def is_empty(self) -> bool:
        """Return ``True`` if no parameter has been set."""
        return all(
            v is None
            for v in (self.country, self.timeframe, self.signal_type, self.comparison_target)
        )

    def as_context_hint(self) -> str:
        """Return a compact, human-readable summary for prompt injection.

        Returns an empty string when no parameters are set.
        """
        parts: list[str] = []
        if self.country:
            parts.append(f"country={self.country}")
        if self.timeframe:
            parts.append(f"timeframe={self.timeframe}")
        if self.signal_type:
            parts.append(f"signal_type={self.signal_type}")
        if self.comparison_target:
            parts.append(f"comparison_target={self.comparison_target}")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Conversation turn
# ---------------------------------------------------------------------------


class ConversationTurn(BaseModel, extra="forbid"):
    """A single turn in the session-scoped conversation context.

    Attributes:
        request_type: The class name of the agent request.
        request_snapshot: Serialised request data for reference.
        response_summary: The ``summary`` field from the agent response.
        success: Whether the operation succeeded.
        active_parameters: The :class:`AnalysisParameters` extracted from
            this turn's request.  Defaults to an empty parameter set.
    """

    request_type: str = Field(..., description="Agent request class name")
    request_snapshot: dict[str, Any] = Field(..., description="Serialised request data")
    response_summary: str = Field(default="", description="Summary from the agent response")
    success: bool = Field(default=True, description="Whether the operation succeeded")
    active_parameters: AnalysisParameters = Field(
        default_factory=AnalysisParameters,
        description="Analysis parameters extracted from this turn",
    )


# ---------------------------------------------------------------------------
# Conversation context
# ---------------------------------------------------------------------------


class ConversationContext:
    """Session-scoped, in-memory conversation context for recent-turn carryover.

    Stores up to ``max_turns`` recent :class:`ConversationTurn` objects and
    tracks the most-recently-set :class:`AnalysisParameters`.

    No database or persistence of any kind is used.  All data is lost when
    the object is garbage-collected or :meth:`clear` is called.

    Args:
        max_turns: Maximum number of turns to retain.  Oldest turns are
            evicted first when the cap is reached (FIFO).

    Example::

        ctx = ConversationContext(max_turns=5)
        ctx.add_turn(ConversationTurn(
            request_type="SignalReviewRequest",
            request_snapshot={"request_id": "r1"},
            response_summary="3 signals generated.",
            success=True,
            active_parameters=AnalysisParameters(country="US"),
        ))
        hint = ctx.active_parameters.as_context_hint()  # "country=US"
    """

    def __init__(self, max_turns: int = _DEFAULT_MAX_TURNS) -> None:
        if max_turns < 1:
            raise ValueError(f"max_turns must be >= 1, got {max_turns}")
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self._active_parameters = AnalysisParameters()

    def add_turn(self, turn: ConversationTurn) -> None:
        """Append a turn and update the active analysis parameters.

        The active parameters are merged: the new turn's parameters override
        the prior values, and any ``None`` fields fall back to prior values.

        Args:
            turn: The completed conversation turn to record.
        """
        self._active_parameters = turn.active_parameters.merge(self._active_parameters)
        self._turns.append(turn)

    @property
    def turns(self) -> list[ConversationTurn]:
        """Return all stored turns in chronological order (oldest first)."""
        return list(self._turns)

    @property
    def turn_count(self) -> int:
        """Return the number of stored turns."""
        return len(self._turns)

    @property
    def active_parameters(self) -> AnalysisParameters:
        """Return the current merged :class:`AnalysisParameters`.

        These represent the most recently active analysis context, suitable
        for injection into the next prompt.
        """
        return self._active_parameters

    def context_summary(self) -> str:
        """Build a compact, human-readable context hint for prompt injection.

        Returns a plain string that can be appended to the system message.
        Returns an empty string when there is no useful context.

        The summary includes:
        * The active analysis parameters (when any are set).
        * A digest of the most recent turn summaries.
        """
        parts: list[str] = []

        params_hint = self._active_parameters.as_context_hint()
        if params_hint:
            parts.append(f"Active parameters: {params_hint}.")

        recent_turns = list(self._turns)[-3:]  # At most 3 for the hint
        if recent_turns:
            digests: list[str] = []
            for i, turn in enumerate(recent_turns, 1):
                status = "ok" if turn.success else "failed"
                digest = (
                    f"[{i}] {turn.request_type} ({status})"
                    + (f": {turn.response_summary[:80]}" if turn.response_summary else "")
                )
                digests.append(digest)
            parts.append("Recent turns: " + " | ".join(digests) + ".")

        return " ".join(parts)

    def clear(self) -> None:
        """Remove all stored turns and reset parameters."""
        self._turns.clear()
        self._active_parameters = AnalysisParameters()
