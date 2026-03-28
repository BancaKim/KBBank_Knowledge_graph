"""Parse markdown product files from data/products/ into Pydantic models.

Regex-based parser (fallback). Primary extraction is now LLM-based via llm_mapper.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter
from slugify import slugify

from knowledge_graph.md_utils import (
    CATEGORY_NAME_EN,
    CATEGORY_TO_PARENT,
    CATEGORY_TO_PRODUCT_TYPE,
    CHANNEL_MAP,
    extract_channels as _extract_channels,
    extract_list_items as _extract_list_items,
    load_md_file,
    parse_korean_amount,
    parse_korean_term,
    parse_rate_string,
    safe_float as _safe_float,
    split_sections as _split_sections,
    split_sections_full as _split_sections_full,
    split_subsections as _split_subsections,
)
from knowledge_graph.deposit_models import (
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

# ---------------------------------------------------------------------------
# Public data container returned per parsed file
# ---------------------------------------------------------------------------


class ParsedProduct:
    """All entities extracted from a single markdown product file."""

    def __init__(self) -> None:
        self.product: Product | None = None
        self.category: Category | None = None
        self.features: list[Feature] = []
        self.rates: list[InterestRate] = []
        self.terms: list[Term] = []
        self.eligibility: EligibilityCondition | None = None
        self.channels: list[Channel] = []
        self.tax_benefit: TaxBenefit | None = None
        self.deposit_protection: DepositProtection | None = None
        self.preferential_rates: list[PreferentialRate] = []
        self.benefits: list[Benefit] = []
        self.product_type: ProductType | None = None




# ---------------------------------------------------------------------------
# Benefit extraction (replaces loan-only Fee/RepaymentMethod)
# ---------------------------------------------------------------------------

def parse_benefits(section_text: str, product_id: str) -> list[Benefit]:
    """Extract benefits (수수료면제, 부가서비스 등) from ## 혜택 sections."""
    benefits: list[Benefit] = []
    idx = 0
    if "수수료" in section_text and ("면제" in section_text or "무료" in section_text):
        benefits.append(Benefit(
            id=f"{product_id}__benefit__{idx}",
            benefit_type="fee_exemption",
            name="수수료 면제",
            description=section_text.strip()[:200],
        ))
        idx += 1
    for line in section_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("- ", "* ")):
            item = line[2:].strip()
            if item and not any(b.name == item for b in benefits):
                benefits.append(Benefit(
                    id=f"{product_id}__benefit__{idx}",
                    benefit_type="service",
                    name=item[:80],
                    description=item[:150],
                ))
                idx += 1
    return benefits


# ---------------------------------------------------------------------------
# Tax benefit extraction
# ---------------------------------------------------------------------------

def parse_tax_benefit(section_text: str) -> dict[str, Any]:
    """Extract tax benefit info from ## 세제혜택 section."""
    eligible = "가능" in section_text and "불가" not in section_text
    if "비과세종합저축" in section_text:
        tax_type = "비과세종합저축"
    elif "비과세" in section_text:
        tax_type = "비과세"
    else:
        tax_type = "일반과세"
    return {"eligible": eligible, "type": tax_type, "description": section_text.strip()[:200]}


# ---------------------------------------------------------------------------
# Deposit protection extraction
# ---------------------------------------------------------------------------

def parse_deposit_protection(section_text: str) -> dict[str, Any]:
    """Extract deposit protection info from ## 예금자보호여부 section."""
    protected = "보호" in section_text and "보호하지" not in section_text
    max_amount = 100_000_000 if "1억원" in section_text else None
    return {"protected": protected, "max_amount_won": max_amount, "description": section_text.strip()[:200]}


# ---------------------------------------------------------------------------
# Preferential rate extraction
# ---------------------------------------------------------------------------

def parse_preferential_rates(section_text: str, product_id: str) -> list[PreferentialRate]:
    """Extract preferential rate conditions from ## 우대이율 section."""
    rates: list[PreferentialRate] = []
    idx = 0
    for line in section_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        rate_match = re.search(r"연\s*(\d+\.?\d*)\s*%", line)
        if rate_match:
            rate_val = float(rate_match.group(1))
            if rate_val > 10.0:
                continue  # filter out multipliers
            # Try to extract a name from numbered items
            name_match = re.match(r"[①②③④⑤⑥⑦⑧⑨⑩ㅇ○\d.)\]]+\s*(.+?)[\s:：]", line)
            name = name_match.group(1).strip() if name_match else line[:40].strip()
            rates.append(
                PreferentialRate(
                    id=f"{product_id}__pref__{idx}",
                    name=name[:80],
                    condition_description=line[:150],
                    rate_value_pp=rate_val,
                )
            )
            idx += 1
    return rates


