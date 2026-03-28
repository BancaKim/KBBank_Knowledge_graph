"""Build Neo4j loan knowledge graph from parsed loan product data.

Loan nodes use :LoanProduct label to coexist with :DepositProduct
in the same Aura DB. Shared nodes (Channel) are reused.
"""

from __future__ import annotations

from pathlib import Path

from knowledge_graph.db import Neo4jConnection
from knowledge_graph.loan_parser import ParsedLoanProduct, parse_all_loan_products

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Scan all loan-related directories (대출, 담보대출, etc.)
_LOAN_BASE = _PROJECT_ROOT / "data" / "products"
_LOAN_SCHEMA_FILE = Path(__file__).resolve().parent / "loan_schema.cypher"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _init_loan_schema(conn: Neo4jConnection) -> None:
    """Run loan schema constraints/indexes."""
    if _LOAN_SCHEMA_FILE.exists():
        text = _LOAN_SCHEMA_FILE.read_text(encoding="utf-8")
        for line in text.splitlines():
            stmt = line.strip()
            if not stmt or stmt.startswith("//"):
                continue
            try:
                conn.run_write(stmt)
            except Exception as exc:  # noqa: BLE001
                print(f"[loan_builder] schema note: {exc}")


# ---------------------------------------------------------------------------
# Node MERGE helpers
# ---------------------------------------------------------------------------

