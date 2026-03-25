"""Multi-agent banking chatbot using create_agent + SubAgentMiddleware.

Supervisor pattern: main agent routes to specialized sub-agents
(deposit_expert, loan_expert, calculator, comparator).

Uses LangChain standard `create_agent` API with SubAgentMiddleware
from deepagents for automatic sub-agent delegation.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pathlib import Path

from backend.agent.prompts import (
    CALCULATOR_PROMPT,
    COMPARATOR_PROMPT,
    DEPOSIT_EXPERT_PROMPT,
    LOAN_EXPERT_PROMPT,
    MAIN_SYSTEM_PROMPT,
)

# Skills directory (contains SKILL.md + references/)
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


# ---------------------------------------------------------------------------
# Tool factory — create tools with db pre-bound via closure
# ---------------------------------------------------------------------------

def _make_tools(db: Any) -> dict[str, Any]:
    """Create all tools with Neo4j db connection pre-bound.

    Wrapper tools capture `db` from closure so the LLM only sees
    the user-facing parameters (query, name, etc).
    """
    # Import raw tool modules
    from backend.agent.skills import (
        graph_rag,
        product_search,
        product_compare,
        rate_calculator,
        eligibility_check,
    )
    from backend.agent.skills import loan_search

    # --- Deposit/common tools (db-bound) ---

    @tool
    def search_products(query: str) -> str:
        """상품을 검색합니다. 예금, 적금, 대출 등 모든 금융상품을 검색합니다."""
        return graph_rag.search_products.invoke({"query": query, "db": db})

    @tool
    def get_product_detail(product_name: str) -> str:
        """특정 상품의 상세 정보(금리, 가입조건, 우대금리, 채널 등)를 조회합니다."""
        return product_search.get_product_detail.invoke({"product_name": product_name, "db": db})

    @tool
    def list_products_by_category(category: str) -> str:
        """특정 카테고리(정기예금, 적금, 신용대출 등)의 상품 목록을 조회합니다."""
        return product_search.list_products_by_category.invoke({"category": category, "db": db})

    @tool
    def compare_products(product_a: str, product_b: str) -> str:
        """두 상품을 비교합니다. 금리, 한도, 기간, 채널 등을 표로 비교합니다."""
        return product_compare.compare_products.invoke({"product_a": product_a, "product_b": product_b, "db": db})

    @tool
    def check_eligibility(product_name: str, age: int = 0, employment_type: str = "") -> str:
        """특정 상품의 가입 자격을 확인합니다."""
        return eligibility_check.check_eligibility.invoke({
            "product_name": product_name, "age": age, "employment_type": employment_type, "db": db,
        })

    # --- Loan-specific tools (db-bound) ---

    @tool
    def search_loan_products(query: str) -> str:
        """대출 상품을 검색합니다. 신용대출, 담보대출, 전세대출, 자동차대출 등을 검색합니다."""
        return loan_search.search_loan_products.invoke({"query": query, "db": db})

    @tool
    def get_loan_product_detail(name: str) -> str:
        """대출 상품의 상세 정보를 조회합니다. 금리(기준금리별), 상환방법, 담보, 수수료, 소비자권리를 포함합니다."""
        return loan_search.get_loan_product_detail.invoke({"name": name, "db": db})

    @tool
    def get_loan_rates(base_rate_type: str) -> str:
        """특정 기준금리 유형(CD91일물, COFIX, 금융채 등)별 대출 금리를 비교 조회합니다."""
        return loan_search.get_loan_rates.invoke({"base_rate_type": base_rate_type, "db": db})

    # --- Calculation tools (no db needed) ---

    @tool
    def calculate_loan_payment(
        principal: int, annual_rate: float, months: int, method: str = "원리금균등"
    ) -> str:
        """대출 월 상환액을 계산합니다. method: 원리금균등, 원금균등, 만기일시"""
        return rate_calculator.calculate_loan_payment.invoke({
            "principal": principal, "annual_rate": annual_rate, "months": months, "method": method,
        })

    @tool
    def calculate_deposit_maturity(
        principal: int, annual_rate: float, months: int, tax_type: str = "일반과세"
    ) -> str:
        """예금 만기 수령액을 계산합니다. tax_type: 일반과세, 비과세, 세금우대"""
        return rate_calculator.calculate_deposit_maturity.invoke({
            "principal": principal, "annual_rate": annual_rate, "months": months, "tax_type": tax_type,
        })

    return {
        # Deposit tools
        "search_products": search_products,
        "get_product_detail": get_product_detail,
        "list_products_by_category": list_products_by_category,
        "check_eligibility": check_eligibility,
        "calculate_deposit_maturity": calculate_deposit_maturity,
        # Loan tools
        "search_loan_products": search_loan_products,
        "get_loan_product_detail": get_loan_product_detail,
        "get_loan_rates": get_loan_rates,
        # Shared tools
        "compare_products": compare_products,
        "calculate_loan_payment": calculate_loan_payment,
    }


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_banking_agent(db: Any = None, api_key: str | None = None):
    """Create a multi-agent banking chatbot with SubAgentMiddleware.

    Architecture:
      Main Agent (supervisor) → routes to specialized sub-agents
      ├── deposit_expert: 예금/적금 상담
      ├── loan_expert: 대출 상담
      ├── calculator: 금융 계산
      └── comparator: 상품 비교/추천
    """
    from langchain.agents import create_agent
    from deepagents.middleware.subagents import SubAgentMiddleware

    resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=resolved_key)

    # Create tools with db pre-bound
    tools = _make_tools(db)

    # Define sub-agents with specialized tools and prompts
    subagents = [
        {
            "name": "deposit_expert",
            "description": (
                "예금/적금 상품 관련 질문에 답변합니다. "
                "정기예금, 적금, 자유입출금통장, 주택청약의 금리, 가입조건, "
                "세제혜택, 우대금리, 예금자보호 등을 안내합니다."
            ),
            "system_prompt": DEPOSIT_EXPERT_PROMPT,
            "tools": [
                tools["search_products"],
                tools["get_product_detail"],
                tools["list_products_by_category"],
                tools["check_eligibility"],
                tools["calculate_deposit_maturity"],
            ],
        },
        {
            "name": "loan_expert",
            "description": (
                "대출 상품 관련 질문에 답변합니다. "
                "신용대출, 담보대출, 전월세대출, 자동차대출의 금리(기준금리별), "
                "상환방법, 담보, 중도상환수수료, 소비자 3대 권리를 안내합니다. "
                "LTV, DSR, 대출한도, 생애최초 등 규제 관련 질문도 답변합니다."
            ),
            "system_prompt": LOAN_EXPERT_PROMPT,
            "tools": [
                tools["search_loan_products"],
                tools["get_loan_product_detail"],
                tools["get_loan_rates"],
                tools["list_products_by_category"],
                tools["check_eligibility"],
            ],
        },
        {
            "name": "calculator",
            "description": (
                "금융 계산을 수행합니다. "
                "대출 월 상환액(원리금균등/원금균등/만기일시), "
                "예금 만기 수령액(세전/세후) 등을 계산합니다."
            ),
            "system_prompt": CALCULATOR_PROMPT,
            "tools": [
                tools["calculate_loan_payment"],
                tools["calculate_deposit_maturity"],
            ],
        },
        {
            "name": "comparator",
            "description": (
                "여러 금융상품을 비교하거나 조건에 맞는 상품을 추천합니다. "
                "예금/대출 간 크로스 비교, 금리 비교, 조건별 추천을 수행합니다."
            ),
            "system_prompt": COMPARATOR_PROMPT,
            "tools": [
                tools["search_products"],
                tools["search_loan_products"],
                tools["get_product_detail"],
                tools["get_loan_product_detail"],
                tools["compare_products"],
                tools["list_products_by_category"],
            ],
        },
    ]

    # SkillsMiddleware — LLM loads skills on-demand (token efficient)
    from deepagents.backends import FilesystemBackend
    from deepagents.middleware.skills import SkillsMiddleware

    skills_backend = FilesystemBackend(root_dir=str(_SKILLS_DIR.parent))
    skills_sources = [str(_SKILLS_DIR)]

    # Create main agent — no direct tools, MUST delegate to sub-agents
    agent = create_agent(
        model=llm,
        tools=[],  # No direct tools — forces delegation to sub-agents
        system_prompt=MAIN_SYSTEM_PROMPT,
        middleware=[
            SubAgentMiddleware(
                default_model=llm,
                subagents=subagents,
            ),
            SkillsMiddleware(
                backend=skills_backend,
                sources=skills_sources,
            ),
        ],
        name="kb_banking_agent",
    )

    return agent


# ---------------------------------------------------------------------------
# Public API — backward compatible
# ---------------------------------------------------------------------------

def _extract_refs(db: Any, answer: str) -> list[dict]:
    """Extract referenced product nodes from answer text."""
    if not db or not answer:
        return []
    try:
        # Search for product names mentioned in the answer
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
    """Process a chat query using the multi-agent banking chatbot.

    Drop-in replacement for the previous single-agent ``chat`` function.
    Returns: {"answer": str, "referenced_nodes": list[dict]}
    """
    try:
        agent = create_banking_agent(db, api_key=api_key)

        # Build messages from history
        from langchain_core.messages import HumanMessage, AIMessage
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
