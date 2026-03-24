"""Convert extracted product data to markdown files with YAML frontmatter."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import yaml
from slugify import slugify

from scraper.config import CATEGORY_DIR_MAP, OUTPUT_DIR
from scraper.extractor import ProductData

logger = logging.getLogger(__name__)


def write_product_markdown(
    product: ProductData,
    output_dir: Path | None = None,
) -> Path:
    """Write a single product to a markdown file.

    Returns the path of the written file.
    """
    base_dir = output_dir or OUTPUT_DIR
    category_dir_name = CATEGORY_DIR_MAP.get(product.category, product.category)
    dest_dir = base_dir / category_dir_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = _make_filename(product.product_name)
    filepath = dest_dir / filename

    frontmatter = _build_frontmatter(product)
    body = _build_body(product)

    content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False, sort_keys=False).rstrip()}\n---\n\n{body}"

    filepath.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", filepath)
    return filepath


def write_many(
    products: list[ProductData],
    output_dir: Path | None = None,
) -> list[Path]:
    """Write multiple products to markdown files."""
    paths: list[Path] = []
    for product in products:
        try:
            path = write_product_markdown(product, output_dir)
            paths.append(path)
        except Exception as exc:
            logger.error("Failed to write '%s': %s", product.product_name, exc)
    logger.info("Wrote %d markdown files", len(paths))
    return paths


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_filename(product_name: str) -> str:
    """Generate a filesystem-safe filename from a Korean product name."""
    slug = slugify(product_name, allow_unicode=True)
    if not slug:
        slug = slugify(product_name, allow_unicode=False) or "unknown"
    return f"{slug}.md"


def _build_frontmatter(product: ProductData) -> dict:
    """Build the YAML frontmatter dict."""
    fm: dict = {
        "name": product.product_name,
        "category": product.category,
    }

    if product.interest_rate_min or product.interest_rate_max:
        rates: dict = {}
        if product.interest_rate_min:
            rates["min"] = product.interest_rate_min
        if product.interest_rate_max:
            rates["max"] = product.interest_rate_max
        if product.rate_type:
            rates["type"] = product.rate_type
        fm["rates"] = rates

    if product.term_min or product.term_max:
        terms: dict = {}
        if product.term_min:
            terms["min"] = product.term_min
        if product.term_max:
            terms["max"] = product.term_max
        fm["terms"] = terms

    if product.amount_min or product.amount_max:
        amounts: dict = {}
        if product.amount_min:
            amounts["min"] = product.amount_min
        if product.amount_max:
            amounts["max"] = product.amount_max
        fm["amounts"] = amounts

    if product.risk_level:
        fm["risk_level"] = product.risk_level

    if product.channels:
        fm["channels"] = product.channels

    fm["page_url"] = product.page_url
    fm["page_id"] = product.page_id
    fm["scraped_at"] = product.scraped_at or datetime.now().isoformat(timespec="seconds")

    return fm


def _build_body(product: ProductData) -> str:
    """Build the markdown body with Korean section headers."""
    sections: list[str] = []

    sections.append(f"# {product.product_name}\n")

    if product.description:
        sections.append(f"## 상품설명\n\n{product.description}\n")

    if product.interest_rate_min or product.interest_rate_max:
        rate_lines = []
        if product.interest_rate_min and product.interest_rate_max:
            rate_lines.append(f"- 금리 범위: {product.interest_rate_min} ~ {product.interest_rate_max}")
        elif product.interest_rate_min:
            rate_lines.append(f"- 금리: {product.interest_rate_min}")
        elif product.interest_rate_max:
            rate_lines.append(f"- 최대 금리: {product.interest_rate_max}")
        if product.rate_type:
            rate_lines.append(f"- 금리 유형: {product.rate_type}")
        sections.append("## 금리\n\n" + "\n".join(rate_lines) + "\n")

    if product.conditions or product.term_min:
        cond_lines = []
        if product.term_min or product.term_max:
            term_str = product.term_min
            if product.term_max and product.term_max != product.term_min:
                term_str += f" ~ {product.term_max}"
            cond_lines.append(f"- 가입기간: {term_str}")
        if product.amount_min or product.amount_max:
            amt_str = product.amount_min
            if product.amount_max and product.amount_max != product.amount_min:
                amt_str += f" ~ {product.amount_max}"
            cond_lines.append(f"- 가입금액: {amt_str}")
        if product.conditions:
            cond_lines.append(f"- 기타조건: {product.conditions}")
        sections.append("## 가입조건\n\n" + "\n".join(cond_lines) + "\n")

    if product.eligibility:
        sections.append(f"## 가입대상\n\n{product.eligibility}\n")

    if product.fees:
        sections.append(f"## 수수료\n\n{product.fees}\n")

    if product.tax_benefits:
        sections.append(f"## 세제혜택\n\n{product.tax_benefits}\n")

    if product.features:
        feature_lines = "\n".join(f"- {f}" for f in product.features)
        sections.append(f"## 특징\n\n{feature_lines}\n")

    if product.channels:
        sections.append(f"## 가입채널\n\n{', '.join(product.channels)}\n")

    return "\n".join(sections)
