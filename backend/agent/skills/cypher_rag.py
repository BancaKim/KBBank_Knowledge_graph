"""Agentic GraphRAG — LLM이 Cypher를 동적 생성하여 지식그래프를 검색하는 스킬.

3단계 검색 전략:
1. LLM → Cypher 생성 → Neo4j 실행
2. 실패 시 에러 피드백 + 재시도 (1회)
3. 최종 실패 시 풀텍스트 검색 fallback

기존 하드코딩 도구(search_products 등)로 처리 안 되는 복합 조건 질문에 사용.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graph Schema — LLM에게 제공하는 스키마 정보
# ---------------------------------------------------------------------------

DEPOSIT_SCHEMA = """\
## 금융상품 지식그래프 스키마 (예금)

### 예금 상품 노드
- (:Product {id, name, product_type, description, amount_max_raw, amount_max_won, eligibility_summary, page_url})
- (:Category {id, name})  — 예: 정기예금, 적금, 자유입출금, 주택청약
- (:ParentCategory {id, name})
- (:InterestRate {id, rate_type, min_rate, max_rate, base_rate_name, spread})  — rate_type: base/preferential/penalty
- (:Term {id, min_months, max_months, raw_text})
- (:Channel {id, name})  — 예: 모바일뱅킹, 인터넷뱅킹, 영업점
- (:EligibilityCondition {id, description, min_age, max_age, target_audience})
- (:PreferentialRate {id, name, condition_description, rate_value_pp})
- (:TaxBenefit {id, type, eligible, description})  — type: 일반과세/비과세종합저축/비과세
- (:DepositProtection {id, protected, max_amount_won, description})
- (:Feature {id, name, description})
- (:Benefit {id, benefit_type, name, description})
- (:ProductType {id, name})

### 관계 (예금)
(:Product)-[:BELONGS_TO]->(:Category)
(:Product)-[:HAS_RATE]->(:InterestRate)
(:Product)-[:HAS_PREFERENTIAL_RATE]->(:PreferentialRate)
(:Product)-[:HAS_TERM]->(:Term)
(:Product)-[:AVAILABLE_VIA]->(:Channel)
(:Product)-[:REQUIRES]->(:EligibilityCondition)
(:Product)-[:HAS_TAX_BENEFIT]->(:TaxBenefit)
(:Product)-[:PROTECTED_BY]->(:DepositProtection)
(:Product)-[:HAS_FEATURE]->(:Feature)
(:Product)-[:HAS_BENEFIT]->(:Benefit)
(:Product)-[:HAS_TYPE]->(:ProductType)
(:Product)-[:COMPETES_WITH]->(:Product)
(:ParentCategory)-[:HAS_SUBCATEGORY]->(:Category)

### 풀텍스트 인덱스 (예금)
- 'product_search' on Product(name, description) — CJK analyzer
"""

LOAN_SCHEMA = """\
## 금융상품 지식그래프 스키마 (대출)

### 대출 상품 노드
- (:LoanProduct {id, name, loan_type, description, amount_max_raw, eligibility_summary, rate_cut_request_available, contract_withdrawal_available, illegal_contract_termination})
  — loan_type: credit(신용)/secured(담보)/jeonse(전세)/auto(자동차)
- (:LoanCategory {id, name})  — 예: 신용대출, 주택담보대출, 전월세보증금대출
- (:LoanRate {id, rate_type, min_rate, max_rate, base_rate_name, spread})
  — base_rate_name: CD91일물, COFIX신규, COFIX잔액, 금융채6개월, 금융채12개월
- (:LoanTerm {id, min_months, max_months, raw_text})
- (:LoanEligibility {id, description, target_audience})
- (:RepaymentMethod {id, name, description})  — 예: 원리금균등분할상환, 원금균등분할상환, 만기일시상환
- (:LoanFee {id, fee_type, description})  — fee_type: early_repayment/incidental
- (:LoanPreferentialRate {id, name, condition_description, rate_value_pp})
- (:Collateral {id, collateral_type, description})

