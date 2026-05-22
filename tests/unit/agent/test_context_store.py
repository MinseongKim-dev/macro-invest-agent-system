"""Unit tests for agent.context.store.

Covers:
- InMemoryContextStore.get_or_create: creates new context, returns same context, respects max_turns
- InMemoryContextStore.get: returns None for unknown, returns context for known
- InMemoryContextStore.clear: removes session, safe on unknown session
- Session isolation: different session IDs get independent contexts
- session_count introspection
- ContextStore protocol conformance
"""

from __future__ import annotations

import pytest

from src.agent.context.models import AnalysisParameters, ConversationContext, ConversationTurn
from src.agent.context.store import ContextStore, InMemoryContextStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_turn(country: str | None = None) -> ConversationTurn:
    return ConversationTurn(
        request_type="SignalReviewRequest",
        request_snapshot={"request_id": "r1"},
        response_summary="ok",
        success=True,
        active_parameters=AnalysisParameters(country=country),
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestContextStoreProtocol:
    def test_in_memory_store_satisfies_protocol(self) -> None:
        store = InMemoryContextStore()
        assert isinstance(store, ContextStore)

    def test_protocol_is_runtime_checkable(self) -> None:
        # The @runtime_checkable decorator enables isinstance checks.
        assert issubclass(InMemoryContextStore, ContextStore)


# ---------------------------------------------------------------------------
# get_or_create — basic behaviour
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    def test_creates_new_context_for_new_session(self) -> None:
        store = InMemoryContextStore()
        ctx = store.get_or_create("sess-001")
        assert isinstance(ctx, ConversationContext)

    def test_returns_same_context_for_same_session(self) -> None:
        store = InMemoryContextStore()
        ctx1 = store.get_or_create("sess-abc")
        ctx2 = store.get_or_create("sess-abc")
        assert ctx1 is ctx2

    def test_different_sessions_get_different_contexts(self) -> None:
        store = InMemoryContextStore()
        ctx_a = store.get_or_create("sess-A")
        ctx_b = store.get_or_create("sess-B")
        assert ctx_a is not ctx_b

    def test_max_turns_applied_on_creation(self) -> None:
        store = InMemoryContextStore()
        ctx = store.get_or_create("sess-mt", max_turns=2)
        # Fill past the cap to confirm max_turns=2 was respected.
        for _ in range(4):
            ctx.add_turn(_make_turn())
        assert ctx.turn_count == 2

    def test_max_turns_ignored_on_existing_session(self) -> None:
        store = InMemoryContextStore()
        ctx1 = store.get_or_create("sess-existing", max_turns=5)
        ctx2 = store.get_or_create("sess-existing", max_turns=1)
        # The existing context must be returned unchanged (max_turns=5).
        assert ctx1 is ctx2


# ---------------------------------------------------------------------------
# get — basic behaviour
# ---------------------------------------------------------------------------


class TestGet:
    def test_returns_none_for_unknown_session(self) -> None:
        store = InMemoryContextStore()
        assert store.get("nonexistent") is None

    def test_returns_context_for_known_session(self) -> None:
        store = InMemoryContextStore()
        ctx = store.get_or_create("sess-known")
        assert store.get("sess-known") is ctx

    def test_get_is_consistent_with_get_or_create(self) -> None:
        store = InMemoryContextStore()
        created = store.get_or_create("sess-check")
        retrieved = store.get("sess-check")
        assert created is retrieved


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_session(self) -> None:
        store = InMemoryContextStore()
        store.get_or_create("sess-to-clear")
        store.clear("sess-to-clear")
        assert store.get("sess-to-clear") is None

    def test_clear_on_unknown_session_is_safe(self) -> None:
        store = InMemoryContextStore()
        store.clear("does-not-exist")  # Should not raise

    def test_clear_decrements_session_count(self) -> None:
        store = InMemoryContextStore()
        store.get_or_create("sess-1")
        store.get_or_create("sess-2")
        assert store.session_count() == 2
        store.clear("sess-1")
        assert store.session_count() == 1

    def test_clear_only_removes_targeted_session(self) -> None:
        store = InMemoryContextStore()
        store.get_or_create("sess-keep")
        store.get_or_create("sess-drop")
        store.clear("sess-drop")
        assert store.get("sess-keep") is not None
        assert store.get("sess-drop") is None

    def test_get_or_create_after_clear_creates_fresh_context(self) -> None:
        store = InMemoryContextStore()
        ctx_orig = store.get_or_create("sess-recycle")
        ctx_orig.add_turn(_make_turn(country="US"))

        store.clear("sess-recycle")
        ctx_new = store.get_or_create("sess-recycle")

        assert ctx_new is not ctx_orig
        assert ctx_new.turn_count == 0


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    def test_turns_do_not_leak_between_sessions(self) -> None:
        store = InMemoryContextStore()
        ctx_a = store.get_or_create("sess-A")
        ctx_b = store.get_or_create("sess-B")

        ctx_a.add_turn(_make_turn(country="US"))
        assert ctx_b.turn_count == 0

    def test_active_parameters_do_not_leak_between_sessions(self) -> None:
        store = InMemoryContextStore()
        ctx_a = store.get_or_create("sess-A")
        ctx_b = store.get_or_create("sess-B")

        ctx_a.add_turn(_make_turn(country="JP"))
        assert ctx_b.active_parameters.country is None

    def test_clear_one_session_does_not_affect_other(self) -> None:
        store = InMemoryContextStore()
        ctx_a = store.get_or_create("sess-A")
        ctx_a.add_turn(_make_turn(country="US"))
        store.get_or_create("sess-B")

        store.clear("sess-B")
        # sess-A must still have its turn.
        assert store.get("sess-A") is not None
        assert store.get("sess-A").turn_count == 1  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# session_count
# ---------------------------------------------------------------------------


class TestSessionCount:
    def test_initially_zero(self) -> None:
        store = InMemoryContextStore()
        assert store.session_count() == 0

    def test_increments_on_create(self) -> None:
        store = InMemoryContextStore()
        store.get_or_create("s1")
        store.get_or_create("s2")
        assert store.session_count() == 2

    def test_does_not_increment_on_retrieval(self) -> None:
        store = InMemoryContextStore()
        store.get_or_create("s1")
        store.get_or_create("s1")
        assert store.session_count() == 1

    def test_decrements_on_clear(self) -> None:
        store = InMemoryContextStore()
        store.get_or_create("s1")
        store.clear("s1")
        assert store.session_count() == 0


# ---------------------------------------------------------------------------
# Missing context path (stateless — no session at all)
# ---------------------------------------------------------------------------


class TestMissingContextPath:
    def test_get_returns_none_before_any_create(self) -> None:
        store = InMemoryContextStore()
        assert store.get("never-seen") is None

    def test_context_not_required_to_exist_before_clear(self) -> None:
        store = InMemoryContextStore()
        store.clear("ghost-session")  # No error expected
        assert store.session_count() == 0

    @pytest.mark.asyncio
    async def test_multiple_stores_are_independent(self) -> None:
        store_x = InMemoryContextStore()
        store_y = InMemoryContextStore()

        store_x.get_or_create("shared-id")
        assert store_y.get("shared-id") is None
