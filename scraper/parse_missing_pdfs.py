"""Parse only MISSING PDFs that don't yet have corresponding markdown files.

Uses PyMuPDF (fitz) for text extraction (no GPT-4o Vision OCR) to save cost,
then GPT-4o-mini for structured extraction, reusing functions from parse_pdfs.py.
"""

import sys
from pathlib import Path

# Ensure the scraper package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse_pdfs import (
    CAT_DIR_MAP,
    PRODUCTS_DIR,
    RAW_DIR,
    generate_md,
    parse_with_gpt,
    pdf_to_text_fallback,
)


def find_missing_pdfs() -> list[Path]:
    """Return PDF paths that have no corresponding markdown in data/products/."""
    pdf_files = sorted(RAW_DIR.glob("**/*.pdf"))
    missing: list[Path] = []

    for pdf_path in pdf_files:
        category = pdf_path.parent.name
        name_slug = pdf_path.stem
        out_subdir = CAT_DIR_MAP.get(category, category)
        out_dir = PRODUCTS_DIR / out_subdir

        existing = list(out_dir.glob(f"*{name_slug}*"))
        if not existing:
            missing.append(pdf_path)

    return missing


def main() -> None:
    """Parse only missing PDFs using PyMuPDF + GPT-4o-mini."""
    if not RAW_DIR.exists():
        print(f"No raw directory found at {RAW_DIR}")
        return

    missing = find_missing_pdfs()
    total_pdfs = len(sorted(RAW_DIR.glob("**/*.pdf")))

    print(f"Total PDFs: {total_pdfs}")
    print(f"Already parsed: {total_pdfs - len(missing)}")
    print(f"Missing (to parse): {len(missing)}")

    if not missing:
        print("\nNothing to do -- all PDFs have been parsed.")
        return

    # Verify PyMuPDF is available
    try:
        import fitz  # noqa: F401
    except ImportError:
        print("ERROR: PyMuPDF is not installed. Run: pip3 install PyMuPDF")
        return

    processed = 0
    errors = 0

    for i, pdf_path in enumerate(missing, 1):
        category = pdf_path.parent.name
        name_slug = pdf_path.stem

        print(f"\n[{i}/{len(missing)}] {category}/{pdf_path.name}")

        # -- Stage 1: PyMuPDF text extraction (no Vision OCR) --
        print("  Stage 1: PyMuPDF text extraction...")
        try:
            raw_text = pdf_to_text_fallback(str(pdf_path))
            print(f"  Extracted: {len(raw_text)} chars")
        except Exception as e:
            print(f"  Extraction error: {e}")
            errors += 1
            continue

        if len(raw_text.strip()) < 50:
            print("  Skipping: too little text extracted")
            errors += 1
            continue

        # -- Stage 2: GPT-4o-mini structured extraction --
        print("  Stage 2: GPT-4o-mini parsing...")
        try:
            parsed = parse_with_gpt(raw_text, name_slug)
            if parsed.get("error"):
                print(f"  GPT error: {parsed['error']}")
                errors += 1
                continue
            print(f"  Parsed: {parsed.get('name', 'unknown')}")
        except Exception as e:
            print(f"  GPT error: {e}")
            errors += 1
            continue

        # -- Stage 3: Generate MD with YAML frontmatter --
        print("  Stage 3: Writing MD...")

        out_subdir = CAT_DIR_MAP.get(category, category)
        out_dir = PRODUCTS_DIR / out_subdir
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / f"{name_slug}.md"
        md_content = generate_md(parsed, str(pdf_path))
        out_path.write_text(md_content, encoding="utf-8")
        print(f"  Written: {out_path}")
        processed += 1

    print(f"\n{'=' * 50}")
    print(f"Done! Processed: {processed}, Errors: {errors}, Total missing: {len(missing)}")


if __name__ == "__main__":
    main()
