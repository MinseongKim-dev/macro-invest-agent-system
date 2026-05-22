"""Shared fixtures for the evals test suite.

Provides lightweight factories for the core services and runtime so that every
eval sub-suite can stay focused on the scenario being tested rather than
construction boilerplate.

Fixtures
--------
* :func:`session_id` — unique string identifier per test.
* :func:`make_service` — constructs a fully-wired :class:`~agent.service.AgentService`.
* :func:`make_lc_runtime` — constructs a :class:`~agent.runtime.langchain_runtime.LangChainAgentRuntime`
  with ``enable_context=True`` and a configurable turn cap.
"""

from __future__ import annotations

import uuid

import pytest

from agent.mcp_adapter import MCPAdapter
from agent.runtime.langchain_runtime import LangChainAgentRuntime
from agent.service import AgentService
from services.macro_service import MacroService
from services.signal_service import SignalService


@pytest.fixture()
def session_id() -> str:
    """Return a unique session ID string for each test."""
    return f"eval-session-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def make_service() -> AgentService:
    """Return a fully-wired :class:`~agent.service.AgentService` instance."""
    macro_service = MacroService()
    signal_service = SignalService()
    return AgentService(macro_service, signal_service)


@pytest.fixture()
def make_lc_runtime(make_service: AgentService) -> LangChainAgentRuntime:
    """Return a :class:`~agent.runtime.langchain_runtime.LangChainAgentRuntime`
    with ``enable_context=True`` and ``max_context_turns=10``.
    """
    macro_service = MacroService()
    signal_service = SignalService()
    adapter = MCPAdapter(macro_service, signal_service)
    return LangChainAgentRuntime(
        make_service,
        adapter,
        enable_context=True,
        max_context_turns=10,
    )
