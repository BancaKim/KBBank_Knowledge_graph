"""LangGraph agent state."""
from __future__ import annotations
from typing import Any, Literal
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """State for the banking chatbot agent."""
    # Input
    query: str
    history: list[dict]
    db: Any  # Neo4jConnection

    # Intent classification
    intent: Literal["lookup", "compare", "recommend", "calculate", "general"]
    entities: list[str]  # Extracted product names or keywords

    # Retrieval
    context: str
    referenced_nodes: list[dict]

    # Generation
    answer: str

    # Verification
    verified: bool
