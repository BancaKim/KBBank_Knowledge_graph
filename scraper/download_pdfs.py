"""Download loan product PDFs via the print popup page.

Flow per product:
  1. Navigate to category listing page (C103429 / C103557 / C103507 / C103573)
  2. Click product via onclick JS (dtlLoan/dtlCredit/... function)
  3. On detail page, click 인쇄 button → new popup tab opens (C060283)
  4. Override window.print() to prevent browser dialog
  5. Click popup's 인쇄 button
  6. Save popup page as PDF
"""

import asyncio
import logging
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Category listing pages — each category has its own page ID
ALL_CATEGORIES = [
    {"url": "https://obank.kbstar.com/quics?page=C103429", "category": "신용대출"},        # 72 PDFs
    {"url": "https://obank.kbstar.com/quics?page=C103557", "category": "담보대출"},        # 42 PDFs
    {"url": "https://obank.kbstar.com/quics?page=C103507", "category": "전월세대출"},      # 38 PDFs
    {"url": "https://obank.kbstar.com/quics?page=C103573", "category": "자동차대출"},      # 11 PDFs
    {"url": "https://obank.kbstar.com/quics?page=C109229", "category": "집단중도금_이주비대출"},  # 2 PDFs
    {"url": "https://obank.kbstar.com/quics?page=C103998", "category": "주택도시기금대출"},      # 18 PDFs
    # 개인사업자대출 제외 (사용자 요청)
]

TEST_CATEGORIES = [
    {"url": "https://obank.kbstar.com/quics?page=C103429", "category": "신용대출"},
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    text = re.sub(r"\s+", "-", text)
    return text


async def get_products_on_page(page) -> list[dict]:
    """Extract product names, prcode, onclick from listing page via JS."""
    return await page.evaluate("""() => {
        const results = [];
        const links = document.querySelectorAll('a[onclick]');
        for (const link of links) {
            const onclick = link.getAttribute('onclick');
            if (!onclick) continue;
            const match = onclick.match(/dtl\\w+\\('([A-Z0-9]+)'/);
            if (!match) continue;
            const name = link.querySelector('strong')?.textContent?.trim();
            if (!name) continue;
            results.push({ name, prcode: match[1], onclick: onclick.trim() });
        }
        return results;
    }""")


async def get_all_products(page, url: str) -> list[dict]:
    """Get all products from listing page including pagination."""
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(2)

    all_products = []
    seen = set()

    products = await get_products_on_page(page)
    for p in products:
        if p["prcode"] not in seen:
            seen.add(p["prcode"])
            all_products.append(p)

    # Paginate
    page_num = 2
    while True:
        try:
            btn = page.get_by_role("button", name=str(page_num), exact=True)
            if await btn.count() == 0:
                break
            await btn.click()
            await asyncio.sleep(2)
            products = await get_products_on_page(page)
            new = 0
            for p in products:
                if p["prcode"] not in seen:
                    seen.add(p["prcode"])
                    all_products.append(p)
                    new += 1
            if new == 0:
                break
            page_num += 1
        except Exception:
            break

    return all_products


async def download_product_pdf(page, product: dict, category: str, listing_url: str) -> Path | None:
    """Download a single product's PDF via the 2-step print popup flow."""
    name = product["name"]
    prcode = product["prcode"]
    onclick_js = product["onclick"].rstrip(";")

    out_dir = RAW_DIR / "대출" / category
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = slugify(name) or prcode
    pdf_path = out_dir / f"{filename}.pdf"

    if pdf_path.exists():
        logger.info("  SKIP (exists): %s", pdf_path.name)
        return pdf_path

    try:
        # Step 1: Navigate to listing page
        await page.goto(listing_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        # Step 2: Click product via onclick JS (dtlLoan/dtlCredit/etc.)
        await page.evaluate(f"() => {{ {onclick_js}; }}")
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle")

        # Step 3: Click 인쇄 button on detail page → expect new popup tab
        print_btn = None
        for selector in ["a:has-text('인쇄')", "button:has-text('인쇄')", "[onclick*='print']"]:
            el = await page.query_selector(selector)
            if el:
                print_btn = el
                break

        if not print_btn:
            logger.warning("  No 인쇄 button found for %s", name)
            return None

        try:
            async with page.context.expect_page(timeout=10000) as new_page_info:
                await print_btn.click()

            # Step 4: Capture the popup tab (C060283)
            print_page = await new_page_info.value
            await print_page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

        except PlaywrightTimeout:
            # Fallback: no new tab opened — save current page
            logger.warning("  No popup tab for %s, saving current page", name)
            await page.pdf(path=str(pdf_path), format="A4", print_background=True)
            logger.info("  SAVED (fallback): %s", pdf_path.name)
            return pdf_path

        # Step 5: Override window.print() before clicking the popup's 인쇄 button
        await print_page.evaluate("window.print = () => {}")

        # Step 6: Click the second 인쇄 button inside the popup
        popup_print_btn = None
        for selector in ["a:has-text('인쇄')", "button:has-text('인쇄')", "[onclick*='print']"]:
            el = await print_page.query_selector(selector)
            if el:
                popup_print_btn = el
                break

        if popup_print_btn:
            await popup_print_btn.click()
            await asyncio.sleep(1)

        # Step 7: Save the print popup page as PDF
        await print_page.pdf(path=str(pdf_path), format="A4", print_background=True)
        logger.info("  SAVED: %s (%dKB)", pdf_path.name, pdf_path.stat().st_size // 1024)

        # Step 8: Close the popup tab
        await print_page.close()
        return pdf_path

    except Exception as e:
        logger.error("  ERROR: %s - %s", name, e)
        return None


async def main():
    test_mode = "--all" not in sys.argv
    categories = TEST_CATEGORIES if test_mode else ALL_CATEGORIES

    mode_label = "TEST (신용대출 only)" if test_mode else "FULL (all categories)"
    logger.info("=" * 60)
    logger.info("대출 상품 PDF 다운로드 — %s", mode_label)
    logger.info("Use --all flag to process all categories")
    logger.info("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
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

        total = 0

        for listing in categories:
            url = listing["url"]
            category = listing["category"]

            logger.info("\n[%s] Discovering products...", category)
            products = await get_all_products(page, url)
            logger.info("[%s] Found %d products", category, len(products))

            for i, product in enumerate(products, 1):
                logger.info(
                    "  [%d/%d] %s (prcode=%s)",
                    i, len(products), product["name"], product["prcode"],
                )
                result = await download_product_pdf(page, product, category, url)
                if result:
                    total += 1
                await asyncio.sleep(2)

        await browser.close()

    logger.info("=" * 60)
    logger.info("DONE! Saved: %d PDFs", total)
    logger.info("Output: %s", RAW_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
