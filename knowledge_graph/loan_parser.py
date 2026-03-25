"""Parse markdown loan product files into Pydantic models.

Mirrors parser.py structure but for loan-specific entities.
Reads from data/products/대출/*.md
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter
from slugify import slugify

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
from knowledge_graph.models import Channel

# Re-use shared helpers from md_utils (previously duplicated across parsers)
from knowledge_graph.md_utils import (
    extract_channels as _extract_channels,
    parse_korean_amount,
    parse_korean_term,
    parse_rate_string,
    split_sections as _split_sections,
    split_sections_full as _split_sections_full,
    split_subsections as _split_subsections,
)

# ---------------------------------------------------------------------------
# Public data container
# ---------------------------------------------------------------------------


class ParsedLoanProduct:
    """All entities extracted from a single loan markdown file."""

    def __init__(self) -> None:
        self.product: LoanProduct | None = None
        self.category: LoanCategory | None = None
        self.rates: list[LoanRate] = []
        self.terms: list[LoanTerm] = []
        self.eligibility: LoanEligibility | None = None
        self.channels: list[Channel] = []
        self.repayment_methods: list[RepaymentMethod] = []
        self.fees: list[LoanFee] = []
        self.preferential_rates: list[LoanPreferentialRate] = []
        self.collateral: Collateral | None = None


# ---------------------------------------------------------------------------
# Category mapping (loan only)
# ---------------------------------------------------------------------------

LOAN_CATEGORY_EN: dict[str, str] = {
    "신용대출": "Credit Loan",
    "담보대출": "Secured Loan",
    "전월세대출": "Jeonse/Wolse Loan",
    "전월세/반환보증": "Jeonse/Wolse Loan",
    "자동차대출": "Auto Loan",
}

CATEGORY_TO_LOAN_TYPE: dict[str, str] = {
    "신용대출": "credit",
    "담보대출": "secured",
    "전월세대출": "jeonse",
    "전월세/반환보증": "jeonse",
    "자동차대출": "auto",
}


# ---------------------------------------------------------------------------
# Repayment method parsing
# ---------------------------------------------------------------------------

def parse_repayment(text: str) -> list[str]:
    """Split and normalize repayment methods from body or frontmatter."""
    if not text:
        return []
    methods: list[str] = []
    text = text.replace("원(리)금균등분할상환", "원리금균등분할상환")

    known = [
        "마이너스통장", "일시상환", "원리금균등분할상환",
        "원금균등분할상환", "혼합상환", "분할상환", "만기일시상환",
    ]
    for k in known:
        if k in text:
            methods.append(k)

    if not methods:
        for sep in [",", "/", "\n"]:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                methods.extend(parts)
                return methods
        if text.strip():
            methods.append(text.strip())
    return methods


# ---------------------------------------------------------------------------
# Fee parsing
# ---------------------------------------------------------------------------

def parse_loan_fees(section_text: str, product_id: str) -> list[LoanFee]:
    """Extract fees from 중도상환해약금/수수료 sections."""
    fees: list[LoanFee] = []
    idx = 0
    if "중도상환" in section_text:
        fees.append(LoanFee(
            id=f"{product_id}__fee__{idx}",
            fee_type="early_repayment",
            description=section_text.strip()[:200],
        ))
        idx += 1
    if "부대비용" in section_text:
        fees.append(LoanFee(
            id=f"{product_id}__fee__{idx}",
            fee_type="incidental",
            description=section_text.strip()[:200],
        ))
        idx += 1
    if "조기상환" in section_text:
        fees.append(LoanFee(
            id=f"{product_id}__fee__{idx}",
            fee_type="early_repayment",
            description=section_text.strip()[:200],
        ))
        idx += 1
    return fees


# ---------------------------------------------------------------------------
# Eligibility parsing
# ---------------------------------------------------------------------------

def parse_loan_eligibility(text: str, product_id: str) -> LoanEligibility:
    """Extract loan eligibility from body text."""
    target = ""
    if "직장인" in text:
        target = "직장인"
    elif "공무원" in text:
        target = "공무원"
    elif "개인사업자" in text:
        target = "개인사업자"
    elif "개인" in text:
        target = "개인"

    min_income = ""
    income_match = re.search(r"연소득\s*(\d[\d,]*)\s*만?\s*원", text)
    if income_match:
        min_income = income_match.group(0)

    return LoanEligibility(
        id=f"{product_id}__elig",
        description=text.strip()[:300],
        target_audience=target,
        min_income=min_income,
    )


# ---------------------------------------------------------------------------
# Preferential rate parsing
# ---------------------------------------------------------------------------

def parse_loan_preferential_rates(section_text: str, product_id: str) -> list[LoanPreferentialRate]:
    """Extract preferential rate conditions from 우대금리 section."""
    rates: list[LoanPreferentialRate] = []
    idx = 0
    for line in section_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        rate_match = re.search(r"(\d+\.?\d*)\s*%", line)
        if rate_match:
            rate_val = float(rate_match.group(1))
            if rate_val > 10.0:
                continue
            name = line[:40].strip()
            rates.append(LoanPreferentialRate(
                id=f"{product_id}__lpref__{idx}",
                name=name[:80],
                condition_description=line[:150],
                rate_value_pp=rate_val,
            ))
            idx += 1
    return rates


# ---------------------------------------------------------------------------
# Collateral parsing
# ---------------------------------------------------------------------------

def parse_collateral(section_text: str, product_id: str) -> Collateral | None:
    """Extract collateral info from 담보 section."""
    if not section_text.strip():
        return None
    col_type = ""
    if "부동산" in section_text:
        col_type = "부동산"
    elif "예적금" in section_text or "예금" in section_text:
        col_type = "예적금"
    elif "보증서" in section_text:
        col_type = "보증서"
    elif "주택" in section_text:
        col_type = "주택"
    return Collateral(
        id=f"{product_id}__collateral",
        collateral_type=col_type,
        description=section_text.strip()[:200],
    )


# ---------------------------------------------------------------------------
# Rate table parsing (loan-specific: table format from scraper)
# ---------------------------------------------------------------------------

def parse_loan_rate_table(rate_text: str, product_id: str) -> list[LoanRate]:
    """Parse rate table from ## 금리 및 이율 section (pipe-delimited)."""
    rates: list[LoanRate] = []
    if not rate_text:
        return rates

    # Try to extract min/max rates from the text
    all_rates = [float(m.group(1)) for m in re.finditer(r"(\d+\.\d+)\s*%?", rate_text) if float(m.group(1)) <= 20.0]

    if all_rates:
        min_r = min(all_rates)
        max_r = max(all_rates)
        rate_type = "variable" if "변동" in rate_text else "fixed" if "고정" in rate_text else "mixed"

        # Try to find base rate name
        base_rate = ""
        for keyword in ["CD", "COFIX", "금융채", "MOR"]:
            if keyword in rate_text:
                base_rate = keyword
                break

        rates.append(LoanRate(
            id=f"{product_id}__lrate__base",
            rate_type=rate_type,
            min_rate=min_r,
            max_rate=max_r,
            base_rate_name=base_rate,
            rate_example=rate_text.strip()[:300],
        ))

    return rates


# Section splitting functions imported from md_utils:
# _split_sections, _split_sections_full, _split_subsections


# ---------------------------------------------------------------------------
# Core: parse a single loan product file
# ---------------------------------------------------------------------------

def parse_loan_file(path: Path) -> ParsedLoanProduct:
    """Parse a single loan markdown file and return extracted entities."""
    post = frontmatter.load(str(path))
    meta: dict[str, Any] = dict(post.metadata)
    body: str = post.content

    product_id = meta.get("id") or slugify(path.stem) or path.stem
    name = meta.get("name") or path.stem.replace("-", " ").title()
    category_name = str(meta.get("category", ""))

    parsed = ParsedLoanProduct()

    # --- Loan type from category ---
    loan_type = CATEGORY_TO_LOAN_TYPE.get(category_name, "")

    # --- Parse amounts ---
    amounts = meta.get("amounts", {}) or {}
    amount_max_raw = str(amounts.get("max", "")) if isinstance(amounts, dict) else ""
    amount_max_won = parse_korean_amount(amount_max_raw)

    # --- Eligibility summary ---
    eligibility_summary = str(meta.get("eligibility_summary", ""))

    # --- LoanProduct node ---
    parsed.product = LoanProduct(
        id=product_id,
        name=str(name),
        loan_type=loan_type,
        description=str(meta.get("description", "")),
        amount_max_raw=amount_max_raw,
        amount_max_won=amount_max_won,
        eligibility_summary=eligibility_summary,
        page_url=str(meta.get("page_url", "")),
        scraped_at=meta.get("scraped_at"),
    )

    # --- Category ---
    if category_name:
        cat_id = f"loan__{slugify(category_name) or category_name}"
        parsed.category = LoanCategory(
            id=cat_id,
            name=category_name,
            name_en=LOAN_CATEGORY_EN.get(category_name, ""),
        )

    # --- Channels ---
    channels_raw = meta.get("channels", [])
    if isinstance(channels_raw, list):
        parsed.channels = _extract_channels(channels_raw)

    # --- Repayment methods from frontmatter ---
    repayment_raw = str(meta.get("repayment", ""))
    if repayment_raw:
        method_names = parse_repayment(repayment_raw)
        seen: set[str] = set()
        for mn in method_names:
            mid = f"repay__{slugify(mn) or mn}"
            if mid not in seen:
                seen.add(mid)
                parsed.repayment_methods.append(
                    RepaymentMethod(id=mid, name=mn, description="")
                )

    # --- Terms from frontmatter ---
    term_raw = str(meta.get("term", ""))
    if term_raw:
        min_m, max_m = parse_korean_term(term_raw)
        if min_m is not None or max_m is not None:
            parsed.terms.append(LoanTerm(
                id=f"{product_id}__term__primary",
                min_months=min_m, max_months=max_m, raw_text=term_raw,
            ))

    # --- Body sections ---
    sections = _split_sections(body)
    subsections = _split_subsections(body)
    full_sections = _split_sections_full(body)

    # --- Rates from body (table format) ---
    for key in ("금리 및 이율", "금리", "대출금리"):
        if key in full_sections:
            parsed.rates = parse_loan_rate_table(full_sections[key], product_id)
            break
    # Fallback: from frontmatter (supports both dict and string format)
    if not parsed.rates:
        rates_meta = meta.get("rates", {}) or {}
        rate_min: float | None = None
        rate_max: float | None = None
        rate_type_str = "mixed"
        if isinstance(rates_meta, dict):
            rate_min = parse_rate_string(str(rates_meta.get("min", "")))
            rate_max = parse_rate_string(str(rates_meta.get("max", "")))
            rate_type_str = str(rates_meta.get("type", "mixed"))
        elif isinstance(rates_meta, str):
            # Parse string: "기준금리: CD91일 2.84%, COFIX 2.82%" or "연 3.5% ~ 5.2%"
            all_rates_found = [float(m.group(1)) for m in re.finditer(r"(\d+\.\d+)\s*%?", rates_meta) if float(m.group(1)) <= 20.0]
            if len(all_rates_found) >= 2:
                rate_min = min(all_rates_found)
                rate_max = max(all_rates_found)
            elif len(all_rates_found) == 1:
                rate_min = all_rates_found[0]
                rate_max = all_rates_found[0]
            # Detect rate type from text
            if "변동" in rates_meta or "COFIX" in rates_meta or "CD" in rates_meta:
                rate_type_str = "variable"
            elif "고정" in rates_meta or "금융채" in rates_meta:
                rate_type_str = "fixed"
            # Detect base rate name
            base_name = ""
            for kw in ["CD91일물", "CD", "COFIX", "금융채", "MOR"]:
                if kw in rates_meta:
                    base_name = kw
                    break
        if rate_min is not None or rate_max is not None:
            parsed.rates.append(LoanRate(
                id=f"{product_id}__lrate__base",
                rate_type=rate_type_str,
                min_rate=rate_min, max_rate=rate_max,
                base_rate_name=base_name if isinstance(rates_meta, str) else "",
                rate_example=rates_meta if isinstance(rates_meta, str) else "",
            ))

    # --- Eligibility from body ---
    elig_text = eligibility_summary
    for key in ("대출신청자격", "신청자격", "가입대상", "대상"):
        if key in sections:
            elig_text = sections[key]
            break
    if elig_text:
        parsed.eligibility = parse_loan_eligibility(elig_text, product_id)
        # Also extract 준비서류
        for key in ("준비서류",):
            if key in sections:
                parsed.eligibility.required_docs = sections[key].strip()[:200]

    # --- Repayment methods from body (supplement frontmatter) ---
    if not parsed.repayment_methods:
        for key in ("대출기간 및 상환 방법", "대출기간 및 상환방법", "상환방법"):
            if key in sections:
                method_names = parse_repayment(sections[key])
                seen_body: set[str] = set()
                for mn in method_names:
                    mid = f"repay__{slugify(mn) or mn}"
                    if mid not in seen_body:
                        seen_body.add(mid)
                        parsed.repayment_methods.append(
                            RepaymentMethod(id=mid, name=mn, description="")
                        )
                break

    # --- Fees from body ---
    for key in ("중도상환해약금", "중도상환수수료", "수수료"):
        text = subsections.get(key, "") or sections.get(key, "")
        if text:
            parsed.fees = parse_loan_fees(text, product_id)
            break

    # --- Preferential rates ---
    for key in ("우대금리", "우대이율"):
        if key in sections:
            parsed.preferential_rates = parse_loan_preferential_rates(sections[key], product_id)
            break

    # --- Collateral (for 담보대출) ---
    for key in ("담보", "담보물"):
        text = subsections.get(key, "") or sections.get(key, "")
        if text:
            parsed.collateral = parse_collateral(text, product_id)
            break

    # --- Consumer rights from full body text (boolean flags) ---
    if parsed.product:
        if "금리인하요구권" in body:
            parsed.product.rate_cut_request_available = True
        if "대출계약철회권" in body:
            parsed.product.contract_withdrawal_available = True
        if "위법계약해지권" in body:
            parsed.product.illegal_contract_termination = True

    return parsed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_all_loan_products(products_dir: Path) -> list[ParsedLoanProduct]:
    """Parse every *.md file in the loan products directory."""
    if not products_dir.is_dir():
        return []
    results: list[ParsedLoanProduct] = []
    for md_path in sorted(products_dir.glob("**/*.md")):
        try:
            results.append(parse_loan_file(md_path))
        except Exception as exc:  # noqa: BLE001
            print(f"[loan_parser] WARNING: skipping {md_path.name}: {exc}")
    return results
