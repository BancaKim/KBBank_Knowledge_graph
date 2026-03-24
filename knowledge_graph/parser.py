"""Parse markdown product files from data/products/ into Pydantic models."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter
from slugify import slugify

from knowledge_graph.models import (
    Category,
    Channel,
    DepositProtection,
    EligibilityCondition,
    Feature,
    Fee,
    InterestRate,
    PreferentialRate,
    Product,
    ProductType,
    RepaymentMethod,
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
        self.repayment_methods: list[RepaymentMethod] = []
        self.tax_benefit: TaxBenefit | None = None
        self.deposit_protection: DepositProtection | None = None
        self.preferential_rates: list[PreferentialRate] = []
        self.fees: list[Fee] = []
        self.product_type: ProductType | None = None


# ---------------------------------------------------------------------------
# Korean amount / term / rate parsing helpers
# ---------------------------------------------------------------------------


def parse_korean_amount(text: str) -> int | None:
    """Parse Korean currency string to integer won.

    Examples: '3백만원' -> 3_000_000, '3.5억원' -> 350_000_000
    """
    if not text:
        return None
    text = text.strip()
    patterns = [
        (r"(\d+\.?\d*)\s*억", lambda m: int(float(m.group(1)) * 100_000_000)),
        (r"(\d+\.?\d*)\s*천만", lambda m: int(float(m.group(1)) * 10_000_000)),
        (r"(\d+\.?\d*)\s*백만", lambda m: int(float(m.group(1)) * 1_000_000)),
        (r"(\d+\.?\d*)\s*만", lambda m: int(float(m.group(1)) * 10_000)),
        (r"(\d+\.?\d*)\s*천", lambda m: int(float(m.group(1)) * 1_000)),
    ]
    for pat, conv in patterns:
        m = re.search(pat, text)
        if m:
            return conv(m)
    return None


def parse_korean_term(text: str) -> tuple[int | None, int | None]:
    """Parse Korean duration to (min_months, max_months).

    Examples: '6~36개월' -> (6, 36), '최장 10년' -> (None, 120)
    """
    if not text:
        return None, None

    # Range with 개월
    range_match = re.search(r"(\d+)\s*[~～\-]\s*(\d+)\s*개월", text)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    # Range with 년
    range_match = re.search(r"(\d+)\s*[~～\-]\s*(\d+)\s*년", text)
    if range_match:
        return int(range_match.group(1)) * 12, int(range_match.group(2)) * 12

    months = re.findall(r"(\d+)\s*개월", text)
    years = re.findall(r"(\d+)\s*년", text)

    values = [int(m) for m in months] + [int(y) * 12 for y in years]
    if len(values) >= 2:
        return min(values), max(values)
    elif len(values) == 1:
        # Check for "최장" (max) prefix
        if "최장" in text or "이내" in text:
            return None, values[0]
        return values[0], values[0]
    return None, None


def parse_rate_string(text: str) -> float | None:
    """Parse rate string like '2.25%' to float. Filter out invalid rates > 20%."""
    if text is None:
        return None
    m = re.search(r"(\d+\.?\d*)\s*%", str(text))
    if m:
        val = float(m.group(1))
        if val <= 15.0:  # Korean bank rates are typically 0.01% ~ 15%; values > 15% are likely early-termination multipliers
            return val
    return None


# ---------------------------------------------------------------------------
# Channel extraction
# ---------------------------------------------------------------------------

CHANNEL_MAP: dict[str, tuple[str, str]] = {
    "스타뱅킹": ("channel__스타뱅킹", "KB Star Banking App"),
    "인터넷": ("channel__인터넷", "Internet Banking"),
    "영업점": ("channel__영업점", "Branch"),
    "고객센터": ("channel__고객센터", "Call Center"),
    "모바일": ("channel__모바일", "Mobile"),
    "리브 next": ("channel__리브넥스트", "Liiv Next"),
    "리브next": ("channel__리브넥스트", "Liiv Next"),
}


def _extract_channels(channel_list: list[str]) -> list[Channel]:
    """Map frontmatter channel strings to Channel entities."""
    channels: list[Channel] = []
    seen: set[str] = set()
    for raw in channel_list:
        raw_lower = raw.strip().lower()
        for key, (cid, name_en) in CHANNEL_MAP.items():
            if key in raw_lower or raw_lower in key:
                if cid not in seen:
                    seen.add(cid)
                    channels.append(Channel(id=cid, name=raw.strip(), name_en=name_en))
                break
        else:
            # Fallback: use as-is
            cid = f"channel__{slugify(raw.strip()) or raw.strip()}"
            if cid not in seen:
                seen.add(cid)
                channels.append(Channel(id=cid, name=raw.strip(), name_en=""))
    return channels


# ---------------------------------------------------------------------------
# Repayment method extraction
# ---------------------------------------------------------------------------

def parse_repayment(text: str) -> list[str]:
    """Split and normalize repayment methods from body text."""
    if not text:
        return []
    methods: list[str] = []
    text = text.replace("원(리)금균등분할상환", "원리금균등분할상환")

    known = [
        "마이너스통장",
        "일시상환",
        "원리금균등분할상환",
        "원금균등분할상환",
        "혼합상환",
        "분할상환",
    ]
    for k in known:
        if k in text:
            methods.append(k)

    # If nothing matched, try splitting
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
# Fee extraction
# ---------------------------------------------------------------------------

def parse_fees(section_text: str, product_id: str) -> list[Fee]:
    """Extract fees from ## 수수료 or ### 중도상환수수료 sections."""
    fees: list[Fee] = []
    idx = 0
    if "중도상환" in section_text:
        fees.append(Fee(id=f"{product_id}__fee__{idx}", fee_type="중도상환수수료", description=section_text.strip()[:200]))
        idx += 1
    if "부대비용" in section_text:
        fees.append(Fee(id=f"{product_id}__fee__{idx}", fee_type="부대비용", description=section_text.strip()[:200]))
        idx += 1
    if "조기상환" in section_text:
        fees.append(Fee(id=f"{product_id}__fee__{idx}", fee_type="조기상환수수료", description=section_text.strip()[:200]))
        idx += 1
    if not fees:
        fees.append(Fee(id=f"{product_id}__fee__{idx}", fee_type="수수료", description=section_text.strip()[:200]))
    return fees


