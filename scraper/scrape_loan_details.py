"""Scrape loan product detail pages from KB Star Bank.

Detail pages are only accessible via JavaScript function calls (dtlLoan)
from the listing page. This script:
1. Navigates to the loan listing page
2. Iterates all 4 loan tabs (신용대출, 담보대출, 전월세/반환보증, 자동차대출)
3. For each product calls dtlLoan() to open the detail page
4. Extracts header info, 상품안내, 금리 및 이율, 유의사항 및 기타
5. Updates existing MD files with enriched data
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from slugify import slugify
from playwright.async_api import Page, async_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LISTING_URL = "https://obank.kbstar.com/quics?page=C103429"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "products" / "대출"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

LOAN_TABS = [
    {"text": "신용대출",       "index": 0},
    {"text": "담보대출",       "index": 1},
    {"text": "전월세/반환보증", "index": 2},
    {"text": "자동차대출",     "index": 3},
]

HEADLESS = True
DELAY_BETWEEN_PRODUCTS = 2.5   # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JS snippets
# ---------------------------------------------------------------------------

JS_GET_PRODUCT_LIST = """() => {
    const results = [];
    const anchors = document.querySelectorAll('a[onclick*="dtlLoan"]');
    for (const a of anchors) {
        const onclick = a.getAttribute('onclick') || '';
        // dtlLoan('LN20001319','','0','신용대출 ','N', '');
        const m = onclick.match(/dtlLoan\\('([^']+)','([^']*)','([^']*)','([^']*)'/);
        if (!m) continue;
        const prcode = m[1];
        const arg2   = m[2];
        const arg3   = m[3];
        const arg4   = m[4];
        // Product name: look for strong inside the same li, or link text
        let name = '';
        const li = a.closest('li');
        if (li) {
            const strong = li.querySelector('strong');
            name = strong ? strong.textContent.trim() : a.textContent.trim();
        } else {
            name = a.textContent.trim();
        }
        results.push({ prcode, arg2, arg3, arg4, name, onclick });
    }
    return results;
}"""

JS_EXTRACT_DETAIL = """() => {
    const result = {};

    // Header: h2 with subtitle + product name
    const h2s = document.querySelectorAll('h2');
    for (const h2 of h2s) {
        const divs = h2.querySelectorAll('div, span');
        if (divs.length >= 2) {
            result.subtitle = (divs[0]?.textContent || '').trim();
            result.name     = (divs[1]?.textContent || '').trim();
            break;
        }
    }

    // dt/dd header metadata
    const dts = document.querySelectorAll('dt');
    for (const dt of dts) {
        const key = dt.textContent.trim();
        const dd  = dt.nextElementSibling;
        if (dd && dd.tagName === 'DD') {
            result[key] = dd.textContent.trim();
        }
    }

    // 상품안내 tab: li items with strong labels
    const sections = {};
    const allLis = document.querySelectorAll('li');
    for (const li of allLis) {
        const strong = li.querySelector('strong');
        if (!strong) continue;
        const label = strong.textContent.trim();
        if (label.length < 2 || label.length > 40) continue;

        // Nested list?
        const subList = li.querySelector('ul, ol');
        if (subList) {
            const items = [];
            for (const subLi of subList.querySelectorAll('li')) {
                const t = subLi.textContent.trim();
                if (t) items.push(t);
            }
            if (items.length > 0) {
                sections[label] = items.join('\\n');
                continue;
            }
        }

        // Sibling element after strong
        const next = strong.nextElementSibling;
        if (next) {
            const t = next.textContent.trim();
            if (t) { sections[label] = t; continue; }
        }

        // Fallback: strip label from li text
        const text = li.textContent.replace(label, '').trim();
        if (text) sections[label] = text;
    }

    result.sections = sections;
    return result;
}"""

JS_EXTRACT_RATE_TAB = """() => {
    const tables = document.querySelectorAll('table');
    const rows = [];
    for (const table of tables) {
        for (const row of table.querySelectorAll('tr')) {
            const cells = [];
            for (const cell of row.querySelectorAll('th, td')) {
                cells.push(cell.textContent.trim());
            }
            if (cells.length > 0) rows.push(cells.join(' | '));
        }
    }
    return rows.join('\\n');
}"""

JS_EXTRACT_NOTES_TAB = """() => {
    // 유의사항 및 기타 tab content
    const paras = document.querySelectorAll('p, li');
    const lines = [];
    for (const el of paras) {
        const t = el.textContent.trim();
        if (t && t.length > 5) lines.push(t);
    }
    return lines.join('\\n');
}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_slug(name: str) -> str:
    slug = slugify(name, allow_unicode=True)
    if not slug:
        slug = slugify(name, allow_unicode=False) or "unknown"
    return slug


def find_existing_md(name: str) -> Path | None:
    """Try to find an existing MD file that matches the product name."""
    target_slug = make_slug(name)
    for md in DATA_DIR.glob("*.md"):
        if make_slug(md.stem) == target_slug:
            return md
    # Looser match: name slug is contained in file stem slug
    for md in DATA_DIR.glob("*.md"):
        file_slug = make_slug(md.stem)
        if target_slug in file_slug or file_slug in target_slug:
            return md
    return None


def parse_existing_frontmatter(md_path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text) from an existing MD file."""
    text = md_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
                return fm, parts[2]
            except Exception:
                pass
    return {}, text


def clean_whitespace(text: str) -> str:
    """Collapse whitespace/newlines/tabs into a single space and strip."""
    if not text:
        return text
    return re.sub(r"[\s\t\n]+", " ", text).strip()


def build_updated_md(
    name: str,
    category: str,
    prcode: str,
    detail: dict,
    rate_content: str,
    notes_content: str,
    existing_fm: dict,
    existing_body: str,
) -> str:
    """Merge scraped detail data into an updated markdown document."""
    sections = detail.get("sections", {})
    scraped_at = datetime.now().isoformat(timespec="seconds")

    # --- Frontmatter ---
    fm = dict(existing_fm)  # preserve existing fields
    fm["name"] = name
    fm["category"] = category

    # Channels from detail header
    channel_val = clean_whitespace(detail.get("가입가능채널") or detail.get("가입가능경로") or "")
    if channel_val:
        channels = [c.strip() for c in re.split(r"[,\s]+", channel_val) if c.strip()]
        fm["channels"] = channels

    # Term from header
    term_val = clean_whitespace(detail.get("기간") or "")
    if term_val:
        fm["term"] = term_val

    # Repayment
    repay_val = clean_whitespace(detail.get("상환방법") or "")
    if repay_val:
        fm["repayment"] = repay_val

    # Amount from header
    amount_val = clean_whitespace(detail.get("대출한도") or detail.get("금액") or "")
    if amount_val:
        if "amounts" not in fm:
            fm["amounts"] = {}
        fm["amounts"]["max"] = amount_val

    # Eligibility from sections
    elig_val = (sections.get("대출신청자격")
                or sections.get("가입대상")
                or sections.get("신청자격")
                or "")
    if elig_val:
        fm["eligibility_summary"] = elig_val[:200]

    fm["page_url"] = f"https://obank.kbstar.com/quics?page=C103429&cc=b061496:b061645&isNew=N&prcode={prcode}"
    fm["page_id"] = "C103429"
    fm["scraped_at"] = scraped_at

    # --- Body ---
    lines: list[str] = []
    lines.append(f"# {name}\n")

    subtitle = detail.get("subtitle") or detail.get("name") or ""
    if subtitle and subtitle != name:
        lines.append(f"## 상품설명\n\n{subtitle}\n")

    # 대출한도 / 기간 / 상환방법
    meta_items = []
    if term_val:
        meta_items.append(f"- 기간: {term_val}")
    if repay_val:
        meta_items.append(f"- 상환방법: {repay_val}")
    if amount_val:
        meta_items.append(f"- 대출한도: {amount_val}")
    if channel_val:
        meta_items.append(f"- 가입가능채널: {channel_val}")
    if meta_items:
        lines.append("## 기본정보\n\n" + "\n".join(meta_items) + "\n")

    # 상품안내 sections
    SECTION_ORDER = [
        "상품특징",
        "대출신청자격",
        "대출금액",
        "대출기간 및 상환 방법",
        "대출기간",
        "상환방법",
        "대출신청방법",
        "준비서류",
        "중도상환해약금",
    ]
    written_sections = set()

    # Write priority sections first
    for sec_key in SECTION_ORDER:
        if sec_key in sections:
            lines.append(f"## {sec_key}\n\n{sections[sec_key]}\n")
            written_sections.add(sec_key)

    # Write remaining sections
    remaining = {k: v for k, v in sections.items() if k not in written_sections}
    if remaining:
        lines.append("## 상품안내\n")
        for k, v in remaining.items():
            lines.append(f"### {k}\n\n{v}\n")

    # Rate tab
    if rate_content and rate_content.strip():
        lines.append(f"## 금리 및 이율\n\n```\n{rate_content.strip()}\n```\n")

    # Notes tab
    if notes_content and notes_content.strip():
        # Limit notes to first 2000 chars to keep files manageable
        notes_trimmed = notes_content.strip()[:2000]
        lines.append(f"## 유의사항\n\n{notes_trimmed}\n")

    body = "\n".join(lines)
    fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False).rstrip()
    return f"---\n{fm_yaml}\n---\n\n{body}"


async def click_tab_by_text(page: Page, tab_text: str) -> bool:
    """Click a tab link by its text. Returns True on success."""
    try:
        # Try role=link
        tab = page.get_by_role("link", name=tab_text, exact=True).first
        if await tab.count() > 0:
            await tab.click()
            await asyncio.sleep(1.5)
            await page.wait_for_load_state("networkidle")
            return True
    except Exception:
        pass

    # Fallback: evaluate
    clicked = await page.evaluate(f"""() => {{
        const links = document.querySelectorAll('a');
        for (const a of links) {{
            if (a.textContent.trim() === '{tab_text}') {{
                a.click();
                return true;
            }}
        }}
        return false;
    }}""")
    if clicked:
        await asyncio.sleep(1.5)
        await page.wait_for_load_state("networkidle")
        return True
    return False


# ---------------------------------------------------------------------------
# Main scraping logic
# ---------------------------------------------------------------------------

async def scrape_loan_products() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.set_default_navigation_timeout(30_000)
        context.set_default_timeout(15_000)
        page = await context.new_page()

        total_written = 0
        total_products = 0

        for tab_info in LOAN_TABS:
            tab_text = tab_info["text"]
            tab_index = tab_info["index"]

            log.info("=" * 60)
            log.info("Processing loan tab: %s", tab_text)
            log.info("=" * 60)

            # Navigate to listing page
            log.info("Navigating to listing page: %s", LISTING_URL)
            await page.goto(LISTING_URL, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)

            # Click the tab (index 0 = 신용대출 is default, still click to be sure)
            if tab_index > 0:
                log.info("Clicking tab: %s", tab_text)
                ok = await click_tab_by_text(page, tab_text)
                if not ok:
                    log.warning("Could not click tab '%s', attempting index-based click", tab_text)
                    # Try by index
                    try:
                        tab_links = await page.query_selector_all('.tabMenu li a, .tab-menu li a, ul.tabs li a')
                        if tab_links and len(tab_links) > tab_index:
                            await tab_links[tab_index].click()
                            await asyncio.sleep(1.5)
                            await page.wait_for_load_state("networkidle")
                    except Exception as e:
                        log.error("Tab click failed: %s", e)
                await asyncio.sleep(1)

            # Extract product list from this tab
            log.info("Extracting product list for tab: %s", tab_text)
            products = await page.evaluate(JS_GET_PRODUCT_LIST)
            log.info("Found %d products on tab '%s'", len(products), tab_text)

            if not products:
                # Debug: save snapshot
                snap_path = RAW_DIR / f"loan_tab_{tab_text}_listing.html"
                content = await page.content()
                snap_path.write_text(content, encoding="utf-8")
                log.warning("No products found on tab '%s' - saved HTML to %s", tab_text, snap_path)
                continue

            for i, prod in enumerate(products, 1):
                prcode = prod["prcode"]
                prod_name = prod["name"] or prcode
                arg2 = prod.get("arg2", "")
                arg3 = prod.get("arg3", "0")
                arg4 = prod.get("arg4", tab_text)

                log.info("[%d/%d] Processing: %s (%s)", i, len(products), prod_name, prcode)
                total_products += 1

                try:
                    # Call dtlLoan() to open the detail view
                    log.info("  Calling dtlLoan('%s', '%s', '%s', '%s', 'N', '')",
                             prcode, arg2, arg3, arg4)
                    await page.evaluate(
                        f"dtlLoan('{prcode}', '{arg2}', '{arg3}', '{arg4}', 'N', '');"
                    )
                    await asyncio.sleep(2)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(1)

                    # Extract detail header + 상품안내
                    log.info("  Extracting detail info...")
                    detail = await page.evaluate(JS_EXTRACT_DETAIL)
                    # Use name from detail if available (more reliable than listing)
                    actual_name = detail.get("name") or prod_name
                    log.info("  Product name confirmed: %s", actual_name)

                    # Click "금리 및 이율" tab
                    rate_content = ""
                    try:
                        rate_clicked = await click_tab_by_text(page, "금리 및 이율")
                        if rate_clicked:
                            await asyncio.sleep(1)
                            rate_content = await page.evaluate(JS_EXTRACT_RATE_TAB)
                            log.info("  Rate tab: extracted %d chars", len(rate_content))
                        else:
                            log.info("  Rate tab not found")
                    except Exception as e:
                        log.warning("  Rate tab error: %s", e)

                    # Click "유의사항 및 기타" tab
                    notes_content = ""
                    try:
                        notes_tab_texts = ["유의사항 및 기타", "유의사항"]
                        for ntxt in notes_tab_texts:
                            notes_clicked = await click_tab_by_text(page, ntxt)
                            if notes_clicked:
                                await asyncio.sleep(1)
                                notes_content = await page.evaluate(JS_EXTRACT_NOTES_TAB)
                                log.info("  Notes tab: extracted %d chars", len(notes_content))
                                break
                    except Exception as e:
                        log.warning("  Notes tab error: %s", e)

                    # Find or create MD file
                    md_path = find_existing_md(actual_name)
                    if md_path:
                        log.info("  Updating existing file: %s", md_path.name)
                        existing_fm, existing_body = parse_existing_frontmatter(md_path)
                    else:
                        slug = make_slug(actual_name)
                        md_path = DATA_DIR / f"{slug}.md"
                        log.info("  Creating new file: %s", md_path.name)
                        existing_fm = {}
                        existing_body = ""

                    # Build and write updated content
                    updated = build_updated_md(
                        name=actual_name,
                        category=tab_text if tab_text != "전월세/반환보증" else "전월세대출",
                        prcode=prcode,
                        detail=detail,
                        rate_content=rate_content,
                        notes_content=notes_content,
                        existing_fm=existing_fm,
                        existing_body=existing_body,
                    )
                    md_path.write_text(updated, encoding="utf-8")
                    log.info("  Written: %s", md_path)
                    total_written += 1

                except Exception as e:
                    log.error("  ERROR processing %s: %s", prod_name, e)
                    # Save debug snapshot
                    try:
                        snap_html = await page.content()
                        snap_path = RAW_DIR / f"error_{prcode}.html"
                        snap_path.write_text(snap_html, encoding="utf-8")
                        log.info("  Debug HTML saved to %s", snap_path)
                    except Exception:
                        pass

                # Navigate back to listing for the next product
                log.info("  Returning to listing page...")
                try:
                    await page.goto(LISTING_URL, wait_until="domcontentloaded")
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(1)

                    # Re-click the tab if needed (not the first tab)
                    if tab_index > 0:
                        await click_tab_by_text(page, tab_text)
                        await asyncio.sleep(1)
                except Exception as e:
                    log.warning("  Could not navigate back to listing: %s", e)

                # Polite delay between products
                await asyncio.sleep(DELAY_BETWEEN_PRODUCTS)

        await page.close()
        await context.close()
        await browser.close()

    log.info("")
    log.info("=" * 60)
    log.info("DONE. Processed %d products, wrote %d files.", total_products, total_written)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(scrape_loan_products())
