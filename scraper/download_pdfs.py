"""Download PDF product sheets from KB Star Bank print popup pages."""
import asyncio
import re
from pathlib import Path
from slugify import slugify
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

LISTING_PAGES = [
    {"url": "https://obank.kbstar.com/quics?page=C103429", "category": "신용대출"},
    {"url": "https://obank.kbstar.com/quics?page=C103557", "category": "담보대출"},
    {"url": "https://obank.kbstar.com/quics?page=C103507", "category": "전월세대출"},
    {"url": "https://obank.kbstar.com/quics?page=C103573", "category": "자동차대출"},
]


async def get_products_on_page(page) -> list[dict]:
    """Extract product names and prcode from listing page."""
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


async def get_all_products(page, url) -> list[dict]:
    """Get all products from listing page including pagination."""
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(2)

    all_products = []
    seen = set()

    # Get products from page 1
    products = await get_products_on_page(page)
    for p in products:
        if p['prcode'] not in seen:
            seen.add(p['prcode'])
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
                if p['prcode'] not in seen:
                    seen.add(p['prcode'])
                    all_products.append(p)
                    new += 1
            if new == 0:
                break
            page_num += 1
        except:
            break

    return all_products


async def download_product_pdf(page, product, category, listing_url):
    """Follow the exact user flow: listing -> detail -> 인쇄 -> print popup -> PDF."""
    name = product['name']
    prcode = product['prcode']

    out_dir = RAW_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = slugify(name, allow_unicode=True) or slugify(name) or prcode
    pdf_path = out_dir / f"{filename}.pdf"

    if pdf_path.exists():
        print(f"    Skip (exists): {pdf_path.name}")
        return pdf_path

    try:
        # Step 1: Navigate to listing page
        await page.goto(listing_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        # Step 2: Click product to go to detail page (call dtlLoan JS function)
        onclick_js = product['onclick'].rstrip(';')
        await page.evaluate(f"() => {{ {onclick_js}; }}")
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle")

        # Step 3: Click 인쇄 button - this opens a NEW TAB (not browser print dialog)
        async with page.context.expect_page() as new_page_info:
            print_btn = page.get_by_role("button", name="인쇄")
            if await print_btn.count() > 0:
                await print_btn.click()
            else:
                print(f"    No 인쇄 button found for {name}")
                return None

        # Step 4: Get the new popup tab
        print_page = await new_page_info.value
        await print_page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Step 5: Save the print popup page as PDF
        await print_page.pdf(path=str(pdf_path), format="A4", print_background=True)
        print(f"    Saved: {pdf_path.name}")

        # Step 6: Close the print popup tab
        await print_page.close()

        return pdf_path

    except Exception as e:
        print(f"    Error: {name} - {e}")
        return None


async def main():
    print("KB Star Bank Product PDF Downloader (Print Popup Method)")
    print("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        total = 0

        for listing in LISTING_PAGES:
            url = listing["url"]
            category = listing["category"]

            print(f"\n[{category}] Discovering products...")
            products = await get_all_products(page, url)
            print(f"  Found {len(products)} products")

            for i, product in enumerate(products, 1):
                print(f"  [{i}/{len(products)}] {product['name']}")
                result = await download_product_pdf(page, product, category, url)
                if result:
                    total += 1
                await asyncio.sleep(2)

        await browser.close()

    print(f"\n{'=' * 60}")
    print(f"Done! Downloaded {total} PDFs to {RAW_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
