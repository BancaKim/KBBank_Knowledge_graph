"""2-pass PDF parsing pipeline: GLM-OCR (MLX, Pass 1) + GPT-4o Vision (Pass 2).

Pipeline:
  data/raw/{대분류}/{중분류}/*.pdf
    -> Pass 1: GLM-OCR via local mlx-vlm server (Metal GPU) -> raw markdown
    -> Pass 2: GPT-4o Vision (anchored text + page image)   -> refined markdown
    -> Output: data/products/{대분류}/{중분류}/*.md

Prerequisites:
  - mlx-vlm server running: .venv-mlx/bin/python -m mlx_vlm.server --model mlx-community/GLM-OCR-bf16 --trust-remote-code --port 8090
  - OPENAI_API_KEY set in environment or .env
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PRODUCTS_DIR = PROJECT_ROOT / "data" / "products"

GLM_OCR_URL = "http://localhost:8090/v1"
GLM_OCR_MODEL = "mlx-community/GLM-OCR-bf16"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Rate limiting
GLM_DELAY = 1.0       # seconds between GLM-OCR calls
GPT4O_DELAY = 0.5     # seconds between GPT-4o calls
DPI = 150              # PDF rasterization DPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pass 1: GLM-OCR via mlx-vlm server (local Metal GPU)
# ---------------------------------------------------------------------------

def pdf_to_page_images(pdf_path: str, dpi: int = DPI) -> list[tuple[str, bytes]]:
    """Convert each PDF page to (base64_png, raw_bytes) tuple."""
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode()
        pages.append((b64, img_bytes))
    doc.close()
    return pages


def extract_text_with_coords(pdf_path: str) -> list[str]:
    """Extract raw text blocks with positional info per page (for anchoring)."""
    doc = fitz.open(pdf_path)
    pages_text = []
    for page in doc:
        blocks = page.get_text("blocks")
        anchored = ""
        for b in blocks:
            x0, y0, x1, y1, text, *_ = b
            text = text.strip()
            if text:
                anchored += f"[({int(x0)},{int(y0)})-({int(x1)},{int(y1)})] {text}\n"
        pages_text.append(anchored)
    doc.close()
    return pages_text


def glm_ocr_page(client: OpenAI, image_b64: str, page_num: int) -> str:
    """Send a single page image to GLM-OCR server for OCR."""
    try:
        response = client.chat.completions.create(
            model=GLM_OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Text Recognition:",
                        },
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        log.warning("  GLM-OCR page %d error: %s", page_num + 1, e)
        return ""


def pass1_glm_ocr(pdf_path: str, glm_client: OpenAI) -> tuple[str, list[str]]:
    """Pass 1: Run GLM-OCR on all pages. Returns (combined_md, per_page_list)."""
    pages = pdf_to_page_images(pdf_path)
    coord_texts = extract_text_with_coords(pdf_path)

    page_results = []
    for i, (b64, _) in enumerate(pages):
        log.info("    Pass1 GLM-OCR page %d/%d", i + 1, len(pages))
        ocr_text = glm_ocr_page(glm_client, b64, i)

        # Combine GLM-OCR output with coordinate text for richer anchoring
        combined = ocr_text
        if coord_texts[i].strip():
            combined += f"\n\n<!-- raw text blocks -->\n{coord_texts[i]}"

        page_results.append(combined)
        if i < len(pages) - 1:
            time.sleep(GLM_DELAY)

    full_md = "\n\n---\n\n".join(page_results)
    return full_md, page_results


# ---------------------------------------------------------------------------
# Pass 2: GPT-4o Vision (anchored text + page image)
# ---------------------------------------------------------------------------

PASS2_SYSTEM = """당신은 한국 금융상품 문서 파싱 전문가입니다.
1차 OCR 결과 텍스트와 원본 페이지 이미지를 함께 받습니다.
두 입력을 교차 검증하여 정확한 마크다운을 생성하세요.

