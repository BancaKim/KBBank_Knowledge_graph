"""Cypher-based query functions for the banking knowledge graph."""

from __future__ import annotations

from typing import Any

from knowledge_graph.db import Neo4jConnection
from knowledge_graph.deposit_models import Product


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_product(row: dict[str, Any]) -> Product:
    """Convert a Neo4j record dict into a Product model (best-effort)."""
    props = row.get("p") or row
    return Product(
        id=props.get("id", ""),
        name=props.get("name", ""),
        product_type=props.get("product_type", ""),
        description=props.get("description", ""),
        amount_max_raw=props.get("amount_max_raw", ""),
        amount_max_won=props.get("amount_max_won"),
        eligibility_summary=props.get("eligibility_summary", ""),
        page_url=props.get("page_url", ""),
        scraped_at=props.get("scraped_at"),
    )


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

def get_products_by_category(conn: Neo4jConnection, category: str) -> list[Product]:
    """Return all products belonging to *category*."""
    rows = conn.run_query(
        """
        MATCH (p:Product)-[:BELONGS_TO]->(c:Category)
        WHERE c.name = $category OR c.id = $category
        RETURN properties(p) AS p
        ORDER BY p.name
        """,
        {"category": category},
    )
    return [_row_to_product(r) for r in rows]


def get_competing_products(conn: Neo4jConnection, product_id: str) -> list[Product]:
    """Return products that compete with the given product."""
    rows = conn.run_query(
        """
        MATCH (a:Product {id: $pid})-[:COMPETES_WITH]-(b:Product)
        RETURN properties(b) AS p
        ORDER BY b.name
        """,
        {"pid": product_id},
    )
    return [_row_to_product(r) for r in rows]


def get_products_by_rate_range(
    conn: Neo4jConnection,
    min_rate: float,
    max_rate: float,
) -> list[Product]:
    """Return products with interest rates in the given range."""
    rows = conn.run_query(
        """
        MATCH (p:Product)-[:HAS_RATE]->(r:InterestRate)
        WHERE r.min_rate IS NOT NULL
          AND r.max_rate IS NOT NULL
          AND r.min_rate <= $max_rate
          AND r.max_rate >= $min_rate
        RETURN properties(p) AS p
        ORDER BY r.min_rate
        """,
        {"min_rate": min_rate, "max_rate": max_rate},
    )
    return [_row_to_product(r) for r in rows]


def search_products(conn: Neo4jConnection, keyword: str) -> list[Product]:
    """Full-text search across product name and description."""
    rows = conn.run_query(
        """
        CALL db.index.fulltext.queryNodes('product_search', $keyword)
        YIELD node, score
        RETURN properties(node) AS p, score
        ORDER BY score DESC
        """,
        {"keyword": keyword},
    )
    return [_row_to_product(r) for r in rows]


