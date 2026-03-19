"""
KnowledgeGraph — extracts named entities from synthesis output and manages
the cross-run entity store. Makes the system smarter with each successive run.

Entity types extracted:
  company     — named companies, competitors, partners
  person      — executives, key personnel (name + role)
  product     — products, platforms, services
  metric      — financial or market metrics with values
  trend       — market trends and themes
  risk        — identified risks and threats
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List

import anthropic

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """You are extracting structured entities from a competitive intelligence synthesis.

Research target: {target}

Synthesis content:
{synthesis_summary}

Extract all named entities and return ONLY a JSON array. Each entity must have:
  - entity_type: one of "company", "person", "product", "metric", "trend", "risk"
  - name: the entity name (concise)
  - description: 1 sentence describing this entity in context
  - value: for metrics/trends, the specific value or stat (e.g. "14% CAGR", "$2.1B revenue"); null for others
  - confidence: "high" | "medium" | "low"

Extract 10-30 entities. Focus on factual, specific entities — not vague concepts.

Return ONLY the JSON array, no other text:
[
  {{"entity_type": "company", "name": "Roche", "description": "Swiss pharma; target of analysis", "value": null, "confidence": "high"}},
  {{"entity_type": "metric", "name": "IT spend as % revenue", "description": "Roche IT budget relative to revenue", "value": "~3.5%", "confidence": "medium"}},
  ...
]"""

_PRIOR_KNOWLEDGE_INTRO = """## Prior Knowledge (from previous research runs on this topic)

The following entities and facts were established in prior research. Use this as background
context — do not contradict it without strong evidence from the current data:

{entities_text}

---
"""


class KnowledgeGraph:
    """Extracts entities from synthesis and injects prior knowledge into new research."""

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    async def extract_entities(self, target: str, synthesis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract named entities from synthesis output using Claude Haiku (cheap + fast).

        Args:
            target:    The research target slug (e.g. "roche", "novartis-it")
            synthesis: SynthesisAgent output dict

        Returns:
            List of entity dicts ready for Store.save_entities()
        """
        summary = self._synthesis_to_text(synthesis)
        if not summary.strip():
            return []

        prompt = _EXTRACT_PROMPT.format(target=target, synthesis_summary=summary[:6000])

        try:
            response = await asyncio.to_thread(
                self._client.messages.create,
                model="claude-haiku-4-5-20251001",  # cheap, fast — entity extraction is mechanical
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Strip markdown fences
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

            import re
            json_match = re.search(r"\[[\s\S]*\]", text)
            if json_match:
                entities = json.loads(json_match.group())
                logger.info("KnowledgeGraph: extracted %d entities for target '%s'", len(entities), target)
                return entities
        except Exception as e:
            logger.warning("KnowledgeGraph: entity extraction failed: %s", e)

        return []

    def build_prior_knowledge_context(self, entities: List[Dict[str, Any]]) -> str:
        """
        Format prior entities as a context block for injection into SynthesisAgent.

        Returns empty string if no entities.
        """
        if not entities:
            return ""

        lines = []
        by_type: Dict[str, List] = {}
        for e in entities:
            by_type.setdefault(e.get("entity_type", "general"), []).append(e)

        type_order = ["company", "person", "product", "metric", "trend", "risk", "general"]
        for etype in type_order:
            if etype not in by_type:
                continue
            lines.append(f"\n### {etype.title()}s")
            for e in by_type[etype][:10]:
                val_str = f" [{e['value']}]" if e.get("value") else ""
                lines.append(f"- **{e['name']}**{val_str}: {e.get('description', '')}")

        entities_text = "\n".join(lines)
        return _PRIOR_KNOWLEDGE_INTRO.format(entities_text=entities_text)

    @staticmethod
    def _synthesis_to_text(synthesis: Dict[str, Any]) -> str:
        """Flatten synthesis to plain text for entity extraction."""
        parts = []
        if synthesis.get("executive_summary"):
            parts.append(synthesis["executive_summary"])

        ml = synthesis.get("market_landscape") or {}
        if ml.get("size_and_growth"):
            parts.append(ml["size_and_growth"])
        for p in (ml.get("key_players") or [])[:8]:
            parts.append(f"{p.get('name')}: {p.get('position')} — {p.get('signal')}")
        for t in (ml.get("trends") or [])[:5]:
            parts.append(t)

        ca = synthesis.get("competitive_analysis") or {}
        for r in (ca.get("comparison_table") or [])[:6]:
            parts.append(f"{r.get('dimension')}: {r.get('findings')}")
        for w in (ca.get("winner_signals") or [])[:3]:
            parts.append(w)

        recs = synthesis.get("recommendations") or []
        for r in recs[:5]:
            parts.append(r)

        return "\n".join(parts)
