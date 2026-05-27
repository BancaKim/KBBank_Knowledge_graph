"""Banking chatbot using pure LangGraph StateGraph.

Lightweight single-agent with all tools. No deepagents dependency.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Annotated, TypedDict

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.agent.prompts import (
    CALCULATOR_PROMPT,
    COMPARATOR_PROMPT,
    DEPOSIT_EXPERT_PROMPT,
    MAIN_SYSTEM_PROMPT,
)

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

CHATBOT_MODEL = os.environ.get("CHATBOT_MODEL", "claude-sonnet-4-6")
# Cypher generation is a narrow, structured task — use a faster/cheaper model.
CYPHER_MODEL = os.environ.get("CYPHER_MODEL", "claude-haiku-4-5-20251001")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _merge_messages(left: list, right: list) -> list:
    return left + right


class AgentState(TypedDict):
    messages: Annotated[list, _merge_messages]


# ---------------------------------------------------------------------------
# Skills loader (lazy, cached)
# ---------------------------------------------------------------------------

_skills_cache: dict[str, str] = {}


def _load_skill(name: str) -> str:
    if name not in _skills_cache:
        skill_path = _SKILLS_DIR / name / "SKILL.md"
        if skill_path.exists():
            _skills_cache[name] = skill_path.read_text(encoding="utf-8")[:3000]
        else:
            ref_dir = _SKILLS_DIR / name / "references"
            if ref_dir.exists():
                parts = []
                for f in sorted(ref_dir.glob("*.md")):
                    parts.append(f.read_text(encoding="utf-8")[:2000])
                _skills_cache[name] = "\n\n".join(parts)[:3000]
            else:
                _skills_cache[name] = ""
    return _skills_cache[name]


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def _make_tools(db: Any, api_key: str | None = None) -> list:
    from backend.agent.skills import (
        graph_rag,
        product_search,
        product_compare,
        rate_calculator,
        eligibility_check,
    )
    from backend.agent.skills.cypher_rag import query_knowledge_graph

    # Wrap cypher_rag tool with db + llm pre-bound
    _cypher_llm = ChatAnthropic(model=CYPHER_MODEL, max_tokens=2048, api_key=api_key)

    @tool
    def query_graph(question: str) -> str:
        """[기본 검색 도구] 금융상품 지식그래프에 자연어로 질문합니다. 상품명, 금리, 기간, 우대조건, 가입자격 등 모든 정보를 동적으로 조회합니다.
        상품 검색, 금리 비교, 조건별 필터링 등 데이터 조회가 필요한 모든 질문에 이 도구를 우선 사용하세요.
        Cypher 쿼리를 자동 생성하여 실행하므로 어떤 복합 조건도 처리 가능합니다."""
        return query_knowledge_graph.invoke({"question": question, "db": db, "llm": _cypher_llm})

    @tool
    def search_products(query: str) -> str:
        """[보조] 키워드 기반 예금/적금 상품 검색. query_graph로 결과가 부족할 때 보조로 사용합니다."""
        return graph_rag.search_products.invoke({"query": query, "db": db})

    @tool
    def get_product_detail(product_name: str) -> str:
        """특정 상품의 상세 정보를 조회합니다."""
        return product_search.get_product_detail.invoke({"product_name": product_name, "db": db})

    @tool
    def list_products_by_category(category: str) -> str:
        """특정 카테고리의 상품 목록을 조회합니다."""
        return product_search.list_products_by_category.invoke({"category": category, "db": db})

    @tool
    def compare_products(product_a: str, product_b: str) -> str:
        """두 상품을 비교합니다."""
        return product_compare.compare_products.invoke({"product_a": product_a, "product_b": product_b, "db": db})

    @tool
    def check_eligibility(product_name: str, age: int = 0, employment: str = "") -> str:
        """특정 상품의 가입 자격을 확인합니다."""
        return eligibility_check.check_eligibility.invoke({
            "product_name": product_name, "age": age, "employment": employment, "db": db,
        })

    @tool
    def calculate_deposit_maturity(
        principal: int, annual_rate: float, months: int, tax_type: str = "일반과세"
    ) -> str:
        """예금 만기 수령액을 계산합니다."""
        return rate_calculator.calculate_deposit_maturity.invoke({
            "principal": principal, "annual_rate": annual_rate, "months": months, "tax_type": tax_type,
        })

    return [
        # 기본 검색 도구 (Text2Cypher) — 최우선 사용
        query_graph,
        # 보조 검색 도구 (하드코딩 Cypher)
        search_products, get_product_detail, list_products_by_category,
        compare_products, check_eligibility,
        # 계산 도구 (예금 만기 수령액)
        calculate_deposit_maturity,
    ]


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    return "\n\n".join([
        MAIN_SYSTEM_PROMPT,
        "## 예금/적금 전문 지식\n" + DEPOSIT_EXPERT_PROMPT,
        "## 금융 계산\n" + CALCULATOR_PROMPT,
        "## 상품 비교/추천\n" + COMPARATOR_PROMPT,
    ])


_agent_cache: dict[str, Any] = {}
_AGENT_CACHE_MAX = 4


def _get_or_create_agent(db: Any, api_key: str | None):
    cache_key = f"{id(db)}:{api_key[:8] if api_key else 'none'}"
    if cache_key not in _agent_cache:
        if len(_agent_cache) >= _AGENT_CACHE_MAX:
            oldest = next(iter(_agent_cache))
            del _agent_cache[oldest]
        _agent_cache[cache_key] = create_banking_agent(db, api_key=api_key)
    return _agent_cache[cache_key]


def create_banking_agent(db: Any = None, api_key: str | None = None):
    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    llm = ChatAnthropic(model=CHATBOT_MODEL, max_tokens=4096, api_key=resolved_key)

    tools = _make_tools(db, api_key=resolved_key)
    llm_with_tools = llm.bind_tools(tools)
    system_prompt = _build_system_prompt()
    # Cache the large static system prompt across the multi-call agent loop
    # (Anthropic prompt caching) to cut latency/cost on repeated calls.
    system_message = SystemMessage(
        content=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    )

    def agent_node(state: AgentState) -> dict:
        messages = [system_message] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _extract_refs(db: Any, answer: str) -> list[dict]:
    if not db or not answer:
        return []
    try:
        results = db.run_query(
            """
            MATCH (p:Product)
            WHERE any(word IN split($answer, ' ') WHERE size(word) > 3 AND p.name CONTAINS word)
            RETURN p.id AS id, p.name AS name
            LIMIT 5
            """,
            {"answer": answer},
        )
        return [{"id": r["id"], "type": "product", "name": r["name"]} for r in results]
    except Exception:
        return []


def chat(
    query: str,
    history: list[dict] | None = None,
    db: Any = None,
    api_key: str | None = None,
) -> dict:
    try:
        agent = _get_or_create_agent(db, api_key=api_key)

        messages = []
        if history:
            for msg in history[-6:]:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=query))

        result = agent.invoke({"messages": messages})
        answer = result["messages"][-1].content if result.get("messages") else "답변을 생성할 수 없습니다."

        return {
            "answer": answer,
            "referenced_nodes": _extract_refs(db, answer),
        }
    except Exception as exc:
        return {
            "answer": f"죄송합니다. 답변 생성 중 오류가 발생했습니다: {type(exc).__name__}. 잠시 후 다시 시도해주세요.",
            "referenced_nodes": [],
        }


# ---------------------------------------------------------------------------
# Streaming API (progress steps + answer tokens)
# ---------------------------------------------------------------------------

_STEP_LABELS = {
    "query_graph": "🔍 지식그래프 검색 중...",
    "search_products": "🔍 상품 검색 중...",
    "get_product_detail": "📄 상품 상세 조회 중...",
    "list_products_by_category": "📂 카테고리 조회 중...",
    "compare_products": "⚖️ 상품 비교 중...",
    "check_eligibility": "✅ 가입자격 확인 중...",
    "calculate_deposit_maturity": "🧮 만기 수령액 계산 중...",
}


def _step_label(tool_name: str) -> str:
    return _STEP_LABELS.get(tool_name, "🔧 도구 실행 중...")


def _chunk_text(chunk: Any) -> str:
    """Extract plain text from an AIMessageChunk (str or Anthropic content blocks)."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


