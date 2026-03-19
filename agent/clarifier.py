# agent/clarifier.py
"""
Goal Clarifier — uses 5W1H research framework to ask sharpening questions
before the orchestrator runs, producing a tighter goal context.
"""
import json
import logging
import os
import re
from typing import Any, Dict

import anthropic

logger = logging.getLogger(__name__)

_CLARIFY_PROMPT = """You are a research scoping expert. A user has submitted a research goal.
Apply the 5W1H framework (Who, What, When, Where, Why, How) to identify the 1-3 most
important ambiguities that, if resolved, would significantly improve result quality.

If the goal is already specific and unambiguous, return zero questions.

Goal: {goal}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "questions": ["question1", "question2"],
  "refined_context": {{
    "company": "extracted company name or null",
    "scope": "department/topic extracted or null",
    "level": "seniority filter extracted or null",
    "time_horizon": "time period if relevant or null",
    "output_preference": "deck | report | both or null"
  }}
}}
"""

_REFINE_PROMPT = """A user submitted this research goal: {goal}

They answered these clarifying questions:
{qa_pairs}

Rewrite the goal as a single, precise, actionable research instruction that incorporates
all the answers. Be specific. Include company name, department, seniority level, and any
other constraints that were clarified. Return only the refined goal string, no explanation.
"""


class Clarifier:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    def clarify(self, goal: str) -> Dict[str, Any]:
        """Return questions + extracted context for a goal."""
        prompt = _CLARIFY_PROMPT.format(goal=goal)
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
            return json.loads(text)
        except Exception as e:
            logger.warning("Clarifier failed (%s), returning empty", e)
            return {"questions": [], "refined_context": {}}

    def build_refined_goal(self, goal: str, answers: Dict[str, str]) -> str:
        """Produce a tightened goal string from original goal + Q&A answers."""
        if not answers:
            return goal
        qa_pairs = "\n".join(f"Q: {q}\nA: {a}" for q, a in answers.items())
        prompt = _REFINE_PROMPT.format(goal=goal, qa_pairs=qa_pairs)
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning("build_refined_goal failed (%s), returning original", e)
            return goal
