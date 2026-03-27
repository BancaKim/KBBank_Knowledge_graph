"""Download deposit product PDFs from financial institution website.

Navigates through 4 tabs (예금, 적금, 입출금자유, 주택청약),
clicks each product to view details, then saves as PDF.
"""

import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_BASE = PROJECT_ROOT / "data" / "raw"
BASE_URL = "https://obank.kbstar.com/quics?page=C016613"

# Tab indices (0-based) and output directory names
TABS = [
    (0, "예금"),
    (1, "적금"),
    (2, "입출금자유"),
    (3, "주택청약"),
]


def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', '', text)
    text = re.sub(r'\s+', '-', text)
    return text


async def main():
    print("금융기관 예금 상품 PDF 다운로드")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        total = 0

        for tab_idx, tab_name in TABS:
            output_dir = OUTPUT_BASE / tab_name
            output_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n{'='*60}")
            print(f"Tab: {tab_name} -> {output_dir}")
            print(f"{'='*60}")

            # Step 1: Go to main page
            await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Step 2: Click the tab using JavaScript (tabs use JS onclick)
            tab_links = await page.query_selector_all("ul > li > a")
            tab_texts = []
            for tl in tab_links:
                txt = (await tl.inner_text()).strip()
                tab_texts.append(txt)

            # Find tab link in the product tab area
            tab_area_links = await page.query_selector_all("ul:has(> li > a[href='#none']) > li > a")
            if tab_idx < len(tab_area_links):
                await tab_area_links[tab_idx].click(force=True)
                await asyncio.sleep(2)
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(1)
            else:
                print(f"  ERROR: Tab index {tab_idx} not found")
                continue

            # Step 3: Click "전체" radio for product type to see all products
            try:
                all_radios = await page.query_selector_all("input[type='radio']")
                for r in all_radios:
                    # Find the first "전체" in the product type row
                    parent_text = await r.evaluate("el => el.parentElement?.textContent || ''")
                    val = await r.get_attribute("value") or ""
                    if "전체" in parent_text and val == "" or "전체" in val:
                        label = await r.evaluate("el => el.nextElementSibling?.textContent || ''")
                        if "전체" in label:
                            await r.click(force=True)
                            break
            except:
                pass

            # Click search button
            try:
                search_btn = await page.query_selector("button:has-text('조회')")
                if search_btn:
                    await search_btn.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    await asyncio.sleep(2)
            except:
                pass

            # Step 4: Collect product names
            product_links = await page.query_selector_all("ul > li a[href='#none'] strong")
            product_names = []
            for pl in product_links:
                name = (await pl.inner_text()).strip()
                if name and len(name) > 1:
                    product_names.append(name)

            # Remove duplicates while preserving order
            seen = set()
            unique_names = []
            for n in product_names:
                if n not in seen:
                    seen.add(n)
                    unique_names.append(n)
            product_names = unique_names

            print(f"  Found {len(product_names)} products: {product_names}")

            # Step 5: Click each product, save detail page as PDF
            for i, name in enumerate(product_names):
                slug = slugify(name)
                pdf_path = output_dir / f"{slug}.pdf"

                if pdf_path.exists():
                    print(f"  [{i+1}/{len(product_names)}] SKIP (exists): {name}")
                    total += 1
                    continue

                print(f"  [{i+1}/{len(product_names)}] {name}...")

                try:
                    # Go back to list page
                    await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(1)

                    # Re-click tab
                    tab_area_links = await page.query_selector_all("ul:has(> li > a[href='#none']) > li > a")
                    if tab_idx < len(tab_area_links):
                        await tab_area_links[tab_idx].click(force=True)
                        await asyncio.sleep(2)
                        await page.wait_for_load_state("networkidle", timeout=15000)

                    # Click the product
                    product_link = await page.query_selector(f"a:has(strong:text-is('{name}'))")
                    if not product_link:
                        # Fallback: try partial match
                        product_link = await page.query_selector(f"a:has(strong:has-text('{name[:10]}'))")

                    if not product_link:
                        print(f"    ERROR: Link not found for '{name}'")
                        continue

                    await product_link.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(2)

                    # Save as PDF
                    await page.pdf(path=str(pdf_path), format="A4", print_background=True)
                    print(f"    SAVED: {pdf_path.name} ({pdf_path.stat().st_size // 1024}KB)")
                    total += 1

                except Exception as e:
                    print(f"    ERROR: {e}")

            print(f"  Tab '{tab_name}': done")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"DONE! Total: {total} PDFs")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
