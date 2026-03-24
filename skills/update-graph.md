---
name: update-graph
description: Add or modify entities and relationships in the KB banking knowledge graph
---

# 지식그래프 업데이트

## 트리거
- 사용자가 그래프에 새 엔티티/관계 추가, 수정, 삭제 요청 시
- 스크래핑 후 그래프 재빌드 필요 시

## 동작

### 전체 재빌드
```bash
cd /Users/a1654530/Desktop/banking_bot
python -m knowledge_graph.builder
```

### 그래프 JSON 재출력
```python
import sys
sys.path.insert(0, "/Users/a1654530/Desktop/banking_bot")
from knowledge_graph.db import Neo4jConnection
from knowledge_graph.exporter import export_graph

db = Neo4jConnection()
export_graph(db, "data/graph/graph.json")
db.close()
```

### 수동 Cypher 쿼리
```python
from knowledge_graph.db import Neo4jConnection
db = Neo4jConnection()

# 노드 추가 예시
db.run_write(
    "MERGE (p:Product {id: $id}) SET p.name = $name, p.category = $category",
    {"id": "custom_product_1", "name": "커스텀 상품", "category": "예금"}
)

# 관계 추가 예시
db.run_write(
    "MATCH (a:Product {id: $a_id}), (b:Product {id: $b_id}) "
    "MERGE (a)-[:COMPETES_WITH]->(b)",
    {"a_id": "product_1", "b_id": "product_2"}
)

db.close()
```

## 주의사항
- Neo4j 컨테이너가 실행 중이어야 함: `docker compose up -d`
- MERGE 사용으로 중복 생성 방지
- 변경 후 프론트엔드에 반영하려면 graph.json 재출력 필요
