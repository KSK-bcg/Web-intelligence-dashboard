# agent/crawlers/crunchbase.py
"""
Crunchbase Basic API crawler — free tier (requires CRUNCHBASE_API_KEY).
Fetches funding rounds, investors, company overview for startup intelligence.
Free key: https://www.crunchbase.com/account/api
"""
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.crunchbase.com/api/v4"
_TIMEOUT = 15.0


class CrunchbaseCrawler:
    """Fetches startup funding + investor data from Crunchbase Basic API."""

    def __init__(self) -> None:
        self._key = os.getenv("CRUNCHBASE_API_KEY", "")
        if not self._key:
            logger.warning("CrunchbaseCrawler: CRUNCHBASE_API_KEY not set — skipping")

    async def run(
        self,
        company_name: str,
        companies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search Crunchbase for each company and return structured intel."""
        if not self._key:
            return []

        targets = companies if companies else [company_name]
        results = []
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for name in targets[:5]:  # cap to 5 to conserve free quota
                try:
                    items = await self._fetch_company(client, name)
                    results.extend(items)
                except Exception as e:
                    logger.warning("CrunchbaseCrawler: failed for '%s': %s", name, e)
        return results

    async def _fetch_company(
        self, client: httpx.AsyncClient, name: str
    ) -> List[Dict[str, Any]]:
        # Search for company by name
        search_url = f"{_BASE}/searches/organizations"
        payload = {
            "field_ids": [
                "identifier", "short_description", "funding_total",
                "num_funding_rounds", "last_funding_at", "last_funding_type",
                "investor_identifiers", "num_employees_enum", "founded_on",
                "categories", "website_url", "location_identifiers",
            ],
            "query": [
                {
                    "type": "predicate",
                    "field_id": "facet_ids",
                    "operator_id": "includes",
                    "values": ["company"],
                }
            ],
            "predicate": {
                "type": "predicate",
                "field_id": "name",
                "operator_id": "contains",
                "values": [name],
            },
            "limit": 3,
        }
        resp = await client.post(
            search_url,
            json=payload,
            params={"user_key": self._key},
        )
        if resp.status_code == 429:
            logger.warning("CrunchbaseCrawler: rate limited")
            return []
        if resp.status_code != 200:
            logger.warning("CrunchbaseCrawler: HTTP %d for '%s'", resp.status_code, name)
            return []

        data = resp.json()
        entities = data.get("entities") or []
        items = []
        for entity in entities[:2]:
            props = entity.get("properties") or {}
            company_id = (props.get("identifier") or {}).get("value", "")
            funding_total = props.get("funding_total") or {}
            investors = [
                (inv.get("identifier") or {}).get("value", "")
                for inv in (props.get("investor_identifiers") or [])[:10]
            ]
            categories = [
                (cat.get("identifier") or {}).get("value", "")
                for cat in (props.get("categories") or [])[:5]
            ]
            body_parts = [
                f"Company: {company_id or name}",
                f"Description: {props.get('short_description', 'N/A')}",
                f"Total Funding: {funding_total.get('value_usd', 'Unknown')} USD" if funding_total else "Total Funding: Unknown",
                f"Funding Rounds: {props.get('num_funding_rounds', 'Unknown')}",
                f"Last Funding: {props.get('last_funding_at', 'Unknown')} ({props.get('last_funding_type', '')})",
                f"Headcount: {props.get('num_employees_enum', 'Unknown')}",
                f"Founded: {(props.get('founded_on') or {}).get('value', 'Unknown')}",
                f"Investors: {', '.join(investors) if investors else 'Unknown'}",
                f"Categories: {', '.join(categories) if categories else 'Unknown'}",
                f"Website: {props.get('website_url', 'Unknown')}",
            ]
            items.append({
                "title": f"Crunchbase: {company_id or name}",
                "body": "\n".join(body_parts),
                "source_url": f"https://www.crunchbase.com/organization/{company_id}",
                "source": "crunchbase",
                "company": name,
            })
        return items
