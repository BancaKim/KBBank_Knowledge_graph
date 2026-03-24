"""LangGraph-based banking chatbot agent."""
from __future__ import annotations

import os
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END

from backend.agent.state import AgentState

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


SYSTEM_PROMPT = """당신은 KB국민은행 금융상품 전문 상담 에이전트입니다.
주어진 도구(tools)를 활용하여 고객의 질문에 정확하게 답변합니다.

사용 가능한 도구:
- search_products: 상품 검색
- get_product_detail: 상품 상세 조회
- list_products_by_category: 카테고리별 상품 목록
- compare_products: 상품 비교
- calculate_loan_payment: 대출 상환액 계산
- calculate_deposit_maturity: 예금 만기액 계산
- check_eligibility: 가입 자격 확인

규칙:
1. 도구에서 얻은 정보만 사용합니다.
2. 구체적인 수치(금리, 한도 등)를 포함합니다.
3. 한국어로 답변합니다.
4. 확실하지 않으면 KB국민은행 문의를 안내합니다.
"""

# Tools that accept a db parameter for Neo4j connection injection
_DB_TOOLS = frozenset({
    "search_products", "get_product_detail", "list_products_by_category",
    "compare_products", "check_eligibility",
})


def _get_tools():
    """Import and return all available tools."""
    from backend.agent.skills.graph_rag import search_products
    from backend.agent.skills.product_search import get_product_detail, list_products_by_category
    from backend.agent.skills.product_compare import compare_products
    from backend.agent.skills.rate_calculator import calculate_loan_payment, calculate_deposit_maturity
    from backend.agent.skills.eligibility_check import check_eligibility

    return [
        search_products,
        get_product_detail,
        list_products_by_category,
        compare_products,
        calculate_loan_payment,
        calculate_deposit_maturity,
        check_eligibility,
    ]


def create_agent(db=None, api_key: str | None = None):
    """Create a LangGraph agent for banking chatbot."""
    tools = _get_tools()
    tools_by_name = {t.name: t for t in tools}

    resolved_key = api_key or os.environ.get("OPENAI_API_KEY")

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=resolved_key,
    )

    llm_with_tools = llm.bind_tools(tools)

    # ── Node: retrieve context from knowledge graph ──────────────────────
    def retrieve_context(state: AgentState) -> AgentState:
        """Pre-retrieve relevant context from knowledge graph."""
        conn = state.get("db")
        if not conn:
            return state

        query = state["query"]
        referenced_nodes: list[dict] = []
        context_parts: list[str] = []

        try:
            products = conn.run_query("""
                CALL db.index.fulltext.queryNodes('product_search', $query)
                YIELD node, score
                WHERE score > 0.5
                RETURN node.id AS id, node.name AS name, node.category AS category,
                       node.description AS description, score
                ORDER BY score DESC LIMIT 3
            """, {"query": query})

            for p in products:
                referenced_nodes.append({"id": p["id"], "type": "product", "name": p["name"]})
                ctx = f"{p['name']} ({p.get('category', '')})"
                if p.get('description'):
                    ctx += f": {p['description'][:100]}"
                context_parts.append(ctx)
        except Exception:
            pass

        return {
            **state,
            "context": "\n".join(context_parts) if context_parts else "",
            "referenced_nodes": referenced_nodes,
        }

    # ── Node: run the LLM agent with tool calling ────────────────────────
    def call_agent(state: AgentState) -> AgentState:
        """Run the agent with tools."""
        messages: list = [SystemMessage(content=SYSTEM_PROMPT)]

        # Add conversation history
        if state.get("history"):
            for msg in state["history"][-6:]:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # Add context from previous retrieval if available
        query = state["query"]
        if state.get("context"):
            query = f"[참고 정보]\n{state['context']}\n\n[질문] {query}"

        messages.append(HumanMessage(content=query))

        # Invoke LLM with tools
        response = llm_with_tools.invoke(messages)

        referenced_nodes = list(state.get("referenced_nodes", []))

        if response.tool_calls:
            messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = dict(tool_call["args"])

                # Inject db connection for Neo4j-dependent tools
                if tool_name in _DB_TOOLS:
                    tool_args["db"] = state.get("db")

                tool_fn = tools_by_name.get(tool_name)
                if tool_fn:
                    try:
                        result = tool_fn.invoke(tool_args)
                    except Exception as e:
                        result = f"도구 실행 오류: {type(e).__name__}"
                else:
                    result = f"알 수 없는 도구: {tool_name}"

                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

                # Collect referenced nodes from search results
                if tool_name in _DB_TOOLS:
                    _extract_refs(state.get("db"), tool_args, referenced_nodes)

            # Get final response after tool calls
            final_response = llm.invoke(messages)
            answer = final_response.content
        else:
            answer = response.content

        return {
            **state,
            "answer": answer,
            "referenced_nodes": referenced_nodes,
        }

    # ── Build LangGraph ──────────────────────────────────────────────────
    workflow = StateGraph(AgentState)
    workflow.add_node("retrieve", retrieve_context)
    workflow.add_node("agent", call_agent)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "agent")
    workflow.add_edge("agent", END)

    return workflow.compile()


def _extract_refs(db, tool_args: dict, referenced_nodes: list[dict]) -> None:
    """Extract referenced node IDs from tool args."""
    if not db:
        return
    try:
        query = tool_args.get("query") or tool_args.get("product_name") or tool_args.get("product_a", "")
        if query:
            results = db.run_query("""
                MATCH (p:Product)
                WHERE p.name CONTAINS $q
                RETURN p.id AS id, p.name AS name
                LIMIT 5
            """, {"q": query})
            for r in results:
                if not any(n["id"] == r["id"] for n in referenced_nodes):
                    referenced_nodes.append({"id": r["id"], "type": "product", "name": r["name"]})
    except Exception:
        pass


def chat(query: str, history: list[dict] | None = None, db=None, api_key: str | None = None) -> dict:
    """Process a chat query using the LangGraph agent.

    Drop-in replacement for the previous ``backend.chatbot.chat`` function.
    """
    agent = create_agent(db, api_key=api_key)

    state = AgentState(
        query=query,
        history=history or [],
        db=db,
        intent="general",
        entities=[],
        context="",
        referenced_nodes=[],
        answer="",
        verified=False,
    )

    try:
        result = agent.invoke(state)
        return {
            "answer": result.get("answer", "답변을 생성할 수 없습니다."),
            "referenced_nodes": result.get("referenced_nodes", []),
        }
    except Exception:
        return {
            "answer": "죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            "referenced_nodes": [],
        }
