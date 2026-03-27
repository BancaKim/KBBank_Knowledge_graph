"""Enrich sparse MD product files with detailed content from financial institution."""

import asyncio
import re
import sys
from pathlib import Path
from datetime import datetime

import frontmatter
import yaml
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_DIR = PROJECT_ROOT / "data" / "products"


async def extract_detail(page, url: str) -> dict:
    """Visit a product detail page and extract all available info."""
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
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)  # Wait for dynamic content
    except Exception as e:
        print(f"  Navigation failed: {e}")
        return result

    # Extract header info (dt/dd pairs)
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
            pcts = re.findall(r'(\d+\.?\d*)\s*%', val)
            if pcts:
                rates = sorted(set(float(p) for p in pcts))
                result["rate_min"] = f"{rates[0]}%"
                result["rate_max"] = f"{rates[-1]}%"
        elif "가입가능경로" in key:
            pass  # Already have channels

    # Extract 상품안내 tab sections (li > strong label + content)
    sections = await page.evaluate("""() => {
        const sections = {};
        const listItems = document.querySelectorAll('li');
        for (const li of listItems) {
            const strong = li.querySelector('strong');
            if (!strong) continue;
            const label = strong.textContent.trim();
            if (label.length > 30 || label.length < 2) continue;

            // Get content after the strong tag
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

    # Map sections to fields
    for label, value in sections.items():
        if "특징" in label or "소개" in label:
            if len(value) > len(result["description"]):
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
        elif "이자" in label or "만기" in label or "분할" in label:
            result["features"].append(f"{label}: {value[:200]}")

    # Try clicking 금리 및 이율 tab
    try:
        rate_tab = page.get_by_role("link", name="금리 및 이율").first
        if await rate_tab.count() > 0:
            await rate_tab.click()
            await asyncio.sleep(1.5)

            rate_content = await page.evaluate("""() => {
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
                result["raw_sections"]["금리_및_이율"] = rate_content
                pcts = re.findall(r'(\d+\.?\d*)\s*%', rate_content)
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

    # Try clicking 유의사항 tab
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
                    if (text.length > 10 && text.length < 500) {
                        notes.push(text);
                    }
                }
                return notes.slice(0, 10).join('\\n');
            }""")

            if notes_content:
                result["notes"] = notes_content
    except Exception:
        pass

    return result


def build_enriched_md(meta: dict, detail: dict) -> str:
    """Build an enriched markdown file from frontmatter + scraped detail."""
    fm = {
        "name": meta.get("name", ""),
        "category": meta.get("category", ""),
    }

    # Rates
    if detail["rate_min"] or detail["rate_max"]:
        rates = {}
        if detail["rate_min"]:
            rates["min"] = detail["rate_min"]
        if detail["rate_max"]:
            rates["max"] = detail["rate_max"]
        if detail["rate_type"]:
            rates["type"] = detail["rate_type"]
        fm["rates"] = rates

    # Terms
    if detail["term_info"]:
        fm["terms"] = detail["term_info"]

    # Amounts
    if detail["amount_info"]:
        fm["amounts"] = detail["amount_info"]

    if meta.get("channels"):
        fm["channels"] = meta["channels"]

    fm["page_url"] = meta.get("page_url", "")
    fm["page_id"] = meta.get("page_id", "")
    fm["scraped_at"] = datetime.now().isoformat(timespec="seconds")

    # Build body
    name = meta.get("name", "")
    sections = [f"# {name}\n"]

    if detail["description"]:
        sections.append(f"## 상품설명\n\n{detail['description']}\n")

    if detail["rate_min"] or detail["rate_max"]:
        rate_lines = []
        if detail["rate_min"] and detail["rate_max"]:
            rate_lines.append(f"- 금리 범위: {detail['rate_min']} ~ {detail['rate_max']}")
        elif detail["rate_min"]:
            rate_lines.append(f"- 금리: {detail['rate_min']}")
        if detail["rate_type"]:
            rate_lines.append(f"- 금리 유형: {detail['rate_type']}")
        sections.append("## 금리\n\n" + "\n".join(rate_lines) + "\n")

    if detail["rate_min"] or detail["rate_max"]:
        rate_detail = detail["raw_sections"].get("금리_및_이율", "")
        if rate_detail:
            sections.append(f"## 금리 상세\n\n```\n{rate_detail}\n```\n")

    cond_lines = []
    if detail["term_info"]:
        cond_lines.append(f"- 가입기간: {detail['term_info']}")
    if detail["amount_info"]:
        cond_lines.append(f"- 가입금액: {detail['amount_info']}")
    if detail["conditions"]:
        cond_lines.append(f"- 기타조건: {detail['conditions']}")
    if cond_lines:
        sections.append("## 가입조건\n\n" + "\n".join(cond_lines) + "\n")

    if detail["eligibility"]:
        sections.append(f"## 가입대상\n\n{detail['eligibility']}\n")

    if detail["fees"]:
        sections.append(f"## 수수료\n\n{detail['fees']}\n")

    if detail["tax_benefits"]:
        sections.append(f"## 세제혜택\n\n{detail['tax_benefits']}\n")

    if detail["features"]:
        feature_lines = "\n".join(f"- {f}" for f in detail["features"])
        sections.append(f"## 특징\n\n{feature_lines}\n")

    if detail["notes"]:
        sections.append(f"## 유의사항\n\n{detail['notes']}\n")

    # Add remaining raw sections not already mapped
    mapped_keys = {"특징", "소개", "대상", "기간", "금액", "수수료", "중도해지", "세제", "비과세", "세금", "조건", "이자", "만기", "분할", "금리_및_이율"}
    for label, value in detail["raw_sections"].items():
        if label == "금리_및_이율":
            continue
        if not any(mk in label for mk in mapped_keys):
            sections.append(f"## {label}\n\n{value}\n")

    if meta.get("channels"):
        sections.append(f"## 가입채널\n\n{', '.join(meta['channels'])}\n")

    body = "\n".join(sections)
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False).rstrip()
    return f"---\n{fm_str}\n---\n\n{body}"


async def main():
    # Find all MD files
    md_files = sorted(PRODUCTS_DIR.glob("**/*.md"))
    print(f"Found {len(md_files)} product files to enrich")

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

        enriched = 0
        for i, md_path in enumerate(md_files, 1):
            try:
                post = frontmatter.load(str(md_path))
                meta = dict(post.metadata)
                url = meta.get("page_url", "")
                name = meta.get("name", md_path.stem)

                if not url or not url.startswith("http"):
                    print(f"[{i}/{len(md_files)}] Skipping {name} (no URL)")
                    continue

                print(f"[{i}/{len(md_files)}] Enriching: {name}")

                detail = await extract_detail(page, url)

                # Only rewrite if we got meaningful new data
                has_new_data = bool(
                    detail["description"] or detail["eligibility"] or
                    detail["rate_min"] or detail["term_info"] or
                    detail["amount_info"] or detail["fees"] or
                    len(detail["raw_sections"]) > 0
                )

                if has_new_data:
                    content = build_enriched_md(meta, detail)
                    md_path.write_text(content, encoding="utf-8")
                    field_count = sum(1 for v in [detail["description"], detail["eligibility"],
                                                   detail["rate_min"], detail["term_info"],
                                                   detail["amount_info"], detail["fees"]] if v)
                    print(f"  -> Enriched ({field_count} fields, {len(detail['raw_sections'])} sections)")
                    enriched += 1
                else:
                    print(f"  -> No new data found")

                # Polite delay
                await asyncio.sleep(2)

            except Exception as e:
                print(f"  -> Error: {e}")
                continue

        await browser.close()

    print(f"\nDone! Enriched {enriched}/{len(md_files)} files")


if __name__ == "__main__":
    asyncio.run(main())
