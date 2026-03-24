from fastapi import Request

from knowledge_graph.db import Neo4jConnection


def get_db(request: Request) -> Neo4jConnection:
    """Return the shared Neo4j connection instance stored on app state."""
    return request.app.state.db


def get_db_optional(request: Request) -> Neo4jConnection | None:
    """Return the Neo4j connection if available, else None."""
    return getattr(request.app.state, "db", None)
