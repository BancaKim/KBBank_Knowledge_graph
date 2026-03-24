"""Product comparison skill."""
from langchain_core.tools import tool


@tool
def compare_products(product_a: str, product_b: str, db=None) -> str:
    """두 금융상품을 비교합니다.

    Args:
        product_a: 첫 번째 상품 이름 또는 ID
        product_b: 두 번째 상품 이름 또는 ID
    """
    from knowledge_graph.db import Neo4jConnection
    conn = db or Neo4jConnection()
    try:
        # Find products by name
        result = conn.run_query("""
            MATCH (a:Product), (b:Product)
            WHERE a.name CONTAINS $name_a AND b.name CONTAINS $name_b
            OPTIONAL MATCH (a)-[:HAS_RATE]->(ra:InterestRate)
            OPTIONAL MATCH (b)-[:HAS_RATE]->(rb:InterestRate)
            OPTIONAL MATCH (a)-[:HAS_TERM]->(ta:Term)
            OPTIONAL MATCH (b)-[:HAS_TERM]->(tb:Term)
            OPTIONAL MATCH (a)-[:AVAILABLE_VIA]->(cha:Channel)
            OPTIONAL MATCH (b)-[:AVAILABLE_VIA]->(chb:Channel)
            RETURN a.name AS name_a, a.category AS cat_a, a.amount_max_raw AS amount_a, a.eligibility_summary AS elig_a,
                   b.name AS name_b, b.category AS cat_b, b.amount_max_raw AS amount_b, b.eligibility_summary AS elig_b,
                   ra.min_rate AS rate_min_a, ra.max_rate AS rate_max_a,
                   rb.min_rate AS rate_min_b, rb.max_rate AS rate_max_b,
                   ta.raw_text AS term_a, tb.raw_text AS term_b,
                   collect(DISTINCT cha.name) AS channels_a,
                   collect(DISTINCT chb.name) AS channels_b
            LIMIT 1
        """, {"name_a": product_a, "name_b": product_b})

        if not result:
            return f"'{product_a}' 또는 '{product_b}' 상품을 찾을 수 없습니다."

        r = result[0]
        comparison = f"""## 상품 비교

| 항목 | {r['name_a']} | {r['name_b']} |
|------|------|------|
| 카테고리 | {r.get('cat_a', '-')} | {r.get('cat_b', '-')} |
| 금리(최저) | {r.get('rate_min_a', '-')}% | {r.get('rate_min_b', '-')}% |
| 금리(최고) | {r.get('rate_max_a', '-')}% | {r.get('rate_max_b', '-')}% |
| 한도 | {r.get('amount_a', '-')} | {r.get('amount_b', '-')} |
| 기간 | {r.get('term_a', '-')} | {r.get('term_b', '-')} |
| 채널 | {', '.join(r.get('channels_a', []))} | {', '.join(r.get('channels_b', []))} |
| 자격 | {(r.get('elig_a', '') or '-')[:50]} | {(r.get('elig_b', '') or '-')[:50]} |
"""
        return comparison
    finally:
        if not db:
            conn.close()