# ---------------------------------------------------------------------------
# Eligibility extraction
# ---------------------------------------------------------------------------

def parse_eligibility(text: str, product_id: str) -> EligibilityCondition:
    """Extract eligibility condition from frontmatter or body text."""
    min_age = None
    age_match = re.search(r"만\s*(\d+)\s*세", text)
    if age_match:
        min_age = int(age_match.group(1))

    target = ""
    if "직장인" in text:
        target = "직장인"
    elif "공무원" in text:
        target = "공무원"
    elif "개인사업자" in text:
        target = "개인사업자"
    elif "개인" in text:
        target = "개인"
    elif "내국인" in text:
        target = "내국인"

    return EligibilityCondition(
        id=f"{product_id}__elig",
        description=text.strip()[:300],
        min_age=min_age,
        target_audience=target,
    )




# ---------------------------------------------------------------------------
# Feature extraction from body sections
# ---------------------------------------------------------------------------

def _parse_features(section: str, product_id: str) -> list[Feature]:
    items = _extract_list_items(section)
    return [
        Feature(id=f"{product_id}__feat__{slugify(item[:40]) or str(i)}", name=item)
        for i, item in enumerate(items)
        if item
    ]


# ---------------------------------------------------------------------------
# Core: parse a single product file
# ---------------------------------------------------------------------------