규칙:
1. 표는 마크다운 테이블로 정확하게 변환 (셀 내용, 행/열 구조 유지)
2. 제목/소제목은 ## / ### 헤딩
3. 금리(%), 금액, 기간 등 숫자는 반드시 원본 그대로 유지
4. 1차 OCR에 있지만 이미지에 없는 내용은 제거 (환각 방지)
5. 이미지에 있지만 1차 OCR에서 누락된 내용은 보충
6. 불필요한 설명 없이 문서 내용만 출력"""


def pass2_gpt4o_page(
    gpt_client: OpenAI,
    pass1_text: str,
    image_b64: str,
    page_num: int,
) -> str:
    """Send Pass 1 text + page image to GPT-4o for refined parsing."""
    try:
        response = gpt_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PASS2_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"## 1차 OCR 결과 (참고용)\n\n{pass1_text}\n\n"
                                "---\n\n"
                                "위 1차 OCR 결과와 아래 원본 이미지를 교차 검증하여 "
                                "정확한 마크다운을 생성해주세요."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=4096,
            temperature=0,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        log.warning("  GPT-4o page %d error: %s, using Pass1 fallback", page_num + 1, e)
        return pass1_text  # fallback to pass1


def pass2_gpt4o(
    pdf_path: str,
    pass1_pages: list[str],
    gpt_client: OpenAI,
) -> str:
    """Pass 2: Refine each page with GPT-4o Vision + anchored text."""
    pages = pdf_to_page_images(pdf_path)
    refined_pages = []

    for i, (b64, _) in enumerate(pages):
        pass1_text = pass1_pages[i] if i < len(pass1_pages) else ""
        log.info("    Pass2 GPT-4o page %d/%d", i + 1, len(pages))
        refined = pass2_gpt4o_page(gpt_client, pass1_text, b64, i)
        refined_pages.append(refined)
        if i < len(pages) - 1:
            time.sleep(GPT4O_DELAY)

    return "\n\n---\n\n".join(refined_pages)


# ---------------------------------------------------------------------------
# Output: Generate MD with YAML frontmatter
# ---------------------------------------------------------------------------

def generate_product_md(refined_md: str, pdf_path: Path) -> str:
    """Wrap refined markdown with YAML frontmatter."""
    fm = {
        "source_pdf": pdf_path.name,
        "category": pdf_path.parent.name,
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
        "pipeline": "GLM-OCR(MLX) + GPT-4o Vision (2-pass)",
    }
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False).rstrip()
    return f"---\n{fm_str}\n---\n\n{refined_md}"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    # Parse arguments
    test_mode = "--all" not in sys.argv
    pass1_only = "--pass1-only" in sys.argv

    # Discover PDFs
    all_pdfs = sorted(RAW_DIR.glob("**/*.pdf"))

    # Skip 판매중단 products
    pdf_files = [p for p in all_pdfs if "판매중단" not in p.stem]
    skipped = len(all_pdfs) - len(pdf_files)
    log.info("Found %d PDF files in %s (skipped %d 판매중단)", len(pdf_files), RAW_DIR, skipped)

    if not pdf_files:
        log.error("No PDFs found. Run download scripts first.")
        return

    if test_mode:
        # Test with first 3 PDFs
        pdf_files = pdf_files[:3]
        log.info("TEST MODE: processing first %d PDFs (use --all for full run)", len(pdf_files))

    # Initialize clients
    glm_client = OpenAI(base_url=GLM_OCR_URL, api_key="not-needed")

    if not pass1_only:
        if not OPENAI_API_KEY:
            log.error("OPENAI_API_KEY not set. Use --pass1-only for GLM-OCR only.")
            return
        gpt_client = OpenAI(api_key=OPENAI_API_KEY, timeout=120.0)
    else:
        gpt_client = None

    # Verify GLM-OCR server
    try:
        glm_client.models.list()
        log.info("GLM-OCR server connected at %s", GLM_OCR_URL)
    except Exception as e:
        log.error("Cannot connect to GLM-OCR server at %s: %s", GLM_OCR_URL, e)
        log.error("Start server: .venv-mlx/bin/python -m mlx_vlm.server --model mlx-community/GLM-OCR-bf16 --trust-remote-code --port 8090")
        return

    processed = 0
    errors = 0
    start_time = time.time()

    for i, pdf_path in enumerate(pdf_files, 1):
        # Determine output path preserving directory structure
        rel = pdf_path.relative_to(RAW_DIR)  # e.g. 대출/신용대출/KB-신용대출.pdf
        out_path = PRODUCTS_DIR / rel.with_suffix(".md")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if out_path.exists():
            log.info("[%d/%d] SKIP (exists): %s", i, len(pdf_files), rel)
            processed += 1
            continue

        log.info("[%d/%d] %s", i, len(pdf_files), rel)

        try:
            # Pass 1: GLM-OCR
            log.info("  Pass 1: GLM-OCR (MLX Metal)")
            pass1_md, pass1_pages = pass1_glm_ocr(str(pdf_path), glm_client)
            log.info("  Pass 1 done: %d chars", len(pass1_md))

            if len(pass1_md.strip()) < 30:
                log.warning("  Too little text from Pass 1, skipping")
                errors += 1
                continue

            # Pass 2: GPT-4o Vision (unless --pass1-only)
            if gpt_client and not pass1_only:
                log.info("  Pass 2: GPT-4o Vision (anchored)")
                final_md = pass2_gpt4o(str(pdf_path), pass1_pages, gpt_client)
                log.info("  Pass 2 done: %d chars", len(final_md))
            else:
                final_md = pass1_md

            # Write output
            content = generate_product_md(final_md, pdf_path)
            out_path.write_text(content, encoding="utf-8")
            log.info("  SAVED: %s", out_path)
            processed += 1

        except Exception as e:
            log.error("  ERROR: %s — %s", rel, e)
            errors += 1

    elapsed = time.time() - start_time
    log.info("")
    log.info("=" * 60)
    log.info("DONE! Processed: %d, Errors: %d, Time: %.1fs", processed, errors, elapsed)
    log.info("Output: %s", PRODUCTS_DIR)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