### 관계 (대출)
(:LoanProduct)-[:BELONGS_TO]->(:LoanCategory)
(:LoanProduct)-[:HAS_RATE]->(:LoanRate)
(:LoanProduct)-[:HAS_TERM]->(:LoanTerm)
(:LoanProduct)-[:REQUIRES]->(:LoanEligibility)
(:LoanProduct)-[:AVAILABLE_VIA]->(:Channel)
(:LoanProduct)-[:REPAID_VIA]->(:RepaymentMethod)
(:LoanProduct)-[:HAS_FEE]->(:LoanFee)
(:LoanProduct)-[:HAS_PREFERENTIAL_RATE]->(:LoanPreferentialRate)
(:LoanProduct)-[:SECURED_BY]->(:Collateral)

### 풀텍스트 인덱스 (대출)
- 'loan_product_search' on LoanProduct(name, description) — CJK analyzer
"""

GRAPH_SCHEMA = DEPOSIT_SCHEMA + "\n\n" + LOAN_SCHEMA  # backward compat

# ---------------------------------------------------------------------------
# Few-shot Cypher 예시 — 질문 유형별 대표 패턴
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = [
    {
        "question": "금리가 가장 높은 정기예금은?",
        "cypher": (
            "MATCH (p:Product)-[:BELONGS_TO]->(c:Category), (p)-[:HAS_RATE]->(r:InterestRate) "
            "WHERE c.name CONTAINS '정기예금' AND r.max_rate IS NOT NULL "
            "RETURN p.name AS 상품명, r.min_rate AS 최저금리, r.max_rate AS 최고금리 "
            "ORDER BY r.max_rate DESC LIMIT 5"
        ),
    },
    {
        "question": "모바일뱅킹에서 가입 가능한 예금 상품",
        "cypher": (
            "MATCH (p:Product)-[:AVAILABLE_VIA]->(ch:Channel) "
            "WHERE ch.name CONTAINS '큽큽뱅킹' "
            "RETURN p.name AS 상품명, p.description AS 설명"
        ),
    },
    {
        "question": "비과세 가능한 예금 상품",
        "cypher": (
            "MATCH (p:Product)-[:HAS_TAX_BENEFIT]->(tb:TaxBenefit) "
            "WHERE tb.type CONTAINS '비과세' "
            "RETURN p.name AS 상품명, tb.type AS 세제유형, tb.description AS 조건"
        ),
    },
    {
        "question": "우대금리 조건이 가장 많은 상품",
        "cypher": (
            "MATCH (p:Product)-[:HAS_PREFERENTIAL_RATE]->(pr:PreferentialRate) "
            "WITH p, count(pr) AS 우대건수, collect(pr.name) AS 우대목록 "
            "RETURN p.name AS 상품명, 우대건수, 우대목록 "
            "ORDER BY 우대건수 DESC LIMIT 5"
        ),
    },
    {
        "question": "12개월 이상 가입할 수 있는 적금",
        "cypher": (
            "MATCH (p:Product)-[:BELONGS_TO]->(c:Category), (p)-[:HAS_TERM]->(t:Term) "
            "WHERE c.name CONTAINS '적금' AND t.max_months >= 12 "
            "RETURN p.name AS 상품명, t.min_months AS 최소기간, t.max_months AS 최대기간"
        ),
    },
    {
        "question": "CD91일물 기준 최저금리 대출 TOP5",
        "cypher": (
            "MATCH (lp:LoanProduct)-[:HAS_RATE]->(lr:LoanRate) "
            "WHERE lr.base_rate_name CONTAINS 'CD91일물' "
            "RETURN lp.name AS 상품명, lr.base_rate_name AS 기준금리, "
            "lr.min_rate AS 최저금리, lr.max_rate AS 최고금리 "
            "ORDER BY lr.min_rate ASC LIMIT 5"
        ),
    },
    {
        "question": "원금균등분할상환 가능한 대출 상품",
        "cypher": (
            "MATCH (lp:LoanProduct)-[:REPAID_VIA]->(rm:RepaymentMethod) "
            "WHERE rm.name CONTAINS '원금균등' "
            "RETURN lp.name AS 상품명, collect(rm.name) AS 상환방법"
        ),
    },
    {
        "question": "중도상환수수료가 있는 대출 상품",
        "cypher": (
            "MATCH (lp:LoanProduct)-[:HAS_FEE]->(f:LoanFee) "
            "WHERE f.fee_type = 'early_repayment' "
            "RETURN lp.name AS 상품명, f.description AS 수수료내용"
        ),
    },
    {
        "question": "전세대출 상품 목록과 금리",
        "cypher": (
            "MATCH (lp:LoanProduct)-[:HAS_RATE]->(lr:LoanRate) "
            "WHERE lp.loan_type = 'jeonse' "
            "RETURN lp.name AS 상품명, lr.base_rate_name AS 기준금리, "
            "lr.min_rate AS 최저금리, lr.max_rate AS 최고금리 "
            "ORDER BY lr.min_rate"
        ),
    },
    {
        "question": "금리인하요구권 가능한 대출",
        "cypher": (
            "MATCH (lp:LoanProduct) "
            "WHERE lp.rate_cut_request_available = true "
            "RETURN lp.name AS 상품명, lp.loan_type AS 대출유형, lp.description AS 설명"
        ),
    },
    {
        "question": "부동산 담보로 가능한 대출",
        "cypher": (
            "MATCH (lp:LoanProduct)-[:SECURED_BY]->(col:Collateral) "
            "WHERE col.collateral_type CONTAINS '부동산' "
            "RETURN lp.name AS 상품명, col.collateral_type AS 담보유형, col.description AS 설명"
        ),
    },
    {
        "question": "비상금대출 검색",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('loan_product_search', '비상금대출') "
            "YIELD node, score "
            "RETURN node.name AS 상품명, node.description AS 설명, score "
            "ORDER BY score DESC LIMIT 5"
        ),
    },
    {
        "question": "자동차대출 상품과 금리",
        "cypher": (
            "MATCH (lp:LoanProduct)-[:HAS_RATE]->(lr:LoanRate) "
            "WHERE lp.loan_type = 'auto' "
            "OPTIONAL MATCH (lp)-[:SECURED_BY]->(col:Collateral) "
            "RETURN lp.name AS 상품명, lr.base_rate_name AS 기준금리, "
            "lr.min_rate AS 최저금리, lr.max_rate AS 최고금리, "
            "col.description AS 담보조건 "
            "ORDER BY lr.min_rate"
        ),
    },
    {
        "question": "예금담보대출 상품",
        "cypher": (
            "CALL db.index.fulltext.queryNodes('loan_product_search', '예금담보 예적금담보 유가증권담보') "
            "YIELD node, score "
            "OPTIONAL MATCH (node)-[:HAS_RATE]->(lr:LoanRate) "
            "RETURN node.name AS 상품명, node.description AS 설명, "
            "lr.min_rate AS 최저금리, lr.max_rate AS 최고금리, score "
            "ORDER BY score DESC LIMIT 5"
        ),
    },
]

# ---------------------------------------------------------------------------
# Cypher 생성 프롬프트
# ---------------------------------------------------------------------------

CYPHER_SYSTEM_PROMPT = """\
당신은 Neo4j Cypher 쿼리 생성 전문가입니다.
사용자의 자연어 질문을 아래 스키마에 맞는 Cypher READ 쿼리로 변환하세요.

