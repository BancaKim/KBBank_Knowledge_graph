"""2-stage PDF parsing pipeline for KB Star Bank financial products.

Pipeline:
  data/raw/{category}/*.pdf
    -> Stage 1: GPT-4o Vision OCR (or PyMuPDF fallback) -> raw markdown
    -> Stage 2: GPT-4o-mini (structured re-parsing)   -> enriched JSON
    -> Stage 3: Generate MD with YAML frontmatter
    -> Output: data/products/{category}/*.md
"""

import asyncio
import base64
import json
import os
from datetime import datetime
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PRODUCTS_DIR = PROJECT_ROOT / "data" / "products"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Stage 1: GPT-4o Vision OCR
# ---------------------------------------------------------------------------


def pdf_to_images(pdf_path: str) -> list[str]:
    """Convert each PDF page to a base64-encoded PNG image."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    images: list[str] = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode()
        images.append(b64)
    doc.close()
    return images


def ocr_with_gpt4o(images_b64: list[str]) -> str:
    """OCR PDF pages using GPT-4o Vision."""
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)

    all_text: list[str] = []
    for i, img_b64 in enumerate(images_b64):
        print(f"    OCR page {i+1}/{len(images_b64)}...")
        messages = [
            {
                "role": "system",
                "content": "당신은 금융 문서 OCR 전문가입니다. 이미지의 모든 텍스트를 정확하게 마크다운으로 변환합니다.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "이 금융상품 설명서 페이지의 모든 텍스트를 정확하게 추출해주세요.\n"
                            "규칙:\n"
                            "1. 표가 있으면 마크다운 테이블로 변환\n"
                            "2. 제목/소제목은 ## / ### 헤딩 사용\n"
                            "3. 목록은 - 불릿 사용\n"
                            "4. 숫자, 금리(%), 금액은 정확하게 유지\n"
                            "5. 원본 레이아웃과 순서를 최대한 유지\n"
                            "6. 불필요한 설명 없이 텍스트만 출력"
                        ),
                    },
                ],
            },
        ]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4096,
            temperature=0,
        )
        page_text = response.choices[0].message.content
        all_text.append(page_text)

    return "\n\n---\n\n".join(all_text)


def pdf_to_text_fallback(pdf_path: str) -> str:
    """Fallback: extract text from PDF using PyMuPDF (fitz) without VLM."""
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n\n"
    doc.close()
    return text


# ---------------------------------------------------------------------------
# Stage 2: GPT-4o-mini structured extraction
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = '''당신은 KB국민은행 금융상품 문서 파서입니다.
아래 상품 설명서 텍스트에서 다음 정보를 JSON으로 추출하세요.

추출 항목:
{
  "name": "상품명",
  "category": "카테고리 (신용대출/담보대출/전월세대출/자동차대출/정기예금/적금/입출금통장/청약)",
  "description": "상품 특징 설명 (1-2문장)",
  "eligibility": "가입/대출 자격 요건",
  "term": "가입/대출 기간",
  "amount": "가입/대출 금액 한도",
  "rate_info": "금리 정보 (기본금리, 우대금리 등)",
  "repayment": "상환 방법 (대출인 경우)",
  "channels": ["가입 가능 채널 목록"],
  "fees": "수수료 정보",
  "tax_benefits": "세제혜택 (예금인 경우)",
  "deposit_protection": "예금자보호 여부",
  "preferential_rates": [
    {"name": "우대 조건명", "rate": "우대금리(연 %p)", "condition": "조건 설명"}
  ],
  "features": ["상품 주요 특징 목록"],
  "notes": "유의사항 요약"
}

규칙:
1. 텍스트에 없는 항목은 빈 문자열("") 또는 빈 배열([])로 표시
2. 금액은 원본 표기 유지 (예: "최소 50만원 ~ 최대 300만원")
3. 금리는 숫자와 % 포함 (예: "연 3.5%")
4. JSON만 출력, 다른 텍스트 없이

상품 설명서:
'''


def parse_with_gpt(raw_text: str, filename: str = "") -> dict:
    """Send raw markdown to GPT-4o-mini for structured extraction."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Truncate to fit context window
    max_chars = 12000
    text = raw_text[:max_chars]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a Korean financial document parser. Output only valid JSON.",
            },
            {"role": "user", "content": EXTRACTION_PROMPT + text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {"name": filename, "error": "JSON parse failed"}


# ---------------------------------------------------------------------------
# Stage 3: Generate enriched Markdown with YAML frontmatter
# ---------------------------------------------------------------------------


def generate_md(parsed: dict, pdf_path: str) -> str:
    """Generate a markdown file with YAML frontmatter from parsed data."""
    fm: dict = {
        "name": parsed.get("name", ""),
        "category": parsed.get("category", ""),
    }

    if parsed.get("rate_info"):
        fm["rates"] = parsed["rate_info"]
    if parsed.get("term"):
        fm["terms"] = parsed["term"]
    if parsed.get("amount"):
        fm["amounts"] = parsed["amount"]
    if parsed.get("channels"):
        fm["channels"] = parsed["channels"]
    if parsed.get("repayment"):
        fm["repayment"] = parsed["repayment"]
    if parsed.get("eligibility"):
        fm["eligibility_summary"] = parsed["eligibility"][:200]

    fm["source"] = f"PDF: {Path(pdf_path).name}"
    fm["parsed_at"] = datetime.now().isoformat(timespec="seconds")

    # Build body sections
    name = parsed.get("name", "")
    sections: list[str] = [f"# {name}\n"]

    if parsed.get("description"):
        sections.append(f"## 상품설명\n\n{parsed['description']}\n")

    if parsed.get("rate_info"):
        sections.append(f"## 금리\n\n{parsed['rate_info']}\n")

    if parsed.get("eligibility"):
        sections.append(f"## 가입대상\n\n{parsed['eligibility']}\n")

    if parsed.get("term"):
        sections.append(f"## 가입기간\n\n{parsed['term']}\n")

    if parsed.get("amount"):
        sections.append(f"## 한도\n\n{parsed['amount']}\n")

    if parsed.get("repayment"):
        sections.append(f"## 상환방법\n\n{parsed['repayment']}\n")

    if parsed.get("fees"):
        sections.append(f"## 수수료\n\n{parsed['fees']}\n")

    if parsed.get("tax_benefits"):
        sections.append(f"## 세제혜택\n\n{parsed['tax_benefits']}\n")

    if parsed.get("deposit_protection"):
        sections.append(f"## 예금자보호\n\n{parsed['deposit_protection']}\n")

    if parsed.get("preferential_rates"):
        pref_lines = []
        for pr in parsed["preferential_rates"]:
            pref_lines.append(
                f"- **{pr.get('name', '')}**: {pr.get('rate', '')} ({pr.get('condition', '')})"
            )
        sections.append("## 우대금리\n\n" + "\n".join(pref_lines) + "\n")

    if parsed.get("features"):
        feat_lines = "\n".join(f"- {f}" for f in parsed["features"])
        sections.append(f"## 주요특징\n\n{feat_lines}\n")

    if parsed.get("notes"):
        sections.append(f"## 유의사항\n\n{parsed['notes']}\n")

    if parsed.get("channels"):
        sections.append(f"## 가입채널\n\n{', '.join(parsed['channels'])}\n")

    body = "\n".join(sections)
    fm_str = yaml.dump(
        fm, allow_unicode=True, default_flow_style=False, sort_keys=False
    ).rstrip()
    return f"---\n{fm_str}\n---\n\n{body}"


# ---------------------------------------------------------------------------
# Category -> output sub-directory mapping
# ---------------------------------------------------------------------------

CAT_DIR_MAP: dict[str, str] = {
    "신용대출": "대출",
    "담보대출": "대출",
    "전월세대출": "대출",
    "자동차대출": "대출",
    "정기예금": "예금",
    "입출금통장": "예금",
    "적금": "적금",
    "청약": "적금",
}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the full PDF parsing pipeline."""
    if not RAW_DIR.exists():
        print(f"No PDFs found in {RAW_DIR}. Run download_pdfs.py first.")
        return

    pdf_files = sorted(RAW_DIR.glob("**/*.pdf"))
    print(f"Found {len(pdf_files)} PDF files to parse")

    if not pdf_files:
        print("Nothing to do.")
        return

    # Determine OCR strategy
    gpt4o_available = bool(OPENAI_API_KEY)
    fitz_available = False

    try:
        import fitz  # noqa: F401
        fitz_available = True
    except ImportError:
        pass

    if gpt4o_available and fitz_available:
        print("Using DeepSeek VL for OCR (PDF -> images -> DeepSeek API)")
    elif fitz_available:
        print("OPENAI_API_KEY not set, using PyMuPDF text extraction fallback")
    else:
        print("ERROR: PyMuPDF is not installed!")
        print("Install: pip3 install PyMuPDF")
        return

    processed = 0
    errors = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        category = pdf_path.parent.name
        name_slug = pdf_path.stem

        print(f"\n[{i}/{len(pdf_files)}] {category}/{pdf_path.name}")

        # -- Stage 1: OCR / text extraction ---------------------------------
        print("  Stage 1: OCR...")
        try:
            if gpt4o_available and fitz_available:
                images_b64 = pdf_to_images(str(pdf_path))
                print(f"  Converted {len(images_b64)} pages to images")
                raw_md = ocr_with_gpt4o(images_b64)
            else:
                raw_md = pdf_to_text_fallback(str(pdf_path))

            print(f"  OCR result: {len(raw_md)} chars")
        except Exception as e:
            print(f"  DeepSeek OCR error, trying PyMuPDF fallback: {e}")
            try:
                raw_md = pdf_to_text_fallback(str(pdf_path))
                print(f"  Fallback OCR result: {len(raw_md)} chars")
            except Exception as e2:
                print(f"  OCR error: {e2}")
                errors += 1
                continue

        if len(raw_md.strip()) < 50:
            print("  Skipping: too little text extracted")
            errors += 1
            continue

        # -- Stage 2: GPT-4o-mini structured extraction ---------------------
        print("  Stage 2: GPT parsing...")
        try:
            parsed = parse_with_gpt(raw_md, pdf_path.stem)
            if parsed.get("error"):
                print(f"  GPT error: {parsed['error']}")
                errors += 1
                continue
            print(f"  Parsed: {parsed.get('name', 'unknown')}")
        except Exception as e:
            print(f"  GPT error: {e}")
            errors += 1
            continue

        # -- Stage 3: Generate MD -------------------------------------------
        print("  Stage 3: Writing MD...")

        out_subdir = CAT_DIR_MAP.get(category, category)
        out_dir = PRODUCTS_DIR / out_subdir
        out_dir.mkdir(parents=True, exist_ok=True)

        # Re-use existing file if one matches, otherwise create new
        existing = list(out_dir.glob(f"*{name_slug}*"))
        if existing:
            out_path = existing[0]
        else:
            out_path = out_dir / f"{name_slug}.md"

        md_content = generate_md(parsed, str(pdf_path))
        out_path.write_text(md_content, encoding="utf-8")
        print(f"  Written: {out_path}")
        processed += 1

    print(f"\n{'=' * 50}")
    print(f"Done! Processed: {processed}, Errors: {errors}")


if __name__ == "__main__":
    asyncio.run(main())
