"""Configuration for financial institution (obank.kbstar.com) scraper.

Source: public banking website
"""

from pathlib import Path

# Base URL for online banking
BASE_URL = "https://obank.kbstar.com/quics"

# The site uses ?page=C###### pattern for navigation.
# C016613 is the deposit/savings product listing page with tabs.
# Verified page IDs from actual site navigation (2026-03-23)
CATEGORIES = {
    "예금": {"page_id": "C016613", "tab_index": 0, "tab_text": "예금"},
    "적금": {"page_id": "C016613", "tab_index": 1, "tab_text": "적금"},
    "입출금자유": {"page_id": "C016613", "tab_index": 2, "tab_text": "입출금자유"},
    "주택청약": {"page_id": "C016613", "tab_index": 3, "tab_text": "주택청약"},
    "신용대출": {"page_id": "C103429", "tab_index": 0, "tab_text": "신용대출"},
    "담보대출": {"page_id": "C103429", "tab_index": 1, "tab_text": "담보대출"},
    "전월세대출": {"page_id": "C103429", "tab_index": 2, "tab_text": "전월세/반환보증"},
    "자동차대출": {"page_id": "C103429", "tab_index": 3, "tab_text": "자동차대출"},
    "펀드": {"page_id": "C016529", "tab_index": None, "tab_text": None},
    "신탁": {"page_id": "C016531", "tab_index": None, "tab_text": None},
    "ISA": {"page_id": "C040686", "tab_index": None, "tab_text": None},
    "외화예금": {"page_id": "C101324", "tab_index": None, "tab_text": None},
}

# Convenience alias: "대출" maps to all loan sub-categories
LOAN_CATEGORIES = ["신용대출", "담보대출", "전월세대출", "자동차대출"]

# Directory paths (relative to project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "products"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Polite scraping delays (seconds)
REQUEST_DELAY_MIN = 2
REQUEST_DELAY_MAX = 5

# Browser settings
HEADLESS = True
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900
NAVIGATION_TIMEOUT_MS = 30_000
CONTENT_WAIT_TIMEOUT_MS = 15_000

# User agents to rotate through
USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.1 Safari/605.1.15"
    ),
]

# Category to output subdirectory mapping
CATEGORY_DIR_MAP = {
    "정기예금": "예금",
    "적금": "적금",
    "입출금통장": "예금",
    "청약": "적금",
    "신용대출": "대출",
    "담보대출": "대출",
    "전월세대출": "대출",
    "자동차대출": "대출",
    "펀드": "펀드",
    "신탁": "신탁",
    "ISA": "ISA",
    "외화예금": "외화예금",
    # Legacy names for backwards compatibility
    "예금": "예금",
    "입출금자유": "예금",
    "주택청약": "적금",
}
