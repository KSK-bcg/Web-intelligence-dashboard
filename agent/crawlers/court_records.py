# agent/crawlers/court_records.py
"""
CourtListener crawler — free public API, no key required.
Fetches federal court dockets for litigation intelligence.
API: https://www.courtlistener.com/api/rest/v4/
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://www.courtlistener.com/api/rest/v4"
_TIMEOUT = 15.0
_MAX_RESULTS = 10


class CourtRecordsCrawler:
    """Fetches litigation records from CourtListener (free, no key needed)."""

    async def run(
        self,
        company_name: str,
        companies: Optional[List[str]] = None,
        max_results: int = _MAX_RESULTS,
    ) -> List[Dict[str, Any]]:
        targets = companies if companies else [company_name]
        results = []
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for name in targets[:3]:
                try:
                    items = await self._search(client, name, max_results)
                    results.extend(items)
                except Exception as e:
                    logger.warning("CourtRecordsCrawler: failed for '%s': %s", name, e)
        return results

    async def _search(
        self, client: httpx.AsyncClient, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        resp = await client.get(
            f"{_BASE}/dockets/",
            params={
                "q": query,
                "order_by": "score desc",
                "type": "r",  # RECAP (federal court) dockets
                "page_size": min(max_results, 20),
            },
        )
        if resp.status_code != 200:
            logger.warning("CourtRecordsCrawler: HTTP %d for '%s'", resp.status_code, query)
            return []

        data = resp.json()
        results_list = data.get("results") or []
        items = []
        for r in results_list[:max_results]:
            case_name = r.get("case_name") or "Unknown Case"
            court = r.get("court") or "Unknown Court"
            date_filed = r.get("date_filed") or "Unknown Date"
            nature_of_suit = r.get("nature_of_suit") or ""
            docket_number = r.get("docket_number") or ""
            absolute_url = r.get("absolute_url") or ""

            body_parts = [
                f"Case: {case_name}",
                f"Court: {court}",
                f"Date Filed: {date_filed}",
                f"Docket Number: {docket_number}",
                f"Nature of Suit: {nature_of_suit}",
                f"Query: {query}",
            ]
            items.append({
                "title": f"Court Record: {case_name}",
                "body": "\n".join(body_parts),
                "source_url": f"https://www.courtlistener.com{absolute_url}" if absolute_url else "https://www.courtlistener.com",
                "source": "court_records",
                "company": query,
            })
        return items
