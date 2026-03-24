"""Eligibility checker skill."""
from langchain_core.tools import tool


@tool
def check_eligibility(product_name: str, age: int = 0, employment: str = "", db=None) -> str:
    """특정 금융상품의 가입 자격을 확인합니다.

    Args:
        product_name: 상품 이름 (예: "KB 비상금대출")
        age: 나이 (0이면 무시)
        employment: 직업 유형 (예: "직장인", "공무원", "개인사업자")
    """
    from knowledge_graph.db import Neo4jConnection
    conn = db or Neo4jConnection()
    try:
        result = conn.run_query("""
            MATCH (p:Product)-[:REQUIRES]->(e:EligibilityCondition)
            WHERE p.name CONTAINS $name
            RETURN p.name AS product, e.description AS eligibility,
                   e.min_age AS min_age, e.target_audience AS target
        """, {"name": product_name})

        if not result:
            return f"'{product_name}' 상품을 찾을 수 없습니다."

        r = result[0]
        eligible = True
        reasons = []

        if age > 0 and r.get("min_age") and age < r["min_age"]:
            eligible = False
            reasons.append(f"최소 연령 만{r['min_age']}세 미만")

        if employment and r.get("target") and r["target"] not in ["개인", ""] and employment != r["target"]:
            eligible = False
            reasons.append(f"대상: {r['target']} (입력: {employment})")

        status = "가입 가능" if eligible else "가입 불가"
        reason_text = "\n".join(f"  - {reason}" for reason in reasons) if reasons else "  - 조건 충족"

        return f"""## {r['product']} 가입 자격 확인

- 결과: **{status}**
- 상세 자격: {r.get('eligibility', '-')[:200]}
{reason_text}
"""
    finally:
        if not db:
            conn.close()
