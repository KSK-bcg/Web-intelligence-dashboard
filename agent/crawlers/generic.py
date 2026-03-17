# agent/crawlers/generic.py
"""
Generic Web Crawler — Firecrawl for public pages, Playwright fallback for auth-gated.
"""
from agent.crawlers.blog import BlogCrawler
from agent.base_agent import BaseAgent
from agent.exceptions import FirecrawlBlockedError, FirecrawlFetchError


class GenericWebCrawler(BaseAgent):
    """
    Tries Firecrawl first. Falls back to Playwright if blocked or auth required.
    """

    def __init__(self):
        super().__init__(name="generic-crawler")
        self._blog_crawler = BlogCrawler()

    async def run(self, url: str, max_pages: int = 10):
        try:
            return await self._blog_crawler.run(url=url, max_pages=max_pages)
        except (FirecrawlBlockedError, FirecrawlFetchError) as e:
            self.logger.warning("Firecrawl blocked/failed (%s) — falling back to Playwright", e)
            return await self._playwright_fallback(url)

    async def _playwright_fallback(self, url: str):
        """Minimal Playwright fallback for when Firecrawl is blocked."""
        from playwright.async_api import async_playwright
        results = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url)
            content = await page.content()
            title = await page.title()
            await browser.close()
        results.append({
            "title": title,
            "body": self.wrap_content(content, source=url),
            "source_url": url,
            "source": "generic-playwright-fallback",
        })
        return results
