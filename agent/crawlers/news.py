# agent/crawlers/news.py
"""
News crawler — NewsAPI (free tier, 100 req/day) with GDELT fallback (free, no key).
Fetches recent news for signal detection and market intelligence.
NewsAPI key: https://newsapi.org/register
GDELT: https://api.gdeltproject.org/api/v2/doc/doc
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_NEWSAPI_BASE = "https://newsapi.org/v2"
_GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT = 15.0
_MAX_RESULTS = 10


class NewsCrawler:
    """Fetches recent news via NewsAPI (free key) with GDELT as keyless fallback."""

    def __init__(self) -> None:
        self._news_key = os.getenv("NEWS_API_KEY", "")
        if not self._news_key:
            logger.info("NewsCrawler: NEWS_API_KEY not set — will use GDELT fallback")

    async def run(
        self,
        company_name: str,
        companies: Optional[List[str]] = None,
        max_results: int = _MAX_RESULTS,
        days_back: int = 90,
    ) -> List[Dict[str, Any]]:
        targets = companies if companies else [company_name]
        results = []
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for name in targets[:3]:
                try:
                    if self._news_key:
                        items = await self._newsapi(client, name, max_results, days_back)
                    else:
                        items = await self._gdelt(client, name, max_results)
                    results.extend(items)
                except Exception as e:
                    logger.warning("NewsCrawler: failed for '%s': %s", name, e)
        return results

    async def _newsapi(
        self,
        client: httpx.AsyncClient,
        query: str,
        max_results: int,
        days_back: int,
    ) -> List[Dict[str, Any]]:
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        resp = await client.get(
            f"{_NEWSAPI_BASE}/everything",
            params={
                "q": f'"{query}"',
                "apiKey": self._news_key,
                "pageSize": min(max_results, 20),
                "sortBy": "publishedAt",
                "from": from_date,
                "language": "en",
            },
        )
        if resp.status_code == 426:
            logger.warning("NewsCrawler: NewsAPI requires upgrade — falling back to GDELT")
            return await self._gdelt(client, query, max_results)
        if resp.status_code != 200:
            logger.warning("NewsCrawler: NewsAPI HTTP %d — falling back to GDELT", resp.status_code)
            return await self._gdelt(client, query, max_results)

        data = resp.json()
        articles = data.get("articles") or []
        return self._articles_to_items(articles[:max_results], query)

    async def _gdelt(
        self, client: httpx.AsyncClient, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        """GDELT API — no key required, free forever."""
        resp = await client.get(
            _GDELT_BASE,
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": min(max_results, 25),
                "format": "json",
                "sort": "DateDesc",
                "timespan": "90d",
            },
        )
        if resp.status_code != 200:
            logger.warning("NewsCrawler: GDELT HTTP %d for '%s'", resp.status_code, query)
            return []

        data = resp.json()
        articles = data.get("articles") or []
        items = []
        for a in articles[:max_results]:
            title = a.get("title") or "Untitled"
            url = a.get("url") or ""
            seendate = a.get("seendate") or ""
            domain = a.get("domain") or ""
            body_parts = [
                f"Headline: {title}",
                f"Source: {domain}",
                f"Date: {seendate[:8] if len(seendate) >= 8 else seendate}",
                f"URL: {url}",
                f"Query: {query}",
            ]
            items.append({
                "title": f"News: {title}",
                "body": "\n".join(body_parts),
                "source_url": url,
                "source": "news",
                "company": query,
            })
        return items

    def _articles_to_items(
        self, articles: list, query: str
    ) -> List[Dict[str, Any]]:
        items = []
        for a in articles:
            title = a.get("title") or "Untitled"
            description = a.get("description") or ""
            content = a.get("content") or ""
            url = a.get("url") or ""
            published = a.get("publishedAt") or ""
            source_name = (a.get("source") or {}).get("name", "Unknown")
            body_parts = [
                f"Headline: {title}",
                f"Source: {source_name}",
                f"Published: {published[:10] if len(published) >= 10 else published}",
                f"Summary: {description}",
                f"Content: {content[:400]}",
            ]
            items.append({
                "title": f"News: {title}",
                "body": "\n".join(body_parts),
                "source_url": url,
                "source": "news",
                "company": query,
            })
        return items
