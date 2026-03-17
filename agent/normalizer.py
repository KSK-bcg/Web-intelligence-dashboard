# agent/normalizer.py
"""
Normalizes raw crawl output into canonical Person/Article records.

Responsibilities:
- Deduplication (by linkedin_id, then by name similarity)
- Confidence scoring (high/medium/low per record)
- Department inference from title
- Source provenance tagging
"""
import logging
from difflib import SequenceMatcher
from typing import List, Optional

logger = logging.getLogger(__name__)

DEPARTMENT_KEYWORDS = {
    "Cloud": ["cloud", "azure", "aws", "gcp"],
    "Security": ["security", "ciso", "cyber", "infosec"],
    "Infrastructure": ["infrastructure", "platform", "network", "ops"],
    "Data": ["data", "analytics", "bi", "machine learning", "ai"],
    "Applications": ["application", "software", "development", "engineering"],
    "IT Leadership": ["cio", "cto", "vp of it", "head of it", "director of it"],
}


class Normalizer:
    def normalize(self, raw_records: List[dict]) -> List[dict]:
        """
        Deduplicate and enrich raw person records.
        Returns list of canonical person dicts.
        """
        if not raw_records:
            return []

        deduped = self._deduplicate(raw_records)
        enriched = [self._enrich(r) for r in deduped]
        return enriched

    def _deduplicate(self, records: List[dict]) -> List[dict]:
        seen_ids = {}
        seen_names = []

        for record in records:
            lid = record.get("linkedin_id")
            if lid:
                if lid not in seen_ids:
                    seen_ids[lid] = record
                continue
            # No linkedin_id: compare by name similarity
            duplicate = False
            for existing in seen_names:
                if self._name_similarity(record.get("name", ""), existing.get("name", "")) > 0.85:
                    duplicate = True
                    break
            if not duplicate:
                seen_names.append(record)

        return list(seen_ids.values()) + seen_names

    def _enrich(self, record: dict) -> dict:
        enriched = dict(record)
        enriched["confidence"] = self._score_confidence(record)
        if not enriched.get("department"):
            enriched["department"] = self._infer_department(record.get("title", ""))
        return enriched

    def _score_confidence(self, record: dict) -> str:
        if record.get("linkedin_id") and record.get("name") and record.get("title"):
            return "high"
        if record.get("name") and record.get("title") and record.get("source") != "inferred":
            return "medium"
        return "low"

    def _infer_department(self, title: str) -> str:
        title_lower = title.lower()
        for dept, keywords in DEPARTMENT_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                return dept
        return "IT"

    @staticmethod
    def _name_similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
