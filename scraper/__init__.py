"""KB Star Bank financial products scraper."""

from scraper.browser import BrowserManager
from scraper.config import CATEGORIES, BASE_URL, OUTPUT_DIR
from scraper.discovery import discover_all, DiscoveredProduct
from scraper.extractor import extract_many, extract_product, ProductData
from scraper.markdown_writer import write_many, write_product_markdown
from scraper.run_scraper import main

__all__ = [
    "BrowserManager",
    "CATEGORIES",
    "BASE_URL",
    "OUTPUT_DIR",
    "discover_all",
    "DiscoveredProduct",
    "extract_many",
    "extract_product",
    "ProductData",
    "write_many",
    "write_product_markdown",
    "main",
]
