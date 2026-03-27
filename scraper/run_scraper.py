"""CLI entry point for the financial institution financial products scraper."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from scraper.browser import BrowserManager
from scraper.config import CATEGORIES, LOAN_CATEGORIES, OUTPUT_DIR
from scraper.discovery import discover_all
from scraper.extractor import extract_many
from scraper.markdown_writer import write_many

logger = logging.getLogger("scraper")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scrape",
        description="Scrape financial institution (obank.kbstar.com) financial product pages.",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        metavar="CAT",
        help=(
            "Categories to scrape. Available: "
            + ", ".join(CATEGORIES.keys())
            + ". Default: all."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for markdown files (default: data/products).",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run browser in headless mode (default: True).",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        default=False,
        help="Only discover product URLs, do not extract or write.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


async def async_main(args: argparse.Namespace) -> None:
    """Run the full scrape pipeline."""
    _setup_logging(args.verbose)

    categories = args.categories
    if categories:
        # Expand "대출" alias to all loan sub-categories
        expanded = []
        for c in categories:
            if c == "대출":
                expanded.extend(LOAN_CATEGORIES)
            else:
                expanded.append(c)
        categories = expanded

        unknown = set(categories) - set(CATEGORIES.keys())
        if unknown:
            logger.error("Unknown categories: %s", ", ".join(unknown))
            logger.error("Available: %s", ", ".join(CATEGORIES.keys()))
            sys.exit(1)

    logger.info("=" * 60)
    logger.info("Financial Institution Scraper")
    logger.info("=" * 60)
    logger.info("Categories: %s", ", ".join(categories or CATEGORIES.keys()))
    logger.info("Output: %s", args.output)
    logger.info("Headless: %s", args.headless)
    logger.info("")

    async with BrowserManager(headless=args.headless) as bm:
        # Phase 1: Discovery
        logger.info("[Phase 1] Discovering product pages...")
        products = await discover_all(bm, categories)
        logger.info("Discovered %d products", len(products))

        if not products:
            logger.warning("No products found. Try running with --no-headless for debugging.")
            return

        for p in products:
            logger.info("  - [%s] %s (%s)", p.category, p.name, p.page_id or p.page_url)

        if args.discover_only:
            logger.info("Discovery-only mode; stopping here.")
            return

        # Phase 2: Extraction
        logger.info("")
        logger.info("[Phase 2] Extracting product details...")
        extracted = await extract_many(bm, products)
        logger.info("Extracted data for %d / %d products", len(extracted), len(products))

        if not extracted:
            logger.warning("No product data extracted.")
            return

    # Phase 3: Write markdown (browser no longer needed)
    logger.info("")
    logger.info("[Phase 3] Writing markdown files...")
    written = write_many(extracted, args.output)
    logger.info("")
    logger.info("=" * 60)
    logger.info("Done! Wrote %d files to %s", len(written), args.output)
    for p in written:
        logger.info("  %s", p)
    logger.info("=" * 60)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger("scraper")
    root.setLevel(level)
    root.addHandler(handler)


def main() -> None:
    """Entry point called by ``pyproject.toml [project.scripts]``."""
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