def get_product_detail(conn: Neo4jConnection, product_id: str) -> dict[str, Any] | None:
    """Return a product with all its related entities in a single query."""
    rows = conn.run_query(
        """
        MATCH (p:Product {id: $pid})
        CALL { WITH p OPTIONAL MATCH (p)-[:BELONGS_TO]->(c:Category) RETURN collect(properties(c)) AS categories }
        CALL { WITH p OPTIONAL MATCH (p)-[:HAS_FEATURE]->(f:Feature) RETURN collect(properties(f)) AS features }
        CALL { WITH p OPTIONAL MATCH (p)-[:HAS_RATE]->(r:InterestRate) RETURN collect(properties(r)) AS rates }
        CALL { WITH p OPTIONAL MATCH (p)-[:HAS_TERM]->(t:Term) RETURN collect(properties(t)) AS terms }
        CALL { WITH p OPTIONAL MATCH (p)-[:REQUIRES]->(e:EligibilityCondition) RETURN collect(properties(e)) AS eligibility }
        CALL { WITH p OPTIONAL MATCH (p)-[:AVAILABLE_VIA]->(ch:Channel) RETURN collect(properties(ch)) AS channels }
        CALL { WITH p OPTIONAL MATCH (p)-[:REPAID_VIA]->(rm:RepaymentMethod) RETURN collect(properties(rm)) AS repayment_methods }
        CALL { WITH p OPTIONAL MATCH (p)-[:HAS_TAX_BENEFIT]->(tb:TaxBenefit) RETURN collect(properties(tb)) AS tax_benefits }
        CALL { WITH p OPTIONAL MATCH (p)-[:PROTECTED_BY]->(dp:DepositProtection) RETURN collect(properties(dp)) AS deposit_protection }
        CALL { WITH p OPTIONAL MATCH (p)-[:HAS_PREFERENTIAL_RATE]->(pr:PreferentialRate) RETURN collect(properties(pr)) AS preferential_rates }
        CALL { WITH p OPTIONAL MATCH (p)-[:HAS_FEE]->(fee:Fee) RETURN collect(properties(fee)) AS fees }
        CALL { WITH p OPTIONAL MATCH (p)-[:HAS_TYPE]->(pt:ProductType) RETURN collect(properties(pt)) AS product_types }
        CALL { WITH p OPTIONAL MATCH (p)-[:COMPETES_WITH]-(comp:Product) RETURN collect(properties(comp)) AS competitors }
        RETURN properties(p) AS product, categories, features, rates, terms, eligibility,
               channels, repayment_methods, tax_benefits, deposit_protection,
               preferential_rates, fees, product_types, competitors
        """,
        {"pid": product_id},
    )

    if not rows:
        return None

    row = rows[0]
    return {
        "product": row["product"],
        "categories": row["categories"],
        "features": row["features"],
        "rates": row["rates"],
        "terms": row["terms"],
        "eligibility": row["eligibility"],
        "channels": row["channels"],
        "repayment_methods": row["repayment_methods"],
        "tax_benefits": row["tax_benefits"],
        "deposit_protection": row["deposit_protection"],
        "preferential_rates": row["preferential_rates"],
        "fees": row["fees"],
        "product_types": row["product_types"],
        "competitors": row["competitors"],
    }


def compare_products(
    conn: Neo4jConnection,
    id_a: str,
    id_b: str,
) -> dict[str, Any] | None:
    """Side-by-side comparison of two products."""
    detail_a = get_product_detail(conn, id_a)
    detail_b = get_product_detail(conn, id_b)

    if not detail_a or not detail_b:
        return None

    shared_rows = conn.run_query(
        """
        MATCH (a:Product {id: $id_a})-[r]-(b:Product {id: $id_b})
        RETURN type(r) AS rel_type
        """,
        {"id_a": id_a, "id_b": id_b},
    )

    return {
        "product_a": detail_a,
        "product_b": detail_b,
        "shared_relationships": [r["rel_type"] for r in shared_rows],
        "same_category": detail_a.get("product", {}).get("product_type")
        == detail_b.get("product", {}).get("product_type"),
    }


def get_graph_stats(conn: Neo4jConnection) -> dict[str, Any]:
    """Return aggregate statistics about the knowledge graph."""
    node_counts = conn.run_query(
        """
        MATCH (n)
        WITH labels(n) AS lbls
        UNWIND lbls AS lbl
        RETURN lbl AS label, count(*) AS count
        ORDER BY count DESC
        """
    )

    rel_counts = conn.run_query(
        """
        MATCH ()-[r]->()
        RETURN type(r) AS type, count(*) AS count
        ORDER BY count DESC
        """
    )

    total_nodes = conn.run_query("MATCH (n) RETURN count(n) AS cnt")
    total_rels = conn.run_query("MATCH ()-[r]->() RETURN count(r) AS cnt")

    return {
        "total_nodes": total_nodes[0]["cnt"] if total_nodes else 0,
        "total_relationships": total_rels[0]["cnt"] if total_rels else 0,
        "nodes_by_label": {r["label"]: r["count"] for r in node_counts},
        "relationships_by_type": {r["type"]: r["count"] for r in rel_counts},
    }
