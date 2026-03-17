import json
import logging
import os
from typing import Any, Dict, List, Optional

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

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
You are a senior strategy consultant producing a competitive intelligence briefing.

Below is research data collected from public sources. Analyze it and produce a structured synthesis.

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
    ) -> Dict[str, Any]:
        """
        Synthesize all collected data into a competitive narrative.

        Args:
            raw_data: List of crawler items (filings + earnings + blog items)
            financial: List of FinancialAgent results (trusted, already extracted)
            qual: QualAgent result dict (trusted, already extracted)

        Returns:
            Synthesis dict matching _EMPTY_SYNTHESIS schema.
            Never raises — returns _EMPTY_SYNTHESIS on any error.
        """
        if self._client is None:
            return dict(_EMPTY_SYNTHESIS)

        try:
            return await self._synthesize(raw_data, financial or [], qual or {})
        except Exception as e:
            logger.warning("SynthesisAgent error, returning empty synthesis: %s", e)
            return dict(_EMPTY_SYNTHESIS)

    async def _synthesize(
        self,
        raw_data: List[Dict[str, Any]],
        financial: List[Dict[str, Any]],
        qual: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Build untrusted content block — wrap all raw text in safety tags
        untrusted_parts: List[str] = []
        for item in raw_data:
            raw_text = item.get("raw_text") or item.get("body") or ""
            if raw_text:
                title = item.get("title") or item.get("company") or item.get("source_url", "")
                untrusted_parts.append(
                    f"<content source='untrusted' title='{title}'>\n{raw_text[:5000]}\n</content>"
                )

        untrusted_content = "\n\n".join(untrusted_parts) if untrusted_parts else "No raw research data available."

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
            untrusted_content=untrusted_content,
            financial_summary=financial_summary,
            qual_summary=qual_summary,
        )

        response = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
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