# ---------------------------------------------------------------------------
# Feature extraction from body sections
# ---------------------------------------------------------------------------

def _extract_list_items(text: str) -> list[str]:
    """Return lines that start with ``-`` or ``*`` as stripped strings."""
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip())
    return items


def _parse_features(section: str, product_id: str) -> list[Feature]:
    items = _extract_list_items(section)
    return [
        Feature(id=f"{product_id}__feat__{slugify(item[:40]) or str(i)}", name=item)
        for i, item in enumerate(items)
        if item
    ]


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

CATEGORY_NAME_EN: dict[str, str] = {
    "신용대출": "Credit Loan",
    "담보대출": "Secured Loan",
    "전월세대출": "Jeonse/Wolse Loan",
    "자동차대출": "Auto Loan",
    "적금": "Installment Savings",
    "입출금통장": "Checking Account",
    "정기예금": "Time Deposit",
    "청약": "Housing Subscription",
}

CATEGORY_TO_PARENT: dict[str, str] = {
    "신용대출": "대출",
    "담보대출": "대출",
    "전월세대출": "대출",
    "자동차대출": "대출",
    "적금": "예금",
    "입출금통장": "예금",
    "정기예금": "예금",
    "청약": "예금",
}

CATEGORY_TO_PRODUCT_TYPE: dict[str, str] = {
    "신용대출": "loan",
    "담보대출": "loan",
    "전월세대출": "loan",
    "자동차대출": "loan",
    "적금": "savings",
    "입출금통장": "deposit",
    "정기예금": "deposit",
    "청약": "savings",
}


# ---------------------------------------------------------------------------
# Body section splitting
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^##\s+(.+)", re.MULTILINE)


def _split_sections(body: str) -> dict[str, str]:
    """Split a markdown body into {heading: content} dict.

    Stops at ## 유의사항 to avoid HTML noise.
    """
    # Truncate at 유의사항
    stop_idx = body.find("## 유의사항")
    if stop_idx != -1:
        body = body[:stop_idx]

    headings = list(_SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for idx, match in enumerate(headings):
        title = match.group(1).strip()
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def _split_sections_full(body: str) -> dict[str, str]:
    """Split a markdown body into {heading: content} dict WITHOUT truncation.

    Used for sections like 예금자보호여부 that appear after 유의사항.
    """
    headings = list(_SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for idx, match in enumerate(headings):
        title = match.group(1).strip()
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def _split_subsections(body: str) -> dict[str, str]:
    """Split body into ### sub-headings as well (for loan product details)."""
    sub_re = re.compile(r"^###\s+(.+)", re.MULTILINE)

    # Truncate at 유의사항
    stop_idx = body.find("## 유의사항")
    if stop_idx != -1:
        body = body[:stop_idx]

    headings = list(sub_re.finditer(body))
    sections: dict[str, str] = {}
    for idx, match in enumerate(headings):
        title = match.group(1).strip()
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(body)
        sections[title] = body[start:end].strip()
    return sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    rates_meta = meta.get("rates", {}) or {}
    if isinstance(rates_meta, dict):
        rate_min = parse_rate_string(str(rates_meta.get("min", "")))
        rate_max = parse_rate_string(str(rates_meta.get("max", "")))
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

    # --- Repayment methods from body ---
    for key in ("대출기간 및 상환 방법", "대출기간 및 상환방법", "상환방법"):
        if key in sections:
            method_names = parse_repayment(sections[key])
            seen: set[str] = set()
            for mn in method_names:
                mid = f"repay__{slugify(mn) or mn}"
                if mid not in seen:
                    seen.add(mid)
                    parsed.repayment_methods.append(
                        RepaymentMethod(id=mid, name=mn, description="")
                    )
            break

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

    # --- Fees from body subsections ---
    for key in ("중도상환수수료", "조기상환수수료", "수수료"):
        if key in subsections:
            parsed.fees = parse_fees(subsections[key], product_id)
            break
    # Also check main sections
    if not parsed.fees:
        for key in ("부대비용",):
            if key in subsections:
                parsed.fees = parse_fees(subsections[key], product_id)
                break

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
