import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.dependencies import get_db_optional
from knowledge_graph.db import Neo4jConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])

_STATIC_GRAPH = Path(__file__).resolve().parent.parent.parent / "data" / "graph" / "graph.json"


@router.get("")
async def search(
    q: str = Query(..., min_length=1, description="Search query string"),
    category: Optional[str] = None,
    db: Neo4jConnection | None = Depends(get_db_optional),
):
    """
    Keyword search across products.
    Optionally filter results by category.
    Returns a list of matching products with relevance scores.
    """
    try:
        if db is not None:
            from knowledge_graph.query import search_products
            results = search_products(db, q)
            if category:
                results = [
                    r for r in results
                    if hasattr(r, "product_type") and r.product_type == category
                ]
            return {
                "query": q,
                "category": category,
                "results": [r.model_dump() if hasattr(r, "model_dump") else r for r in results],
                "total": len(results),
            }

        # Static fallback: simple keyword search on product nodes
        if not _STATIC_GRAPH.exists():
            return {"query": q, "category": category, "results": [], "total": 0}
        data = json.loads(_STATIC_GRAPH.read_text(encoding="utf-8"))
        q_lower = q.lower()
        results = []
        for n in data.get("nodes", []):
            if n.get("type") != "product":
                continue
            searchable = (
                n.get("label", "") + " " +
                n.get("data", {}).get("description", "") + " " +
                n.get("data", {}).get("category", "") + " " +
                n.get("data", {}).get("eligibility_summary", "")
            ).lower()
            if q_lower in searchable:
                if category and n.get("data", {}).get("category", "").lower() != category.lower():
                    continue
                results.append(n)
        return {"query": q, "category": category, "results": results, "total": len(results)}
    except Exception as exc:
        logger.exception("Error in search")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc
