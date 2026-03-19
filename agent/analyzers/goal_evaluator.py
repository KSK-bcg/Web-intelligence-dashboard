"""
GoalEvaluator — BCG-standard quality gate for intelligence output.

Applies BCG consulting frameworks to verify that the synthesis output:
  1. Fully addresses the original research goal (coverage)
  2. Follows the Pyramid Principle (answer-first, MECE arguments)
  3. Frames the executive summary using SCQA (Situation → Complication → Question → Answer)
  4. Produces actionable, specific recommendations (not platitudes)
  5. Sources every material data point

Output schema:
  {
    "score":             0–100 (weighted average of 5 dimensions),
    "verdict":           "PASS" | "PARTIAL" | "FAIL",

    "goal_coverage": {
      "score": 0–100,
      "mece_components": ["component A", "component B", ...],   # original goal decomposed
      "satisfied":       ["component A — addressed because ..."],
      "gaps":            ["component B — not found in synthesis"],
    },

    "pyramid_principle": {
      "score": 0–100,
      "answer_first":    true/false,
      "arguments_mece":  true/false,
      "findings":        ["exec summary leads with recommendation ✓",
                          "market section repeats competitive findings ✗ (MECE overlap)"],
    },

    "scqa": {
      "score": 0–100,
      "situation":    "<identified or 'MISSING'>",
      "complication": "<identified or 'MISSING'>",
      "question":     "<identified or 'MISSING'>",
      "answer":       "<identified or 'MISSING'>",
    },

    "recommendations_quality": {
      "score": 0–100,
      "findings": ["Rec 1 is specific and owner-attributable ✓",
                   "Rec 2 is generic ('improve capabilities') — needs quantification ✗"],
    },

    "sourcing": {
      "score": 0–100,
      "findings": ["financial data has source citations ✓",
                   "market size figure is unsourced ✗"],
    },

    "recommendation": "<one sentence — how to re-run or expand to fill the highest-priority gap>"
  }

Verdict thresholds (weighted score):
  PASS    ≥ 75
  PARTIAL ≥ 45
  FAIL    < 45

Weights:
  goal_coverage            40%
  pyramid_principle        20%
  scqa                     15%
  recommendations_quality  15%
  sourcing                 10%
"""
import asyncio
import json
import logging
import os
import re
from typing import Any, Dict

import anthropic

logger = logging.getLogger(__name__)

# ── Weights ───────────────────────────────────────────────────────────────────
_WEIGHTS = {
    "goal_coverage": 0.40,
    "pyramid_principle": 0.20,
    "scqa": 0.15,
    "recommendations_quality": 0.15,
    "sourcing": 0.10,
}

_EVAL_PROMPT = """You are a senior BCG consultant performing a quality gate review on an
AI-generated competitive intelligence brief. Apply BCG consulting standards rigorously.

## Original Research Goal
{goal}

## Synthesis Output
{synthesis_summary}

## Your Task
Evaluate the synthesis across 5 dimensions. Return ONLY valid JSON — no markdown, no explanation.

### Dimension 1 — Goal Coverage (weight 40%)
Decompose the original goal into MECE sub-questions (mutually exclusive, collectively exhaustive).
For each component, state whether it was satisfied with evidence from the synthesis.

### Dimension 2 — Pyramid Principle (weight 20%)
- Does the executive summary lead with the answer/recommendation (not context)?
- Are the deck sections MECE — no overlapping arguments, no missing arguments?
- Can you follow the storyline from action titles alone?

### Dimension 3 — SCQA (weight 15%)
Does the executive summary follow Situation → Complication → Question → Answer?
Extract each element if present, or mark "MISSING".

### Dimension 4 — Recommendations Quality (weight 15%)
BCG recommendations must be:
  - Specific (not "improve capabilities" — but "reduce MTTR below 2h by Q3 2026")
  - Actionable (owner-attributable, time-bound where possible)
  - Prioritised (why this over alternatives?)

### Dimension 5 — Sourcing (weight 10%)
Are material data points (market size, growth rates, financial figures) sourced?
Flag any unsourced claims.

---

Return this exact JSON structure:
{{
  "goal_coverage": {{
    "score": <0-100>,
    "mece_components": ["<component 1>", "<component 2>"],
    "satisfied": ["<component> — addressed because <evidence>"],
    "gaps": ["<component> — not found because <reason>"]
  }},
  "pyramid_principle": {{
    "score": <0-100>,
    "answer_first": <true|false>,
    "arguments_mece": <true|false>,
    "findings": ["<finding 1>", "<finding 2>"]
  }},
  "scqa": {{
    "score": <0-100>,
    "situation": "<text or MISSING>",
    "complication": "<text or MISSING>",
    "question": "<text or MISSING>",
    "answer": "<text or MISSING>"
  }},
  "recommendations_quality": {{
    "score": <0-100>,
    "findings": ["<finding 1>", "<finding 2>"]
  }},
  "sourcing": {{
    "score": <0-100>,
    "findings": ["<finding 1>", "<finding 2>"]
  }},
  "recommendation": "<one sentence: highest-priority action to improve quality or fill gaps>"
}}
"""


