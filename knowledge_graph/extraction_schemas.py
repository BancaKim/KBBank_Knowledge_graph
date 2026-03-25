"""Pydantic schemas for LLM-based entity extraction.

Maps Legacy ontology's 35 entity types into structured extraction targets.
Used with LangChain's `with_structured_output(strict=True)`.

These are EXTRACTION schemas (what the LLM fills), not storage models.
Mapping to ParsedProduct/ParsedLoanProduct happens in llm_mapper.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------

class ExtractedAmount(BaseModel):
    """Legacy: (:금액 {최소값, 최대값, 증가값, 단위, 통화})"""
    min_text: str = Field(default="", description="최소 금액 원문 (e.g., '1백만원 이상')")
    max_text: str = Field(default="", description="최대 금액 원문 (e.g., '제한없음', '3억원 이내')")
    increment_unit: str = Field(default="", description="증가 단위 (e.g., '만원 단위', '천원 단위')")
    currency: Literal["KRW", "USD", "EUR", "JPY", "CNY", ""] = ""

class ExtractedTerm(BaseModel):
    """Legacy: (:기간 {최소값, 최대값, 증가값, 단위})"""
    min_months: int | None = Field(default=None, description="최소 기간 (월)")
    max_months: int | None = Field(default=None, description="최대 기간 (월)")
    raw_text: str = Field(default="", description="기간 원문 (e.g., '6개월~36개월')")


# ---------------------------------------------------------------------------
# 예금 추출 스키마 — Legacy 예금 온톨로지 매핑
# ---------------------------------------------------------------------------

class ExtractedDepositRate(BaseModel):
    """Legacy: (:예금이율 {기준일자, 금리유형, 거주자유형, 적립방법유형, 개인기업구분, 기간시작/종료, 금액구간, 이율값, 이자지급방법})"""
    rate_type: Literal["기본", "변동", "확정", "단계", ""] = Field(default="", description="금리유형")
    min_rate: float | None = Field(default=None, description="최저 이율 (%)")
    max_rate: float | None = Field(default=None, description="최고 이율 (%)")
    base_rate_name: str = Field(default="", description="기준금리명 (CD91일물, COFIX 등 — 있으면 변동금리)")
    residency_type: Literal["거주자", "비거주자", "전체", ""] = Field(default="", description="거주자유형")
    savings_method: Literal["자유적립", "정액적립", "거치식", ""] = Field(default="", description="적립방법유형")
    customer_segment: Literal["개인", "기업", "전체", ""] = Field(default="", description="개인기업구분")
    term_months_min: int | None = Field(default=None, description="적용 기간구간 시작 (월)")
    term_months_max: int | None = Field(default=None, description="적용 기간구간 종료 (월)")
    interest_pay_method: Literal["만기일시", "매월", "매분기", "매년", ""] = Field(default="", description="이자지급방법")

class ExtractedPreferentialRate(BaseModel):
    """Legacy: (:예금우대이율 {조건, 이율값}) / (:대출우대금리 {우대금리유형, 조건, 이율값})"""
    name: str = Field(default="", description="우대 조건명")
    condition_description: str = Field(default="", description="우대 조건 상세")
    rate_value_pp: float | None = Field(default=None, description="우대금리 %p")
    rate_type: Literal["실적연동", "영업점", "고정", ""] = Field(default="", description="우대금리유형")

class ExtractedEligibility(BaseModel):
    """Legacy: (:예금가입대상 {가입고객세부유형, 법인고객세부유형, 비거주자유형, 최소/최대나이})"""
    summary: str = Field(default="", description="가입대상 요약")
    target_audience: Literal["개인", "법인", "개인사업자", "직장인", "공무원", "군인", "학생", "전체", ""] = ""
    min_age: int | None = None
    max_age: int | None = None
    customer_sub_types: list[str] = Field(default_factory=list, description="가입고객세부유형 (군인, 학생, 직장인 등)")
    corporate_sub_types: list[str] = Field(default_factory=list, description="법인고객세부유형 (영리, 비영리 등)")
    non_resident_types: list[str] = Field(default_factory=list, description="비거주자유형 (재외동포, 외국인근로자 등)")

class ExtractedBenefit(BaseModel):
    """Legacy: (:수수료면제) + (:서비스) — 혜택 2종"""
    benefit_type: Literal["수수료면제", "서비스", "경품", "금리우대", ""] = ""
    name: str = ""
    description: str = ""

class ExtractedDepositProduct(BaseModel):
    """예금 상품 전체 추출 스키마.

    Legacy 매핑:
    - (:예금) → name, product_type, description
    - (:적립식예금)/(:거치식예금)/(:요구불예금) → deposit_subclass
    - (:금액) → amount
    - (:기간) → term
    - (:예금이율) → rates[]
    - (:예금우대이율) → preferential_rates[]
    - (:예금가입대상) → eligibility
    - (:수수료면제)+(:서비스) → benefits[]
    """
    # 상품 기본 정보
    name: str
    product_type: Literal["deposit", "savings"] = "deposit"
    deposit_subclass: Literal["적립식예금", "거치식예금", "요구불예금", ""] = Field(
        default="", description="Legacy 서브클래스"
    )
    description: str = ""
    category: str = Field(default="", description="상품카테고리 (정기예금, 적금, 입출금통장, 청약)")

    # 금액 / 기간
    amount: ExtractedAmount = Field(default_factory=ExtractedAmount)
    term: ExtractedTerm = Field(default_factory=ExtractedTerm)

    # 금리 체계
    rates: list[ExtractedDepositRate] = Field(default_factory=list, description="예금이율 목록 (다차원)")
    max_preferential_rate: float | None = Field(default=None, description="최대우대이율값")
    preferential_rates: list[ExtractedPreferentialRate] = Field(default_factory=list)

    # 가입 조건
    eligibility: ExtractedEligibility = Field(default_factory=ExtractedEligibility)
    channels: list[str] = Field(default_factory=list, description="가입채널 (스타뱅킹, 인터넷, 영업점 등)")

    # 혜택
    benefits: list[ExtractedBenefit] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list, description="상품특징 목록")

    # 세제/보호
    tax_benefit_type: Literal["비과세종합저축", "일반과세", "비과세", ""] = "일반과세"
    tax_benefit_eligible: bool = False
    deposit_insured: bool = True
    deposit_protection_max_won: int | None = Field(default=None, description="예금자보호 한도 (원)")

    # 예금 속성 (Legacy)
    settlement_basis: str = Field(default="", description="결산기준일 (매월/매분기/매년)")
    interest_calc_method: Literal["단리", "복리", ""] = Field(default="", description="이자계산방법")


# ---------------------------------------------------------------------------
# 대출 추출 스키마 — Legacy 대출 온톨로지 매핑
# ---------------------------------------------------------------------------

class ExtractedLoanRate(BaseModel):
    """Legacy: (:대출금리 {대출자격유형, 기준금리유형, 기준금리, 가산금리, 우대금리, 최저금리, 최고금리})"""
    base_rate_name: str = Field(default="", description="기준금리유형 (CD91일물, COFIX신규, 금융채6개월 등)")
    base_rate_value: float | None = Field(default=None, description="기준금리 값 (%)")
    spread: float | None = Field(default=None, description="가산금리 (%p)")
    preferential_rate: float | None = Field(default=None, description="우대금리 합계 (%p)")
    min_rate: float | None = Field(default=None, description="최저금리 (%)")
    max_rate: float | None = Field(default=None, description="최고금리 (%)")
    loan_qualification_type: str = Field(default="", description="대출자격유형 (가계일반, 가계전세 등)")
    rate_example: str = Field(default="", description="금리예시 원문")

class ExtractedPenaltyRate(BaseModel):
    """Legacy: (:연체금리 {상환방법유형, 이자계산단위유형, 선후취유형, 연체이자계산적용방법유형})"""
    max_rate: float | None = Field(default=None, description="최고 연체금리 (%)")
    penalty_spread: float | None = Field(default=None, description="연체가산금리 (%p)")
    description: str = Field(default="", description="연체금리 설명 원문")

class ExtractedTermExtension(BaseModel):
    """Legacy: (:기한연장 {대출자격유형, 상환방법유형, 기한연장여부})"""
    available: bool = False
    description: str = Field(default="", description="기한연장 조건 설명")

class ExtractedOverdraft(BaseModel):
    """Legacy: (:통장자동대출 {상환방법유형, 통장자동대출여부})"""
    available: bool = False
    max_text: str = Field(default="", description="통장자동대출 한도 원문")
    description: str = Field(default="", description="통장자동대출 상세")

class ExtractedRepaymentMethod(BaseModel):
    """Legacy: (:상환방법 {대출자격유형, 한도개별거래구분유형, 상환방법유형})"""
    name: str = Field(description="상환방법명 (원리금균등, 원금균등, 만기일시 등)")
    loan_qualification_type: str = Field(default="", description="대출자격유형")
    limit_type: str = Field(default="", description="한도개별거래구분유형")

class ExtractedLoanFee(BaseModel):
    """Legacy: (:중도상환수수료 {대출자격유형, 한도개별거래구분유형, 상환방법유형})"""
    fee_type: Literal["중도상환수수료", "부대비용", "조기상환수수료", "인지세", "기타", ""] = ""
    description: str = ""
    loan_qualification_type: str = Field(default="", description="대출자격유형")

class ExtractedCollateral(BaseModel):
    """Legacy: (:담보 {담보유형})"""
    collateral_type: Literal["부동산", "보증서", "예적금", "차량", "기타", ""] = ""
    description: str = ""
    guarantee_institution: str = Field(default="", description="보증기관 (SGI, HF, HUG 등)")

class ExtractedLoanProduct(BaseModel):
    """대출 상품 전체 추출 스키마.

    Legacy 매핑:
    - (:대출) → name, loan_type, description
    - (:가계대출)/(:기업대출)/(:기금대출) → loan_subclass
    - (:대출금리) → rates[]
    - (:대출우대금리) → preferential_rates[]
    - (:연체금리) → penalty_rate
    - (:기한연장) → term_extension
    - (:통장자동대출) → overdraft
    - (:상환방법) → repayment_methods[]
    - (:중도상환수수료) → fees[]
    - (:담보) → collateral
    """
    # 상품 기본 정보
    name: str
    loan_type: Literal["credit", "secured", "jeonse", "auto", ""] = ""
    loan_subclass: Literal["가계대출", "기업대출", "기금대출", ""] = Field(
        default="", description="Legacy 서브클래스"
    )
    description: str = ""
    category: str = Field(default="", description="대출카테고리 (신용대출, 담보대출, 전월세대출, 자동차대출)")

    # 금액 / 기간
    amount: ExtractedAmount = Field(default_factory=ExtractedAmount)
    term: ExtractedTerm = Field(default_factory=ExtractedTerm)

    # 금리 체계 (Legacy 5차원 분해)
    rates: list[ExtractedLoanRate] = Field(default_factory=list, description="대출금리 목록 (기준금리유형별)")
    preferential_rates: list[ExtractedPreferentialRate] = Field(default_factory=list)
    penalty_rate: ExtractedPenaltyRate = Field(default_factory=ExtractedPenaltyRate)

    # Legacy 핵심 엔티티
    term_extension: ExtractedTermExtension = Field(default_factory=ExtractedTermExtension)
    overdraft: ExtractedOverdraft = Field(default_factory=ExtractedOverdraft)

    # 상환 / 수수료 / 담보
    repayment_methods: list[ExtractedRepaymentMethod] = Field(default_factory=list)
    fees: list[ExtractedLoanFee] = Field(default_factory=list)
    collateral: ExtractedCollateral = Field(default_factory=ExtractedCollateral)

    # 자격
    eligibility: ExtractedEligibility = Field(default_factory=ExtractedEligibility)
    required_docs: str = Field(default="", description="필요서류/준비서류")
    channels: list[str] = Field(default_factory=list)

    # 소비자 권리
    rate_cut_request_available: bool = Field(default=False, description="금리인하요구권")
    contract_withdrawal_available: bool = Field(default=False, description="대출계약철회권")
    illegal_contract_termination: bool = Field(default=False, description="위법계약해지권")

    # 원문 보존 (Legacy 설명 필드)
    rate_description_raw: str = Field(default="", description="대출금리설명 원문")
    penalty_rate_description_raw: str = Field(default="", description="연체금리설명 원문")
    fee_description_raw: str = Field(default="", description="중도상환수수료설명 원문")
    collateral_description_raw: str = Field(default="", description="담보설명 원문")
    repayment_description_raw: str = Field(default="", description="상환방법설명 원문")
