"""Shared utilities for parsing markdown product files.

Extracted from parser.py and loan_parser.py to eliminate 100% code duplication.
Used by regex parsers (fallback) and LLM mapper.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frontmatter
from slugify import slugify

from knowledge_graph.models import Channel


# ---------------------------------------------------------------------------
# Load markdown file
# ---------------------------------------------------------------------------

def load_md_file(path: Path) -> tuple[dict[str, Any], str]:
    """Load a markdown file with YAML frontmatter.

    Returns (metadata_dict, body_string).
    """
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


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

    range_match = re.search(r"(\d+)\s*[~～\-]\s*(\d+)\s*개월", text)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    range_match = re.search(r"(\d+)\s*[~～\-]\s*(\d+)\s*년", text)
    if range_match:
        return int(range_match.group(1)) * 12, int(range_match.group(2)) * 12

    months = re.findall(r"(\d+)\s*개월", text)
    years = re.findall(r"(\d+)\s*년", text)

    values = [int(m) for m in months] + [int(y) * 12 for y in years]
    if len(values) >= 2:
        return min(values), max(values)
    elif len(values) == 1:
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
        if val <= 15.0:
            return val
    return None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
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


def extract_channels(channel_list: list[str]) -> list[Channel]:
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
            cid = f"channel__{slugify(raw.strip()) or raw.strip()}"
            if cid not in seen:
                seen.add(cid)
                channels.append(Channel(id=cid, name=raw.strip(), name_en=""))
    return channels


def extract_list_items(text: str) -> list[str]:
    """Return lines that start with ``-`` or ``*`` as stripped strings."""
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip())
    return items


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

CATEGORY_NAME_EN: dict[str, str] = {
    "적금": "Installment Savings",
    "입출금통장": "Checking Account",
    "입출금자유": "Checking Account",
    "정기예금": "Time Deposit",
    "예금": "Time Deposit",
    "청약": "Housing Subscription",
    "주택청약": "Housing Subscription",
    "신용대출": "Credit Loan",
    "담보대출": "Secured Loan",
    "전월세대출": "Jeonse/Wolse Loan",
    "자동차대출": "Auto Loan",
}

CATEGORY_TO_PARENT: dict[str, str] = {
    "적금": "예금",
    "입출금통장": "예금",
    "입출금자유": "예금",
    "정기예금": "예금",
    "예금": "예금",
    "청약": "예금",
    "주택청약": "예금",
    "신용대출": "대출",
    "담보대출": "대출",
    "전월세대출": "대출",
    "자동차대출": "대출",
}

DEPOSIT_CATEGORIES = {"적금", "입출금통장", "입출금자유", "정기예금", "예금", "청약", "주택청약"}
LOAN_CATEGORIES = {"신용대출", "담보대출", "전월세대출", "자동차대출"}

CATEGORY_TO_PRODUCT_TYPE: dict[str, str] = {
    "적금": "savings",
    "입출금통장": "deposit",
    "입출금자유": "deposit",
    "정기예금": "deposit",
    "예금": "deposit",
    "청약": "savings",
    "주택청약": "savings",
    "신용대출": "loan",
    "담보대출": "loan",
    "전월세대출": "loan",
    "자동차대출": "loan",
}


def is_loan_product(category: str, path: Path) -> bool:
    """Determine if a product is a loan based on category or file path."""
    if category in LOAN_CATEGORIES:
        return True
    loan_dirs = {"대출", "담보대출"}
    return any(p.name in loan_dirs for p in path.parents)


# ---------------------------------------------------------------------------
# Body section splitting
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^##\s+(.+)", re.MULTILINE)
_SUBSECTION_RE = re.compile(r"^###\s+(.+)", re.MULTILINE)


def split_sections(body: str) -> dict[str, str]:
    """Split markdown body into {heading: content}. Stops at ## 유의사항."""
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


def split_sections_full(body: str) -> dict[str, str]:
    """Split markdown body without truncation (for sections after 유의사항)."""
    headings = list(_SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for idx, match in enumerate(headings):
        title = match.group(1).strip()
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def split_subsections(body: str) -> dict[str, str]:
    """Split body into ### sub-headings."""
    stop_idx = body.find("## 유의사항")
    if stop_idx != -1:
        body = body[:stop_idx]
    headings = list(_SUBSECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for idx, match in enumerate(headings):
        title = match.group(1).strip()
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(body)
        sections[title] = body[start:end].strip()
    return sections
