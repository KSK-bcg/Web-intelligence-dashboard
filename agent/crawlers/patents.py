# agent/crawlers/patents.py
"""
USPTO PatentsView crawler — free public API, no key required.
Fetches patent filings for IP intelligence.
API: https://search.patentsview.org/api/v1/
"""
import logging
import json
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://search.patentsview.org/api/v1"
_TIMEOUT = 15.0
_MAX_RESULTS = 10


class PatentsCrawler:
    """Fetches patent filings from USPTO PatentsView (free, no key needed)."""

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
                    items = await self._search_patents(client, name, max_results)
                    results.extend(items)
                except Exception as e:
                    logger.warning("PatentsCrawler: failed for '%s': %s", name, e)
        return results

    async def _search_patents(
        self, client: httpx.AsyncClient, company: str, max_results: int
    ) -> List[Dict[str, Any]]:
        # Search by assignee organization name
        query = {
            "_text_any": {
                "assignee_organization": company,
            }
        }
        params = {
            "q": json.dumps(query),
            "f": json.dumps([
                "patent_id", "patent_title", "patent_abstract",
                "patent_date", "patent_type", "assignees",
                "inventors", "cpcs",
            ]),
            "s": json.dumps([{"patent_date": "desc"}]),
            "o": json.dumps({"per_page": min(max_results, 25)}),
        }
        resp = await client.get(f"{_BASE}/patent/", params=params)

        if resp.status_code != 200:
            logger.warning("PatentsCrawler: HTTP %d for '%s'", resp.status_code, company)
            return []

        data = resp.json()
        patents = data.get("patents") or []
        items = []
        for p in patents[:max_results]:
            assignees = [
                a.get("assignee_organization", "")
                for a in (p.get("assignees") or [])
            ]
            cpcs = list({
                c.get("cpc_subgroup_id", "")
                for c in (p.get("cpcs") or [])
            })[:5]
            body_parts = [
                f"Patent: {p.get('patent_title', 'Untitled')}",
                f"Patent ID: {p.get('patent_id', 'Unknown')}",
                f"Date: {p.get('patent_date', 'Unknown')}",
                f"Type: {p.get('patent_type', 'Unknown')}",
                f"Assignees: {', '.join(filter(None, assignees)) or company}",
                f"CPC Categories: {', '.join(filter(None, cpcs)) or 'N/A'}",
                f"Abstract: {(p.get('patent_abstract') or '')[:400]}",
            ]
            items.append({
                "title": f"Patent: {p.get('patent_title', 'Untitled')}",
                "body": "\n".join(body_parts),
                "source_url": f"https://patents.google.com/patent/US{p.get('patent_id', '')}",
                "source": "patents",
                "company": company,
            })
        return items
