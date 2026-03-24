import json
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_db_optional
from knowledge_graph.db import Neo4jConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/graph", tags=["graph"])

# Simple in-memory cache for graph export
_graph_cache: dict = {"data": None, "timestamp": 0}
CACHE_TTL = 300  # 5 minutes

_STATIC_GRAPH = Path(__file__).resolve().parent.parent.parent / "data" / "graph" / "graph.json"


def _load_graph_data(db: Neo4jConnection | None) -> dict:
    """Load graph data from Neo4j (if available) or static graph.json fallback."""
    # Try Neo4j first
    if db is not None:
        try:
            from knowledge_graph.exporter import export_graph
            output_path = export_graph(db)
            return json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Neo4j export failed, falling back to static file: %s", exc)

    # Fallback: static graph.json
    if _STATIC_GRAPH.exists():
        return json.loads(_STATIC_GRAPH.read_text(encoding="utf-8"))

    return {"nodes": [], "links": [], "metadata": {}}


@router.get("")
async def get_graph(
    category: Optional[str] = None,
    node_type: Optional[str] = None,
    db: Neo4jConnection | None = Depends(get_db_optional),
):
    """Return the full graph (nodes + links). Optionally filter by category or node_type."""
    try:
        now = time.time()
        if _graph_cache["data"] is None or now - _graph_cache["timestamp"] > CACHE_TTL:
            _graph_cache["data"] = _load_graph_data(db)
            _graph_cache["timestamp"] = now

        graph_data = _graph_cache["data"]
        nodes = list(graph_data.get("nodes", []))
        links = list(graph_data.get("links", []))
        metadata = graph_data.get("metadata", {})

        if category:
            # Keep only nodes that match the category (or are linked to matching product nodes)
            category_lower = category.lower()
            matching_node_ids = {
                n["id"]
                for n in nodes
                if n.get("category", "").lower() == category_lower
                or n.get("properties", {}).get("category", "").lower() == category_lower
            }
            nodes = [
                n
                for n in nodes
                if n["id"] in matching_node_ids
                or n.get("category", "").lower() == category_lower
            ]
            node_ids = {n["id"] for n in nodes}
            links = [
                lnk
                for lnk in links
                if lnk.get("source") in node_ids and lnk.get("target") in node_ids
            ]

        if node_type:
            node_type_lower = node_type.lower()
            nodes = [
                n
                for n in nodes
                if n.get("type", "").lower() == node_type_lower
                or n.get("label", "").lower() == node_type_lower
            ]
            node_ids = {n["id"] for n in nodes}
            links = [
                lnk
                for lnk in links
                if lnk.get("source") in node_ids and lnk.get("target") in node_ids
            ]

        return {"nodes": nodes, "links": links, "metadata": metadata}
    except Exception as exc:
        logger.exception("Error in get_graph")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc


@router.get("/stats")
async def graph_stats(db: Neo4jConnection | None = Depends(get_db_optional)):
    """Return aggregate statistics about the knowledge graph."""
    try:
        if db is not None:
            from knowledge_graph.query import get_graph_stats
            stats = get_graph_stats(db)
            return stats
        # Fallback: compute stats from static graph.json
        graph_data = _load_graph_data(None)
        return graph_data.get("metadata", {}).get("stats", {})
    except Exception as exc:
        logger.exception("Error in graph_stats")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc
