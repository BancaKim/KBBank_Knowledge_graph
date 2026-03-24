"""Enrich MD files using data scraped from KB Star Bank listing pages.

Strategy:
- Visit each listing page with Playwright
- Extract product info (name, description, channel, max amount) from listing items
- For deposit/savings products, also click through to detail pages to get rates/terms
- Match scraped products to existing MD files by name (slug comparison)
- Rewrite MD files with enriched YAML frontmatter + markdown body
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

import frontmatter
import yaml
from playwright.async_api import async_playwright
from slugify import slugify

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = PROJECT_ROOT / "data" / "products"

# Category display name -> (url, tab_text_to_click or None, output_subdir, category_key)
LISTING_PAGES = [
    # Loans - C103429
    ("신용대출", "https://obank.kbstar.com/quics?page=C103429", None, "대출", "신용대출"),
    ("담보대출", "https://obank.kbstar.com/quics?page=C103429", "담보대출", "대출", "담보대출"),
    ("전월세/반환보증", "https://obank.kbstar.com/quics?page=C103429", "전월세/반환보증", "대출", "전월세대출"),
    ("자동차대출", "https://obank.kbstar.com/quics?page=C103429", "자동차대출", "대출", "자동차대출"),
    # Deposits - C016613
    ("예금", "https://obank.kbstar.com/quics?page=C016613", None, "예금", "예금"),
    ("적금", "https://obank.kbstar.com/quics?page=C016613", "적금", "적금", "적금"),
    ("입출금자유", "https://obank.kbstar.com/quics?page=C016613", "입출금자유", "예금", "입출금자유"),
    ("주택청약", "https://obank.kbstar.com/quics?page=C016613", "주택청약", "적금", "주택청약"),
]

# Categories where detail pages are accessible (deposits/savings)
DETAIL_ACCESSIBLE_CATEGORIES = {"예금", "적금", "입출금자유", "주택청약"}

EXTRACT_LISTING_JS = """
() => {
    const results = [];
    const items = document.querySelectorAll('li');
    for (const li of items) {
        const buttons = li.querySelectorAll('button');
        let hasProductButton = false;
        for (const btn of buttons) {
            if (btn.textContent.trim() === '장바구니' || btn.textContent.trim() === '비교하기') {
                hasProductButton = true;
                break;
            }
        }
        if (!hasProductButton) continue;

        const nameEl = li.querySelector('a strong');
        if (!nameEl) continue;
        const name = nameEl.textContent.trim();

        // Description: div element after the product link, no sub-strong
        let description = '';
        const descDivs = li.querySelectorAll('div');
        for (const div of descDivs) {
            const text = div.textContent.trim();
            if (text && !text.includes('장바구니') && !text.includes('비교하기') &&
                !text.includes('가입가능채널') && !text.includes('최고') &&
                text.length > 5 && text.length < 200 && div.querySelector('strong') === null) {
                description = text;
                break;
            }
        }

        // Channel from dt/dd pair
        let channel = '';
        const dds = li.querySelectorAll('dd');
        for (const dd of dds) {
            channel = dd.textContent.trim();
            break;
        }

        // Max amount: strong tags containing amount keywords, but not the product name
        let maxAmount = '';
        const strongEls = li.querySelectorAll('strong');
        for (const s of strongEls) {
            const text = s.textContent.trim();
            if (text !== name && (text.includes('원') || text.includes('억') ||
                text.includes('만') || text.includes('백'))) {
                maxAmount = text;
                break;
            }
        }

        // prcode from onclick attribute on the anchor
        let prcode = '';
        const anchor = li.querySelector('a');
        if (anchor) {
            const onclick = anchor.getAttribute('onclick') || '';
            const match = onclick.match(/dtl\\w+\\('([A-Z0-9]+)'/);
            if (match) prcode = match[1];
        }

        results.push({ name, description, channel, maxAmount, prcode });
    }
    return results;
}
"""


def make_slug(name: str) -> str:
    return slugify(name, allow_unicode=True)


def find_md_file(name: str, subdir: str) -> Path | None:
    """Find an existing MD file matching the product name slug."""
    slug = make_slug(name)
    candidate = PRODUCTS_DIR / subdir / f"{slug}.md"
    if candidate.exists():
        return candidate

    # Search all md files in that subdir by slug
    subdir_path = PRODUCTS_DIR / subdir
    if subdir_path.exists():
        for md in subdir_path.glob("*.md"):
            if md.stem == slug:
                return md

    # Broader search across all subdirs
    for md in PRODUCTS_DIR.glob("**/*.md"):
        if md.stem == slug:
            return md

    return None


def parse_channels(channel_str: str) -> list[str]:
    """Split channel string into a list."""
    if not channel_str:
        return []
    # Common separators
    parts = re.split(r"[,·/\n]+", channel_str)
    return [p.strip() for p in parts if p.strip()]


def parse_rates(text: str) -> tuple[str, str, str]:
    """Extract min/max rate and type from rate text."""
    if not text:
        return "", "", ""
    pcts = re.findall(r"(\d+\.?\d*)\s*%", text)
    if not pcts:
        return "", "", ""
    rates = sorted(set(float(p) for p in pcts))
    rate_min = f"{rates[0]}%"
    rate_max = f"{rates[-1]}%"
    rate_type = ""
    if "고정" in text:
        rate_type = "고정"
    elif "변동" in text:
        rate_type = "변동"
    return rate_min, rate_max, rate_type


async def click_tab_if_needed(page, tab_text: str | None) -> None:
    """Click a listing tab by text if specified."""
    if not tab_text:
        return
    try:
        tab = page.get_by_role("link", name=tab_text, exact=True).first
        if await tab.count() > 0:
            await tab.click()
            await asyncio.sleep(3)
            await page.wait_for_load_state("networkidle")
            print(f"  Clicked tab: {tab_text}")
            return
    except Exception:
        pass

    # Fallback: look for button with text
    try:
        btn = page.get_by_role("button", name=tab_text, exact=True).first
        if await btn.count() > 0:
            await btn.click()
            await asyncio.sleep(3)
            await page.wait_for_load_state("networkidle")
            print(f"  Clicked tab (button): {tab_text}")
            return
    except Exception:
        pass

    print(f"  WARNING: Could not find tab '{tab_text}'")


async def handle_pagination(page) -> list[dict]:
    """Extract all products across all pages."""
    all_products: list[dict] = []
    page_num = 1

    while True:
        products = await page.evaluate(EXTRACT_LISTING_JS)
        print(f"  Page {page_num}: found {len(products)} products")
        all_products.extend(products)

        # Look for next page button
        next_clicked = False
        try:
            # Try numeric page buttons
            next_page_num = page_num + 1
            next_btn = page.get_by_role("link", name=str(next_page_num), exact=True).first
            if await next_btn.count() > 0:
                await next_btn.click()
                await asyncio.sleep(2)
                await page.wait_for_load_state("networkidle")
                page_num = next_page_num
                next_clicked = True
        except Exception:
            pass

        if not next_clicked:
            # Try "다음" button
            try:
                next_btn = page.get_by_role("link", name="다음").first
                if await next_btn.count() > 0:
                    await next_btn.click()
                    await asyncio.sleep(2)
                    await page.wait_for_load_state("networkidle")
                    page_num += 1
                    next_clicked = True
            except Exception:
                pass

        if not next_clicked:
            break

    return all_products


async def extract_detail_page(page, url: str) -> dict:
    """Visit a detail page and extract structured data."""
    result = {
        "description": "",
        "eligibility": "",
        "term_info": "",
        "amount_info": "",
        "rate_min": "",
        "rate_max": "",
        "rate_type": "",
        "features": [],
        "fees": "",
        "tax_benefits": "",
        "conditions": "",
        "notes": "",
        "raw_sections": {},
    }

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
    except Exception as e:
        print(f"    Detail page nav failed: {e}")
        return result

    # Extract header dt/dd pairs
    header_info = await page.evaluate("""() => {
        const info = {};
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

    for key, val in header_info.items():
        if "기간" in key:
            result["term_info"] = val
        elif "금액" in key:
            result["amount_info"] = val
        elif "금리" in key or "이율" in key:
            pcts = re.findall(r"(\d+\.?\d*)\s*%", val)
            if pcts:
                rates = sorted(set(float(p) for p in pcts))
                result["rate_min"] = f"{rates[0]}%"
                result["rate_max"] = f"{rates[-1]}%"

    # Extract 상품안내 sections
    sections = await page.evaluate("""() => {
        const sections = {};
        const listItems = document.querySelectorAll('li');
        for (const li of listItems) {
            const strong = li.querySelector('strong');
            if (!strong) continue;
            const label = strong.textContent.trim();
            if (label.length > 40 || label.length < 2) continue;
            let content = '';
            const nextEl = strong.nextElementSibling;
            if (nextEl) {
                content = nextEl.innerText || nextEl.textContent || '';
            } else {
                const parent = strong.parentElement;
                if (parent) {
                    content = parent.textContent.replace(label, '').trim();
                }
            }
            content = content.trim();
            if (content.length > 0) {
                sections[label] = content;
            }
        }
        return sections;
    }""")

    result["raw_sections"] = sections

    for label, value in sections.items():
        if ("특징" in label or "소개" in label) and len(value) > len(result["description"]):
            result["description"] = value
        elif "대상" in label:
            result["eligibility"] = value
        elif "기간" in label and not result["term_info"]:
            result["term_info"] = value
        elif "금액" in label and not result["amount_info"]:
            result["amount_info"] = value
        elif "수수료" in label or "중도해지" in label:
            result["fees"] = value
        elif "세제" in label or "비과세" in label or "세금" in label:
            result["tax_benefits"] = value
        elif "조건" in label:
            result["conditions"] = value
        elif any(k in label for k in ("이자", "만기", "분할")):
            result["features"].append(f"{label}: {value[:200]}")

    # Try 금리 및 이율 tab
    try:
        rate_tab = page.get_by_role("link", name="금리 및 이율").first
        if await rate_tab.count() > 0:
            await rate_tab.click()
            await asyncio.sleep(1.5)

            rate_content = await page.evaluate("""() => {
                const tables = document.querySelectorAll('table');
                const result = [];
                for (const table of tables) {
                    for (const row of table.querySelectorAll('tr')) {
                        const cells = row.querySelectorAll('th, td');
                        const rowData = [];
                        for (const cell of cells) rowData.push(cell.textContent.trim());
                        if (rowData.length > 0) result.push(rowData.join(' | '));
                    }
                }
                return result.join('\\n');
            }""")

            if rate_content:
                result["raw_sections"]["금리_및_이율"] = rate_content
                pcts = re.findall(r"(\d+\.?\d*)\s*%", rate_content)
                if pcts:
                    rates = sorted(set(float(p) for p in pcts))
                    result["rate_min"] = f"{rates[0]}%"
                    result["rate_max"] = f"{rates[-1]}%"
                if "고정" in rate_content:
                    result["rate_type"] = "고정"
                elif "변동" in rate_content:
                    result["rate_type"] = "변동"
    except Exception:
        pass

    # Try 유의사항 tab
    try:
        notes_tab = page.get_by_role("link", name="유의사항").first
        if await notes_tab.count() > 0:
            await notes_tab.click()
            await asyncio.sleep(1)

            notes_content = await page.evaluate("""() => {
                const items = document.querySelectorAll('li');
                const notes = [];
                for (const li of items) {
                    const text = li.textContent.trim();
                    if (text.length > 10 && text.length < 500) notes.push(text);
                }
                return notes.slice(0, 10).join('\\n');
            }""")

            if notes_content:
                result["notes"] = notes_content
    except Exception:
        pass

    return result


def build_enriched_md(meta: dict, listing_item: dict, detail: dict | None) -> str:
    """Build enriched markdown from existing frontmatter + listing + detail data."""
    fm: dict = {
        "name": meta.get("name", ""),
        "category": meta.get("category", ""),
    }

    # Description - prefer detail page, fall back to listing
    description = ""
    if detail and detail.get("description"):
        description = detail["description"]
    elif listing_item.get("description"):
        description = listing_item["description"]
    elif meta.get("description"):
        description = meta["description"]

    if description:
        fm["description"] = description

    # Amounts - prefer listing's maxAmount for max, detail for structured info
    amounts: dict = {}
    existing_amounts = meta.get("amounts")
    if isinstance(existing_amounts, dict):
        amounts.update(existing_amounts)

    listing_max = listing_item.get("maxAmount", "")
    if listing_max and not amounts.get("max"):
        amounts["max"] = listing_max

    if detail and detail.get("amount_info"):
        # Only use if it looks like valid amount info
        amt = detail["amount_info"]
        if len(amt) < 100 and not amounts.get("max"):
            amounts["max"] = amt

    if amounts:
        fm["amounts"] = amounts

    # Rates - prefer detail page data
    rate_min = ""
    rate_max = ""
    rate_type = ""
    if detail:
        rate_min = detail.get("rate_min", "")
        rate_max = detail.get("rate_max", "")
        rate_type = detail.get("rate_type", "")

    # Fall back to existing frontmatter rates
    if not rate_min and not rate_max:
        existing_rates = meta.get("rates")
        if isinstance(existing_rates, dict):
            rate_min = existing_rates.get("min", "")
            rate_max = existing_rates.get("max", "")
            rate_type = existing_rates.get("type", "")

    if rate_min or rate_max:
        rates: dict = {}
        if rate_min:
            rates["min"] = rate_min
        if rate_max:
            rates["max"] = rate_max
        if rate_type:
            rates["type"] = rate_type
        fm["rates"] = rates

    # Terms - from detail
    if detail and detail.get("term_info"):
        fm["terms"] = detail["term_info"]
    elif meta.get("terms"):
        fm["terms"] = meta["terms"]

    # Channels - prefer listing item data, fall back to existing
    channels = parse_channels(listing_item.get("channel", ""))
    if not channels and meta.get("channels"):
        channels = meta["channels"]
    if channels:
        fm["channels"] = channels

    # Preserve page_url - prefer existing (has prcode), fall back to listing
    existing_url = meta.get("page_url", "")
    if existing_url and existing_url.startswith("http"):
        fm["page_url"] = existing_url
    else:
        fm["page_url"] = meta.get("page_url", "")

    fm["page_id"] = meta.get("page_id", "")
    fm["scraped_at"] = datetime.now().isoformat(timespec="seconds")

    # Build body
    name = meta.get("name", "")
    sections: list[str] = [f"# {name}\n"]

    if description:
        sections.append(f"## 상품설명\n\n{description}\n")

    if rate_min or rate_max:
        rate_lines = []
        if rate_min and rate_max:
            rate_lines.append(f"- 금리 범위: {rate_min} ~ {rate_max}")
        elif rate_min:
            rate_lines.append(f"- 금리: {rate_min}")
        if rate_type:
            rate_lines.append(f"- 금리 유형: {rate_type}")
        sections.append("## 금리\n\n" + "\n".join(rate_lines) + "\n")

    if detail and detail.get("raw_sections", {}).get("금리_및_이율"):
        rate_detail = detail["raw_sections"]["금리_및_이율"]
        sections.append(f"## 금리 상세\n\n```\n{rate_detail}\n```\n")

    cond_lines = []
    if amounts.get("max"):
        cond_lines.append(f"- 최대 금액: {amounts['max']}")
    elif amounts.get("min"):
        cond_lines.append(f"- 최소 금액: {amounts['min']}")
    if detail and detail.get("term_info"):
        cond_lines.append(f"- 가입기간: {detail['term_info']}")
    elif meta.get("terms"):
        t = meta["terms"]
        if isinstance(t, dict):
            term_str = t.get("min", "")
            if t.get("max") and t["max"] != term_str:
                term_str += f" ~ {t['max']}"
            cond_lines.append(f"- 가입기간: {term_str}")
        else:
            cond_lines.append(f"- 가입기간: {t}")
    if detail and detail.get("conditions"):
        cond_lines.append(f"- 기타조건: {detail['conditions']}")
    if cond_lines:
        sections.append("## 가입조건\n\n" + "\n".join(cond_lines) + "\n")

    if detail and detail.get("eligibility"):
        sections.append(f"## 가입대상\n\n{detail['eligibility']}\n")

    if detail and detail.get("fees"):
        sections.append(f"## 수수료\n\n{detail['fees']}\n")

    if detail and detail.get("tax_benefits"):
        sections.append(f"## 세제혜택\n\n{detail['tax_benefits']}\n")

    if detail and detail.get("features"):
        feature_lines = "\n".join(f"- {f}" for f in detail["features"])
        sections.append(f"## 특징\n\n{feature_lines}\n")

    if detail and detail.get("notes"):
        sections.append(f"## 유의사항\n\n{detail['notes']}\n")

    # Extra raw sections not already mapped
    if detail:
        mapped_keys = {
            "특징", "소개", "대상", "기간", "금액", "수수료", "중도해지",
            "세제", "비과세", "세금", "조건", "이자", "만기", "분할", "금리_및_이율"
        }
        for label, value in detail.get("raw_sections", {}).items():
            if label == "금리_및_이율":
                continue
            if not any(mk in label for mk in mapped_keys):
                sections.append(f"## {label}\n\n{value}\n")

    if channels:
        sections.append(f"## 가입채널\n\n{', '.join(channels)}\n")

    body = "\n".join(sections)
    fm_str = yaml.dump(
        fm, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).rstrip()
    return f"---\n{fm_str}\n---\n\n{body}"


async def process_listing_page(
    page,
    detail_page,
    display_name: str,
    url: str,
    tab_text: str | None,
    subdir: str,
    category_key: str,
) -> int:
    """Process one listing page: extract products and enrich matching MD files."""
    print(f"\n=== {display_name} ===")
    print(f"  URL: {url}")

    # Navigate to listing
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)
    await page.wait_for_load_state("networkidle")

    # Click tab if needed
    await click_tab_if_needed(page, tab_text)

    # Extract all products (with pagination)
    listing_products = await handle_pagination(page)
    print(f"  Total products found: {len(listing_products)}")

    enriched_count = 0
    can_use_detail = category_key in DETAIL_ACCESSIBLE_CATEGORIES

    for item in listing_products:
        name = item.get("name", "").strip()
        if not name:
            continue

        # Find matching MD file
        md_path = find_md_file(name, subdir)

        if not md_path:
            slug = make_slug(name)
            print(f"  [NO MD] {name} (slug: {slug})")
            continue

        print(f"  Enriching: {name}")

        # Load existing frontmatter
        try:
            post = frontmatter.load(str(md_path))
            meta = dict(post.metadata)
        except Exception as e:
            print(f"    Error loading {md_path}: {e}")
            continue

        # For deposit/savings products try to navigate to detail page
        detail = None
        if can_use_detail:
            prcode = item.get("prcode", "")
            existing_url = meta.get("page_url", "")

            detail_url = ""
            if existing_url and existing_url.startswith("http"):
                detail_url = existing_url
            elif prcode:
                page_id = "C016613"
                detail_url = f"https://obank.kbstar.com/quics?page={page_id}&cc=b061496:b061645&isNew=N&prcode={prcode}"

            if detail_url:
                print(f"    Fetching detail: {detail_url}")
                detail = await extract_detail_page(detail_page, detail_url)
                has_detail = bool(
                    detail.get("description") or detail.get("rate_min") or
                    detail.get("term_info") or detail.get("amount_info") or
                    detail.get("raw_sections")
                )
                print(f"    Detail fetched: {'yes' if has_detail else 'empty'}")
                await asyncio.sleep(2)

        # Build enriched content
        content = build_enriched_md(meta, item, detail)
        md_path.write_text(content, encoding="utf-8")
        enriched_count += 1
        print(f"    -> Written: {md_path.name}")

        await asyncio.sleep(1)

    return enriched_count


async def main() -> None:
    print("KB Star Bank - Enrich MD files from listing pages")
    print(f"Products directory: {PRODUCTS_DIR}")

    md_files = list(PRODUCTS_DIR.glob("**/*.md"))
    print(f"Found {len(md_files)} existing MD files\n")

    total_enriched = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        # Two pages: one for listing, one for detail (so listing state is preserved)
        listing_page = await context.new_page()
        detail_page = await context.new_page()

        for display_name, url, tab_text, subdir, category_key in LISTING_PAGES:
            try:
                count = await process_listing_page(
                    listing_page,
                    detail_page,
                    display_name,
                    url,
                    tab_text,
                    subdir,
                    category_key,
                )
                total_enriched += count
            except Exception as e:
                print(f"  ERROR processing {display_name}: {e}")
                import traceback
                traceback.print_exc()
            finally:
                await asyncio.sleep(2)

        await browser.close()

    print(f"\n{'='*50}")
    print(f"Done! Enriched {total_enriched} files total.")


if __name__ == "__main__":
    asyncio.run(main())
