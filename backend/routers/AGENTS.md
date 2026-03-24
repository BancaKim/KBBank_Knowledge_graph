# backend/routers/

FastAPI API 라우터 모듈. 각 라우터는 특정 API 경로를 담당.

## 파일

| 파일 | 역할 |
|------|------|
| `graph.py` | `GET /api/graph` - D3.js용 그래프 데이터 (5분 캐싱), `GET /api/graph/stats` - 통계 |
| `products.py` | `GET /api/products` - 상품 목록, `GET /api/products/{id}` - 상세, 비교, 경쟁 상품 |
| `search.py` | `GET /api/search?q=` - CJK 풀텍스트 검색 (카테고리 필터 지원) |
| `chat.py` | `POST /api/chat` - GraphRAG 챗봇 (LangGraph 에이전트 호출, async, 입력 검증) |
| `__init__.py` | 패키지 초기화 |
