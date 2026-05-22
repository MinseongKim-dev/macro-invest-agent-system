"""LangChain prompt templates for agent summary formatting.

This module provides :class:`~langchain_core.prompts.ChatPromptTemplate`
instances for each agent operation.  In the current implementation the
templates are rendered **directly** (no LLM call) to produce deterministic
summaries.  When an LLM-backed formatting stage is introduced, these same
templates can be passed to a chat model without modification.

Design constraints
------------------
* Templates receive **only** structured data fields produced by MCP tools.
  They never override or reinterpret deterministic tool results.
* The rendered text is factual and conservative — it describes what the
  engine produced and never makes investment recommendations.
* All template variables are documented so callers can supply them without
  inspecting source code.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

# ---------------------------------------------------------------------------
# Signal review
# ---------------------------------------------------------------------------

SIGNAL_REVIEW_SYSTEM_MESSAGE = (
    "You are a read-only macro-investment signal review assistant. "
    "Your job is to present the results of a deterministic signal engine run. "
    "Report exactly what the engine produced — signal counts, dominant "
    "direction, execution metadata — without adding interpretation, opinion, "
    "or investment advice. Never override or contradict the engine output."
)

SIGNAL_REVIEW_HUMAN_TEMPLATE = (
    "Signal review for [{signal_ids}] (country={country}): "
    "{signals_generated} signal(s) generated "
    "(BUY={buy_signals}, SELL={sell_signals}, HOLD={hold_signals}). "
    "Dominant signal direction: {dominant_direction}. "
    "Engine run ID: {engine_run_id}. "
    "Execution time: {execution_time_ms}ms."
)

SIGNAL_REVIEW_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SIGNAL_REVIEW_SYSTEM_MESSAGE),
        ("human", SIGNAL_REVIEW_HUMAN_TEMPLATE),
    ]
)
"""Prompt template for signal review summaries.

Expected variables:

* ``signal_ids`` — comma-separated list of reviewed signal IDs.
* ``country`` — ISO 3166-1 alpha-2 country code.
* ``signals_generated`` — total number of signals produced by the engine.
* ``buy_signals`` — count of BUY signals.
* ``sell_signals`` — count of SELL signals.
* ``hold_signals`` — count of HOLD signals.
* ``dominant_direction`` — ``"BUY"``, ``"SELL"``, ``"HOLD"``, or ``"none"``.
* ``engine_run_id`` — unique ID of the engine run.
* ``execution_time_ms`` — wall-clock time formatted as ``"X.Y"`` (one decimal).
"""

# ---------------------------------------------------------------------------
# Macro snapshot summary
# ---------------------------------------------------------------------------

SNAPSHOT_SUMMARY_SYSTEM_MESSAGE = (
    "You are a read-only macro-investment data assistant. "
    "Your job is to present the contents of a macro-economic snapshot. "
    "Report exactly what data is available — feature count and timestamp — "
    "without adding interpretation, opinion, or investment advice."
)

SNAPSHOT_SUMMARY_HUMAN_TEMPLATE = (
    "Macro snapshot for country={country}: "
    "{features_count} feature(s) available as of {snapshot_timestamp}."
)

SNAPSHOT_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SNAPSHOT_SUMMARY_SYSTEM_MESSAGE),
        ("human", SNAPSHOT_SUMMARY_HUMAN_TEMPLATE),
    ]
)
"""Prompt template for macro snapshot summaries.

Expected variables:

* ``country`` — ISO 3166-1 alpha-2 country code.
* ``features_count`` — number of macro features in the snapshot.
* ``snapshot_timestamp`` — ISO 8601 datetime string or ``"unknown"``.
"""


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def render_signal_review_summary(
    *,
    signal_ids: str,
    country: str,
    signals_generated: int,
    buy_signals: int,
    sell_signals: int,
    hold_signals: int,
    dominant_direction: str,
    engine_run_id: str,
    execution_time_ms: str,
    context_summary: str = "",
) -> str:
    """Render the signal review prompt template and return the human message.

    Extracts the ``human`` message content from the rendered prompt so the
    result is a plain string suitable for the ``summary`` field.  The system
    message is retained in the template for future LLM usage but is not
    included in the rendered summary.

    When *context_summary* is non-empty it is appended to the system message
    as a read-only context hint.  It never overrides or reinterprets tool
    results.

    Returns:
        The rendered human message as a plain string.
    """
    system = SIGNAL_REVIEW_SYSTEM_MESSAGE
    if context_summary:
        system = system + f" [Session context: {context_summary}]"

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", SIGNAL_REVIEW_HUMAN_TEMPLATE),
        ]
    )
    messages = prompt.format_messages(
        signal_ids=signal_ids,
        country=country,
        signals_generated=signals_generated,
        buy_signals=buy_signals,
        sell_signals=sell_signals,
        hold_signals=hold_signals,
        dominant_direction=dominant_direction,
        engine_run_id=engine_run_id,
        execution_time_ms=execution_time_ms,
    )
    # The human message is the last message in the template.
    return str(messages[-1].content)


def render_snapshot_summary(
    *,
    country: str,
    features_count: int,
    snapshot_timestamp: str,
    context_summary: str = "",
) -> str:
    """Render the snapshot summary prompt template and return the human message.

    When *context_summary* is non-empty it is appended to the system message
    as a read-only context hint.

    Returns:
        The rendered human message as a plain string.
    """
    system = SNAPSHOT_SUMMARY_SYSTEM_MESSAGE
    if context_summary:
        system = system + f" [Session context: {context_summary}]"

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", SNAPSHOT_SUMMARY_HUMAN_TEMPLATE),
        ]
    )
    messages = prompt.format_messages(
        country=country,
        features_count=features_count,
        snapshot_timestamp=snapshot_timestamp,
    )
    return str(messages[-1].content)


# ---------------------------------------------------------------------------
# Snapshot comparison
# ---------------------------------------------------------------------------

SNAPSHOT_COMPARISON_SYSTEM_MESSAGE = (
    "You are a read-only macro-investment data assistant. "
    "Your job is to present the results of a deterministic snapshot comparison. "
    "Report exactly what changed — indicator counts, directions — without "
    "adding interpretation, opinion, or investment advice. "
    "Never override or contradict the deterministic comparison output."
)

SNAPSHOT_COMPARISON_HUMAN_TEMPLATE = (
    "Snapshot comparison for country={country} vs prior ({prior_snapshot_label}): "
    "{changed_count} indicator(s) changed, "
    "{unchanged_count} unchanged"
    "{no_prior_suffix}."
)

SNAPSHOT_COMPARISON_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SNAPSHOT_COMPARISON_SYSTEM_MESSAGE),
        ("human", SNAPSHOT_COMPARISON_HUMAN_TEMPLATE),
    ]
)
"""Prompt template for snapshot comparison summaries.

Expected variables:

* ``country`` — ISO 3166-1 alpha-2 country code.
* ``prior_snapshot_label`` — human-readable label for the prior snapshot.
* ``changed_count`` — number of indicators that changed.
* ``unchanged_count`` — number of indicators with no change.
* ``no_prior_suffix`` — extra text for no-prior counts, e.g. ", 2 with no prior data"
  or empty string when no_prior_count == 0.
"""


def render_snapshot_comparison_summary(
    *,
    country: str,
    prior_snapshot_label: str,
    changed_count: int,
    unchanged_count: int,
    no_prior_count: int,
    context_summary: str = "",
) -> str:
    """Render the snapshot comparison prompt template and return the human message.

    When *context_summary* is non-empty it is appended to the system message
    as a read-only context hint.  It never overrides or reinterprets tool
    results.

    Args:
        country: ISO 3166-1 alpha-2 country code.
        prior_snapshot_label: Human-readable label for the prior snapshot.
        changed_count: Number of indicators that changed.
        unchanged_count: Number of indicators with no change.
        no_prior_count: Number of indicators with no prior data.
        context_summary: Optional session context hint.

    Returns:
        The rendered human message as a plain string.
    """
    system = SNAPSHOT_COMPARISON_SYSTEM_MESSAGE
    if context_summary:
        system = system + f" [Session context: {context_summary}]"

    no_prior_suffix = (
        f", {no_prior_count} with no prior data" if no_prior_count > 0 else ""
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", SNAPSHOT_COMPARISON_HUMAN_TEMPLATE),
        ]
    )
    messages = prompt.format_messages(
        country=country,
        prior_snapshot_label=prior_snapshot_label,
        changed_count=changed_count,
        unchanged_count=unchanged_count,
        no_prior_suffix=no_prior_suffix,
    )
    return str(messages[-1].content)
