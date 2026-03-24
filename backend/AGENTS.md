# backend/

FastAPI 백엔드 서버 모듈.

## 파일

| 파일 | 역할 |
|------|------|
| `main.py` | FastAPI 앱 설정, 라이프사이클 관리, CORS, 라우터 등록, `/health` 엔드포인트 |
| `dependencies.py` | FastAPI 의존성 주입 (Neo4j 커넥션 공유) |
| `chatbot.py` | LangGraph 에이전트 shim - `backend.agent.graph.chat`으로 위임 |
| `__init__.py` | 패키지 초기화 |

## 하위 디렉토리

- [agent/AGENTS.md](agent/AGENTS.md) - LangGraph 에이전트 및 Skills
- [routers/AGENTS.md](routers/AGENTS.md) - API 라우터
