"""Async Playwright browser manager for KB Star Bank scraper."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path
from types import TracebackType

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from scraper.config import (
    CONTENT_WAIT_TIMEOUT_MS,
    HEADLESS,
    NAVIGATION_TIMEOUT_MS,
    RAW_DIR,
    REQUEST_DELAY_MIN,
    REQUEST_DELAY_MAX,
    USER_AGENTS,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)

logger = logging.getLogger(__name__)


class BrowserManager:
    """Async context manager wrapping a headless Chromium browser.

    Usage::

        async with BrowserManager(headless=True) as bm:
            page = await bm.new_page()
            await bm.goto(page, "https://example.com")
    """

    def __init__(self, headless: bool = HEADLESS) -> None:
        self._headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._ua_index = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "BrowserManager":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
        )
        self._context = await self._browser.new_context(
            locale="ko-KR",
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            user_agent=self._pick_user_agent(),
            accept_downloads=False,
        )
        self._context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
        self._context.set_default_timeout(CONTENT_WAIT_TIMEOUT_MS)
        logger.info("Browser launched (headless=%s)", self._headless)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def new_page(self) -> Page:
        """Create a new page in the current browser context."""
        if self._context is None:
            raise RuntimeError("BrowserManager not started; use 'async with'")
        page = await self._context.new_page()
        return page

    async def goto(self, page: Page, url: str, *, wait_until: str = "domcontentloaded") -> None:
        """Navigate to *url* with a polite random delay beforehand."""
        await self.random_delay()
        logger.debug("Navigating to %s", url)
        try:
            await page.goto(url, wait_until=wait_until)
        except Exception:
            logger.warning("Navigation to %s failed, retrying once...", url)
            await asyncio.sleep(3)
            await page.goto(url, wait_until=wait_until)

    async def wait_for_content(self, page: Page, selector: str, *, timeout: int | None = None) -> None:
        """Wait for a CSS selector to appear on the page."""
        timeout = timeout or CONTENT_WAIT_TIMEOUT_MS
        try:
            await page.wait_for_selector(selector, timeout=timeout)
        except Exception:
            logger.warning("Selector '%s' not found within %dms", selector, timeout)

    async def random_delay(self) -> None:
        """Sleep for a random interval to be polite."""
        delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        logger.debug("Sleeping %.1fs", delay)
        await asyncio.sleep(delay)

    async def save_debug_snapshot(self, page: Page, label: str) -> None:
        """Save a screenshot and HTML dump for debugging.

        Files are written to ``data/raw/{label}_{timestamp}.*``.
        """
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{label}_{ts}"

        screenshot_path = RAW_DIR / f"{stem}.png"
        html_path = RAW_DIR / f"{stem}.html"

        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
            logger.info("Screenshot saved: %s", screenshot_path)
        except Exception as exc:
            logger.warning("Screenshot failed: %s", exc)

        try:
            content = await page.content()
            html_path.write_text(content, encoding="utf-8")
            logger.info("HTML saved: %s", html_path)
        except Exception as exc:
            logger.warning("HTML save failed: %s", exc)

    def rotate_user_agent(self) -> None:
        """Advance to the next user agent (applied on next context)."""
        self._ua_index = (self._ua_index + 1) % len(USER_AGENTS)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _pick_user_agent(self) -> str:
        ua = USER_AGENTS[self._ua_index % len(USER_AGENTS)]
        self._ua_index += 1
        return ua
