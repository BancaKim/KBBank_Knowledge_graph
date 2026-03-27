"""GraphRAG skill - Query Neo4j knowledge graph for product information."""
from langchain_core.tools import tool


@tool
def search_products(query: str, db=None) -> str:
    """금융상품 지식그래프에서 상품을 검색합니다.

    Args:
        query: 검색할 키워드 (예: "비상금대출", "정기예금", "전세대출")
    """
    from knowledge_graph.db import Neo4jConnection
    conn = db or Neo4jConnection()
    try:
        products = conn.run_query("""
            CALL db.index.fulltext.queryNodes('product_search', $query)
            YIELD node, score
            WHERE score > 0.5
            WITH node, score ORDER BY score DESC LIMIT 5
            OPTIONAL MATCH (node)-[:HAS_RATE]->(rate:InterestRate)
            OPTIONAL MATCH (node)-[:HAS_TERM]->(term:Term)
            OPTIONAL MATCH (node)-[:BELONGS_TO]->(cat:Category)
            OPTIONAL MATCH (node)-[:HAS_PREFERENTIAL_RATE]->(pref:PreferentialRate)
            OPTIONAL MATCH (node)-[:PROTECTED_BY]->(dp:DepositProtection)
            RETURN node.id AS id, node.name AS name, cat.name AS category,
                   node.product_type AS product_type, node.description AS description,
                   node.amount_max_raw AS amount_max, node.eligibility_summary AS eligibility,
                   rate.min_rate AS min_rate, rate.max_rate AS max_rate,
                   term.min_months AS min_months, term.max_months AS max_months, term.raw_text AS term_text,
                   dp.protected AS deposit_protected, dp.max_amount_won AS dp_max,
                   collect(DISTINCT {name: pref.name, rate: pref.rate_value_pp, cond: pref.condition_description})[0..3] AS top_prefs,
                   score
        """, {"query": query})

        if not products:
            return "검색 결과가 없습니다."

        # Deduplicate by product name (multiple rates/terms may create duplicate rows)
        seen = set()
        result_parts = []
        for p in products:
            name = p.get('name', '')
            if name in seen:
                continue
            seen.add(name)
            part = f"**{name}** ({p.get('category', '')})"
            if p.get('description'):
                part += f"\n  설명: {p['description']}"
            if p.get('min_rate') is not None or p.get('max_rate') is not None:
                min_r = p.get('min_rate', '?')
                max_r = p.get('max_rate', '?')
                part += f"\n  금리: 연 {min_r}% ~ {max_r}%"
            if p.get('term_text') or p.get('min_months') is not None:
                term_str = p.get('term_text') or f"{p.get('min_months', '?')}~{p.get('max_months', '?')}개월"
                part += f"\n  가입기간: {term_str}"
            if p.get('amount_max'):
                part += f"\n  한도: {p['amount_max']}"
            if p.get('eligibility'):
                part += f"\n  자격: {p['eligibility']}"
            if p.get('deposit_protected'):
                dp_amount = f"{int(p['dp_max']):,}원" if p.get('dp_max') else "해당"
                part += f"\n  예금자보호: {dp_amount}"
            prefs = p.get('top_prefs', [])
            if prefs and prefs[0].get('name'):
                pref_strs = [f"{pr['name']} (+{pr['rate']}%p)" for pr in prefs if pr.get('name')]
                if pref_strs:
                    part += f"\n  우대조건: {', '.join(pref_strs)}"
            result_parts.append(part)

        return "\n\n".join(result_parts)
    finally:
        if not db:
            conn.close()