def parse_product_file(path: Path) -> ParsedProduct:
    """Parse a single markdown product file and return extracted entities."""
    post = frontmatter.load(str(path))
    meta: dict[str, Any] = dict(post.metadata)
    body: str = post.content

    product_id = meta.get("id") or slugify(path.stem) or path.stem
    name = meta.get("name") or path.stem.replace("-", " ").title()
    category_name = str(meta.get("category", ""))

    parsed = ParsedProduct()

    # --- Determine product type from category ---
    product_type = CATEGORY_TO_PRODUCT_TYPE.get(category_name, "")

    # --- Parse amounts ---
    amounts = meta.get("amounts", {}) or {}
    amount_max_raw = str(amounts.get("max", "")) if isinstance(amounts, dict) else ""
    amount_max_won = parse_korean_amount(amount_max_raw)
    amount_min_raw = str(amounts.get("min", "")) if isinstance(amounts, dict) else ""
    amount_min_won = parse_korean_amount(amount_min_raw)

    # --- Parse eligibility summary ---
    eligibility_summary = str(meta.get("eligibility_summary", ""))

    # --- Product node ---
    parsed.product = Product(
        id=product_id,
        name=str(name),
        product_type=product_type,
        description=str(meta.get("description", "")),
        amount_max_raw=amount_max_raw,
        amount_max_won=amount_max_won,
        amount_min_won=amount_min_won,
        eligibility_summary=eligibility_summary,
        page_url=str(meta.get("page_url", "")),
        scraped_at=meta.get("scraped_at"),
    )

    # --- Category ---
    if category_name:
        cat_id = slugify(category_name) or category_name
        parsed.category = Category(
            id=cat_id,
            name=category_name,
            name_en=CATEGORY_NAME_EN.get(category_name, ""),
        )

    # --- Channels from frontmatter ---
    channels_raw = meta.get("channels", [])
    if isinstance(channels_raw, list):
        parsed.channels = _extract_channels(channels_raw)

    # --- Rates from frontmatter ---
    # Supports both dict format (rates.min/rates.max) and string format ("연 2.4% ~ 2.9%")
    rates_meta = meta.get("rates", {}) or {}
    rate_min: float | None = None
    rate_max: float | None = None
    if isinstance(rates_meta, dict):
        rate_min = parse_rate_string(str(rates_meta.get("min", "")))
        rate_max = parse_rate_string(str(rates_meta.get("max", "")))
    elif isinstance(rates_meta, str):
        # Parse string format: "연 2.4% ~ 2.9%" or "연 2.4%"
        all_rates = [float(m.group(1)) for m in re.finditer(r"(\d+\.?\d*)\s*%", rates_meta) if float(m.group(1)) <= 15.0]
        if len(all_rates) >= 2:
            rate_min = min(all_rates)
            rate_max = max(all_rates)
        elif len(all_rates) == 1:
            rate_min = all_rates[0]
            rate_max = all_rates[0]
    if rate_min is not None or rate_max is not None:
        parsed.rates.append(
            InterestRate(
                id=f"{product_id}__rate__base",
                rate_type="base",
                min_rate=rate_min,
                max_rate=rate_max,
            )
        )

    # --- Terms from frontmatter ---
    term_raw = str(meta.get("terms", meta.get("term", "")))
    if term_raw:
        min_m, max_m = parse_korean_term(term_raw)
        if min_m is not None or max_m is not None:
            parsed.terms.append(
                Term(
                    id=f"{product_id}__term__primary",
                    min_months=min_m,
                    max_months=max_m,
                    raw_text=term_raw,
                )
            )

    # --- Body sections ---
    sections = _split_sections(body)
    subsections = _split_subsections(body)
    full_sections = _split_sections_full(body)  # for sections after 유의사항

    # --- Features ---
    for key in ("특징", "상품특징", "주요특징", "features"):
        if key in sections:
            parsed.features = _parse_features(sections[key], product_id)
            # If no list items, create a single feature from the text
            if not parsed.features and sections[key].strip():
                parsed.features = [
                    Feature(
                        id=f"{product_id}__feat__0",
                        name=sections[key].strip()[:150],
                    )
                ]
            break

    # --- Eligibility from frontmatter or body ---
    elig_text = eligibility_summary
    for key in ("대출신청자격", "가입대상", "가입조건", "eligibility"):
        if key in sections:
            elig_text = sections[key]
            break
    if elig_text:
        parsed.eligibility = parse_eligibility(elig_text, product_id)

    # --- Tax benefit ---
    for key in ("세제혜택",):
        if key in sections:
            tb = parse_tax_benefit(sections[key])
            parsed.tax_benefit = TaxBenefit(
                id=f"{product_id}__tax",
                type=tb["type"],
                eligible=tb["eligible"],
                description=tb["description"],
            )
            break

    # --- Deposit protection (appears after 유의사항, use full_sections) ---
    for key in ("예금자보호여부", "예금자보호"):
        if key in full_sections:
            dp = parse_deposit_protection(full_sections[key])
            parsed.deposit_protection = DepositProtection(
                id=f"{product_id}__dp",
                protected=dp["protected"],
                max_amount_won=dp["max_amount_won"],
                description=dp["description"],
            )
            break

    # --- Preferential rates from body ---
    for key in ("우대이율", "우대금리"):
        if key in sections:
            parsed.preferential_rates = parse_preferential_rates(sections[key], product_id)
            break
    # Also check subsections for 최고 ... 우대
    for key, text in subsections.items():
        if "우대" in key and not parsed.preferential_rates:
            parsed.preferential_rates = parse_preferential_rates(text, product_id)

    # --- Benefits from body sections (Legacy 수수료면제 + 서비스) ---
    for key in ("혜택", "부가서비스", "우대서비스"):
        if key in sections:
            parsed.benefits = parse_benefits(sections[key], product_id)
            break

    # --- Populate deposit_insured on Product from deposit_protection ---
    if parsed.deposit_protection is not None and parsed.product is not None:
        parsed.product.deposit_insured = parsed.deposit_protection.protected

    # --- Populate tax_free_savings_eligible on Product from tax_benefit ---
    if parsed.tax_benefit is not None and parsed.product is not None:
        parsed.product.tax_free_savings_eligible = (
            parsed.tax_benefit.type == "비과세종합저축" and parsed.tax_benefit.eligible
        )

    # --- Product type from body (appears after 유의사항, use full_sections) ---
    for key in ("상품유형",):
        if key in full_sections:
            pt_name = full_sections[key].strip()[:100]
            if pt_name:
                parsed.product_type = ProductType(
                    id=f"ptype__{slugify(pt_name) or pt_name}",
                    name=pt_name,
                )
            break

    # --- Channels from body sections too (may appear after 유의사항) ---
    for key in ("가입채널", "거래방법", "상품 가입채널"):
        sect_text = full_sections.get(key, "") or subsections.get(key, "")
        if sect_text and not parsed.channels:
            # Try to find channel names in the text
            for ch_key, (cid, name_en) in CHANNEL_MAP.items():
                if ch_key in sect_text:
                    if not any(c.id == cid for c in parsed.channels):
                        parsed.channels.append(Channel(id=cid, name=ch_key, name_en=name_en))

    return parsed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_all_products(products_dir: Path) -> list[ParsedProduct]:
    """Parse every ``*.md`` file in *products_dir*."""
    if not products_dir.is_dir():
        return []
    results: list[ParsedProduct] = []
    for md_path in sorted(products_dir.glob("**/*.md")):
        try:
            results.append(parse_product_file(md_path))
        except Exception as exc:  # noqa: BLE001
            print(f"[parser] WARNING: skipping {md_path.name}: {exc}")
    return results
