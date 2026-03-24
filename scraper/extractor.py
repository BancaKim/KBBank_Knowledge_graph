"""Extract structured product data from KB Star Bank detail pages.

Detail page structure (verified 2026-03-23):
- Product header: heading with subtitle + name
- Key info: 가입가능경로, 기간, 금액, 최고금리
- Tabs: 상품안내, 금리 및 이율, 유의사항, 약관·상품설명서
- 상품안내 tab: <listitem> with <strong> label + <generic> value
  e.g. <strong>상품특징</strong><div>인터넷뱅킹...</div>
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from playwright.async_api import Page

from scraper.browser import BrowserManager
from scraper.discovery import DiscoveredProduct

logger = logging.getLogger(__name__)


@dataclass
class ProductData:
    """Structured representation of a financial product."""

    product_name: str = ""
    category: str = ""
    description: str = ""
    interest_rate_min: str = ""
    interest_rate_max: str = ""
    rate_type: str = ""
    term_min: str = ""
    term_max: str = ""
    amount_min: str = ""
    amount_max: str = ""
    eligibility: str = ""
    features: list[str] = field(default_factory=list)
    conditions: str = ""
    fees: str = ""
    tax_benefits: str = ""
    risk_level: str = ""
    channels: list[str] = field(default_factory=list)
    page_url: str = ""
    page_id: str = ""
    prcode: str = ""
    scraped_at: str = ""
    raw_sections: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


async def extract_product(
    bm: BrowserManager,
    page: Page,
    product: DiscoveredProduct,
) -> ProductData | None:
    """Navigate to a product detail page and extract structured data."""
    data = ProductData(
        product_name=product.name,
        category=product.category,
        page_url=product.page_url,
        page_id=product.page_id,
        prcode=product.prcode,
        channels=product.channels,
        scraped_at=datetime.now().isoformat(timespec="seconds"),
    )

    # If we already have the detail URL, navigate to it
    if product.page_url and product.page_url.startswith("http"):
        try:
            await bm.goto(page, product.page_url)
            await page.wait_for_load_state("networkidle")
        except Exception as exc:
            logger.error("Navigation failed for '%s': %s", product.name, exc)
            return None
    else:
        logger.warning("No URL for product '%s', skipping", product.name)
        # Still return partial data from discovery
        data.description = product.summary
        if product.rate_text:
            _parse_rate_text(product.rate_text, data)
        if product.term_text:
            data.term_min = product.term_text
        return data

    try:
        await _extract_from_detail_page(page, data)
    except Exception as exc:
        logger.error("Extraction error for '%s': %s", product.name, exc)
        await bm.save_debug_snapshot(page, f"extract_error_{product.prcode or product.name}")

    # Even partial data is useful
    if data.product_name:
        return data
    return None


async def extract_many(
    bm: BrowserManager,
    products: list[DiscoveredProduct],
) -> list[ProductData]:
    """Extract data from multiple product detail pages sequentially."""
    results: list[ProductData] = []
    page = await bm.new_page()

    for i, product in enumerate(products, 1):
        logger.info("[%d/%d] Extracting: %s", i, len(products), product.name)
        try:
            data = await extract_product(bm, page, product)
            if data:
                results.append(data)
                logger.info("  -> OK: %s (fields: %d)", data.product_name, _count_fields(data))
            else:
                logger.warning("  -> No data for '%s'", product.name)
        except Exception as exc:
            logger.error("  -> Failed: %s - %s", product.name, exc)
            continue

    await page.close()
    return results


# ---------------------------------------------------------------------------
# Detail page extraction
# ---------------------------------------------------------------------------

async def _extract_from_detail_page(page: Page, data: ProductData) -> None:
    """Extract all fields from the product detail page."""

    # 1. Extract header info (기간, 금액, 최고금리)
    header_info = await page.evaluate("""() => {
        const info = {};

        // Product name from heading
        const headings = document.querySelectorAll('h2');
        for (const h of headings) {
            const divs = h.querySelectorAll('div, span');
            if (divs.length >= 2) {
                info.subtitle = divs[0]?.textContent?.trim() || '';
                info.name = divs[1]?.textContent?.trim() || '';
                break;
            }
        }

        // Key-value pairs from dt/dd in the header area
        const dts = document.querySelectorAll('dt');
        for (const dt of dts) {
            const key = dt.textContent.trim();
            const dd = dt.nextElementSibling;
            if (dd && dd.tagName === 'DD') {
                info[key] = dd.textContent.trim();
            }
        }

        return info;
    }""")

    if header_info.get("name"):
        data.product_name = header_info["name"]
    if header_info.get("subtitle"):
        data.description = header_info["subtitle"]

    # Parse header key-value pairs
    for key, val in header_info.items():
        if key == "기간":
            data.raw_sections["기간"] = val
            _parse_term(val, data)
        elif key == "금액":
            data.raw_sections["금액"] = val
            data.amount_min = val
        elif key in ("최고금리", "금리"):
            data.raw_sections["금리_header"] = val
            _parse_rate_text(val, data)
        elif key == "가입가능경로":
            if not data.channels:
                data.channels = [c.strip() for c in val.split() if c.strip()]

    # 2. Extract 상품안내 tab content (the structured list items)
    sections = await page.evaluate("""() => {
        const sections = {};
        // Find list items with <strong> labels (상품안내 section)
        const listItems = document.querySelectorAll('li');
        for (const li of listItems) {
            const strong = li.querySelector('strong');
            if (!strong) continue;
            const label = strong.textContent.trim();
            // Get the content (everything after the strong tag)
            const contentEl = strong.nextElementSibling || strong.parentElement;
            if (contentEl) {
                let content = '';
                if (strong.nextElementSibling) {
                    content = strong.nextElementSibling.textContent.trim();
                } else {
                    // Content is in the same parent, after the strong
                    const full = contentEl.textContent;
                    content = full.replace(label, '').trim();
                }
                if (content && label.length < 20 && content.length > 0) {
                    sections[label] = content;
                }
            }
        }
        return sections;
    }""")

    data.raw_sections.update(sections)

    # Map extracted sections to data fields
    _map_sections_to_data(sections, data)

    # 3. Try clicking "금리 및 이율" tab for more rate details
    try:
        rate_tab = page.get_by_role("link", name="금리 및 이율").first
        if await rate_tab.count() > 0:
            await rate_tab.click()
            await page.wait_for_load_state("networkidle")
            import asyncio
            await asyncio.sleep(1)

            rate_content = await page.evaluate("""() => {
                // Get all table content from the rate tab
                const tables = document.querySelectorAll('table');
                const result = [];
                for (const table of tables) {
                    const rows = table.querySelectorAll('tr');
                    for (const row of rows) {
                        const cells = row.querySelectorAll('th, td');
                        const rowData = [];
                        for (const cell of cells) {
                            rowData.push(cell.textContent.trim());
                        }
                        if (rowData.length > 0) {
                            result.push(rowData.join(' | '));
                        }
                    }
                }
                return result.join('\\n');
            }""")

            if rate_content:
                data.raw_sections["금리_및_이율"] = rate_content
                # Re-parse rates from the detailed table
                _parse_rate_text(rate_content, data)

            # Go back to 상품안내 tab
            try:
                product_tab = page.get_by_role("link", name="상품안내").first
                if await product_tab.count() > 0:
                    await product_tab.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Could not extract rate tab: %s", exc)


def _map_sections_to_data(sections: dict[str, str], data: ProductData) -> None:
    """Map Korean section labels to ProductData fields."""
    label_map = {
        "상품특징": "description",
        "가입대상": "eligibility",
        "계약기간": "_term",
        "가입기간": "_term",
        "예치기간": "_term",
        "가입금액": "_amount",
        "예치금액": "_amount",
        "납입금액": "_amount",
        "수수료": "fees",
        "중도해지": "fees",
        "세제혜택": "tax_benefits",
        "비과세": "tax_benefits",
        "세금우대": "tax_benefits",
        "위험등급": "risk_level",
        "투자위험등급": "risk_level",
        "만기해지방법": "_maturity",
        "분할인출": "_partial_withdrawal",
        "이자지급방식": "_interest_payment",
        "가입조건": "conditions",
    }

    for label, value in sections.items():
        field_name = label_map.get(label)
        if not field_name:
            # Check partial matches
            for key, fname in label_map.items():
                if key in label:
                    field_name = fname
                    break

        if not field_name:
            continue

        if field_name == "description":
            if not data.description or len(value) > len(data.description):
                data.description = value
        elif field_name == "eligibility":
            data.eligibility = value
        elif field_name == "_term":
            _parse_term(value, data)
        elif field_name == "_amount":
            data.amount_min = value
        elif field_name == "fees":
            data.fees = value
        elif field_name == "tax_benefits":
            data.tax_benefits = value
        elif field_name == "risk_level":
            data.risk_level = value
        elif field_name == "conditions":
            data.conditions = value
        elif field_name.startswith("_"):
            # Store as feature
            data.features.append(f"{label}: {value[:100]}")


def _parse_rate_text(text: str, data: ProductData) -> None:
    """Parse rate text to extract min/max rates and type."""
    pct_pattern = r"(\d+\.?\d*)\s*%"
    matches = re.findall(pct_pattern, text)
    if matches:
        rates = sorted(set(float(m) for m in matches))
        if not data.interest_rate_min or float(data.interest_rate_min.rstrip("%") or "0") == 0:
            data.interest_rate_min = f"{rates[0]}%"
            data.interest_rate_max = f"{rates[-1]}%"

    if "고정" in text:
        data.rate_type = "고정"
    elif "변동" in text:
        data.rate_type = "변동"


def _parse_term(text: str, data: ProductData) -> None:
    """Parse term/period text."""
    month_matches = re.findall(r"(\d+)\s*(?:개월|월)", text)
    year_matches = re.findall(r"(\d+)\s*년", text)
    periods = [f"{m}개월" for m in month_matches] + [f"{y}년" for y in year_matches]
    if len(periods) >= 2:
        data.term_min = periods[0]
        data.term_max = periods[-1]
    elif len(periods) == 1:
        data.term_min = periods[0]
    elif not data.term_min:
        data.term_min = text.strip()


def _count_fields(data: ProductData) -> int:
    """Count non-empty fields for logging."""
    count = 0
    for val in [data.product_name, data.category, data.description,
                data.interest_rate_min, data.eligibility, data.term_min,
                data.amount_min, data.fees, data.conditions]:
        if val:
            count += 1
    return count