def _synthesis_to_summary(synthesis: Dict[str, Any]) -> str:
    """Compact text summary of synthesis for the eval prompt."""
    parts = []

    exec_sum = synthesis.get("executive_summary", "")
    if exec_sum:
        parts.append(f"EXECUTIVE SUMMARY:\n{exec_sum[:500]}")

    ml = synthesis.get("market_landscape") or {}
    if ml.get("size_and_growth"):
        parts.append(f"MARKET:\n{ml['size_and_growth'][:250]}")
    if ml.get("key_players"):
        rows = [f"  {p.get('name')}: {p.get('position')} — {p.get('signal')}"
                for p in ml["key_players"][:5]]
        parts.append("KEY PLAYERS:\n" + "\n".join(rows))
    if ml.get("trends"):
        parts.append("TRENDS:\n" + "\n".join(f"  - {t}" for t in ml["trends"][:4]))

    ca = synthesis.get("competitive_analysis") or {}
    if ca.get("comparison_table"):
        rows = [f"  {r.get('dimension')}: {r.get('findings')}"
                for r in ca["comparison_table"][:5]]
        parts.append("COMPETITIVE COMPARISON:\n" + "\n".join(rows))
    if ca.get("winner_signals"):
        parts.append("WINNER SIGNALS:\n" + "\n".join(f"  ✓ {w}" for w in ca["winner_signals"][:3]))
    if ca.get("disruption_risks"):
        parts.append("DISRUPTION RISKS:\n" + "\n".join(f"  ⚠ {d}" for d in ca["disruption_risks"][:3]))

    si = synthesis.get("strategic_implications") or {}
    if si.get("opportunities"):
        parts.append("OPPORTUNITIES:\n" + "\n".join(f"  + {o}" for o in si["opportunities"][:4]))
    if si.get("risks"):
        parts.append("RISKS:\n" + "\n".join(f"  - {r}" for r in si["risks"][:4]))

    recs = synthesis.get("recommendations") or []
    if recs:
        parts.append("RECOMMENDATIONS:\n" + "\n".join(f"  {i+1}. {r}" for i, r in enumerate(recs[:5])))

    if synthesis.get("outlook"):
        parts.append(f"OUTLOOK:\n{synthesis['outlook'][:200]}")

    return "\n\n".join(parts) if parts else "[No synthesis content]"


def _weighted_score(result: Dict[str, Any]) -> int:
    """Compute weighted score from dimension sub-scores."""
    total = 0.0
    for dim, weight in _WEIGHTS.items():
        dim_data = result.get(dim) or {}
        total += dim_data.get("score", 0) * weight
    return round(total)


def _verdict(score: int) -> str:
    if score >= 75:
        return "PASS"
    if score >= 45:
        return "PARTIAL"
    return "FAIL"


def _safe_default() -> Dict[str, Any]:
    return {
        "score": 50,
        "verdict": "PARTIAL",
        "goal_coverage": {
            "score": 50,
            "mece_components": [],
            "satisfied": ["Evaluation could not be completed automatically."],
            "gaps": ["Manual review recommended."],
        },
        "pyramid_principle": {"score": 50, "answer_first": None, "arguments_mece": None, "findings": []},
        "scqa": {"score": 50, "situation": "UNKNOWN", "complication": "UNKNOWN",
                 "question": "UNKNOWN", "answer": "UNKNOWN"},
        "recommendations_quality": {"score": 50, "findings": []},
        "sourcing": {"score": 50, "findings": []},
        "recommendation": "Check agent logs — automatic evaluation failed.",
    }


class GoalEvaluator:
    """
    BCG-standard quality gate: scores synthesis against the original research goal.

    Applies Pyramid Principle, SCQA, MECE, recommendation specificity, and sourcing checks.
    """

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    async def evaluate(self, goal: str, synthesis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score synthesis against the original goal using BCG consulting standards.

        Args:
            goal:      The original (possibly refined) user goal string.
            synthesis: Output dict from SynthesisAgent.run().

        Returns:
            Structured evaluation dict. See module docstring for full schema.
            On failure returns a safe PARTIAL default.
        """
        exec_sum = (synthesis.get("executive_summary") or "").strip()
        if not exec_sum:
            result = _safe_default()
            result["score"] = 0
            result["verdict"] = "FAIL"
            result["goal_coverage"]["score"] = 0
            result["goal_coverage"]["gaps"] = ["No synthesis content produced — all fields empty."]
            result["recommendation"] = "Re-run with a broader goal or check crawler logs."
            return result

        summary = _synthesis_to_summary(synthesis)
        prompt = _EVAL_PROMPT.format(goal=goal, synthesis_summary=summary)

        try:
            response = await asyncio.to_thread(
                self.client.messages.create,
                model="claude-opus-4-6",
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
            raw = json.loads(text)
        except Exception as e:
            logger.warning("GoalEvaluator: Claude call or JSON parse failed (%s)", e)
            return _safe_default()

        # Compute weighted score and verdict
        score = _weighted_score(raw)
        raw["score"] = score
        raw["verdict"] = _verdict(score)

        # Ensure recommendation is present
        if not raw.get("recommendation"):
            gaps = (raw.get("goal_coverage") or {}).get("gaps") or []
            raw["recommendation"] = (
                f"Address gaps: {gaps[0]}" if gaps else "No material gaps identified."
            )

        logger.info(
            "GoalEvaluator: score=%d verdict=%s | coverage=%s pyramid=%s scqa=%s recs=%s sourcing=%s",
            score,
            raw["verdict"],
            (raw.get("goal_coverage") or {}).get("score", "?"),
            (raw.get("pyramid_principle") or {}).get("score", "?"),
            (raw.get("scqa") or {}).get("score", "?"),
            (raw.get("recommendations_quality") or {}).get("score", "?"),
            (raw.get("sourcing") or {}).get("score", "?"),
        )
        return raw