## 규칙
1. 스키마에 정의된 노드 레이블, 관계 타입, 속성만 사용하세요.
2. 관계 방향을 반드시 스키마대로 지정하세요 (예: (:Product)-[:HAS_RATE]->(:InterestRate)).
3. RETURN 절에 한국어 alias를 사용하세요 (예: AS 상품명, AS 금리).
4. 결과는 LIMIT 10 이하로 제한하세요.
5. 쓰기 작업(CREATE, MERGE, DELETE, SET, REMOVE)은 절대 사용하지 마세요.
6. Cypher 쿼리만 반환하세요. 설명이나 마크다운 없이 순수 Cypher만 출력하세요.

{schema}

## 예시
{examples}
"""

CYPHER_RETRY_PROMPT = """\
이전에 생성한 Cypher 쿼리가 실패했습니다. 에러를 참고하여 수정된 쿼리를 생성하세요.

이전 쿼리:
{previous_cypher}

에러:
{error}

수정된 Cypher 쿼리만 반환하세요.
"""


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

def _build_examples_text() -> str:
    """Few-shot 예시를 텍스트로 변환."""
    lines = []
    for ex in FEW_SHOT_EXAMPLES:
        lines.append(f"질문: {ex['question']}")
        lines.append(f"Cypher: {ex['cypher']}")
        lines.append("")
    return "\n".join(lines)


def _extract_cypher(llm_output: str) -> str:
    """LLM 출력에서 순수 Cypher 추출 (마크다운 코드블록 제거)."""
    text = llm_output.strip()
    # ```cypher ... ``` 또는 ``` ... ``` 블록 처리
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:
            # cypher\n... 또는 바로 쿼리
            cleaned = part.strip()
            if cleaned.lower().startswith("cypher"):
                cleaned = cleaned[6:].strip()
            if cleaned and any(kw in cleaned.upper() for kw in ["MATCH", "CALL", "RETURN", "WITH"]):
                return cleaned.rstrip("`").strip()
    # 코드블록 없으면 그대로
    return text


def _detect_domain(question: str) -> str:
    """질문에서 예금/대출 도메인을 감지."""
    loan_keywords = {"대출", "담보", "LTV", "DSR", "상환", "신용대출", "전세대출", "주담대", "모기지", "자동차대출"}
    deposit_keywords = {"예금", "적금", "정기예금", "저축", "입출금", "청약", "예금자보호", "비과세", "만기"}
    q = question.lower()
    has_loan = any(kw in q for kw in loan_keywords)
    has_deposit = any(kw in q for kw in deposit_keywords)
    if has_loan and not has_deposit:
        return "loan"
    if has_deposit and not has_loan:
        return "deposit"
    return "both"


def _generate_cypher(llm: Any, question: str, domain: str = "both") -> str:
    """LLM을 사용하여 자연어 → Cypher 변환."""
    from langchain_core.messages import HumanMessage, SystemMessage

    schema = {"deposit": DEPOSIT_SCHEMA, "loan": LOAN_SCHEMA, "both": GRAPH_SCHEMA}[domain]

    system = CYPHER_SYSTEM_PROMPT.format(
        schema=schema,
        examples=_build_examples_text(),
    )

    response = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=f"질문: {question}\nCypher:"),
    ])

    return _extract_cypher(response.content)


def _retry_cypher(llm: Any, question: str, previous_cypher: str, error: str) -> str:
    """실패한 Cypher를 에러 피드백과 함께 재생성."""
    from langchain_core.messages import HumanMessage, SystemMessage

    system = CYPHER_SYSTEM_PROMPT.format(
        schema=GRAPH_SCHEMA,
        examples=_build_examples_text(),
    )

    retry_msg = CYPHER_RETRY_PROMPT.format(
        previous_cypher=previous_cypher,
        error=error,
    )

    response = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=f"질문: {question}\n\n{retry_msg}"),
    ])

    return _extract_cypher(response.content)


def _execute_cypher(db: Any, cypher: str) -> list[dict]:
    """Cypher를 Neo4j에서 실행 (읽기 전용)."""
    # 쓰기 작업 방어
    upper = cypher.upper()
    forbidden = ["CREATE", "MERGE", "DELETE", "DETACH", "SET ", "REMOVE"]
    for kw in forbidden:
        if kw in upper:
            raise ValueError(f"쓰기 작업({kw})은 허용되지 않습니다.")
    return db.run_query(cypher)


def _fulltext_fallback(db: Any, question: str) -> str:
    """풀텍스트 검색 fallback."""
    # 예금 검색
    results = db.run_query(
        """
        CALL db.index.fulltext.queryNodes('product_search', $query)
        YIELD node, score WHERE score > 0.3
        RETURN node.name AS name, node.description AS description,
               node.category AS category, score
        ORDER BY score DESC LIMIT 5
        """,
        {"query": question},
    )
    # 대출 검색
    loan_results = db.run_query(
        """
        CALL db.index.fulltext.queryNodes('loan_product_search', $query)
        YIELD node, score WHERE score > 0.3
        RETURN node.name AS name, node.description AS description,
               node.loan_type AS loan_type, score
        ORDER BY score DESC LIMIT 5
        """,
        {"query": question},
    )
    results.extend(loan_results)

    if not results:
        return "검색 결과가 없습니다."

    # 점수순 정렬
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    lines = []
    for r in results[:7]:
        name = r.get("name", "")
        desc = (r.get("description") or "")[:100]
        cat = r.get("category") or r.get("loan_type") or ""
        lines.append(f"- **{name}** ({cat}): {desc}")
    return "\n".join(lines)


def _format_results(results: list[dict], cypher: str) -> str:
    """Cypher 실행 결과를 마크다운 테이블로 변환."""
    if not results:
        return ""

    # 키 추출
    keys = list(results[0].keys())

    # 테이블 헤더
    header = "| " + " | ".join(str(k) for k in keys) + " |"
    separator = "|" + "|".join("---" for _ in keys) + "|"
    rows = []
    for r in results[:15]:  # 최대 15행
        values = []
        for k in keys:
            v = r.get(k, "")
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v[:5])
            elif isinstance(v, float):
                v = f"{v:.2f}" if v != int(v) else str(int(v))
            values.append(str(v)[:80] if v is not None else "")
        rows.append("| " + " | ".join(values) + " |")

    table = "\n".join([header, separator] + rows)
    return f"**실행된 Cypher**: `{cypher[:200]}`\n\n{table}"


# ---------------------------------------------------------------------------
# LangChain Tool
# ---------------------------------------------------------------------------

@tool
def query_knowledge_graph(question: str, db=None, llm=None) -> str:
    """자연어 질문을 Cypher 쿼리로 변환하여 금융상품 지식그래프를 검색합니다.

    복합 조건 검색, 다중 관계 탐색, 집계/비교/정렬 등 기존 검색 도구로
    처리하기 어려운 질문에 사용합니다.

    예시:
    - "금리 3% 이상이면서 비대면 가입 가능한 정기예금"
    - "우대금리 조건이 가장 많은 상품 TOP5"
    - "CD91일물 기준 최저금리 대출"
    - "원금균등 상환 가능하고 중도상환수수료 없는 대출"

    Args:
        question: 자연어 질문
    """
    if db is None:
        return "DB 연결이 필요합니다."
    if llm is None:
        return "LLM 연결이 필요합니다."

    # Step 1: 도메인 감지 + Cypher 생성
    domain = _detect_domain(question)
    try:
        cypher = _generate_cypher(llm, question, domain=domain)
        logger.info("Generated Cypher (domain=%s): %s", domain, cypher)
    except Exception as e:
        logger.warning("Cypher generation failed: %s", e)
        return _fulltext_fallback(db, question)

    # Step 2: 실행
    try:
        results = _execute_cypher(db, cypher)
        if results:
            return _format_results(results, cypher)
        else:
            # Cypher가 정상 실행됐지만 매칭 데이터 없음 — fallback 불필요
            logger.info("Cypher returned no results (domain=%s): %s", domain, cypher)
            return f"검색 조건에 맞는 상품을 찾지 못했습니다. (실행된 쿼리: {cypher[:100]}...)"
    except Exception as e:
        logger.warning("Cypher execution failed: %s (query: %s)", e, cypher)

        # Step 3: 에러 피드백 + 재시도 (1회)
        try:
            cypher2 = _retry_cypher(llm, question, cypher, str(e))
            logger.info("Retry Cypher: %s", cypher2)
            results2 = _execute_cypher(db, cypher2)
            if results2:
                return _format_results(results2, cypher2)
            else:
                logger.info("Retry Cypher also returned no results: %s", cypher2)
                return f"검색 조건에 맞는 상품을 찾지 못했습니다. (실행된 쿼리: {cypher2[:100]}...)"
        except Exception as e2:
            logger.warning("Cypher retry failed: %s", e2)

    # Step 4: 풀텍스트 fallback (실행 오류 발생 시에만 도달)
    logger.info("Falling back to fulltext search for: %s", question)
    return _fulltext_fallback(db, question)
