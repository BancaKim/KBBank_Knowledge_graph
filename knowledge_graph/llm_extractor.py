"""LLM-based entity extraction from markdown product files.

Replaces regex parsers with LangChain `with_structured_output()`.
Injects Foundry ontology skill as domain context for deep extraction.

Usage:
    python -m knowledge_graph.llm_extractor data/products/ [--model gpt-4o-mini] [--dry-run]
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from slugify import slugify

from knowledge_graph.extraction_schemas import (
    ExtractedDepositProduct,
    ExtractedLoanProduct,
)
from knowledge_graph.md_utils import (
    CATEGORY_NAME_EN,
    extract_channels,
    is_loan_product,
    load_md_file,
    parse_korean_amount,
    parse_korean_term,
)
from knowledge_graph.models import (
    Benefit,
    Category,
    Channel,
    DepositProtection,
    EligibilityCondition,
    Feature,
    InterestRate,
    PreferentialRate,
    Product,
    ProductType,
    TaxBenefit,
    Term,
)
from knowledge_graph.parser import ParsedProduct

# Loan models
from knowledge_graph.loan_models import (
    Collateral,
    LoanCategory,
    LoanEligibility,
    LoanFee,
    LoanPreferentialRate,
    LoanProduct,
    LoanRate,
    LoanTerm,
    RepaymentMethod,
)
from knowledge_graph.loan_parser import ParsedLoanProduct


# ---------------------------------------------------------------------------
# Ontology skill loading (catalog only — ~5K tokens)
# ---------------------------------------------------------------------------

SKILL_PATHS = {
    "deposit": Path.home() / ".claude/skills/palantir-deposit-ontology/references/deposit-domain-model.md",
    "loan": Path.home() / ".claude/skills/palantir-loan-ontology/references/loan-domain-model.md",
}


def _load_ontology_catalog(domain: str) -> str:
    """Load catalog Object Types + Enums only. Exclude operational types and Actions."""
    skill_path = SKILL_PATHS.get(domain)
    if not skill_path or not skill_path.exists():
        return ""
    full_text = skill_path.read_text(encoding="utf-8")
    # Extract catalog section (before operational types)
    catalog_end = re.search(r"^##\s+\d+\.\s*(?:운영계|고객|예금계좌|대출계좌)", full_text, re.MULTILINE)
    catalog = full_text[:catalog_end.start()] if catalog_end else full_text[:5000]
    # Extract Enum section
    enum_match = re.search(r"^##\s+\d+\.\s*Enum", full_text, re.MULTILINE)
    if enum_match:
        enum_start = enum_match.start()
        action_match = re.search(r"^##\s+\d+\.\s*Action", full_text[enum_start + 1:], re.MULTILINE)
        enum_end = enum_start + 1 + action_match.start() if action_match else len(full_text)
        enums = full_text[enum_start:enum_end]
    else:
        enums = ""
    return f"{catalog.strip()}\n\n{enums.strip()}"


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

DEPOSIT_SYSTEM_PROMPT = """당신은 한국 은행 금융상품 데이터를 구조화된 JSON으로 추출하는 전문가입니다.

## 추출 규칙

### 금리 (rates)
- 금리유형: 기본(고정금리, 기준금리 없음), 변동(CD/COFIX/금융채 연동), 확정, 단계
- 거주자유형/적립방법유형/개인기업구분별로 금리가 다르면 **각각 별도 항목**으로 추출
- 기간구간별 금리가 다르면 term_months_min/max로 구분하여 **각 구간 별도 항목**
- 이자지급방법: 만기일시, 매월, 매분기, 매년

### 금액
- 한국어 금액을 원문 그대로 보존 (e.g., '1백만원 이상')
- '제한없음', '한도 없음' 등도 그대로

### 가입대상
- 가입고객세부유형: 군인, 학생, 직장인, 공무원 등 해당되면 추출
- 법인고객세부유형: 영리법인, 비영리법인 등
- 비거주자유형: 재외동포, 외국인근로자 등

### 혜택
- 수수료면제와 서비스를 구분하여 추출
- benefit_type을 정확히 지정

### 채널 정규화
- 스타뱅킹/큽스타뱅킹 → '스타뱅킹'
- 인터넷/인터넷뱅킹 → '인터넷'
- 영업점/지점/창구 → '영업점'

## 유의사항 이후 HTML 노이즈는 무시하되, 예금자보호여부와 상품유형 정보는 추출하세요.

