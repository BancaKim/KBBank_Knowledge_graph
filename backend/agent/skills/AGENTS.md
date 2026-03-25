# backend/agent/skills/

LangGraph 에이전트가 사용하는 도구(Skills). 각 skill은 `@tool` 데코레이터로 LangChain Tool로 등록됨.

## 파일

| 파일 | 역할 |
|------|------|
| `graph_rag.py` | `search_products` - Neo4j 풀텍스트 검색으로 상품 검색 (GraphRAG) |
| `cypher_rag.py` | `query_knowledge_graph` - LLM이 Cypher를 동적 생성하여 지식그래프 검색 (Agentic GraphRAG) |
| `product_search.py` | `get_product_detail` - 상품 상세 조회, `list_products_by_category` - 카테고리별 목록 |
| `product_compare.py` | `compare_products` - 두 상품 비교표 생성 |
| `rate_calculator.py` | `calculate_loan_payment` - 대출 상환액 계산, `calculate_deposit_maturity` - 예금 만기액 계산 |
| `dsr_calculator.py` | `calculate_dsr` - DSR 계산 및 규제 충족 판단, `calculate_max_mortgage_by_dsr` - DSR 한도 내 최대 대출 가능액 산출 |
| `eligibility_check.py` | `check_eligibility` - 가입 자격 확인 (나이, 직업 기반) |
| `__init__.py` | 패키지 초기화 |
