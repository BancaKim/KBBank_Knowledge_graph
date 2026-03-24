# knowledge_graph/

Neo4j 지식그래프 구축 및 쿼리 모듈. 14개 Entity 타입, 15개 Relationship 타입.

## 파일

| 파일 | 역할 |
|------|------|
| `models.py` | Pydantic v2 엔티티 모델 (Product, Category, Channel, InterestRate, Term, Fee 등 14종) |
| `parser.py` | MD 파일에서 엔티티 추출 - 한국어 금액/기간/금리 파싱, 채널/상환방법/세제혜택 추출 |
| `builder.py` | Neo4j 그래프 구축 - MERGE 패턴으로 노드/관계 생성, 카테고리 계층, COMPETES_WITH 추론 |
| `exporter.py` | Neo4j → D3.js JSON 변환 - 노드 크기, 색상, 메타데이터 포함 export |
| `ontology.py` | 온톨로지 정의 - NODE_LABELS, RELATIONSHIP_TYPES, COLOR_MAP, GROUP_INDEX |
| `query.py` | Cypher 쿼리 함수 - 상품 검색, 상세 조회(CALL 서브쿼리), 비교, 통계 |
| `db.py` | Neo4j 연결 관리 - dotenv, execute_read/execute_write 트랜잭션 |
| `schema.cypher` | Neo4j 스키마 - 14개 유니크 제약조건, CJK 풀텍스트 인덱스 |
| `standalone_builder.py` | 독립 실행형 그래프 빌더 (대안) |
| `__init__.py` | 패키지 초기화 |
