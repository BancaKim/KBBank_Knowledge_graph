"""Neo4j connection manager with context-managed sessions."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

from neo4j import GraphDatabase, Session

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Neo4jConnection:
    """Thin wrapper around the Neo4j Python driver."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.environ.get("NEO4J_USER", "neo4j")
        self._password = password or os.environ.get("NEO4J_PASSWORD")
        if not self._password:
            raise RuntimeError(
                "NEO4J_PASSWORD environment variable is required. "
                "Create a .env file or set it."
            )
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )

    # -- context manager ----------------------------------------------------

    def __enter__(self) -> "Neo4jConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        self.close()

    # -- session helper -----------------------------------------------------

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Yield a Neo4j session and close it automatically."""
        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    # -- query helpers ------------------------------------------------------

    def run_query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a read query using explicit read transaction."""
        params = params or {}
        with self.session() as session:
            def _work(tx):  # noqa: ANN001, ANN202
                result = tx.run(cypher, params)
                return [record.data() for record in result]
            return session.execute_read(_work)

    def run_write(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a write transaction and return a list of record dicts."""
        params = params or {}
        with self.session() as session:

            def _work(tx):  # noqa: ANN001, ANN202
                result = tx.run(cypher, params)
                return [record.data() for record in result]

            return session.execute_write(_work)

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying driver."""
        self._driver.close()
