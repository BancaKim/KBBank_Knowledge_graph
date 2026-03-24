"""GraphRAG chatbot - delegates to LangGraph agent.

This module is kept as a thin shim so that existing imports
(``from backend.chatbot import chat``) continue to work.
"""
from backend.agent.graph import chat  # noqa: F401

__all__ = ["chat"]
