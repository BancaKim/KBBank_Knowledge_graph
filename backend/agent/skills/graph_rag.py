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
            RETURN node.id AS id, node.name AS name, node.category AS category,
                   node.product_type AS product_type, node.description AS description,
                   node.amount_max_raw AS amount_max, node.eligibility_summary AS eligibility,
                   score
            ORDER BY score DESC LIMIT 5
        """, {"query": query})

        if not products:
            return "검색 결과가 없습니다."

        result_parts = []
        for p in products:
            part = f"상품: {p['name']} ({p.get('category', '')})"
            if p.get('description'):
                part += f"\n  설명: {p['description']}"
            if p.get('amount_max'):
                part += f"\n  한도: {p['amount_max']}"
            if p.get('eligibility'):
                part += f"\n  자격: {p['eligibility']}"
            result_parts.append(part)

        return "\n\n".join(result_parts)
    finally:
        if not db:
            conn.close()