"""

LOAN_SYSTEM_PROMPT = """당신은 한국 은행 대출상품 데이터를 구조화된 JSON으로 추출하는 전문가입니다.

## 추출 규칙

### 금리 (rates) — 5차원 분해
- 기준금리유형별로 **각각 별도 항목**: CD91일물, COFIX신규, COFIX잔액, 금융채6개월, 금융채12개월 등
- 각 항목에 기준금리값(base_rate_value), 가산금리(spread), 우대금리(preferential_rate), 최저금리(min_rate), 최고금리(max_rate) 분리
- 파이프(|) 구분 테이블이 있으면 행 단위로 정확히 파싱
- rate_example에 금리 산출 예시 원문 보존

### 연체금리 (penalty_rate)
- 최고 연체금리율, 연체가산금리, 설명 원문 추출

### 기한연장 (term_extension)
- 기한연장 가능여부, 조건 설명

### 통장자동대출 (overdraft)
- 통장자동대출 여부, 한도, 상세 설명

### 상환방법 (repayment_methods)
- 원리금균등분할상환, 원금균등분할상환, 만기일시상환, 혼합상환, 마이너스통장 등
- 대출자격유형별 가능 상환방법이 다르면 각각 추출

### 중도상환수수료 (fees)
- 수수료 유형, 설명, 대출자격유형별 구분

### 담보 (collateral)
- 담보유형: 부동산, 보증서, 예적금, 차량 등
- 보증기관: 서울보증보험(SGI), 한국주택금융공사(HF), 주택도시보증공사(HUG) 등

### 소비자 권리
- 금리인하요구권, 대출계약철회권, 위법계약해지권 — 문서에 언급되면 True

### 원문 보존 필드
- rate_description_raw, penalty_rate_description_raw 등에 해당 섹션 원문(앞 500자)을 보존

### 채널 정규화
- 스타뱅킹/큽스타뱅킹 → '스타뱅킹'

