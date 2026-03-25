"""Loan-specific search and detail tools for Neo4j LoanProduct nodes.

These tools query :LoanProduct (separate from :Product) with loan-specific
relationships: LoanRate, RepaymentMethod, Collateral, LoanPreferentialRate, LoanFee.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def search_loan_products(query: str, *, db=None) -> str:
    """대출 상품을 검색합니다. 신용대출, 담보대출, 전월세대출, 자동차대출 등을 검색할 때 사용합니다."""
    if db is None:
        return "DB 연결이 필요합니다."
    try:
        results = db.run_query(
            """
            CALL db.index.fulltext.queryNodes('loan_product_search', $query)
            YIELD node, score
            WHERE score > 0.3
            RETURN node.id AS id, node.name AS name, node.loan_type AS loan_type,
                   node.description AS description, node.amount_max_raw AS amount_max,
                   node.eligibility_summary AS eligibility,
                   score
            ORDER BY score DESC
            LIMIT 5
            """,
            {"query": query},
        )
        if not results:
            return f"'{query}'에 해당하는 대출 상품을 찾지 못했습니다."
        lines = []
        for r in results:
            lines.append(
                f"- **{r['name']}** ({r.get('loan_type', '')}) "
                f"| 한도: {r.get('amount_max', '정보없음')} "
                f"| {r.get('description', '')[:80]}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"대출 상품 검색 오류: {exc}"


@tool
def get_loan_product_detail(name: str, *, db=None) -> str:
    """특정 대출 상품의 상세 정보를 조회합니다. 금리, 상환방법, 담보, 수수료, 우대금리, 소비자권리 등을 포함합니다."""
    if db is None:
        return "DB 연결이 필요합니다."
    try:
        results = db.run_query(
            """
            MATCH (lp:LoanProduct)
            WHERE lp.name CONTAINS $name
            OPTIONAL MATCH (lp)-[:BELONGS_TO]->(cat)
            OPTIONAL MATCH (lp)-[:HAS_RATE]->(lr)
            OPTIONAL MATCH (lp)-[:HAS_TERM]->(lt)
            OPTIONAL MATCH (lp)-[:REPAID_VIA]->(rm)
            OPTIONAL MATCH (lp)-[:SECURED_BY]->(col)
            OPTIONAL MATCH (lp)-[:HAS_PREFERENTIAL_RATE]->(lpr)
            OPTIONAL MATCH (lp)-[:HAS_FEE]->(lf)
            OPTIONAL MATCH (lp)-[:AVAILABLE_VIA]->(ch)
            OPTIONAL MATCH (lp)-[:REQUIRES]->(le)
            RETURN lp.name AS name,
                   lp.loan_type AS loan_type,
                   lp.description AS description,
                   lp.amount_max_raw AS amount_max,
                   lp.eligibility_summary AS eligibility,
                   lp.rate_cut_request_available AS rate_cut,
                   lp.contract_withdrawal_available AS contract_withdrawal,
                   lp.illegal_contract_termination AS illegal_termination,
                   cat.name AS category,
                   collect(DISTINCT {base_rate: lr.base_rate_name, min: lr.min_rate, max: lr.max_rate, spread: lr.spread}) AS rates,
                   collect(DISTINCT {min_months: lt.min_months, max_months: lt.max_months}) AS terms,
                   collect(DISTINCT rm.name) AS repayment_methods,
                   collect(DISTINCT {type: col.collateral_type, desc: col.description}) AS collateral,
                   collect(DISTINCT {name: lpr.name, rate: lpr.rate_value_pp, condition: lpr.condition_description}) AS preferential_rates,
                   collect(DISTINCT {type: lf.fee_type, desc: lf.description}) AS fees,
                   collect(DISTINCT ch.name) AS channels,
                   le.description AS eligibility_detail
            LIMIT 1
            """,
            {"name": name},
        )
        if not results:
            return f"'{name}' 대출 상품을 찾지 못했습니다."

        r = results[0]
        lines = [f"# {r['name']}"]
        if r.get("category"):
            lines.append(f"**카테고리**: {r['category']}")
        if r.get("description"):
            lines.append(f"**설명**: {r['description'][:200]}")
        if r.get("amount_max"):
            lines.append(f"**한도**: {r['amount_max']}")

        # 금리 (기준금리별 분리)
        rates = [rate for rate in r.get("rates", []) if rate.get("min") or rate.get("max")]
        if rates:
            lines.append("\n**금리 정보**:")
            for rate in rates:
                base = rate.get("base_rate", "기본")
                mn = rate.get("min", "?")
                mx = rate.get("max", "?")
                spread = rate.get("spread")
                spread_str = f" (가산금리 {spread}%p)" if spread else ""
                lines.append(f"- {base}: 연 {mn}% ~ {mx}%{spread_str}")

        # 상환방법
        methods = [m for m in r.get("repayment_methods", []) if m]
        if methods:
            lines.append(f"\n**상환방법**: {', '.join(methods)}")

        # 담보
        collateral = [c for c in r.get("collateral", []) if c.get("type")]
        if collateral:
            lines.append(f"\n**담보**: {', '.join(c['type'] for c in collateral)}")

        # 우대금리
        prefs = [p for p in r.get("preferential_rates", []) if p.get("name")]
        if prefs:
            lines.append("\n**우대금리**:")
            for p in prefs[:5]:
                lines.append(f"- {p['name']}: {p.get('rate', '?')}%p")

        # 수수료
        fees = [f for f in r.get("fees", []) if f.get("type")]
        if fees:
            lines.append("\n**수수료**:")
            for f in fees:
                lines.append(f"- {f['type']}: {f.get('desc', '')[:80]}")

        # 기간
        terms = [t for t in r.get("terms", []) if t.get("min_months") or t.get("max_months")]
        if terms:
            t = terms[0]
            lines.append(f"\n**대출기간**: {t.get('min_months', '?')}개월 ~ {t.get('max_months', '?')}개월")

        # 채널
        channels = [c for c in r.get("channels", []) if c]
        if channels:
            lines.append(f"\n**가입채널**: {', '.join(channels)}")

        # 소비자 권리
        rights = []
        if r.get("rate_cut"):
            rights.append("금리인하요구권")
        if r.get("contract_withdrawal"):
            rights.append("대출계약철회권")
        if r.get("illegal_termination"):
            rights.append("위법계약해지권")
        if rights:
            lines.append(f"\n**소비자 권리**: {', '.join(rights)}")

        # 가입자격
        if r.get("eligibility_detail"):
            lines.append(f"\n**가입자격**: {r['eligibility_detail'][:200]}")

        return "\n".join(lines)
    except Exception as exc:
        return f"대출 상품 상세 조회 오류: {exc}"


@tool
def get_loan_rates(base_rate_type: str, *, db=None) -> str:
    """특정 기준금리 유형(CD91일물, COFIX, 금융채 등)별 대출 금리를 조회합니다."""
    if db is None:
        return "DB 연결이 필요합니다."
    try:
        results = db.run_query(
            """
            MATCH (lp:LoanProduct)-[:HAS_RATE]->(lr)
            WHERE lr.base_rate_name CONTAINS $base_rate_type
            RETURN lp.name AS product, lr.base_rate_name AS base_rate,
                   lr.min_rate AS min_rate, lr.max_rate AS max_rate,
                   lr.spread AS spread
            ORDER BY lr.min_rate
            LIMIT 20
            """,
            {"base_rate_type": base_rate_type},
        )
        if not results:
            return f"'{base_rate_type}' 기준금리 상품을 찾지 못했습니다."

        lines = [f"## {base_rate_type} 기준 대출 금리"]
        lines.append("| 상품명 | 기준금리 | 최저금리 | 최고금리 | 가산금리 |")
        lines.append("|--------|---------|---------|---------|---------|")
        for r in results:
            spread = f"{r['spread']}%p" if r.get("spread") else "-"
            lines.append(
                f"| {r['product'][:25]} | {r['base_rate']} | "
                f"{r.get('min_rate', '?')}% | {r.get('max_rate', '?')}% | {spread} |"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"금리 조회 오류: {exc}"
