# backend/agent/

LangGraph 기반 GraphRAG 챗봇 에이전트.

## 파일

| 파일 | 역할 |
|------|------|
| `graph.py` | LangGraph StateGraph 워크플로우 정의 (retrieve → agent → END), `create_agent()`, `chat()` |
| `state.py` | AgentState TypedDict - 에이전트 상태 스키마 (query, history, intent, context, answer 등) |
| `__init__.py` | 패키지 초기화 |

## 하위 디렉토리

- [skills/AGENTS.md](skills/AGENTS.md) - 에이전트 도구(Skills)