## 유의사항 이후 HTML 노이즈는 무시하되, 소비자 권리 관련 정보는 추출하세요.
"""


# ---------------------------------------------------------------------------
# LLM extraction functions
# ---------------------------------------------------------------------------

def _build_messages(md_content: str, domain: str) -> list:
    """Build system + user messages with ontology context injection."""
    base_prompt = DEPOSIT_SYSTEM_PROMPT if domain == "deposit" else LOAN_SYSTEM_PROMPT
    ontology = _load_ontology_catalog(domain)
    if ontology:
        system = base_prompt + "\n\n## 온톨로지 참조\n" + ontology
    else:
        system = base_prompt
    return [
        SystemMessage(content=system),
        HumanMessage(content=f"다음 마크다운 문서에서 금융상품 정보를 추출하세요:\n\n{md_content}"),
    ]


def extract_deposit(md_content: str, model: str = "gpt-4o-mini") -> ExtractedDepositProduct:
    """Extract deposit product entities from markdown using LLM structured output."""
    llm = ChatOpenAI(model=model, temperature=0)
    structured = llm.with_structured_output(ExtractedDepositProduct, method="json_schema", strict=True)
    messages = _build_messages(md_content, "deposit")
    return structured.invoke(messages)


def extract_loan(md_content: str, model: str = "gpt-4o-mini") -> ExtractedLoanProduct:
    """Extract loan product entities from markdown using LLM structured output."""
    llm = ChatOpenAI(model=model, temperature=0)
    structured = llm.with_structured_output(ExtractedLoanProduct, method="json_schema", strict=True)
    messages = _build_messages(md_content, "loan")
    return structured.invoke(messages)


async def aextract_deposit(md_content: str, model: str = "gpt-4o-mini") -> ExtractedDepositProduct:
    """Async version of extract_deposit."""
    llm = ChatOpenAI(model=model, temperature=0)
    structured = llm.with_structured_output(ExtractedDepositProduct, method="json_schema", strict=True)
    messages = _build_messages(md_content, "deposit")
    return await structured.ainvoke(messages)


async def aextract_loan(md_content: str, model: str = "gpt-4o-mini") -> ExtractedLoanProduct:
    """Async version of extract_loan."""
    llm = ChatOpenAI(model=model, temperature=0)
    structured = llm.with_structured_output(ExtractedLoanProduct, method="json_schema", strict=True)
    messages = _build_messages(md_content, "loan")
    return await structured.ainvoke(messages)


# ---------------------------------------------------------------------------
# Content-hash ID generation (idempotent)
# ---------------------------------------------------------------------------

def _content_hash(product_id: str, *parts: Any) -> str:
    """Generate a short content-based hash for idempotent IDs."""
    raw = f"{product_id}_{'_'.join(str(p) for p in parts)}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Mapping: ExtractedDepositProduct → ParsedProduct
# ---------------------------------------------------------------------------

def map_deposit(extracted: ExtractedDepositProduct, metadata: dict, path: Path) -> ParsedProduct:
    """Map LLM extraction result to ParsedProduct (compatible with existing builder.py)."""
    product_id = metadata.get("id") or slugify(extracted.name) or path.stem

    parsed = ParsedProduct()

    # Product node
    parsed.product = Product(
        id=product_id,
        name=extracted.name,
        product_type=extracted.product_type,
        description=extracted.description,
        amount_max_raw=extracted.amount.max_text,
        amount_max_won=parse_korean_amount(extracted.amount.max_text),
        amount_min_won=parse_korean_amount(extracted.amount.min_text),
        eligibility_summary=extracted.eligibility.summary,
        page_url=str(metadata.get("page_url", "")),
        scraped_at=metadata.get("scraped_at"),
        deposit_insured=extracted.deposit_insured,
        tax_free_savings_eligible=(extracted.tax_benefit_type == "비과세종합저축" and extracted.tax_benefit_eligible),
    )

    # Category
    cat_name = extracted.category or str(metadata.get("category", ""))
    if cat_name:
        parsed.category = Category(
            id=slugify(cat_name) or cat_name,
            name=cat_name,
            name_en=CATEGORY_NAME_EN.get(cat_name, ""),
        )

    # Rates (multi-dimensional from Legacy)
    for rate in extracted.rates:
        rid = _content_hash(product_id, "rate", rate.rate_type, rate.min_rate, rate.max_rate,
                            rate.residency_type, rate.savings_method, rate.term_months_min)
        parsed.rates.append(InterestRate(
            id=f"{product_id}__rate__{rid}",
            rate_type="base",
            min_rate=rate.min_rate,
            max_rate=rate.max_rate,
            base_rate_name=rate.base_rate_name,
        ))

    # Terms
    term = extracted.term
    if term.min_months or term.max_months:
        tid = _content_hash(product_id, "term", term.min_months, term.max_months)
        parsed.terms.append(Term(
            id=f"{product_id}__term__{tid}",
            min_months=term.min_months,
            max_months=term.max_months,
            raw_text=term.raw_text,
        ))

    # Eligibility
    elig = extracted.eligibility
    if elig.summary or elig.target_audience:
        parsed.eligibility = EligibilityCondition(
            id=f"{product_id}__elig",
            description=elig.summary,
            min_age=elig.min_age,
            max_age=elig.max_age,
            target_audience=elig.target_audience,
        )

    # Channels
    if extracted.channels:
        parsed.channels = extract_channels(extracted.channels)

    # Preferential rates
    for i, pr in enumerate(extracted.preferential_rates):
        prid = _content_hash(product_id, "pref", pr.name, pr.rate_value_pp)
        parsed.preferential_rates.append(PreferentialRate(
            id=f"{product_id}__pref__{prid}",
            name=pr.name,
            condition_description=pr.condition_description,
            rate_value_pp=pr.rate_value_pp,
        ))

    # Features
    for i, feat_text in enumerate(extracted.features):
        fid = _content_hash(product_id, "feat", feat_text[:40])
        parsed.features.append(Feature(
            id=f"{product_id}__feat__{fid}",
            name=feat_text,
        ))

    # Benefits
    for benefit in extracted.benefits:
        bid = _content_hash(product_id, "benefit", benefit.name)
        parsed.benefits.append(Benefit(
            id=f"{product_id}__benefit__{bid}",
            benefit_type=benefit.benefit_type or "service",
            name=benefit.name,
            description=benefit.description,
        ))

    # Tax benefit
    if extracted.tax_benefit_type:
        parsed.tax_benefit = TaxBenefit(
            id=f"{product_id}__tax",
            type=extracted.tax_benefit_type,
            eligible=extracted.tax_benefit_eligible,
        )

    # Deposit protection
    parsed.deposit_protection = DepositProtection(
        id=f"{product_id}__dp",
        protected=extracted.deposit_insured,
        max_amount_won=extracted.deposit_protection_max_won,
    )

    # Product type
    if extracted.deposit_subclass:
        parsed.product_type = ProductType(
            id=f"ptype__{slugify(extracted.deposit_subclass)}",
            name=extracted.deposit_subclass,
        )

    return parsed


# ---------------------------------------------------------------------------
# Mapping: ExtractedLoanProduct → ParsedLoanProduct
# ---------------------------------------------------------------------------

def map_loan(extracted: ExtractedLoanProduct, metadata: dict, path: Path) -> ParsedLoanProduct:
    """Map LLM extraction result to ParsedLoanProduct (compatible with loan_builder.py)."""
    product_id = metadata.get("id") or slugify(extracted.name) or path.stem

    parsed = ParsedLoanProduct()

    # LoanProduct node
    parsed.product = LoanProduct(
        id=product_id,
        name=extracted.name,
        loan_type=extracted.loan_type or "",
        description=extracted.description,
        amount_max_raw=extracted.amount.max_text,
        amount_max_won=parse_korean_amount(extracted.amount.max_text),
        eligibility_summary=extracted.eligibility.summary,
        page_url=str(metadata.get("page_url", "")),
        scraped_at=metadata.get("scraped_at"),
        rate_cut_request_available=extracted.rate_cut_request_available,
        contract_withdrawal_available=extracted.contract_withdrawal_available,
        illegal_contract_termination=extracted.illegal_contract_termination,
    )

    # Category
    cat_name = extracted.category or str(metadata.get("category", ""))
    if cat_name:
        parsed.category = LoanCategory(
            id=slugify(cat_name) or cat_name,
            name=cat_name,
            name_en=CATEGORY_NAME_EN.get(cat_name, ""),
        )

    # Rates (5-dimensional from Legacy)
    for rate in extracted.rates:
        rid = _content_hash(product_id, "rate", rate.base_rate_name, rate.min_rate, rate.max_rate)
        parsed.rates.append(LoanRate(
            id=f"{product_id}__rate__{rid}",
            rate_type="base",
            base_rate_name=rate.base_rate_name,
            min_rate=rate.min_rate,
            max_rate=rate.max_rate,
            spread=rate.spread,
        ))

    # Terms
    term = extracted.term
    if term.min_months or term.max_months:
        tid = _content_hash(product_id, "term", term.min_months, term.max_months)
        parsed.terms.append(LoanTerm(
            id=f"{product_id}__term__{tid}",
            min_months=term.min_months,
            max_months=term.max_months,
            raw_text=term.raw_text,
        ))

    # Eligibility
    elig = extracted.eligibility
    if elig.summary or elig.target_audience:
        parsed.eligibility = LoanEligibility(
            id=f"{product_id}__elig",
            description=elig.summary,
            target_audience=elig.target_audience,
            min_age=elig.min_age,
            required_docs=extracted.required_docs,
        )

    # Channels
    if extracted.channels:
        parsed.channels = extract_channels(extracted.channels)

    # Repayment methods
    for rm in extracted.repayment_methods:
        rmid = _content_hash(product_id, "repay", rm.name)
        parsed.repayment_methods.append(RepaymentMethod(
            id=f"repay__{rmid}",
            name=rm.name,
        ))

    # Fees
    for fee in extracted.fees:
        fid = _content_hash(product_id, "fee", fee.fee_type, fee.description[:30])
        parsed.fees.append(LoanFee(
            id=f"{product_id}__fee__{fid}",
            fee_type=fee.fee_type or "기타",
            description=fee.description,
        ))

    # Preferential rates
    for pr in extracted.preferential_rates:
        prid = _content_hash(product_id, "pref", pr.name, pr.rate_value_pp)
        parsed.preferential_rates.append(LoanPreferentialRate(
            id=f"{product_id}__pref__{prid}",
            name=pr.name,
            condition_description=pr.condition_description,
            rate_value_pp=pr.rate_value_pp,
        ))

    # Collateral
    coll = extracted.collateral
    if coll.collateral_type or coll.description:
        parsed.collateral = Collateral(
            id=f"{product_id}__collateral",
            collateral_type=coll.collateral_type or "",
            description=coll.description,
        )

    return parsed


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def extract_product(
    path: Path,
    model: str = "gpt-4o-mini",
) -> ParsedProduct | ParsedLoanProduct:
    """Extract entities from a single MD file using LLM."""
    metadata, body = load_md_file(path)
    md_content = path.read_text(encoding="utf-8")
    category = str(metadata.get("category", ""))

    if is_loan_product(category, path):
        extracted = await aextract_loan(md_content, model=model)
        return map_loan(extracted, metadata, path)
    else:
        extracted = await aextract_deposit(md_content, model=model)
        return map_deposit(extracted, metadata, path)


async def extract_all(
    products_dir: Path,
    model: str = "gpt-4o-mini",
    concurrency: int = 10,
    max_cost: float = 5.0,
) -> list[ParsedProduct | ParsedLoanProduct]:
    """Extract all products with async concurrency and cost control."""
    md_files = sorted(products_dir.glob("**/*.md"))
    if not md_files:
        print(f"[extractor] No .md files in {products_dir}")
        return []

    print(f"[extractor] Found {len(md_files)} MD files, concurrency={concurrency}")
    semaphore = asyncio.Semaphore(concurrency)
    results: list[ParsedProduct | ParsedLoanProduct] = []
    failed: list[str] = []

    async def _extract_one(p: Path, idx: int) -> None:
        async with semaphore:
            try:
                parsed = await extract_product(p, model=model)
                results.append(parsed)
                name = getattr(parsed.product, "name", "?") if parsed.product else "?"
                print(f"[extractor] ({idx}/{len(md_files)}) OK: {name}")
            except Exception as exc:
                failed.append(f"{p.name}: {exc}")
                print(f"[extractor] ({idx}/{len(md_files)}) FAIL: {p.name}: {exc}")

    tasks = [_extract_one(p, i + 1) for i, p in enumerate(md_files)]
    await asyncio.gather(*tasks)

    print(f"[extractor] Done: {len(results)} success, {len(failed)} failed")
    if failed:
        for f in failed[:10]:
            print(f"  - {f}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _async_main() -> None:
    import argparse
    from knowledge_graph.builder import build_graph
    from knowledge_graph.loan_builder import build_loan_graph
    from knowledge_graph.db import Neo4jConnection

    parser = argparse.ArgumentParser(description="LLM-based entity extraction")
    parser.add_argument("products_dir", type=Path, nargs="?",
                        default=Path(__file__).resolve().parent.parent / "data" / "products")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="Extract without Neo4j write")
    parser.add_argument("--output", type=Path, help="Save extracted JSON to file")
    args = parser.parse_args()

    results = await extract_all(args.products_dir, model=args.model, concurrency=args.concurrency)

    if args.output:
        output_data = []
        for r in results:
            if r.product:
                output_data.append({"name": r.product.name, "id": r.product.id, "type": type(r).__name__})
        args.output.write_text(json.dumps(output_data, ensure_ascii=False, indent=2))
        print(f"[extractor] Saved {len(output_data)} entries to {args.output}")

    if not args.dry_run:
        print("[extractor] Writing to Neo4j...")
        with Neo4jConnection() as conn:
            deposits = [r for r in results if isinstance(r, ParsedProduct)]
            loans = [r for r in results if isinstance(r, ParsedLoanProduct)]
            print(f"[extractor] {len(deposits)} deposits, {len(loans)} loans")
            # Use existing builders
            for pp in deposits:
                from knowledge_graph.builder import (
                    _merge_product, _merge_category, _merge_features, _merge_rates,
                    _merge_terms, _merge_eligibility, _merge_channels, _merge_tax_benefit,
                    _merge_deposit_protection, _merge_preferential_rates, _merge_benefits,
                    _merge_product_type,
                )
                _merge_product(conn, pp)
                _merge_category(conn, pp)
                _merge_features(conn, pp)
                _merge_rates(conn, pp)
                _merge_terms(conn, pp)
                _merge_eligibility(conn, pp)
                _merge_channels(conn, pp)
                _merge_tax_benefit(conn, pp)
                _merge_deposit_protection(conn, pp)
                _merge_preferential_rates(conn, pp)
                _merge_benefits(conn, pp)
                _merge_product_type(conn, pp)
            for lp in loans:
                from knowledge_graph.loan_builder import (
                    _merge_loan_product, _merge_loan_category, _merge_loan_rates,
                    _merge_loan_terms, _merge_loan_eligibility, _merge_loan_channels,
                    _merge_repayment_methods, _merge_loan_fees,
                    _merge_loan_preferential_rates, _merge_collateral,
                )
                _merge_loan_product(conn, lp)
                _merge_loan_category(conn, lp)
                _merge_loan_rates(conn, lp)
                _merge_loan_terms(conn, lp)
                _merge_loan_eligibility(conn, lp)
                _merge_loan_channels(conn, lp)
                _merge_repayment_methods(conn, lp)
                _merge_loan_fees(conn, lp)
                _merge_loan_preferential_rates(conn, lp)
                _merge_collateral(conn, lp)
            print("[extractor] Neo4j write complete.")


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
