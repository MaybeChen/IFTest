from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from playwright.async_api import Browser, BrowserContext, CDPSession, Page, Playwright, async_playwright

from browser_ai_test.browser.cdp import ensure_loopback_no_proxy, fetch_cdp_version
from browser_ai_test.browser.stream_monitor import StreamMonitor
from browser_ai_test.config import BrowserConfig, StreamConfig

logger = logging.getLogger(__name__)


class SharedBrowserSession:
    """Connect Playwright and CDP to one externally managed Chrome."""

    def __init__(self, browser: BrowserConfig, stream: StreamConfig) -> None:
        self.config = browser
        self.stream_config = stream
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.cdp_session: CDPSession | None = None
        self.monitor = StreamMonitor(
            stream.url_keywords,
            stream.done_markers,
            aborted_sse_is_complete=stream.aborted_sse_is_complete,
        )

    async def start(self) -> "SharedBrowserSession":
        if self.config.bypass_proxy_for_loopback:
            ensure_loopback_no_proxy(self.config.cdp_url)
        await asyncio.to_thread(
            fetch_cdp_version, self.config.cdp_url, self.config.cdp_timeout_seconds
        )
        self.playwright = await async_playwright().start()
        try:
            self.browser = await self.playwright.chromium.connect_over_cdp(self.config.cdp_url)
            self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            self.cdp_session = await self.context.new_cdp_session(self.page)
            await self.monitor.attach(self.cdp_session)
            return self
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        if self.cdp_session:
            await self.cdp_session.detach()
            self.cdp_session = None
        if self.browser:
            await self.browser.close()  # disconnects Playwright; external Chrome remains alive
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    async def __aenter__(self) -> "SharedBrowserSession":
        return await self.start()

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.close()
