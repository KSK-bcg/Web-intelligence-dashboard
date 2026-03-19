import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_CONTENT_BUDGET_PER_ITEM = 4000   # chars per source item
_CONTENT_BUDGET_TOTAL = 80000     # total chars for all raw content

_EMPTY_SYNTHESIS: Dict[str, Any] = {
    "executive_summary": "",
    "market_landscape": {
        "size_and_growth": "",
        "key_players": [],
        "trends": [],
    },
    "competitive_analysis": {
        "comparison_table": [],
        "winner_signals": [],
        "disruption_risks": [],
    },
    "strategic_implications": {
        "opportunities": [],
        "risks": [],
        "watch_list": [],
    },
    "recommendations": [],
    "outlook": "",
}

_PROMPT_TEMPLATE = """
You are a senior strategy consultant at a top-tier firm producing a competitive intelligence briefing.
{goal_context}

Below is research data collected from primary and secondary sources. Analyze it and produce a structured synthesis.

## Research Data

{untrusted_content}

## Financial Metrics (pre-extracted, trusted)

{financial_summary}

## Qual Analysis (pre-extracted, trusted)

{qual_summary}

## Instructions

Produce a comprehensive competitive intelligence synthesis. Return ONLY a JSON object with this exact structure:

{{
  "executive_summary": "<3-5 sentence board-level summary>",
  "market_landscape": {{
    "size_and_growth": "<market size and growth narrative>",
    "key_players": [
      {{"name": "<company>", "position": "<market position>", "signal": "<key signal>"}}
    ],
    "trends": ["<trend 1>", "<trend 2>"]
  }},
  "competitive_analysis": {{
    "comparison_table": [
      {{"dimension": "<dimension>", "findings": "<findings across players>"}}
    ],
    "winner_signals": ["<signal 1>"],
    "disruption_risks": ["<risk 1>"]
  }},
  "strategic_implications": {{
    "opportunities": ["<opportunity 1>"],
    "risks": ["<risk 1>"],
    "watch_list": ["<item 1>"]
  }},
  "recommendations": ["<recommendation 1>", "<recommendation 2>"],
  "outlook": "<12-month outlook statement>"
}}

Rules:
- Base all findings strictly on the research data provided
- Do NOT invent data not present in the research
- Return ONLY the JSON object, no other text
"""


class SynthesisAgent:
    """Produces cross-source competitive narrative from all collected data."""

    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — SynthesisAgent will return empty synthesis")
        self._client = Anthropic(api_key=api_key) if api_key else None

    async def run(
        self,
        raw_data: List[Dict[str, Any]],
        financial: Optional[List[Dict[str, Any]]] = None,
        qual: Optional[Dict[str, Any]] = None,
        goal: str = "",
        prior_knowledge: str = "",
    ) -> Dict[str, Any]:
        """
        Synthesize all collected data into a competitive narrative.

        Args:
            raw_data:         List of crawler items (filings + earnings + blog items)
            financial:        List of FinancialAgent results (trusted, already extracted)
            qual:             QualAgent result dict (trusted, already extracted)
            goal:             Optional research goal to tailor synthesis
            prior_knowledge:  Prior entity context from KnowledgeGraph (trusted)

        Returns:
            Synthesis dict matching _EMPTY_SYNTHESIS schema.
            Never raises — returns _EMPTY_SYNTHESIS on any error.
        """
        if self._client is None:
            return dict(_EMPTY_SYNTHESIS)

        try:
            return await self._synthesize(
                raw_data, financial or [], qual or {},
                goal_context=goal, prior_knowledge=prior_knowledge,
            )
        except Exception as e:
            logger.warning("SynthesisAgent error, returning empty synthesis: %s", e)
            return dict(_EMPTY_SYNTHESIS)

    async def _synthesize(
        self,
        raw_data: List[Dict[str, Any]],
        financial: List[Dict[str, Any]],
        qual: Dict[str, Any],
        goal_context: str = "",
        prior_knowledge: str = "",
    ) -> Dict[str, Any]:
        # Build goal context string for prompt
        goal_context_str = (
            f"\nResearch goal: {goal_context[:300]}\nTailor your synthesis specifically to this goal."
            if goal_context
            else ""
        )

        # Build untrusted content block — wrap all raw text in safety tags
        # Apply per-item budget cap (_CONTENT_BUDGET_PER_ITEM chars each)
        untrusted_parts: List[str] = []
        for item in raw_data:
            raw_text = item.get("raw_text") or item.get("body") or ""
            if raw_text:
                title = item.get("title") or item.get("company") or item.get("source_url", "")
                untrusted_parts.append(
                    f"<content source='untrusted' title='{title}'>\n{raw_text[:_CONTENT_BUDGET_PER_ITEM]}\n</content>"
                )

        # Apply total content budget — truncate list if total chars exceed budget
        total = len(untrusted_parts)
        if total > 0:
            kept = 0
            running_total = 0
            trimmed_parts: List[str] = []
            for part in untrusted_parts:
                if running_total + len(part) > _CONTENT_BUDGET_TOTAL:
                    break
                trimmed_parts.append(part)
                running_total += len(part)
                kept += 1
            if kept < total:
                logger.warning(
                    "SynthesisAgent: truncated content to %d/%d items (budget %d chars)",
                    kept, total, _CONTENT_BUDGET_TOTAL,
                )
            untrusted_parts = trimmed_parts

        untrusted_content = "\n\n".join(untrusted_parts) if untrusted_parts else "No raw research data available."

        # Prior knowledge — trusted (from KnowledgeGraph, established in prior runs)
        if prior_knowledge:
            untrusted_content = prior_knowledge + untrusted_content

        # Financial summary — trusted (pre-extracted by FinancialAgent)
        if financial:
            financial_summary = json.dumps(financial, indent=2)
        else:
            financial_summary = "No financial data available."

        # Qual summary — trusted (pre-extracted by QualAgent)
        if qual:
            qual_summary = json.dumps(qual, indent=2)
        else:
            qual_summary = "No qualitative analysis available."

        prompt = _PROMPT_TEMPLATE.format(
            goal_context=goal_context_str,
            untrusted_content=untrusted_content,
            financial_summary=financial_summary,
            qual_summary=qual_summary,
        )

        response = await asyncio.to_thread(
            self._client.messages.create,
            model="claude-opus-4-6",
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("SynthesisAgent: failed to parse Claude response: %s", e)
            return dict(_EMPTY_SYNTHESIS)

        # Merge with empty template to ensure all keys exist
        result = dict(_EMPTY_SYNTHESIS)
        result.update(parsed)
        return result
