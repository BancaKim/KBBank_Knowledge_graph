import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import graph, products, search, chat

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: try to initialize Neo4j connection (graceful fallback if unavailable)
    try:
        from knowledge_graph.db import Neo4jConnection
        db = Neo4jConnection()
        db.run_query("RETURN 1")
        app.state.db = db
        logger.info("Neo4j connected successfully")
    except Exception as exc:
        logger.warning("Neo4j unavailable, running in static-graph mode: %s", exc)
        app.state.db = None
    yield
    # Shutdown: close Neo4j connection if present
    if getattr(app.state, "db", None) is not None:
        app.state.db.close()


app = FastAPI(
    title="Banking Bot API",
    description="Backend API serving knowledge graph data for the banking bot",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(graph.router)
app.include_router(products.router)
app.include_router(search.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    """Health check endpoint that verifies database connectivity."""
    db = getattr(app.state, "db", None)
    if db is None:
        return {"status": "ok", "mode": "static-graph", "neo4j": False}
    try:
        db.run_query("RETURN 1")
        return {"status": "ok", "mode": "neo4j", "neo4j": True}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")


def run():
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()
