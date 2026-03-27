"""Discover financial product pages on financial institution website.

Source: public banking website (verified 2026-03-23)

The site structure:
- Product listing page: /quics?page=C016613 (예금/적금/입출금자유/주택청약 tabs)
- Each tab has a product list after a "상품목록 N건" heading
- Product links use href="#none" and navigate via JavaScript
- Clicking a product changes URL to ?page=C016613&cc=...&prcode=DPXXXXXXXX
- Other categories (대출, 펀드, 신탁, ISA, 외화예금) have separate listing pages
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode

from playwright.async_api import Page

from scraper.browser import BrowserManager
from scraper.config import BASE_URL, CATEGORIES

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredProduct:
    """A single product discovered from a listing page."""

    name: str
    category: str
    page_url: str
    page_id: str = ""
    prcode: str = ""
    summary: str = ""
    rate_text: str = ""
    term_text: str = ""
    channels: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def build_category_url(page_id: str) -> str:
    """Build a full URL for a given page ID."""
    return f"{BASE_URL}?{urlencode({'page': page_id})}"


async def discover_all(
    bm: BrowserManager,
    categories: list[str] | None = None,
) -> list[DiscoveredProduct]:
    """Discover products across requested categories."""
    targets = categories or list(CATEGORIES.keys())
    all_products: list[DiscoveredProduct] = []
    seen_names: set[str] = set()

    page = await bm.new_page()

    for cat_name in targets:
        cat_cfg = CATEGORIES.get(cat_name)
        if cat_cfg is None:
            logger.warning("Unknown category '%s', skipping", cat_name)
            continue

        page_id = cat_cfg["page_id"]
        tab_index = cat_cfg["tab_index"]
        tab_text = cat_cfg.get("tab_text")
        url = build_category_url(page_id)

        logger.info("Discovering category '%s' at %s", cat_name, url)

        try:
            products = await _discover_category(bm, page, url, cat_name, tab_index, tab_text)
        except Exception as exc:
            logger.error("Failed to discover '%s': %s", cat_name, exc)
            await bm.save_debug_snapshot(page, f"discovery_error_{cat_name}")
            continue

        for p in products:
            key = f"{p.category}:{p.name}"
            if key not in seen_names:
                seen_names.add(key)
                all_products.append(p)

        logger.info("Found %d products in '%s'", len(products), cat_name)

    await page.close()
    logger.info("Total unique products discovered: %d", len(all_products))
    return all_products


async def _discover_category(
    bm: BrowserManager,
    page: Page,
    url: str,
    category: str,
    tab_index: int | None,
    tab_text: str | None,
) -> list[DiscoveredProduct]:
    """Discover products for a single category/tab."""
    await bm.goto(page, url)
    await page.wait_for_load_state("networkidle")

    # If the page uses tabs (예금/적금/입출금자유/주택청약), click the correct one
    # Tab index 0 is already selected by default, so skip clicking it
    if tab_index is not None and tab_index > 0 and tab_text:
        await _click_tab(bm, page, tab_index, tab_text)

    return await _extract_product_list(page, category)


async def _click_tab(bm: BrowserManager, page: Page, tab_index: int, tab_text: str) -> None:
    """Click a tab on the deposit product listing page."""
    # The tabs are in a <list> with <listitem> > <link> pattern
    # Try text-based tab click first (most reliable)
    try:
        tab = page.get_by_role("link", name=tab_text, exact=True).first
        if await tab.count() > 0:
            await tab.click()
            await asyncio.sleep(1.5)
            await page.wait_for_load_state("networkidle")
            logger.debug("Clicked tab '%s' by text", tab_text)
            return
    except Exception:
        pass

    # Fallback: try tab selectors by index
    tab_selectors = [".tabMenu li a", ".tab-menu li a", '[role="tab"] a', "ul.tabs li a"]
    for selector in tab_selectors:
        tabs = await page.query_selector_all(selector)
        if tabs and len(tabs) > tab_index:
            await tabs[tab_index].click()
            await asyncio.sleep(1.5)
            await page.wait_for_load_state("networkidle")
            logger.debug("Clicked tab %d using selector '%s'", tab_index, selector)
            return

    logger.warning("Could not find tab '%s' (index=%d)", tab_text, tab_index)


async def _extract_product_list(page: Page, category: str) -> list[DiscoveredProduct]:
    """Extract products from the product listing area.

    The listing shows products in <listitem> elements with:
    - <link> containing <strong> with product name (href="#none")
    - Description text
    - Rate/term info in subsequent elements
    """
    products: list[DiscoveredProduct] = []

    # The products are in the main content area list items that have
    # a product link with href="#none" and a strong tag with the name.
    # We specifically target list items that contain product action buttons
    # (장바구니, 비교하기) to distinguish from navigation.
    product_items = await page.evaluate("""() => {
        const results = [];
        // Find all list items that contain product buttons (장바구니 or 비교하기)
        const allItems = document.querySelectorAll('li');
        for (const li of allItems) {
            const buttons = li.querySelectorAll('button');
            let hasProductButton = false;
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                if (text === '장바구니' || text === '비교하기') {
                    hasProductButton = true;
                    break;
                }
            }
            if (!hasProductButton) continue;

            // Extract product info
            const nameLink = li.querySelector('a strong');
            if (!nameLink) continue;

            const name = nameLink.textContent.trim();

            // Extract prcode from onclick handler: dtlDeposit('DP01000938',...)
            const anchor = li.querySelector('a.title, a[onclick*="dtl"]');
            let prcode = '';
            if (anchor) {
                const onclick = anchor.getAttribute('onclick') || '';
                const match = onclick.match(/dtl\\w+\\('([A-Z0-9]+)'/);
                if (match) prcode = match[1];
            }

            // Description: element right after the anchor
            const descEl = li.querySelector('.area1 > div:nth-child(2), a.title + div');
            const desc = descEl ? descEl.textContent.trim() : '';

            // Extract rate text (look for % pattern)
            let rateText = '';
            const allStrongs = li.querySelectorAll('strong');
            for (const s of allStrongs) {
                if (s.textContent.includes('%')) {
                    rateText = s.textContent.trim();
                    break;
                }
            }

            // Extract full text for term/period info
            const fullText = li.textContent;
            const termMatch = fullText.match(/(\\d+[~～]\\d+개월|\\d+개월[^,]*)/);
            const termText = termMatch ? termMatch[0].trim() : '';

            // Extract channels (가입가능경로)
            const channels = [];
            const dds = li.querySelectorAll('dd');
            for (const dd of dds) {
                const t = dd.textContent.trim();
                if (['인터넷', '모바일뱅킹', '영업점', '리브 Next', '고객센터'].includes(t)) {
                    channels.push(t);
                }
            }

            results.push({
                name: name,
                prcode: prcode,
                summary: desc,
                rateText: rateText,
                termText: termText,
                channels: channels,
            });
        }
        return results;
    }""")

    for item in product_items:
        name = item.get("name", "").strip()
        if not name:
            continue

        prcode = item.get("prcode", "")
        # Build detail URL using prcode (extracted from onclick handler)
        # URL pattern: /quics?page=C016613&cc=b061496:b061645&isNew=N&prcode=DP01000938
        cat_cfg = CATEGORIES.get(category, {})
        page_id = cat_cfg.get("page_id", "C016613")
        if prcode:
            detail_url = f"{BASE_URL}?page={page_id}&cc=b061496:b061645&isNew=N&prcode={prcode}"
        else:
            detail_url = ""

        products.append(DiscoveredProduct(
            name=name,
            category=category,
            page_url=detail_url,
            page_id=page_id,
            prcode=prcode,
            summary=item.get("summary", ""),
            rate_text=item.get("rateText", ""),
            term_text=item.get("termText", ""),
            channels=item.get("channels", []),
        ))

    return products
