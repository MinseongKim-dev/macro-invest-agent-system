"""Unit tests for InMemoryExplanationStore.

Verifies that the in-memory implementation of
:class:`~storage.repositories.explanation_repository.ExplanationRepositoryInterface`
satisfies the repository contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.agent.adapters.repositories.in_memory_explanation_store import InMemoryExplanationStore
from apps.api.dto.explanations import ExplanationResponse
from apps.api.dto.trust import DataAvailability, FreshnessStatus, TrustMetadata


def _make_explanation(
    run_id: str = "run-001",
    signal_id: str | None = "eq_buy",
    summary: str = "Test explanation.",
) -> ExplanationResponse:
    explanation_id = f"{run_id}:{signal_id}" if signal_id else run_id
    return ExplanationResponse(
        explanation_id=explanation_id,
        run_id=run_id,
        signal_id=signal_id,
        summary=summary,
        rationale_points=["rationale 1"],
        generated_at=datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC),
        trust=TrustMetadata(
            freshness_status=FreshnessStatus.FRESH,
            availability=DataAvailability.FULL,
            is_degraded=False,
        ),
    )


class TestInMemoryExplanationStore:
    def test_save_and_get_by_id(self) -> None:
        store = InMemoryExplanationStore()
        e = _make_explanation()
        store.save(e)
        result = store.get_by_id(e.explanation_id)
        assert result is not None
        assert result.explanation_id == e.explanation_id
        assert result.summary == e.summary

    def test_get_by_id_not_found_returns_none(self) -> None:
        store = InMemoryExplanationStore()
        assert store.get_by_id("does-not-exist") is None

    def test_save_is_idempotent(self) -> None:
        store = InMemoryExplanationStore()
        e = _make_explanation(summary="first")
        store.save(e)
        e2 = e.model_copy(update={"summary": "second"})
        store.save(e2)
        result = store.get_by_id(e.explanation_id)
        assert result is not None
        assert result.summary == "second"

    def test_list_by_run_id_returns_all_for_run(self) -> None:
        store = InMemoryExplanationStore()
        e1 = _make_explanation(run_id="run-A", signal_id="s1")
        e2 = _make_explanation(run_id="run-A", signal_id="s2")
        e3 = _make_explanation(run_id="run-B", signal_id="s1")
        store.save(e1)
        store.save(e2)
        store.save(e3)
        results = store.list_by_run_id("run-A")
        assert len(results) == 2
        ids = {r.explanation_id for r in results}
        assert ids == {"run-A:s1", "run-A:s2"}

    def test_list_by_run_id_empty_when_not_found(self) -> None:
        store = InMemoryExplanationStore()
        assert store.list_by_run_id("nonexistent") == []

    def test_list_by_run_id_ordered_by_generated_at(self) -> None:
        store = InMemoryExplanationStore()
        e_late = _make_explanation(run_id="run-X", signal_id="s1", summary="late")
        e_late = e_late.model_copy(
            update={"generated_at": datetime(2026, 4, 19, 14, 0, 0, tzinfo=UTC)}
        )
        e_early = _make_explanation(run_id="run-X", signal_id="s2", summary="early")
        e_early = e_early.model_copy(
            update={"generated_at": datetime(2026, 4, 19, 10, 0, 0, tzinfo=UTC)}
        )
        store.save(e_late)
        store.save(e_early)
        results = store.list_by_run_id("run-X")
        assert results[0].summary == "early"
        assert results[1].summary == "late"

    def test_clear_removes_all(self) -> None:
        store = InMemoryExplanationStore()
        store.save(_make_explanation(run_id="run-1", signal_id="s1"))
        store.save(_make_explanation(run_id="run-2", signal_id="s2"))
        store.clear()
        assert len(store) == 0
        assert store.get_by_id("run-1:s1") is None

    def test_len_after_save(self) -> None:
        store = InMemoryExplanationStore()
        assert len(store) == 0
        store.save(_make_explanation(run_id="run-1", signal_id="s1"))
        assert len(store) == 1
        store.save(_make_explanation(run_id="run-1", signal_id="s2"))
        assert len(store) == 2

    def test_contains(self) -> None:
        store = InMemoryExplanationStore()
        e = _make_explanation()
        store.save(e)
        assert e.explanation_id in store
        assert "missing-id" not in store

    def test_different_run_ids_do_not_collide(self) -> None:
        store = InMemoryExplanationStore()
        store.save(_make_explanation(run_id="run-A", signal_id="s1", summary="A"))
        store.save(_make_explanation(run_id="run-B", signal_id="s1", summary="B"))
        assert store.get_by_id("run-A:s1").summary == "A"  # type: ignore[union-attr]
        assert store.get_by_id("run-B:s1").summary == "B"  # type: ignore[union-attr]

    def test_run_level_explanation_no_signal_id(self) -> None:
        store = InMemoryExplanationStore()
        e = _make_explanation(run_id="run-001", signal_id=None, summary="run-level")
        store.save(e)
        result = store.get_by_id("run-001")
        assert result is not None
        assert result.signal_id is None
