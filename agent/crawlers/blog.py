# agent/crawlers/blog.py
"""
Blog/News Crawler — uses Firecrawl API for public sites.
No browser automation needed for public pages.
"""
import logging
import os

import firecrawl

from agent.base_agent import BaseAgent
from agent.exceptions import FirecrawlAuthError, FirecrawlFetchError

logger = logging.getLogger(__name__)


class BlogCrawler(BaseAgent):
    """
    Crawls blogs and news sites via Firecrawl API.
    Fail-fast: verifies auth on init before any crawl begins.
    """

    def __init__(self, api_key=None):
        super().__init__(name="blog-crawler")
        key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            raise FirecrawlAuthError("FIRECRAWL_API_KEY not set in .env")
        self.client = firecrawl.FirecrawlApp(api_key=key)
        self.verify_auth()

    def verify_auth(self) -> None:
        """Fail-fast: test Firecrawl auth before any crawl begins."""
        try:
            self.client.scrape_url("https://example.com")
        except Exception as e:
            if "unauthorized" in str(e).lower() or "401" in str(e):
                raise FirecrawlAuthError(
                    f"Firecrawl API key is invalid. Set FIRECRAWL_API_KEY in .env. Error: {e}"
                )

    async def run(self, url: str, max_pages: int = 10):
        """Crawl a blog/news site. Returns list of article dicts."""
        try:
            response = self.client.crawl_url(
                url,
                params={"limit": max_pages, "scrapeOptions": {"formats": ["markdown"]}},
            )
        except Exception as e:
            raise FirecrawlFetchError(f"Failed to crawl {url}: {e}") from e

        articles = []
        for item in response.get("data", []):
            articles.append({
                "title": item.get("metadata", {}).get("title", "Untitled"),
                "body": item.get("markdown", ""),
                "source_url": item.get("metadata", {}).get("sourceURL", url),
                "source": "blog",
            })
        return articles

    async def _scrape_url(self, url: str):
        """Scrape a single URL. Returns article dict."""
        try:
            result = self.client.scrape_url(url, params={"formats": ["markdown"]})
        except Exception as e:
            raise FirecrawlFetchError(f"Failed to scrape {url}: {e}") from e

        return {
            "title": result.get("metadata", {}).get("title", "Untitled"),
            "body": result.get("markdown", ""),
            "source_url": url,
            "source": "blog",
        }
