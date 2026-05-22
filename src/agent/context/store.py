"""Session-scoped in-memory context store.

This module provides a protocol and a simple in-memory implementation for
storing per-session :class:`~agent.context.models.ConversationContext` objects.

Design constraints
------------------
* Context is **session-isolated**: each ``session_id`` maps to an independent
  :class:`~agent.context.models.ConversationContext`.  No sharing across
  sessions.
* The store is **process-scoped**: all data is lost on restart.
* No TTL, no cross-session reads, no persistence layer.
* The store is **not thread-safe** — use one instance per request-handling
  coroutine or synchronise externally if needed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent.context.models import ConversationContext

_DEFAULT_MAX_TURNS = 10


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ContextStore(Protocol):
    """Protocol for session-scoped conversation context stores.

    Concrete implementations must support ``get_or_create``, ``get``, and
    ``clear`` with the semantics documented here.
    """

    def get_or_create(
        self,
        session_id: str,
        max_turns: int = _DEFAULT_MAX_TURNS,
    ) -> ConversationContext:
        """Return the existing context for *session_id* or create a new one.

        Args:
            session_id: Unique identifier for the session.
            max_turns: Maximum turns retained when creating a new context.

        Returns:
            The :class:`~agent.context.models.ConversationContext` for
            *session_id*.
        """
        ...

    def get(self, session_id: str) -> ConversationContext | None:
        """Return the existing context for *session_id*, or ``None`` if absent.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            The context, or ``None`` if *session_id* has no stored context.
        """
        ...

    def clear(self, session_id: str) -> None:
        """Remove the context for *session_id* if it exists.

        Args:
            session_id: Unique identifier for the session to clear.
        """
        ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryContextStore:
    """Simple in-memory implementation of :class:`ContextStore`.

    Stores one :class:`~agent.context.models.ConversationContext` per
    ``session_id`` in a plain Python dict.  All state is lost when the object
    is garbage-collected.

    Example::

        store = InMemoryContextStore()
        ctx = store.get_or_create("session-abc", max_turns=5)
        ctx.add_turn(...)

        # Same session retrieves the same context.
        same_ctx = store.get_or_create("session-abc")
        assert same_ctx is ctx

        # Different session gets a fresh context.
        other_ctx = store.get_or_create("session-xyz")
        assert other_ctx is not ctx
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationContext] = {}

    def get_or_create(
        self,
        session_id: str,
        max_turns: int = _DEFAULT_MAX_TURNS,
    ) -> ConversationContext:
        """Return the existing context or create one with *max_turns*.

        If the session already exists, *max_turns* is ignored and the
        existing context is returned unchanged.

        Args:
            session_id: Unique identifier for the session.
            max_turns: Used only when creating a new context.

        Returns:
            The :class:`~agent.context.models.ConversationContext` for
            *session_id*.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationContext(max_turns=max_turns)
        return self._sessions[session_id]

    def get(self, session_id: str) -> ConversationContext | None:
        """Return the context for *session_id*, or ``None`` if absent.

        Args:
            session_id: Unique identifier for the session.
        """
        return self._sessions.get(session_id)

    def clear(self, session_id: str) -> None:
        """Remove the context for *session_id*.

        Args:
            session_id: Unique identifier for the session.
        """
        self._sessions.pop(session_id, None)

    def session_count(self) -> int:
        """Return the total number of active sessions (for introspection)."""
        return len(self._sessions)
