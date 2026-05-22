"""Tests for the explanations route — GET /api/explanations/{id}."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from src.agent.adapters.repositories.in_memory_explanation_store import InMemoryExplanationStore
from apps.api.dependencies import get_explanation_repository
from apps.api.main import app
from apps.api.routers.explanations import build_and_register_explanation


@pytest.fixture()
def explanation_store() -> InMemoryExplanationStore:
    """Fresh in-memory store for each test."""
    return InMemoryExplanationStore()


@pytest.fixture()
def client(explanation_store: InMemoryExplanationStore) -> Generator[TestClient, None, None]:
    """TestClient with a per-test isolated explanation repository."""
    app.dependency_overrides[get_explanation_repository] = lambda: explanation_store
    yield TestClient(app)
    app.dependency_overrides.pop(get_explanation_repository, None)


class TestExplanationsRouter:
    """Tests for GET /api/explanations/{id}."""

    def test_not_found_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/explanations/does-not-exist")
        assert resp.status_code == 404

    def test_found_returns_200(
        self, client: TestClient, explanation_store: InMemoryExplanationStore
    ) -> None:
        build_and_register_explanation(
            run_id="run-abc",
            signal_id="bull_market",
            summary="Bull market conditions confirmed.",
            rationale_points=["GDP > 2%", "Inflation < 4%"],
            repository=explanation_store,
        )
        resp = client.get("/api/explanations/run-abc:bull_market")
        assert resp.status_code == 200

    def test_response_fields(
        self, client: TestClient, explanation_store: InMemoryExplanationStore
    ) -> None:
        build_and_register_explanation(
            run_id="run-xyz",
            signal_id=None,
            summary="Snapshot is healthy.",
            rationale_points=["All indicators within range"],
            repository=explanation_store,
        )
        resp = client.get("/api/explanations/run-xyz")
        data = resp.json()
        assert data["explanation_id"] == "run-xyz"
        assert data["run_id"] == "run-xyz"
        assert data["signal_id"] is None
        assert data["summary"] == "Snapshot is healthy."
        assert len(data["rationale_points"]) == 1

    def test_composite_id_with_signal(
        self, client: TestClient, explanation_store: InMemoryExplanationStore
    ) -> None:
        build_and_register_explanation(
            run_id="run-001",
            signal_id="recession_warning",
            summary="Recession warning.",
            rationale_points=["Unemployment > 7%", "GDP < 0"],
            repository=explanation_store,
        )
        resp = client.get("/api/explanations/run-001:recession_warning")
        data = resp.json()
        assert data["signal_id"] == "recession_warning"
        assert data["explanation_id"] == "run-001:recession_warning"

    def test_trust_metadata_present(
        self, client: TestClient, explanation_store: InMemoryExplanationStore
    ) -> None:
        build_and_register_explanation(
            run_id="run-trust",
            signal_id="bull_market",
            summary="ok",
            rationale_points=[],
            repository=explanation_store,
        )
        resp = client.get("/api/explanations/run-trust:bull_market")
        trust = resp.json()["trust"]
        assert "freshness_status" in trust
        assert "availability" in trust
        assert trust["freshness_status"] == "fresh"

    def test_different_ids_do_not_collide(
        self, client: TestClient, explanation_store: InMemoryExplanationStore
    ) -> None:
        build_and_register_explanation("run-A", "s1", "summary A", [], repository=explanation_store)
        build_and_register_explanation("run-B", "s1", "summary B", [], repository=explanation_store)

        resp_a = client.get("/api/explanations/run-A:s1")
        resp_b = client.get("/api/explanations/run-B:s1")
        assert resp_a.json()["summary"] == "summary A"
        assert resp_b.json()["summary"] == "summary B"

    def test_v2_fields_present(
        self, client: TestClient, explanation_store: InMemoryExplanationStore
    ) -> None:
        """v2 schema fields are present on every ExplanationResponse."""
        build_and_register_explanation(
            run_id="run-v2",
            signal_id="eq_buy",
            summary="Equities buy signal.",
            rationale_points=["growth_accelerating"],
            repository=explanation_store,
            conflict_status="tension",
            conflict_note="One conflicting driver present.",
            quant_support_level="strong",
        )
        data = client.get("/api/explanations/run-v2:eq_buy").json()
        assert data["conflict_status"] == "tension"
        assert data["conflict_note"] == "One conflicting driver present."
        assert data["quant_support_level"] == "strong"
        assert isinstance(data["reasoning_chain"], list)
        assert isinstance(data["analyst_workflow"], dict)
        assert isinstance(data["analyst_workflow"]["steps"], list)

    def test_list_by_run_returns_all_signals(
        self, client: TestClient, explanation_store: InMemoryExplanationStore
    ) -> None:
        """GET /api/explanations/run/{run_id} returns all explanations for a run."""
        build_and_register_explanation("run-multi", "s1", "sig1", [], repository=explanation_store)
        build_and_register_explanation("run-multi", "s2", "sig2", [], repository=explanation_store)
        build_and_register_explanation("run-other", "s3", "sig3", [], repository=explanation_store)

        resp = client.get("/api/explanations/run/run-multi")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        ids = {e["signal_id"] for e in data}
        assert ids == {"s1", "s2"}

    def test_list_by_run_empty_when_not_found(self, client: TestClient) -> None:
        """GET /api/explanations/run/{run_id} returns [] when run has no explanations."""
        resp = client.get("/api/explanations/run/nonexistent-run")
        assert resp.status_code == 200
        assert resp.json() == []
