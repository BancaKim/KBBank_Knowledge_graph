"""Pydantic v2 models for knowledge graph entity types.

Deposit-only ontology. Loan models have been removed — loans will have
a separate ontology.  Only attributes that can actually be populated
from scraped KB product data are included (no overfitting).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core entity models (deposit-only)
# ---------------------------------------------------------------------------

class Product(BaseModel):
    id: str
    name: str
    product_type: str = ""  # deposit / savings
    description: str = ""
    amount_max_raw: str = ""
    amount_max_won: int | None = None
    amount_min_won: int | None = None  # Legacy 최소가입금액
    eligibility_summary: str = ""
    page_url: str = ""
    scraped_at: datetime | None = None
    # --- 파서에서 실제 추출 가능한 Legacy 속성 ---
    deposit_insured: bool = True  # 예금자보호여부 (parse_deposit_protection)
    tax_free_savings_eligible: bool = False  # 비과세종합저축 가능여부 (parse_tax_benefit)


class Category(BaseModel):
    id: str
    name: str
    name_en: str = ""


class ParentCategory(BaseModel):
    id: str
    name: str
    name_en: str = ""


class Channel(BaseModel):
    id: str
    name: str
    name_en: str = ""


class InterestRate(BaseModel):
    id: str
    rate_type: str = "base"  # base / preferential / penalty
    min_rate: float | None = None
    max_rate: float | None = None
    base_rate_name: str = ""
    spread: float | None = None


class Term(BaseModel):
    id: str
    min_months: int | None = None
    max_months: int | None = None
    raw_text: str = ""


class EligibilityCondition(BaseModel):
    id: str
    description: str = ""
    min_age: int | None = None
    max_age: int | None = None
    target_audience: str = ""


class TaxBenefit(BaseModel):
    id: str
    type: str = "일반과세"  # 비과세종합저축 / 일반과세 / 비과세
    eligible: bool = False
    description: str = ""


class DepositProtection(BaseModel):
    id: str
    protected: bool = False
    max_amount_won: int | None = None
    description: str = ""


class PreferentialRate(BaseModel):
    id: str
    name: str = ""
    condition_description: str = ""
    rate_value_pp: float | None = None


class Feature(BaseModel):
    id: str
    name: str
    description: str = ""


class Benefit(BaseModel):
    """상품 혜택 (수수료면제, 부가서비스 등). Legacy :수수료면제 + :서비스 통합."""
    id: str
    benefit_type: str = ""  # fee_exemption / service / gift / rate_bonus
    name: str = ""
    description: str = ""


class ProductType(BaseModel):
    id: str
    name: str = ""


# ---------------------------------------------------------------------------
# D3.js visualization models
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    label: str = ""
    type: str = ""
    group: int = 0
    data: dict[str, Any] = Field(default_factory=dict)


class GraphLink(BaseModel):
    source: str
    target: str
    type: str = ""
    value: float = 1.0
