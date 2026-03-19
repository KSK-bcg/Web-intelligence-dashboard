"""
NarrativePlanner — decides the storyline and slide sequence for a BCG deck.

Instead of always generating the same 7-slide template, this agent:
  1. Analyzes the synthesis output and original goal
  2. Identifies the core argument/thesis
  3. Selects and orders slides from a menu of types
  4. Returns a NarrativePlan that PPTXAgent renders

Available slide types:
  executive_summary   — Board-level SCQA executive summary
  market_landscape    — Market size, players, trends
  competitive_matrix  — Multi-dimension competitive comparison
  org_intelligence    — People / leadership org chart insights
  financial_snapshot  — Key financial metrics and benchmarks
  strategic_options   — Two/three strategic paths with trade-offs
  recommendations     — Prioritized action list with owners
  risk_register       — Key risks with likelihood × impact
  goal_coverage       — Research coverage and gaps (auto-appended if GoalEval present)

Rules:
  - Always start with executive_summary
  - Always end with recommendations
  - goal_coverage is always last content slide (before disclaimer/end)
  - 4–7 content slides total (excluding structural slides)
  - Choose the slides that best serve the research goal
"""
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import anthropic

logger = logging.getLogger(__name__)

_PLAN_PROMPT = """You are a BCG partner deciding the narrative structure for a client presentation.

Research goal: {goal}

Synthesis summary:
{summary}

Available slide types and when to use them:
- executive_summary: ALWAYS include — the board-level argument
- market_landscape: include when market sizing/trends data is available
- competitive_matrix: include when comparing 3+ companies across dimensions
- org_intelligence: include when LinkedIn/people data is available
- financial_snapshot: include when financial metrics/P&L data is available
- strategic_options: include when there are clear strategic choices to present
- recommendations: ALWAYS include — specific, owner-attributable actions
- risk_register: include when significant risks were identified

Choose 4-7 slides that best serve the research goal. The narrative should follow
BCG's Pyramid Principle: lead with the answer, support with evidence, end with action.

Return ONLY a JSON object — no markdown, no explanation:
{{
  "thesis": "<one sentence — the core argument this deck makes>",
  "narrative_arc": "<2-3 sentences — how the story flows from problem to answer>",
  "slide_sequence": ["executive_summary", "market_landscape", ...],
  "slide_emphasis": {{
    "executive_summary": "<what to emphasize on this slide>",
    "market_landscape": "<what to emphasize>",
    ...
  }}
}}

Rules:
- executive_summary must be first
- recommendations must be last content slide (before goal_coverage if present)
- 4-7 slides in slide_sequence (not counting goal_coverage)
- Only include slides where the synthesis has relevant data
"""


class NarrativePlan:
    """The output of NarrativePlanner — drives PPTXAgent slide generation."""

    def __init__(self, data: Dict[str, Any]):
        self.thesis: str = data.get("thesis", "")
        self.narrative_arc: str = data.get("narrative_arc", "")
        self.slide_sequence: List[str] = data.get("slide_sequence", _DEFAULT_SEQUENCE)
        self.slide_emphasis: Dict[str, str] = data.get("slide_emphasis", {})

    def get_emphasis(self, slide_type: str) -> str:
        return self.slide_emphasis.get(slide_type, "")


_DEFAULT_SEQUENCE = [
    "executive_summary",
    "market_landscape",
    "competitive_matrix",
    "recommendations",
]


class NarrativePlanner:
    """
    Plans the BCG deck narrative from synthesis + goal.
    Uses Claude Haiku — this is structural planning, not content generation.
    """

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    async def plan(self, goal: str, synthesis: Dict[str, Any]) -> NarrativePlan:
        """
        Generate a narrative plan for the BCG deck.

        Args:
            goal:      The original research goal
            synthesis: SynthesisAgent output

        Returns:
            NarrativePlan with slide_sequence and emphasis. Falls back to default on error.
        """
        summary = self._synthesis_summary(synthesis)
        safe_goal = goal[:400].replace("{", "(").replace("}", ")")
        prompt = _PLAN_PROMPT.format(goal=safe_goal, summary=summary[:3000])

        try:
            response = await asyncio.to_thread(
                self._client.messages.create,
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                data = json.loads(json_match.group())
                plan = NarrativePlan(data)
                # Validate: executive_summary must be first, recommendations must be near end
                seq = plan.slide_sequence
                if not seq or seq[0] != "executive_summary":
                    seq = ["executive_summary"] + [s for s in seq if s != "executive_summary"]
                if "recommendations" not in seq:
                    seq.append("recommendations")
                elif seq[-1] != "recommendations":
                    seq = [s for s in seq if s != "recommendations"] + ["recommendations"]
                plan.slide_sequence = seq[:7]  # cap at 7 slides
                logger.info("NarrativePlanner: thesis='%s' sequence=%s", plan.thesis[:80], seq)
                return plan
        except Exception as e:
            logger.warning("NarrativePlanner: planning failed (%s) — using default sequence", e)

        return NarrativePlan({"slide_sequence": _DEFAULT_SEQUENCE})

    @staticmethod
    def _synthesis_summary(synthesis: Dict[str, Any]) -> str:
        parts = []
        if synthesis.get("executive_summary"):
            parts.append(f"Executive summary: {synthesis['executive_summary'][:300]}")

        ml = synthesis.get("market_landscape") or {}
        if ml.get("key_players"):
            parts.append(f"Key players: {', '.join(p.get('name','') for p in ml['key_players'][:5])}")
        if ml.get("size_and_growth"):
            parts.append(f"Market: {ml['size_and_growth'][:150]}")

        ca = synthesis.get("competitive_analysis") or {}
        if ca.get("comparison_table"):
            parts.append(f"Competitive dims: {len(ca['comparison_table'])} dimensions analyzed")
        if ca.get("winner_signals"):
            parts.append(f"Winner signals: {ca['winner_signals'][0][:100]}")

        si = synthesis.get("strategic_implications") or {}
        if si.get("opportunities"):
            parts.append(f"Top opportunity: {si['opportunities'][0][:100]}")
        if si.get("risks"):
            parts.append(f"Top risk: {si['risks'][0][:100]}")

        recs = synthesis.get("recommendations") or []
        if recs:
            parts.append(f"Recommendations: {len(recs)} identified")

        fin = synthesis.get("financial_data") or []
        if fin:
            parts.append("Financial data: available")

        people = synthesis.get("org_intelligence") or {}
        if people:
            parts.append("Org/people data: available")

        return "\n".join(parts)