def _merge_loan_product(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None:
        return
    prod = p.product
    conn.run_write(
        """
        MERGE (lp:LoanProduct {id: $id})
        SET lp.name                              = $name,
            lp.loan_type                         = $loan_type,
            lp.description                       = $description,
            lp.amount_max_raw                    = $amount_max_raw,
            lp.amount_max_won                    = $amount_max_won,
            lp.eligibility_summary               = $eligibility_summary,
            lp.page_url                          = $page_url,
            lp.scraped_at                        = $scraped_at,
            lp.rate_cut_request_available        = $rate_cut,
            lp.contract_withdrawal_available     = $contract_withdrawal,
            lp.illegal_contract_termination      = $illegal_termination
        """,
        {
            "id": prod.id,
            "name": prod.name,
            "loan_type": prod.loan_type,
            "description": prod.description,
            "amount_max_raw": prod.amount_max_raw,
            "amount_max_won": prod.amount_max_won,
            "eligibility_summary": prod.eligibility_summary,
            "page_url": prod.page_url,
            "scraped_at": prod.scraped_at.isoformat() if prod.scraped_at else None,
            "rate_cut": prod.rate_cut_request_available,
            "contract_withdrawal": prod.contract_withdrawal_available,
            "illegal_termination": prod.illegal_contract_termination,
        },
    )


def _merge_loan_category(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.category is None or p.product is None:
        return
    cat = p.category
    conn.run_write(
        """
        MERGE (lc:LoanCategory {id: $id})
        SET lc.name    = $name,
            lc.name_en = $name_en
        WITH lc
        MATCH (lp:LoanProduct {id: $pid})
        MERGE (lp)-[:BELONGS_TO]->(lc)
        """,
        {"id": cat.id, "name": cat.name, "name_en": cat.name_en, "pid": p.product.id},
    )


def _merge_loan_rates(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None:
        return
    for rate in p.rates:
        conn.run_write(
            """
            MERGE (lr:LoanRate {id: $rid})
            SET lr.rate_type      = $rate_type,
                lr.min_rate       = $min_rate,
                lr.max_rate       = $max_rate,
                lr.base_rate_name = $base_rate_name,
                lr.spread         = $spread,
                lr.rate_example   = $rate_example
            WITH lr
            MATCH (lp:LoanProduct {id: $pid})
            MERGE (lp)-[:HAS_RATE]->(lr)
            """,
            {
                "rid": rate.id,
                "rate_type": rate.rate_type,
                "min_rate": rate.min_rate,
                "max_rate": rate.max_rate,
                "base_rate_name": rate.base_rate_name,
                "spread": rate.spread,
                "rate_example": rate.rate_example,
                "pid": p.product.id,
            },
        )


def _merge_loan_terms(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None:
        return
    for term in p.terms:
        conn.run_write(
            """
            MERGE (lt:LoanTerm {id: $tid})
            SET lt.min_months = $min_months,
                lt.max_months = $max_months,
                lt.raw_text   = $raw_text
            WITH lt
            MATCH (lp:LoanProduct {id: $pid})
            MERGE (lp)-[:HAS_TERM]->(lt)
            """,
            {
                "tid": term.id,
                "min_months": term.min_months,
                "max_months": term.max_months,
                "raw_text": term.raw_text,
                "pid": p.product.id,
            },
        )


def _merge_loan_eligibility(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.eligibility is None or p.product is None:
        return
    ec = p.eligibility
    conn.run_write(
        """
        MERGE (le:LoanEligibility {id: $eid})
        SET le.description     = $description,
            le.target_audience = $target_audience,
            le.min_income      = $min_income,
            le.required_docs   = $required_docs
        WITH le
        MATCH (lp:LoanProduct {id: $pid})
        MERGE (lp)-[:REQUIRES]->(le)
        """,
        {
            "eid": ec.id,
            "description": ec.description,
            "target_audience": ec.target_audience,
            "min_income": ec.min_income,
            "required_docs": ec.required_docs,
            "pid": p.product.id,
        },
    )


def _merge_loan_channels(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    """Reuse shared :Channel nodes from deposit graph."""
    if p.product is None:
        return
    for ch in p.channels:
        conn.run_write(
            """
            MERGE (ch:Channel {id: $chid})
            SET ch.name    = $name,
                ch.name_en = $name_en
            WITH ch
            MATCH (lp:LoanProduct {id: $pid})
            MERGE (lp)-[:AVAILABLE_VIA]->(ch)
            """,
            {"chid": ch.id, "name": ch.name, "name_en": ch.name_en, "pid": p.product.id},
        )


def _merge_repayment_methods(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None:
        return
    for rm in p.repayment_methods:
        conn.run_write(
            """
            MERGE (rm:RepaymentMethod {id: $rmid})
            SET rm.name        = $name,
                rm.description = $description
            WITH rm
            MATCH (lp:LoanProduct {id: $pid})
            MERGE (lp)-[:REPAID_VIA]->(rm)
            """,
            {"rmid": rm.id, "name": rm.name, "description": rm.description, "pid": p.product.id},
        )


def _merge_loan_fees(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None:
        return
    for fee in p.fees:
        conn.run_write(
            """
            MERGE (lf:LoanFee {id: $fid})
            SET lf.fee_type    = $fee_type,
                lf.description = $description
            WITH lf
            MATCH (lp:LoanProduct {id: $pid})
            MERGE (lp)-[:HAS_FEE]->(lf)
            """,
            {"fid": fee.id, "fee_type": fee.fee_type, "description": fee.description, "pid": p.product.id},
        )


def _merge_loan_preferential_rates(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None:
        return
    for pr in p.preferential_rates:
        conn.run_write(
            """
            MERGE (lpr:LoanPreferentialRate {id: $prid})
            SET lpr.name                  = $name,
                lpr.condition_description = $condition_description,
                lpr.rate_value_pp         = $rate_value_pp
            WITH lpr
            MATCH (lp:LoanProduct {id: $pid})
            MERGE (lp)-[:HAS_PREFERENTIAL_RATE]->(lpr)
            """,
            {
                "prid": pr.id,
                "name": pr.name,
                "condition_description": pr.condition_description,
                "rate_value_pp": pr.rate_value_pp,
                "pid": p.product.id,
            },
        )


def _merge_collateral(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.collateral is None or p.product is None:
        return
    col = p.collateral
    conn.run_write(
        """
        MERGE (c:Collateral {id: $cid})
        SET c.collateral_type = $collateral_type,
            c.description     = $description
        WITH c
        MATCH (lp:LoanProduct {id: $pid})
        MERGE (lp)-[:SECURED_BY]->(c)
        """,
        {
            "cid": col.id,
            "collateral_type": col.collateral_type,
            "description": col.description,
            "pid": p.product.id,
        },
    )


def _merge_penalty_rate(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None or p.penalty_rate is None:
        return
    pr = p.penalty_rate
    conn.run_write(
        """
        MERGE (pr:PenaltyRate {id: $prid})
        SET pr.max_rate       = $max_rate,
            pr.penalty_spread = $penalty_spread,
            pr.description    = $description
        WITH pr
        MATCH (lp:LoanProduct {id: $pid})
        MERGE (lp)-[:HAS_PENALTY_RATE]->(pr)
        """,
        {
            "prid": pr.id,
            "max_rate": pr.max_rate,
            "penalty_spread": pr.penalty_spread,
            "description": pr.description,
            "pid": p.product.id,
        },
    )


def _merge_term_extension(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None or p.term_extension is None:
        return
    te = p.term_extension
    conn.run_write(
        """
        MERGE (te:TermExtension {id: $teid})
        SET te.available   = $available,
            te.description = $description
        WITH te
        MATCH (lp:LoanProduct {id: $pid})
        MERGE (lp)-[:HAS_TERM_EXTENSION]->(te)
        """,
        {
            "teid": te.id,
            "available": te.available,
            "description": te.description,
            "pid": p.product.id,
        },
    )


def _merge_overdraft(conn: Neo4jConnection, p: ParsedLoanProduct) -> None:
    if p.product is None or p.overdraft is None:
        return
    od = p.overdraft
    conn.run_write(
        """
        MERGE (od:Overdraft {id: $odid})
        SET od.available   = $available,
            od.max_text    = $max_text,
            od.description = $description
        WITH od
        MATCH (lp:LoanProduct {id: $pid})
        MERGE (lp)-[:HAS_OVERDRAFT]->(od)
        """,
        {
            "odid": od.id,
            "available": od.available,
            "max_text": od.max_text,
            "description": od.description,
            "pid": p.product.id,
        },
    )


# ---------------------------------------------------------------------------
# Category hierarchy
# ---------------------------------------------------------------------------

def _create_loan_category_hierarchy(conn: Neo4jConnection) -> None:
    """Create parent 대출 category and link sub-categories."""
    conn.run_write(
        """
        MERGE (pc:ParentCategory {id: 'parent__대출'})
        SET pc.name    = '대출',
            pc.name_en = 'Loans'
        """
    )
    for sub_name in ["신용대출", "담보대출", "전월세대출", "자동차대출", "집단중도금_이주비대출", "주택도시기금대출", "개인사업자대출"]:
        conn.run_write(
            """
            MATCH (pc:ParentCategory {id: 'parent__대출'})
            MATCH (lc:LoanCategory {name: $sub_name})
            MERGE (pc)-[:HAS_SUBCATEGORY]->(lc)
            """,
            {"sub_name": sub_name},
        )


# ---------------------------------------------------------------------------
# Inferred relationships
# ---------------------------------------------------------------------------

def _infer_loan_competes_with(conn: Neo4jConnection) -> None:
    """Loan products compete if same category and same loan type."""
    conn.run_write(
        """
        MATCH (a:LoanProduct)-[:BELONGS_TO]->(c:LoanCategory)<-[:BELONGS_TO]-(b:LoanProduct)
        WHERE a.id < b.id
          AND a.loan_type = b.loan_type
        MERGE (a)-[:COMPETES_WITH]->(b)
        """
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_loan_graph(conn: Neo4jConnection, loan_dirs: list[Path] | None = None) -> None:
    """Run the full loan build pipeline across all loan directories."""
    if loan_dirs is None:
        # Auto-discover loan directories
        loan_dirs = []
        for d in sorted(_LOAN_BASE.iterdir()):
            if d.is_dir() and d.name in ("대출", "담보대출"):
                loan_dirs.append(d)
        if not loan_dirs:
            loan_dirs = [_LOAN_BASE / "대출"]

    print("[loan_builder] initializing loan schema ...")
    _init_loan_schema(conn)

    parsed: list[ParsedLoanProduct] = []
    for loan_dir in loan_dirs:
        print(f"[loan_builder] parsing loan products from {loan_dir} ...")
        parsed.extend(parse_all_loan_products(loan_dir))
    print(f"[loan_builder] found {len(parsed)} loan product(s) total")

    for idx, pp in enumerate(parsed, 1):
        name = pp.product.name if pp.product else "(unknown)"
        print(f"[loan_builder] ({idx}/{len(parsed)}) merging: {name}")
        _merge_loan_product(conn, pp)
        _merge_loan_category(conn, pp)
        _merge_loan_rates(conn, pp)
        _merge_loan_terms(conn, pp)
        _merge_loan_eligibility(conn, pp)
        _merge_loan_channels(conn, pp)
        _merge_repayment_methods(conn, pp)
        _merge_loan_fees(conn, pp)
        _merge_loan_preferential_rates(conn, pp)
        _merge_collateral(conn, pp)
        _merge_penalty_rate(conn, pp)
        _merge_term_extension(conn, pp)
        _merge_overdraft(conn, pp)

    print("[loan_builder] creating loan category hierarchy ...")
    _create_loan_category_hierarchy(conn)

    print("[loan_builder] inferring loan COMPETES_WITH ...")
    _infer_loan_competes_with(conn)

    print("[loan_builder] done.")


def main() -> None:
    """Entry point for loan graph build."""
    with Neo4jConnection() as conn:
        build_loan_graph(conn)


if __name__ == "__main__":
    main()
