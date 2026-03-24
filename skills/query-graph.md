---
name: query-graph
description: Query the KB banking products knowledge graph for product information, comparisons, and insights
---

# 지식그래프 쿼리

## 트리거
- 사용자가 금융상품 정보 질문, 카테고리별 조회, 금리 비교 요청 시

## 동작

1. **Neo4j 연결 확인**
   ```bash
   docker compose -f /Users/a1654530/Desktop/banking_bot/docker-compose.yml ps
   ```

2. **쿼리 실행** (Python 사용)
   ```python
   import sys
   sys.path.insert(0, "/Users/a1654530/Desktop/banking_bot")
   from knowledge_graph.query import (
       get_products_by_category,
       search_products,
       get_product_detail,
       compare_products,
       get_products_by_rate_range,
       get_graph_stats,
   )
   from knowledge_graph.db import Neo4jConnection

   db = Neo4jConnection()
   # 사용자 요청에 따라 적절한 쿼리 함수 호출
   results = search_products(db, "정기예금")
   db.close()
   ```

## 쿼리 유형
- **카테고리 조회**: `get_products_by_category(db, "예금")`
- **키워드 검색**: `search_products(db, "적금")`
- **금리 범위**: `get_products_by_rate_range(db, 2.0, 4.0)`
- **상품 상세**: `get_product_detail(db, "product_id")`
- **상품 비교**: `compare_products(db, "id_a", "id_b")`
- **통계**: `get_graph_stats(db)`
