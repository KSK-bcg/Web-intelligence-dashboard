# agent/crawlers/clinical_trials.py
"""
ClinicalTrials.gov crawler — free public API v2, no key required.
Fetches clinical trial registrations for healthcare/biotech intelligence.
API: https://clinicaltrials.gov/api/v2/
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://clinicaltrials.gov/api/v2"
_TIMEOUT = 15.0
_MAX_RESULTS = 15


class ClinicalTrialsCrawler:
    """Fetches clinical trial data from ClinicalTrials.gov (free, no key needed)."""

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
                    logger.warning("ClinicalTrialsCrawler: failed for '%s': %s", name, e)
        return results

    async def _search(
        self, client: httpx.AsyncClient, query: str, max_results: int
    ) -> List[Dict[str, Any]]:
        resp = await client.get(
            f"{_BASE}/studies",
            params={
                "query.term": query,
                "query.spons": query,  # sponsor search
                "pageSize": min(max_results, 25),
                "format": "json",
                "fields": (
                    "NCTId,BriefTitle,OverallStatus,Phase,StudyType,"
                    "StartDate,PrimaryCompletionDate,EnrollmentCount,"
                    "LeadSponsorName,Condition,InterventionName,"
                    "BriefSummary"
                ),
            },
        )
        if resp.status_code != 200:
            logger.warning("ClinicalTrialsCrawler: HTTP %d for '%s'", resp.status_code, query)
            return []

        data = resp.json()
        studies = data.get("studies") or []
        items = []
        for study in studies[:max_results]:
            ps = study.get("protocolSection") or {}
            id_mod = ps.get("identificationModule") or {}
            status_mod = ps.get("statusModule") or {}
            design_mod = ps.get("designModule") or {}
            desc_mod = ps.get("descriptionModule") or {}
            sponsor_mod = ps.get("sponsorCollaboratorsModule") or {}
            conditions_mod = ps.get("conditionsModule") or {}
            arms_mod = ps.get("armsInterventionsModule") or {}

            nct_id = id_mod.get("nctId", "")
            title = id_mod.get("briefTitle", "Untitled Trial")
            status = status_mod.get("overallStatus", "Unknown")
            phase = (design_mod.get("phases") or ["Unknown"])[0] if design_mod.get("phases") else "Unknown"
            sponsor = (sponsor_mod.get("leadSponsor") or {}).get("name", query)
            conditions = (conditions_mod.get("conditions") or [])[:3]
            interventions = [
                i.get("name", "") for i in (arms_mod.get("interventions") or [])[:3]
            ]
            enrollment = (design_mod.get("enrollmentInfo") or {}).get("count", "Unknown")
            start_date = (status_mod.get("startDateStruct") or {}).get("date", "Unknown")
            summary = (desc_mod.get("briefSummary") or "")[:300]

            body_parts = [
                f"Trial ID: {nct_id}",
                f"Title: {title}",
                f"Status: {status}",
                f"Phase: {phase}",
                f"Sponsor: {sponsor}",
                f"Conditions: {', '.join(conditions) or 'N/A'}",
                f"Interventions: {', '.join(filter(None, interventions)) or 'N/A'}",
                f"Enrollment: {enrollment}",
                f"Start Date: {start_date}",
                f"Summary: {summary}",
            ]
            items.append({
                "title": f"Clinical Trial: {title}",
                "body": "\n".join(body_parts),
                "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
                "source": "clinical_trials",
                "company": sponsor,
            })
        return items
