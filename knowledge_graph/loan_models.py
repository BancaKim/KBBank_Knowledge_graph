"""Pydantic v2 models for loan knowledge graph entity types.

Loan-only ontology, separate from deposit models.
Only attributes that can be populated from scraped KB loan data are included.
Legacy depth is preserved in the Foundry skill (design reference).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Core loan entity models
# ---------------------------------------------------------------------------

class LoanProduct(BaseModel):
    """대출상품 — Neo4j label :LoanProduct"""
    id: str
    name: str
    loan_type: str = ""  # credit / secured / jeonse / auto
    description: str = ""
    amount_max_raw: str = ""
    amount_max_won: int | None = None
    eligibility_summary: str = ""
    page_url: str = ""
    scraped_at: datetime | None = None
    # --- 파서에서 실제 추출 가능한 Legacy 속성 ---
    rate_cut_request_available: bool = False  # 금리인하요구권 (body 텍스트 검색)
    contract_withdrawal_available: bool = False  # 대출계약철회권
    illegal_contract_termination: bool = False  # 위법계약해지권


class LoanCategory(BaseModel):
    """신용대출/담보대출/전월세대출/자동차대출"""
    id: str
    name: str
    name_en: str = ""


class LoanRate(BaseModel):
    """대출금리 — Legacy :대출금리 반영"""
    id: str
    rate_type: str = "fixed"  # fixed / variable / mixed
    min_rate: float | None = None
    max_rate: float | None = None
    base_rate_name: str = ""  # CD91일물/COFIX/금융채 등
    spread: float | None = None  # 가산금리
    rate_example: str = ""  # 금리예시 원문


class RepaymentMethod(BaseModel):
    """상환방법 — Legacy :상환방법 반영"""
    id: str
    name: str = ""  # 원리금균등/원금균등/만기일시 등
    description: str = ""


class LoanFee(BaseModel):
    """중도상환수수료/부대비용 — Legacy :중도상환수수료 반영"""
    id: str
    fee_type: str = ""  # early_repayment / incidental
    description: str = ""


class LoanEligibility(BaseModel):
    """대출 가입자격 — Legacy :가입대상 반영"""
    id: str
    description: str = ""
    target_audience: str = ""  # 직장인/사업자/공무원 등
    min_income: str = ""  # 소득 요건 (텍스트)
    required_docs: str = ""  # 준비서류 요약


class LoanTerm(BaseModel):
    """대출기간"""
    id: str
    min_months: int | None = None
    max_months: int | None = None
    raw_text: str = ""


class LoanPreferentialRate(BaseModel):
    """대출 우대금리 — Legacy :대출우대금리 반영"""
    id: str
    name: str = ""
    condition_description: str = ""
    rate_value_pp: float | None = None  # 우대금리 %p


class Collateral(BaseModel):
    """담보 — Legacy :담보 반영"""
    id: str
    collateral_type: str = ""  # 부동산/예적금/보증서 등
    description: str = ""
