"""Banking chatbot using pure LangGraph StateGraph.

Lightweight single-agent with all tools. No deepagents dependency.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Annotated, TypedDict

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
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
    LOAN_EXPERT_PROMPT,
    MAIN_SYSTEM_PROMPT,
)

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


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

def _make_tools(db: Any) -> list:
    from backend.agent.skills import (
        graph_rag,
        product_search,
        product_compare,
        rate_calculator,
        eligibility_check,
    )
    from backend.agent.skills import loan_search
    from backend.agent.skills.dsr_calculator import calculate_dsr, calculate_max_mortgage_by_dsr
    from backend.agent.skills.ltv_calculator import calculate_ltv_limit
    from backend.agent.skills.mortgage_calculator import calculate_mortgage_limit
    from backend.agent.skills.cypher_rag import query_knowledge_graph

    # Wrap cypher_rag tool with db pre-bound
    @tool
    def query_graph(question: str) -> str:
        """Neo4j 지식그래프에 자연어로 질문합니다. Cypher 쿼리를 자동 생성하여 실행합니다."""
        return query_knowledge_graph.invoke({"question": question, "db": db})

    @tool
    def search_products(query: str) -> str:
        """상품을 검색합니다. 예금, 적금, 대출 등 모든 금융상품을 검색합니다."""
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
    def check_eligibility(product_name: str, age: int = 0, employment_type: str = "") -> str:
        """특정 상품의 가입 자격을 확인합니다."""
        return eligibility_check.check_eligibility.invoke({
            "product_name": product_name, "age": age, "employment_type": employment_type, "db": db,
        })

    @tool
    def search_loan_products(query: str) -> str:
        """대출 상품을 검색합니다."""
        return loan_search.search_loan_products.invoke({"query": query, "db": db})

    @tool
    def get_loan_product_detail(name: str) -> str:
        """대출 상품의 상세 정보를 조회합니다."""
        return loan_search.get_loan_product_detail.invoke({"name": name, "db": db})

    @tool
    def get_loan_rates(base_rate_type: str) -> str:
        """특정 기준금리 유형별 대출 금리를 비교 조회합니다."""
        return loan_search.get_loan_rates.invoke({"base_rate_type": base_rate_type, "db": db})

    @tool
    def calculate_loan_payment(
        principal: int, annual_rate: float, months: int, method: str = "원리금균등"
    ) -> str:
        """대출 월 상환액을 계산합니다."""
        return rate_calculator.calculate_loan_payment.invoke({
            "principal": principal, "annual_rate": annual_rate, "months": months, "method": method,
        })

    @tool
    def calculate_deposit_maturity(
        principal: int, annual_rate: float, months: int, tax_type: str = "일반과세"
    ) -> str:
        """예금 만기 수령액을 계산합니다."""
        return rate_calculator.calculate_deposit_maturity.invoke({
            "principal": principal, "annual_rate": annual_rate, "months": months, "tax_type": tax_type,
        })

    @tool
    def get_regulation_info(topic: str) -> str:
        """LTV, DSR, 대출한도, 생애최초 등 부동산 대출 규제 정보를 조회합니다."""
        content = _load_skill("financial-regulations")
        if not content:
            return "규제 정보 스킬이 로드되지 않았습니다."
        return content[:2000]

    return [
        search_products, get_product_detail, list_products_by_category,
        compare_products, check_eligibility,
        search_loan_products, get_loan_product_detail, get_loan_rates,
        calculate_loan_payment, calculate_deposit_maturity,
        get_regulation_info,
        # PR #1 DSR/LTV/모기지 계산기 (정교한 규제 반영)
        calculate_dsr, calculate_max_mortgage_by_dsr,
        calculate_ltv_limit, calculate_mortgage_limit,
        query_graph,
    ]


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    return "\n\n".join([
        MAIN_SYSTEM_PROMPT,
        "## 예금/적금 전문 지식\n" + DEPOSIT_EXPERT_PROMPT,
        "## 대출 전문 지식\n" + LOAN_EXPERT_PROMPT,
        "## 금융 계산\n" + CALCULATOR_PROMPT,
        "## 상품 비교/추천\n" + COMPARATOR_PROMPT,
    ])


def create_banking_agent(db: Any = None, api_key: str | None = None):
    resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=resolved_key)

    tools = _make_tools(db)
    llm_with_tools = llm.bind_tools(tools)
    system_prompt = _build_system_prompt()

    def agent_node(state: AgentState) -> dict:
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
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
            UNION
            MATCH (lp:LoanProduct)
            WHERE any(word IN split($answer, ' ') WHERE size(word) > 3 AND lp.name CONTAINS word)
            RETURN lp.id AS id, lp.name AS name
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
        agent = create_banking_agent(db, api_key=api_key)

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
