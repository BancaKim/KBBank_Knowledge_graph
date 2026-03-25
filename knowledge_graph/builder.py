"""Build the Neo4j knowledge graph from parsed product data."""

from __future__ import annotations

from pathlib import Path

from knowledge_graph.db import Neo4jConnection
from knowledge_graph.parser import ParsedProduct, parse_all_products

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRODUCTS_DIR = _PROJECT_ROOT / "data" / "products"
_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.cypher"


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def _init_schema(conn: Neo4jConnection) -> None:
    """Run every statement in schema.cypher against Neo4j."""
    # Clean up stale constraints from old schema
    stale = [
        "DROP CONSTRAINT condition_id IF EXISTS",
        "DROP CONSTRAINT rate_id IF EXISTS",
        "DROP CONSTRAINT risklevel_id IF EXISTS",
        "DROP INDEX condition_type_idx IF EXISTS",
        "DROP INDEX rate_type_idx IF EXISTS",
        "DROP INDEX product_rate_type IF EXISTS",
        "DROP INDEX product_risk_level IF EXISTS",
    ]
    for stmt in stale:
        try:
            conn.run_write(stmt)
        except Exception:  # noqa: BLE001
            pass

    text = _SCHEMA_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        stmt = line.strip()
        if not stmt or stmt.startswith("//"):
            continue
        try:
            conn.run_write(stmt)
        except Exception as exc:  # noqa: BLE001
            # Constraints/indexes may already exist - skip gracefully.
            print(f"[builder] schema note: {exc}")


# ---------------------------------------------------------------------------
# Node MERGE helpers (idempotent)
# ---------------------------------------------------------------------------

