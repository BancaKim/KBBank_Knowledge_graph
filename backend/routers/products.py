import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_db_optional
from knowledge_graph.db import Neo4jConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["products"])

_STATIC_GRAPH = Path(__file__).resolve().parent.parent.parent / "data" / "graph" / "graph.json"


def _get_static_products(category: Optional[str] = None) -> list[dict]:
    """Load product nodes from static graph.json."""
    if not _STATIC_GRAPH.exists():
        return []
    data = json.loads(_STATIC_GRAPH.read_text(encoding="utf-8"))
    products = [n for n in data.get("nodes", []) if n.get("type") == "product"]
    if category:
        cat_lower = category.lower()
        products = [p for p in products if p.get("data", {}).get("category", "").lower() == cat_lower]
    return sorted(products, key=lambda p: p.get("label", ""))


@router.get("/products")
async def list_products(
    category: Optional[str] = None,
    db: Neo4jConnection | None = Depends(get_db_optional),
):
    """List all products, with optional category filter."""
    try:
        if db is not None:
            from knowledge_graph.query import _row_to_product, get_products_by_category
            if category:
                products = get_products_by_category(db, category)
            else:
                rows = db.run_query("MATCH (p:Product) RETURN properties(p) AS p ORDER BY p.name")
                products = [_row_to_product(r) for r in rows]
            return {"products": [p.model_dump() if hasattr(p, "model_dump") else p for p in products], "total": len(products)}

        # Static fallback
        products = _get_static_products(category)
        return {"products": products, "total": len(products)}
    except Exception as exc:
        logger.exception("Error in list_products")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc


@router.get("/products/{product_id}")
async def product_detail(
    product_id: str,
    db: Neo4jConnection | None = Depends(get_db_optional),
):
    """Return full detail for a single product including all relationships."""
    try:
        if db is not None:
            from knowledge_graph.query import get_product_detail
            detail = get_product_detail(db, product_id)
            if detail is None:
                raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
            return detail

        # Static fallback
        products = _get_static_products()
        for p in products:
            if p.get("id") == product_id:
                return p
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in product_detail")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc


@router.get("/products/{product_id}/compare/{other_id}")
async def compare_two_products(
    product_id: str,
    other_id: str,
    db: Neo4jConnection | None = Depends(get_db_optional),
):
    """Compare two products side by side."""
    try:
        if db is not None:
            from knowledge_graph.query import compare_products
            result = compare_products(db, product_id, other_id)
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"One or both products not found: '{product_id}', '{other_id}'",
                )
            return result

        # Static fallback
        products = {p["id"]: p for p in _get_static_products()}
        a, b = products.get(product_id), products.get(other_id)
        if not a or not b:
            raise HTTPException(status_code=404, detail=f"One or both products not found")
        return {"product_a": a, "product_b": b}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in compare_two_products")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc


@router.get("/products/{product_id}/competitors")
async def product_competitors(
    product_id: str,
    db: Neo4jConnection | None = Depends(get_db_optional),
):
    """Return competing products for the given product."""
    try:
        if db is not None:
            from knowledge_graph.query import get_competing_products
            competitors = get_competing_products(db, product_id)
            return {"product_id": product_id, "competitors": competitors, "total": len(competitors)}

        # Static fallback: products in same category
        products = _get_static_products()
        target = next((p for p in products if p["id"] == product_id), None)
        if not target:
            return {"product_id": product_id, "competitors": [], "total": 0}
        cat = target.get("data", {}).get("category", "")
        competitors = [p for p in products if p["id"] != product_id and p.get("data", {}).get("category") == cat]
        return {"product_id": product_id, "competitors": competitors[:10], "total": len(competitors)}
    except Exception as exc:
        logger.exception("Error in product_competitors")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc


@router.get("/categories")
async def list_categories(db: Neo4jConnection | None = Depends(get_db_optional)):
    """List all product categories with product counts."""
    try:
        if db is not None:
            rows = db.run_query(
                """
                MATCH (c:Category)<-[:BELONGS_TO]-(p:Product)
                RETURN c.name AS category, c.id AS id, count(p) AS product_count
                ORDER BY c.name
                """
            )
            categories = [
                {"id": row.get("id"), "name": row.get("category"), "product_count": row.get("product_count")}
                for row in rows
            ]
            return {"categories": categories, "total": len(categories)}

        # Static fallback
        if not _STATIC_GRAPH.exists():
            return {"categories": [], "total": 0}
        data = json.loads(_STATIC_GRAPH.read_text(encoding="utf-8"))
        cat_nodes = [n for n in data.get("nodes", []) if n.get("type") == "category"]
        links = data.get("links", [])
        categories = []
        for cn in cat_nodes:
            count = sum(1 for lnk in links if lnk.get("target") == cn["id"] and lnk.get("type") == "BELONGS_TO")
            categories.append({"id": cn["id"], "name": cn.get("label", cn["id"]), "product_count": count})
        categories.sort(key=lambda c: c["name"])
        return {"categories": categories, "total": len(categories)}
    except Exception as exc:
        logger.exception("Error in list_categories")
        raise HTTPException(status_code=500, detail="서버 오류가 발생했습니다.") from exc
