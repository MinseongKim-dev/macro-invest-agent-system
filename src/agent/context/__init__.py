"""Session-scoped, in-memory conversation context for the agent layer.

Public API
----------
.. autoclass:: agent.context.models.AnalysisParameters
.. autoclass:: agent.context.models.ConversationTurn
.. autoclass:: agent.context.models.ConversationContext
.. autoclass:: agent.context.store.InMemoryContextStore
.. autoprotocol:: agent.context.store.ContextStore
"""

from agent.context.models import AnalysisParameters, ConversationContext, ConversationTurn
from agent.context.store import ContextStore, InMemoryContextStore
from agent.context.trimming import (
    extract_recent_summaries,
    keep_successful_only,
    trim_to_max_turns,
)

__all__ = [
    "AnalysisParameters",
    "ConversationContext",
    "ConversationTurn",
    "ContextStore",
    "InMemoryContextStore",
    "extract_recent_summaries",
    "keep_successful_only",
    "trim_to_max_turns",
]
