import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers import graph, products, search, chat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Banking Bot API...")
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

cors_origins = [
    "http://localhost:5173",
    "http://localhost:8000",
]
external_url = os.environ.get("EXTERNAL_URL")
if external_url:
    cors_origins.append(external_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-OpenAI-Key"],
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


# --- Static frontend serving (production) ---
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve frontend SPA — any non-API route returns index.html."""
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")


def run():
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run()
