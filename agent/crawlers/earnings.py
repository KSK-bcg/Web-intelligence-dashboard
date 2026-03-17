import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from firecrawl import FirecrawlApp

from agent.exceptions import EarningsFetchError

load_dotenv()

logger = logging.getLogger(__name__)

DELAY_SECONDS = 1.5
MAX_RESULTS = 15

_EARNINGS_KEYWORDS = ["earnings call", "earnings transcript", "quarterly results"]
_ANALYST_KEYWORDS = ["analyst report", "equity research", "price target", "initiates coverage"]


def _classify_source_type(title: str, url: str) -> str:
    """Classify a result as earnings_transcript, analyst_report, or news."""
    combined = (title + " " + url).lower()
    for kw in _EARNINGS_KEYWORDS:
        if kw in combined:
            return "earnings_transcript"
    for kw in _ANALYST_KEYWORDS:
        if kw in combined:
            return "analyst_report"
    return "news"


class EarningsCrawler:
    """Crawls earnings transcripts, analyst reports, and news via Firecrawl search."""

    def __init__(self) -> None:
        api_key = os.getenv("FIRECRAWL_API_KEY", "")
        if not api_key:
            raise EarningsFetchError("FIRECRAWL_API_KEY not set")
        self._app = FirecrawlApp(api_key=api_key)

    async def run(
        self,
        query: str,
        companies: Optional[List[str]] = None,
        max_results: int = MAX_RESULTS,
    ) -> List[Dict[str, Any]]:
        """
        Search for earnings/analyst content matching `query`.

        Returns list of dicts with keys:
            title, body, source_url, source_type, company, date, source="earnings"
        """
        results: List[Dict[str, Any]] = []
        try:
            search_results = self._app.search(query, limit=max_results)
        except Exception as e:
            raise EarningsFetchError(f"Firecrawl search failed: {e}") from e

        company_name = companies[0] if companies else ""

        for item in search_results[:max_results]:
            if len(results) >= max_results:
                break
            url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
            title = getattr(item, "title", None) or (item.get("title") if isinstance(item, dict) else "")
            if not url:
                continue

            # Try to get body from search result first, fall back to scrape
            body = getattr(item, "markdown", None) or (item.get("markdown") if isinstance(item, dict) else None)
            if not body:
                try:
                    scrape = self._app.scrape(url, formats=["markdown"])
                    body = getattr(scrape, "markdown", None)
                    if isinstance(scrape, dict):
                        body = scrape.get("markdown", "")
                    await asyncio.sleep(DELAY_SECONDS)
                except Exception as e:
                    logger.warning("Failed to scrape %s: %s", url, e)
                    body = ""

            source_type = _classify_source_type(title or "", url)

            # Extract company from query/companies or leave as query target
            inferred_company = company_name or _infer_company(title or "", url)

            results.append({
                "title": title or "",
                "body": (body or "")[:30000],
                "source_url": url,
                "source_type": source_type,
                "company": inferred_company,
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "source": "earnings",
            })
            await asyncio.sleep(DELAY_SECONDS)

        return results


def _infer_company(title: str, url: str) -> str:
    """Best-effort company name extraction from title/URL."""
    # Try to extract from URL domain
    import re
    m = re.search(r"https?://(?:www\.)?([^./]+)\.", url)
    if m:
        domain = m.group(1)
        if domain not in ("seekingalpha", "fool", "reuters", "bloomberg", "cnbc", "wsj"):
            return domain.replace("-", " ").title()
    return title.split()[0] if title else "Unknown"
