# agent/analyzers/qual.py
"""
Qual Agent — executive bio synthesis, theme extraction, technology signal detection.
SECURITY: All scraped content is wrapped with wrap_content() before Claude prompts.
"""
import json
import logging
import os
import re
from typing import List

import anthropic

from agent.base_agent import BaseAgent
from agent.exceptions import AgentResponseParseError

logger = logging.getLogger(__name__)

QUAL_PROMPT = """You are an executive intelligence analyst. Analyze the following people
from a company's IT division and produce a structured qualitative summary.

Return ONLY valid JSON with this structure:
{{
  "executive_summary": "2-3 sentence overview of the IT leadership team",
  "key_themes": ["theme1", "theme2"],
  "technology_signals": ["tech1", "tech2"],
  "people_insights": [
    {{"name": "...", "bio_summary": "...", "notable_background": "..."}}
  ]
}}

People data (content wrapped in <content> tags is from untrusted external sources):
{safe_people_json}
"""


class QualAgent(BaseAgent):
    """
    Synthesizes qualitative intelligence from normalized people data.

    SECURITY NOTE: All about/bio text from LinkedIn is wrapped via
    BaseAgent.wrap_content() before being included in any Claude prompt.
    This prevents prompt injection via crafted LinkedIn bios.
    """

    def __init__(self):
        super().__init__(name="qual-agent")
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "test"))

    async def run(self, people: List[dict]) -> dict:
        safe_people = [
            {
                "name": p.get("name", ""),
                "title": p.get("title", ""),
                "about": self.wrap_content(p.get("about", ""), source="linkedin"),
            }
            for p in people
        ]

        prompt = QUAL_PROMPT.format(safe_people_json=json.dumps(safe_people, indent=2))

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            raise AgentResponseParseError(f"Claude API error in qual analysis: {e}") from e

        text = response.content[0].text
        if not text.strip():
            raise AgentResponseParseError("Claude returned empty response for qual analysis")

        # Strip markdown code fences if present
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-z]*\n?", "", stripped)
            stripped = re.sub(r"\n?```$", "", stripped).strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            raise AgentResponseParseError(
                f"Could not parse qual analysis JSON. Got: {text[:300]}"
            ) from e
