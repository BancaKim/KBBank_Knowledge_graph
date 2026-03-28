"""Download deposit product PDFs via the print popup page.

Flow per product:
  1. Navigate to listing page (C016613)
  2. Click category tab (예금/적금/입출금자유/주택청약)
  3. Click product → detail page
  4. Click 인쇄 button → new popup tab opens (C060283)
  5. Override window.print() to prevent browser dialog
  6. Click popup's 인쇄 button → captures print-formatted content
  7. Save popup page as PDF
"""

import asyncio
import logging
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
BASE_URL = "https://obank.kbstar.com/quics?page=C016613"

# Tab definitions: (folder_name, tab_index)
ALL_TABS = [
    ("예금", 0),
    ("적금", 1),
    ("입출금자유", 2),
    ("주택청약", 3),
]
TEST_TABS = [("예금", 0)]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Create a filesystem-safe filename from Korean text."""
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    text = re.sub(r"\s+", "-", text)
    return text


async def discover_products(page, tab_index: int) -> list[dict]:
    """Discover products on a given tab. Returns list of {name, prcode, onclick}."""
    await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(2)

    # Click tab if not the default (index 0)
    if tab_index > 0:
        tab_links = await page.query_selector_all(
            "ul:has(> li > a[href='#none']) > li > a"
        )
        if tab_index < len(tab_links):
            await tab_links[tab_index].click(force=True)
            await asyncio.sleep(2)
            await page.wait_for_load_state("networkidle", timeout=15000)
        else:
            logger.error("Tab index %d not found (only %d tabs)", tab_index, len(tab_links))
            return []

    # Extract products via JS — get name, prcode, onclick
    products = await page.evaluate("""() => {
        const results = [];
        const allItems = document.querySelectorAll('li');
        for (const li of allItems) {
            // Only product items have 장바구니 or 비교하기 buttons
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

            const nameEl = li.querySelector('a strong');
            if (!nameEl) continue;
            const name = nameEl.textContent.trim();

            const anchor = li.querySelector('a[onclick*="dtl"]');
            let prcode = '';
            let onclick = '';
            if (anchor) {
                onclick = anchor.getAttribute('onclick') || '';
                const match = onclick.match(/dtl\\w+\\('([A-Z0-9]+)'/);
                if (match) prcode = match[1];
            }

            if (name && prcode) {
                results.push({ name, prcode, onclick: onclick.trim() });
            }
        }
        return results;
    }""")

    # Deduplicate by prcode
    seen = set()
    unique = []
    for p in products:
        if p["prcode"] not in seen:
            seen.add(p["prcode"])
            unique.append(p)

    return unique


async def download_product_pdf(
    page, product: dict, tab_name: str, tab_index: int, output_dir: Path
) -> Path | None:
    """Download a single product's PDF via the print popup flow."""
    name = product["name"]
    prcode = product["prcode"]
    onclick_js = product["onclick"].rstrip(";")

    filename = slugify(name) or prcode
    pdf_path = output_dir / f"{filename}.pdf"

    if pdf_path.exists():
        logger.info("  SKIP (exists): %s", pdf_path.name)
        return pdf_path

    try:
        # Step 1: Go to listing page and click correct tab
        await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        if tab_index > 0:
            tab_links = await page.query_selector_all(
                "ul:has(> li > a[href='#none']) > li > a"
            )
            if tab_index < len(tab_links):
                await tab_links[tab_index].click(force=True)
                await asyncio.sleep(2)
                await page.wait_for_load_state("networkidle", timeout=15000)

        # Step 2: Click product via onclick JS
        await page.evaluate(f"() => {{ {onclick_js}; }}")
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle")

        # Step 3: Click 인쇄 button on detail page → expect new tab
        print_btn = None
        # Try multiple selectors for the 인쇄 button
        for selector in [
            "a:has-text('인쇄')",
            "button:has-text('인쇄')",
            "[onclick*='print']",
        ]:
            el = await page.query_selector(selector)
            if el:
                print_btn = el
                break

        if not print_btn:
            logger.warning("  No 인쇄 button found for %s", name)
            return None

        # Capture the popup tab that opens
        try:
            async with page.context.expect_page(timeout=10000) as new_page_info:
                await print_btn.click()

            print_page = await new_page_info.value
            await print_page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

        except PlaywrightTimeout:
            # Fallback: no new tab — maybe modal or same page
            logger.warning("  No popup tab for %s, trying page.pdf() fallback", name)
            await page.pdf(path=str(pdf_path), format="A4", print_background=True)
            logger.info("  SAVED (fallback): %s", pdf_path.name)
            return pdf_path

        # Step 4: Override window.print() to prevent browser print dialog
        await print_page.evaluate("window.print = () => {}")

        # Step 5: Find and click the second 인쇄 button on the popup page
        popup_print_btn = None
        for selector in [
            "a:has-text('인쇄')",
            "button:has-text('인쇄')",
            "[onclick*='print']",
        ]:
            el = await print_page.query_selector(selector)
            if el:
                popup_print_btn = el
                break

        if popup_print_btn:
            await popup_print_btn.click()
            await asyncio.sleep(1)

        # Step 6: Save the print popup page as PDF
        await print_page.pdf(path=str(pdf_path), format="A4", print_background=True)
        logger.info("  SAVED: %s (%dKB)", pdf_path.name, pdf_path.stat().st_size // 1024)

        # Step 7: Close popup tab
        await print_page.close()
        return pdf_path

    except Exception as e:
        logger.error("  ERROR downloading %s: %s", name, e)
        return None


async def main():
    # Determine which tabs to process
    test_mode = "--all" not in sys.argv
    tabs = TEST_TABS if test_mode else ALL_TABS

    mode_label = "TEST (예금 only)" if test_mode else "FULL (all tabs)"
    logger.info("=" * 60)
    logger.info("예금 상품 PDF 다운로드 — %s", mode_label)
    logger.info("Use --all flag to process all 4 tabs")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        total_saved = 0
        total_skipped = 0

        for tab_name, tab_index in tabs:
            output_dir = RAW_DIR / tab_name
            output_dir.mkdir(parents=True, exist_ok=True)

            logger.info("\n[%s] (tab %d) Discovering products...", tab_name, tab_index)
            products = await discover_products(page, tab_index)
            logger.info("[%s] Found %d products", tab_name, len(products))

            for i, product in enumerate(products, 1):
                logger.info(
                    "  [%d/%d] %s (prcode=%s)",
                    i, len(products), product["name"], product["prcode"],
                )
                result = await download_product_pdf(
                    page, product, tab_name, tab_index, output_dir
                )
                if result:
                    total_saved += 1
                await asyncio.sleep(2)  # polite delay

        await browser.close()

    logger.info("=" * 60)
    logger.info("DONE! Saved: %d PDFs", total_saved)
    logger.info("Output: %s", RAW_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
