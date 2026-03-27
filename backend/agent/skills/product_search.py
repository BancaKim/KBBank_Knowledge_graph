"""Product search and detail skill."""
from langchain_core.tools import tool


@tool
def get_product_detail(product_name: str, db=None) -> str:
    """특정 금융상품의 상세 정보를 조회합니다.

    Args:
        product_name: 상품 이름 (예: "비상금대출", "정기예금")
    """
    from knowledge_graph.db import Neo4jConnection
    conn = db or Neo4jConnection()
    try:
        result = conn.run_query("""
            MATCH (p:Product)
            WHERE p.name CONTAINS $name
            OPTIONAL MATCH (p)-[:BELONGS_TO]->(c:Category)
            OPTIONAL MATCH (p)-[:HAS_RATE]->(r:InterestRate)
            OPTIONAL MATCH (p)-[:HAS_TERM]->(t:Term)
            OPTIONAL MATCH (p)-[:AVAILABLE_VIA]->(ch:Channel)
            OPTIONAL MATCH (p)-[:REPAID_VIA]->(rm:RepaymentMethod)
            OPTIONAL MATCH (p)-[:HAS_TAX_BENEFIT]->(tb:TaxBenefit)
            OPTIONAL MATCH (p)-[:PROTECTED_BY]->(dp:DepositProtection)
            RETURN p.name AS name, p.category AS category, p.product_type AS type,
                   p.description AS description, p.amount_max_raw AS amount,
                   p.eligibility_summary AS eligibility,
                   r.min_rate AS rate_min, r.max_rate AS rate_max,
                   t.raw_text AS term,
                   collect(DISTINCT ch.name) AS channels,
                   collect(DISTINCT rm.name) AS repayment,
                   tb.name AS tax_benefit,
                   dp.name AS deposit_protection
            LIMIT 1
        """, {"name": product_name})

        if not result:
            return f"'{product_name}' 상품을 찾을 수 없습니다."

        r = result[0]
        detail = f"## {r['name']}\n\n"
        detail += f"- 카테고리: {r.get('category', '')}\n"
        if r.get('description'):
            detail += f"- 설명: {r['description']}\n"
        if r.get('rate_min'):
            detail += f"- 금리: {r['rate_min']}% ~ {r.get('rate_max', '')}%\n"
        if r.get('amount'):
            detail += f"- 한도: {r['amount']}\n"
        if r.get('term'):
            detail += f"- 기간: {r['term']}\n"
        if r.get('channels'):
            detail += f"- 채널: {', '.join(r['channels'])}\n"
        if r.get('repayment'):
            detail += f"- 상환: {', '.join(r['repayment'])}\n"
        if r.get('eligibility'):
            detail += f"- 자격: {r['eligibility'][:150]}\n"
        if r.get('tax_benefit'):
            detail += f"- 세제혜택: {r['tax_benefit']}\n"
        if r.get('deposit_protection'):
            detail += f"- 예금자보호: {r['deposit_protection']}\n"

        return detail
    finally:
        if not db:
            conn.close()


@tool
def list_products_by_category(category: str, db=None) -> str:
    """카테고리별 금융상품 목록을 조회합니다.

    Args:
        category: 카테고리 이름 (예: "신용대출", "정기예금", "적금", "담보대출")
    """
    from knowledge_graph.db import Neo4jConnection
    conn = db or Neo4jConnection()
    try:
        result = conn.run_query("""
            MATCH (p:Product {category: $cat})
            OPTIONAL MATCH (p)-[:HAS_RATE]->(r:InterestRate)
            RETURN p.name AS name, p.amount_max_raw AS amount,
                   r.min_rate AS rate_min, r.max_rate AS rate_max
            ORDER BY p.name
        """, {"cat": category})

        if not result:
            return f"'{category}' 카테고리에 상품이 없습니다."

        lines = [f"## {category} 상품 목록 ({len(result)}개)\n"]
        for r in result:
            line = f"- **{r['name']}**"
            if r.get('rate_min'):
                line += f" (금리: {r['rate_min']}%~{r.get('rate_max', '')}%)"
            if r.get('amount'):
                line += f" / 한도: {r['amount']}"
            lines.append(line)

        return "\n".join(lines)
    finally:
        if not db:
            conn.close()
