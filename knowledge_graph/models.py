"""Pydantic v2 models for knowledge graph entity types."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core entity models (expanded schema)
# ---------------------------------------------------------------------------

class Product(BaseModel):
    id: str
    name: str
    product_type: str = ""  # loan / deposit / savings
    description: str = ""
    amount_max_raw: str = ""
    amount_max_won: int | None = None
    eligibility_summary: str = ""
    page_url: str = ""
    scraped_at: datetime | None = None


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


class RepaymentMethod(BaseModel):
    id: str
    name: str
    description: str = ""


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


class Fee(BaseModel):
    id: str
    fee_type: str = ""  # 중도상환수수료 / 조기상환수수료 / 부대비용
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