async def chat_stream(
    query: str,
    history: list[dict] | None = None,
    db: Any = None,
    api_key: str | None = None,
):
    """Async generator yielding progress/answer events for SSE.

    Event dicts: {"type": "step"|"token"|"done"|"error", ...}
    """
    try:
        agent = _get_or_create_agent(db, api_key=api_key)

        messages: list = []
        if history:
            for msg in history[-6:]:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=query))

        answer_parts: list[str] = []
        yield {"type": "step", "label": "🤔 질문 분석 중..."}

        async for mode, data in agent.astream(
            {"messages": messages}, stream_mode=["updates", "messages"]
        ):
            if mode == "updates":
                agent_out = data.get("agent") if isinstance(data, dict) else None
                msgs = agent_out.get("messages") if agent_out else None
                last = msgs[-1] if msgs else None
                tool_calls = getattr(last, "tool_calls", None) if last is not None else None
                if tool_calls:
                    # Any text streamed before a tool call was just narration —
                    # tell the client to discard it so the final answer stays clean.
                    if answer_parts:
                        answer_parts.clear()
                        yield {"type": "reset"}
                    for tc in tool_calls:
                        yield {"type": "step", "label": _step_label(tc.get("name", ""))}
            elif mode == "messages":
                msg_chunk, meta = data
                if (meta or {}).get("langgraph_node") != "agent":
                    continue
                text = _chunk_text(msg_chunk)
                if text:
                    answer_parts.append(text)
                    yield {"type": "token", "text": text}

        answer = "".join(answer_parts) or "답변을 생성할 수 없습니다."
        yield {"type": "done", "answer": answer, "referenced_nodes": _extract_refs(db, answer)}
    except Exception as exc:
        yield {
            "type": "error",
            "message": f"답변 생성 중 오류가 발생했습니다: {type(exc).__name__}. 잠시 후 다시 시도해주세요.",
        }
