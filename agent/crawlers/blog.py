# agent/crawlers/blog.py
"""
Blog/News Crawler — uses Firecrawl API for public sites.
No browser automation needed for public pages.
Compatible with firecrawl-py v4+ (scrape/crawl, not scrape_url/crawl_url).
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
            self.client.scrape("https://example.com")
        except Exception as e:
            if "unauthorized" in str(e).lower() or "401" in str(e):
                raise FirecrawlAuthError(
                    f"Firecrawl API key is invalid. Set FIRECRAWL_API_KEY in .env. Error: {e}"
                )

    async def run(self, url: str, max_pages: int = 10):
        """Crawl a blog/news site. Returns list of article dicts."""
        try:
            response = self.client.crawl(
                url,
                params={"limit": max_pages, "scrapeOptions": {"formats": ["markdown"]}},
            )
        except Exception as e:
            err = str(e)
            if "402" in err or "Payment Required" in err or "Insufficient credits" in err:
                logger.warning("BlogCrawler: Firecrawl credits exhausted — skipping crawl")
                return []
            raise FirecrawlFetchError(f"Failed to crawl {url}: {e}") from e

        articles = []
        # v4 response: response.data is a list of ScrapeResponse objects
        data = response.data if hasattr(response, "data") else response.get("data", [])
        for item in data:
            if hasattr(item, "markdown"):
                # v4 object-style response
                metadata = item.metadata or {}
                articles.append({
                    "title": getattr(metadata, "title", None) or metadata.get("title", "Untitled"),
                    "body": item.markdown or "",
                    "source_url": getattr(metadata, "source_url", None) or metadata.get("sourceURL", url),
                    "source": "blog",
                })
            else:
                # dict-style fallback
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
            result = self.client.scrape(url)
        except Exception as e:
            raise FirecrawlFetchError(f"Failed to scrape {url}: {e}") from e

        if hasattr(result, "markdown"):
            metadata = result.metadata or {}
            return {
                "title": getattr(metadata, "title", None) or metadata.get("title", "Untitled"),
                "body": result.markdown or "",
                "source_url": url,
                "source": "blog",
            }
        return {
            "title": result.get("metadata", {}).get("title", "Untitled"),
            "body": result.get("markdown", ""),
            "source_url": url,
            "source": "blog",
        }
