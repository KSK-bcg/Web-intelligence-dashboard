import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from firecrawl import FirecrawlApp

from agent.exceptions import FilingsFetchError, FilingsParseError

load_dotenv()

logger = logging.getLogger(__name__)

DELAY_SECONDS = 2.0
MAX_FILINGS = 5


class FilingsCrawler:
    """Crawls public financial filings from SEC EDGAR and company IR pages."""

    def __init__(self) -> None:
        api_key = os.getenv("FIRECRAWL_API_KEY", "")
        if not api_key:
            raise FilingsFetchError("FIRECRAWL_API_KEY not set")
        self._app = FirecrawlApp(api_key=api_key)

    async def run(
        self,
        companies: List[str],
        filing_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Crawl filings for a list of companies.

        Returns list of filing dicts with keys:
            company, filing_type, period, source_url, raw_text, source="filing"
        """
        if filing_types is None:
            filing_types = ["10-K", "annual-report"]

        results: List[Dict[str, Any]] = []
        for company in companies:
            try:
                filings = await self._crawl_company(company, filing_types)
                results.extend(filings)
            except FilingsFetchError as e:
                logger.warning("FilingsFetchError for %s: %s", company, e)
            except Exception as e:
                logger.warning("Unexpected error fetching filings for %s: %s", company, e)
        return results

    async def _crawl_company(
        self, company: str, filing_types: List[str]
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for filing_type in filing_types:
            if len(results) >= MAX_FILINGS:
                break
            try:
                items = await self._search_filings(company, filing_type)
                results.extend(items)
                await asyncio.sleep(DELAY_SECONDS)
            except FilingsFetchError:
                raise
            except Exception as e:
                logger.warning("Error searching %s filings for %s: %s", filing_type, company, e)

        return results[:MAX_FILINGS]

    async def _search_filings(
        self, company: str, filing_type: str
    ) -> List[Dict[str, Any]]:
        """Search for filings and scrape the top result."""
        query = f"{company} {filing_type} annual report investor relations"
        try:
            search_results = self._app.search(query, limit=3)
        except Exception as e:
            raise FilingsFetchError(f"Firecrawl search failed for {company}: {e}") from e

        items: List[Dict[str, Any]] = []
        for result in search_results[:2]:
            url = getattr(result, "url", None) or (result.get("url") if isinstance(result, dict) else None)
            if not url:
                continue
            try:
                item = await self._scrape_filing(url, company, filing_type)
                if item:
                    items.append(item)
                await asyncio.sleep(DELAY_SECONDS)
            except FilingsFetchError as e:
                logger.warning("FilingsFetchError scraping %s: %s", url, e)
            except Exception as e:
                logger.warning("Error scraping filing %s: %s", url, e)

        return items

    async def _scrape_filing(
        self, url: str, company: str, filing_type: str
    ) -> Optional[Dict[str, Any]]:
        """Scrape a filing URL and return a normalized dict."""
        try:
            scrape_result = self._app.scrape(url, formats=["markdown"])
        except Exception as e:
            raise FilingsFetchError(f"Firecrawl scrape failed for {url}: {e}") from e

        raw_text = getattr(scrape_result, "markdown", None)
        if isinstance(scrape_result, dict):
            raw_text = scrape_result.get("markdown", "")

        if not raw_text:
            logger.debug("No markdown content from %s", url)
            return None

        period = self._extract_period(raw_text)

        return {
            "company": company,
            "filing_type": filing_type,
            "period": period,
            "source_url": url,
            "raw_text": raw_text[:50000],  # cap at 50k chars
            "source": "filing",
        }

    def _extract_period(self, text: str) -> str:
        """Extract fiscal year period from filing text. Returns best guess."""
        patterns = [
            r"fiscal year (?:ended|ending)\s+(?:December|January|March|June|September)\s+\d+,?\s*(\d{4})",
            r"FY\s*(\d{4})",
            r"Annual Report\s+(\d{4})",
            r"for the year ended.*?(\d{4})",
        ]
        for pattern in patterns:
            m = re.search(pattern, text[:2000], re.IGNORECASE)
            if m:
                return f"FY{m.group(1)}"
        return "FY_unknown"