def _merge_product(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product is None:
        return
    prod = p.product
    conn.run_write(
        """
        MERGE (p:Product {id: $id})
        SET p.name               = $name,
            p.product_type       = $product_type,
            p.category           = $category,
            p.description        = $description,
            p.amount_max_raw     = $amount_max_raw,
            p.amount_max_won     = $amount_max_won,
            p.eligibility_summary = $eligibility_summary,
            p.page_url           = $page_url,
            p.scraped_at         = $scraped_at
        """,
        {
            "id": prod.id,
            "name": prod.name,
            "product_type": prod.product_type,
            "category": p.category.name if p.category else "",
            "description": prod.description,
            "amount_max_raw": prod.amount_max_raw,
            "amount_max_won": prod.amount_max_won,
            "eligibility_summary": prod.eligibility_summary,
            "page_url": prod.page_url,
            "scraped_at": prod.scraped_at.isoformat() if prod.scraped_at else None,
        },
    )


def _merge_category(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.category is None or p.product is None:
        return
    cat = p.category
    conn.run_write(
        """
        MERGE (c:Category {id: $id})
        SET c.name    = $name,
            c.name_en = $name_en
        WITH c
        MATCH (p:Product {id: $pid})
        MERGE (p)-[:BELONGS_TO]->(c)
        """,
        {"id": cat.id, "name": cat.name, "name_en": cat.name_en, "pid": p.product.id},
    )


def _merge_features(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product is None:
        return
    for feat in p.features:
        conn.run_write(
            """
            MERGE (f:Feature {id: $fid})
            SET f.name        = $name,
                f.description = $description
            WITH f
            MATCH (p:Product {id: $pid})
            MERGE (p)-[:HAS_FEATURE]->(f)
            """,
            {"fid": feat.id, "name": feat.name, "description": feat.description, "pid": p.product.id},
        )


def _merge_rates(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product is None:
        return
    for rate in p.rates:
        conn.run_write(
            """
            MERGE (r:InterestRate {id: $rid})
            SET r.name           = $name,
                r.rate_type      = $rate_type,
                r.min_rate       = $min_rate,
                r.max_rate       = $max_rate,
                r.base_rate_name = $base_rate_name,
                r.spread         = $spread
            WITH r
            MATCH (p:Product {id: $pid})
            MERGE (p)-[:HAS_RATE]->(r)
            """,
            {
                "rid": rate.id,
                "name": f"{p.product.name} 금리" if p.product else "금리",
                "rate_type": rate.rate_type,
                "min_rate": rate.min_rate,
                "max_rate": rate.max_rate,
                "base_rate_name": rate.base_rate_name,
                "spread": rate.spread,
                "pid": p.product.id,
            },
        )


def _merge_terms(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product is None:
        return
    for term in p.terms:
        conn.run_write(
            """
            MERGE (t:Term {id: $tid})
            SET t.name       = $name,
                t.min_months = $min_months,
                t.max_months = $max_months,
                t.raw_text   = $raw_text
            WITH t
            MATCH (p:Product {id: $pid})
            MERGE (p)-[:HAS_TERM]->(t)
            """,
            {
                "tid": term.id,
                "name": term.raw_text or f"{term.min_months or '?'}~{term.max_months or '?'}개월",
                "min_months": term.min_months,
                "max_months": term.max_months,
                "raw_text": term.raw_text,
                "pid": p.product.id,
            },
        )


def _merge_eligibility(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.eligibility is None or p.product is None:
        return
    ec = p.eligibility
    conn.run_write(
        """
        MERGE (e:EligibilityCondition {id: $eid})
        SET e.name            = $name,
            e.description     = $description,
            e.min_age         = $min_age,
            e.target_audience = $target_audience
        WITH e
        MATCH (p:Product {id: $pid})
        MERGE (p)-[:REQUIRES]->(e)
        """,
        {
            "eid": ec.id,
            "name": (ec.target_audience or "가입자격") + (f" 만{ec.min_age}세이상" if ec.min_age else ""),
            "description": ec.description,
            "min_age": ec.min_age,
            "target_audience": ec.target_audience,
            "pid": p.product.id,
        },
    )


def _merge_channels(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product is None:
        return
    for ch in p.channels:
        conn.run_write(
            """
            MERGE (ch:Channel {id: $chid})
            SET ch.name    = $name,
                ch.name_en = $name_en
            WITH ch
            MATCH (p:Product {id: $pid})
            MERGE (p)-[:AVAILABLE_VIA]->(ch)
            """,
            {"chid": ch.id, "name": ch.name, "name_en": ch.name_en, "pid": p.product.id},
        )


def _merge_benefits(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product is None:
        return
    for benefit in p.benefits:
        conn.run_write(
            """
            MERGE (b:Benefit {id: $bid})
            SET b.name          = $name,
                b.benefit_type  = $benefit_type,
                b.description   = $description
            WITH b
            MATCH (p:Product {id: $pid})
            MERGE (p)-[:HAS_BENEFIT]->(b)
            """,
            {"bid": benefit.id, "name": benefit.name, "benefit_type": benefit.benefit_type, "description": benefit.description, "pid": p.product.id},
        )


def _merge_tax_benefit(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.tax_benefit is None or p.product is None:
        return
    tb = p.tax_benefit
    conn.run_write(
        """
        MERGE (tb:TaxBenefit {id: $tbid})
        SET tb.name        = $name,
            tb.type        = $type,
            tb.eligible    = $eligible,
            tb.description = $description
        WITH tb
        MATCH (p:Product {id: $pid})
        MERGE (p)-[:HAS_TAX_BENEFIT]->(tb)
        """,
        {
            "tbid": tb.id,
            "name": tb.type + (" 가능" if tb.eligible else " 불가"),
            "type": tb.type,
            "eligible": tb.eligible,
            "description": tb.description,
            "pid": p.product.id,
        },
    )


def _merge_deposit_protection(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.deposit_protection is None or p.product is None:
        return
    dp = p.deposit_protection
    conn.run_write(
        """
        MERGE (dp:DepositProtection {id: $dpid})
        SET dp.name           = $name,
            dp.protected      = $protected,
            dp.max_amount_won = $max_amount_won,
            dp.description    = $description
        WITH dp
        MATCH (p:Product {id: $pid})
        MERGE (p)-[:PROTECTED_BY]->(dp)
        """,
        {
            "dpid": dp.id,
            "name": "예금자보호 " + ("1억원" if dp.max_amount_won else "해당"),
            "protected": dp.protected,
            "max_amount_won": dp.max_amount_won,
            "description": dp.description,
            "pid": p.product.id,
        },
    )


def _merge_preferential_rates(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product is None:
        return
    for pr in p.preferential_rates:
        conn.run_write(
            """
            MERGE (pr:PreferentialRate {id: $prid})
            SET pr.name                  = $name,
                pr.condition_description = $condition_description,
                pr.rate_value_pp         = $rate_value_pp
            WITH pr
            MATCH (p:Product {id: $pid})
            MERGE (p)-[:HAS_PREFERENTIAL_RATE]->(pr)
            """,
            {
                "prid": pr.id,
                "name": pr.name,
                "condition_description": pr.condition_description,
                "rate_value_pp": pr.rate_value_pp,
                "pid": p.product.id,
            },
        )



def _merge_product_type(conn: Neo4jConnection, p: ParsedProduct) -> None:
    if p.product_type is None or p.product is None:
        return
    pt = p.product_type
    conn.run_write(
        """
        MERGE (pt:ProductType {id: $ptid})
        SET pt.name = $name
        WITH pt
        MATCH (p:Product {id: $pid})
        MERGE (p)-[:HAS_TYPE]->(pt)
        """,
        {"ptid": pt.id, "name": pt.name, "pid": p.product.id},
    )


# ---------------------------------------------------------------------------
# Category hierarchy
# ---------------------------------------------------------------------------

def _create_category_hierarchy(conn: Neo4jConnection) -> None:
    """Create parent categories and link sub-categories to them."""
    hierarchy = {
        "예금": {
            "name_en": "Deposits",
            "subcategories": ["입출금통장", "정기예금", "적금", "청약"],
        },
    }

    for parent_name, info in hierarchy.items():
        parent_id = f"parent__{parent_name}"
        conn.run_write(
            """
            MERGE (pc:ParentCategory {id: $id})
            SET pc.name    = $name,
                pc.name_en = $name_en
            """,
            {"id": parent_id, "name": parent_name, "name_en": info["name_en"]},
        )

        # Link subcategories
        for sub_name in info["subcategories"]:
            conn.run_write(
                """
                MATCH (pc:ParentCategory {id: $parent_id})
                MATCH (sc:Category {name: $sub_name})
                MERGE (pc)-[:HAS_SUBCATEGORY]->(sc)
                """,
                {"parent_id": parent_id, "sub_name": sub_name},
            )


# ---------------------------------------------------------------------------
# Inferred relationships
# ---------------------------------------------------------------------------

def _infer_competes_with(conn: Neo4jConnection) -> None:
    """Products compete if same category AND same product type."""
    conn.run_write(
        """
        MATCH (a:Product)-[:BELONGS_TO]->(c:Category)<-[:BELONGS_TO]-(b:Product)
        WHERE a.id < b.id
          AND a.product_type = b.product_type
        MERGE (a)-[:COMPETES_WITH]->(b)
        """
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_graph(conn: Neo4jConnection, products_dir: Path | None = None) -> None:
    """Run the full build pipeline against an existing connection."""
    products_dir = products_dir or _PRODUCTS_DIR

    print("[builder] initializing schema ...")
    _init_schema(conn)

    print(f"[builder] parsing products from {products_dir} ...")
    parsed_products = parse_all_products(products_dir)
    print(f"[builder] found {len(parsed_products)} product file(s)")

    for idx, pp in enumerate(parsed_products, 1):
        name = pp.product.name if pp.product else "(unknown)"
        print(f"[builder] ({idx}/{len(parsed_products)}) merging: {name}")
        _merge_product(conn, pp)
        _merge_category(conn, pp)
        _merge_features(conn, pp)
        _merge_rates(conn, pp)
        _merge_terms(conn, pp)
        _merge_eligibility(conn, pp)
        _merge_channels(conn, pp)
        _merge_tax_benefit(conn, pp)
        _merge_deposit_protection(conn, pp)
        _merge_preferential_rates(conn, pp)
        _merge_benefits(conn, pp)
        _merge_product_type(conn, pp)

    print("[builder] creating category hierarchy ...")
    _create_category_hierarchy(conn)

    print("[builder] inferring COMPETES_WITH relationships ...")
    _infer_competes_with(conn)

    print("[builder] done.")


def build_all(conn: Neo4jConnection) -> None:
    """Build both deposit and loan graphs in the same Aura DB."""
    from knowledge_graph.loan_builder import build_loan_graph

    build_graph(conn)
    build_loan_graph(conn)
    print("[builder] === all graphs (deposit + loan) built ===")


def main() -> None:
    """Entry point for ``build-graph`` console script.

    Builds deposit graph by default. Pass --all to include loans.
    """
    import sys

    with Neo4jConnection() as conn:
        if "--all" in sys.argv:
            build_all(conn)
        elif "--loan" in sys.argv:
            from knowledge_graph.loan_builder import build_loan_graph
            build_loan_graph(conn)
        else:
            build_graph(conn)


if __name__ == "__main__":
    main()
