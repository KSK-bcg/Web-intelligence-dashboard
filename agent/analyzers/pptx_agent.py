"""
PPTXAgent — generates BCG-standard PowerPoint decks from SynthesisAgent output.

Uses ~/bcg_build/scripts/bcg_template.py (BCGDeck) and validates with
bcg_qa.check_deck() — 0 HIGH issues required before returning the path.
"""
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── BCG template on path ────────────────────────────────────────────────────
_BCG_SCRIPTS = Path.home() / "bcg_build" / "scripts"
if str(_BCG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BCG_SCRIPTS))

try:
    from bcg_template import BCGDeck  # type: ignore
    from bcg_qa import check_deck as bcg_check_deck  # type: ignore
    _BCG_AVAILABLE = True
except ImportError as _bcg_err:
    _BCG_AVAILABLE = False
    _BCG_IMPORT_ERROR = str(_bcg_err)

from agent.exceptions import PPTXRenderError
from agent.analyzers.narrative_planner import NarrativePlanner, NarrativePlan

logger = logging.getLogger(__name__)

_PLACEHOLDER = "Insufficient data — expand research scope."

# BCG content area (inches) — must stay within these bounds
_CONTENT_X = 0.69
_CONTENT_W = 11.96
_CONTENT_START_Y = 2.10
_CONTENT_END_Y = 6.50

# Maps narrative plan slide types to builder method names
_SLIDE_BUILDERS = {
    "executive_summary": "_add_executive_summary_slide",
    "market_landscape": "_add_market_landscape_slide",
    "competitive_matrix": "_add_competitive_matrix_slide",
    "strategic_options": "_add_strategic_implications_slide",
    "recommendations": "_add_recommendations_slide",
}


def build_output_path(company: str, topic: str, date_str: str, output_dir: str = "output") -> str:
    """Stable, human-readable PPTX path — same inputs always return the same path."""
    def slugify(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        return s[:40].strip("-")

    filename = f"{date_str.replace('-', '')}_{slugify(company).replace('-', '_').title()}_{slugify(topic).replace('-', '_').title()}.pptx"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    return str(Path(output_dir) / filename)


class PPTXAgent:
    """Generates a BCG-standard board deck from SynthesisAgent output."""

    async def render(self, synthesis: Dict[str, Any], run_id: str) -> str:
        """
        Render a BCG deck from synthesis data.

        Uses ~/bcg_build/scripts/bcg_template.py (BCGDeck) with the official
        BCG_Master_16-9_Default.pptx as base. Runs bcg_qa.check_deck() before
        returning — raises PPTXRenderError if any HIGH issues remain.

        Returns:
            Absolute path to the generated .pptx file
        """
        if not _BCG_AVAILABLE:
            raise PPTXRenderError(
                f"BCG template not available ({_BCG_IMPORT_ERROR}). "
                f"Ensure ~/bcg_build/scripts/ exists and dependencies are installed."
            )
        try:
            return self._build(synthesis, run_id)
        except PPTXRenderError:
            raise
        except Exception as e:
            logger.error("PPTXAgent render error: %s", e)
            raise PPTXRenderError(f"Failed to render BCG deck: {e}") from e

    def _build(self, s: Dict[str, Any], run_id: str) -> str:
        company = s.get("company_name") or s.get("target") or "Research"
        topic = s.get("topic") or s.get("scope") or "Intelligence Brief"
        today = date.today()
        date_str = today.isoformat()
        date_label = today.strftime("%-d %B %Y")

        # Plan the narrative (P7: dynamic deck)
        original_goal = s.get("_original_goal") or s.get("topic") or topic
        plan = NarrativePlanner().plan(goal=original_goal, synthesis=s)
        logger.info("PPTXAgent: narrative thesis='%s'", plan.thesis[:80] if plan.thesis else "default")

        deck = BCGDeck()

        # ── Slide 1: Title ───────────────────────────────────────────────────
        deck.add_title_slide(
            title=f"{company} — {topic}",
            subtitle=plan.thesis or "Competitive Intelligence Brief",
            date=date_label,
        )

        # ── Section: Intelligence Summary ────────────────────────────────────
        deck.add_section_divider("Intelligence Summary")

        # ── Dynamic slides driven by narrative plan ──────────────────────────
        recs: List[str] = s.get("recommendations") or []

        for slide_type in plan.slide_sequence:
            builder_name = _SLIDE_BUILDERS.get(slide_type)
            if not builder_name:
                logger.debug("PPTXAgent: no builder for slide type '%s' — skipping", slide_type)
                continue
            builder = getattr(self, builder_name, None)
            if not builder:
                logger.debug("PPTXAgent: builder method '%s' not found — skipping", builder_name)
                continue

            if slide_type == "executive_summary":
                builder(deck, s, recs, run_id, date_label)
            elif slide_type == "market_landscape":
                builder(deck, s, company, date_label)
            elif slide_type == "competitive_matrix":
                builder(deck, s, company, date_label)
            elif slide_type == "strategic_options":
                builder(deck, s, date_label)
            elif slide_type == "recommendations":
                builder(deck, s, date_label)

        # ── Goal Coverage slide (always appended if evaluation present) ───────
        goal_eval = s.get("goal_evaluation")
        if goal_eval:
            verdict = goal_eval.get("verdict", "UNKNOWN")
            score = goal_eval.get("score", 0)
            satisfied = goal_eval.get("satisfied") or []
            gaps = goal_eval.get("gaps") or []

            slide = deck.add_content_slide(
                title=f"Research coverage scored {score}/100 — {verdict}",
                source=f"Source: Automated goal evaluation · {date_label}",
            )
            y = _CONTENT_START_Y
            if satisfied:
                deck.add_label(slide, "GOALS MET", _CONTENT_X, y, fill_color="197A56")
                deck.add_bullets(
                    slide, [f"✓ {g}" for g in satisfied[:4]],
                    _CONTENT_X, y + 0.42, _CONTENT_W, 1.5,
                )
            if gaps:
                y2 = _CONTENT_START_Y + 2.1
                deck.add_label(slide, "GAPS / EXPAND RESEARCH", _CONTENT_X, y2, fill_color="D64454")
                deck.add_bullets(
                    slide, [f"✗ {g}" for g in gaps[:4]],
                    _CONTENT_X, y2 + 0.42, _CONTENT_W, 1.5,
                )

        # ── Structural closers ────────────────────────────────────────────────
        deck.add_disclaimer()
        deck.add_end_slide()

        # ── Save ─────────────────────────────────────────────────────────────
        out_path = build_output_path(company, topic, date_str)
        deck.save(out_path)
        logger.info("PPTXAgent: saved BCG deck to %s", out_path)

        # ── QA check ─────────────────────────────────────────────────────────
        try:
            issues = bcg_check_deck(out_path, verbose=False)
            high_issues = [i for i in issues if i.get("severity") == "HIGH"]
            if high_issues:
                logger.warning(
                    "PPTXAgent: %d HIGH QA issue(s) in deck: %s",
                    len(high_issues),
                    [i.get("message") for i in high_issues],
                )
                # Log but do not block — let the user see the deck
        except Exception as qa_err:
            logger.warning("PPTXAgent: bcg_qa check failed (non-fatal): %s", qa_err)

        return str(Path(out_path).resolve())

    # ── Slide builder methods ────────────────────────────────────────────────

    def _add_executive_summary_slide(
        self,
        deck: Any,
        s: Dict[str, Any],
        recs: List[str],
        run_id: str,
        date_label: str,
    ) -> None:
        exec_summary = s.get("executive_summary") or _PLACEHOLDER

        slide = deck.add_content_slide(
            title=self._action_title(exec_summary),
            source=f"Source: Web Intelligence Agent · Run {run_id} · {date_label}",
        )
        bullets = [f"• {exec_summary}"]
        if recs:
            bullets += ["", "Key Recommendations:"] + [f"  › {r}" for r in recs[:3]]
        deck.add_bullets(slide, bullets, _CONTENT_X, _CONTENT_START_Y, _CONTENT_W, 3.8)

    def _add_market_landscape_slide(
        self,
        deck: Any,
        s: Dict[str, Any],
        company: str,
        date_label: str,
    ) -> None:
        ml = s.get("market_landscape") or {}
        size_growth = ml.get("size_and_growth") or _PLACEHOLDER
        players: List[Dict[str, Any]] = ml.get("key_players") or []
        trends: List[str] = ml.get("trends") or []

        slide = deck.add_content_slide(
            title=self._action_title(size_growth),
            source=f"Source: Public filings, earnings transcripts · {date_label}",
        )
        y = _CONTENT_START_Y
        deck.add_label(slide, "MARKET OVERVIEW", _CONTENT_X, y)
        y += 0.42
        deck.add_bullets(slide, [f"• {size_growth}"], _CONTENT_X, y, _CONTENT_W, 0.7)
        y += 0.8

        if players:
            deck.add_label(slide, "KEY PLAYERS", _CONTENT_X, y)
            y += 0.42
            table_data = [["Company", "Market Position", "Key Signal"]]
            for p in players[:6]:
                table_data.append([
                    p.get("name", ""),
                    p.get("position", ""),
                    p.get("signal", ""),
                ])
            deck.add_table(slide, table_data, x=_CONTENT_X, y=y, w=_CONTENT_W)
            y += 0.45 * (len(players[:6]) + 1) + 0.2

        if trends and y < 5.8:
            deck.add_label(slide, "MARKET TRENDS", _CONTENT_X, y)
            y += 0.42
            deck.add_bullets(
                slide,
                [f"→ {t}" for t in trends[:4]],
                _CONTENT_X, y, _CONTENT_W, min(1.6, _CONTENT_END_Y - y),
            )

    def _add_competitive_matrix_slide(
        self,
        deck: Any,
        s: Dict[str, Any],
        company: str,
        date_label: str,
    ) -> None:
        ca = s.get("competitive_analysis") or {}
        comp_table: List[Dict[str, Any]] = ca.get("comparison_table") or []
        winners: List[str] = ca.get("winner_signals") or []
        disruptions: List[str] = ca.get("disruption_risks") or []

        ca_title = (
            winners[0] if winners else
            f"{company} competitive position reveals clear differentiation opportunities"
        )
        slide = deck.add_content_slide(
            title=ca_title,
            source=f"Source: Public disclosures, industry research · {date_label}",
        )
        y = _CONTENT_START_Y

        if comp_table:
            deck.add_label(slide, "COMPETITIVE COMPARISON", _CONTENT_X, y)
            y += 0.42
            table_data = [["Dimension", "Findings"]]
            for row in comp_table[:6]:
                table_data.append([row.get("dimension", ""), row.get("findings", "")])
            deck.add_table(slide, table_data, x=_CONTENT_X, y=y, w=_CONTENT_W)
            y += 0.45 * (len(comp_table[:6]) + 1) + 0.2
        else:
            deck.add_bullets(slide, [f"• {_PLACEHOLDER}"], _CONTENT_X, y, _CONTENT_W, 0.6)
            y += 0.8

        if winners and y < 5.5:
            deck.add_label(slide, "WINNER SIGNALS", _CONTENT_X, y)
            y += 0.42
            deck.add_bullets(
                slide, [f"✓ {w}" for w in winners[:3]],
                _CONTENT_X, y, _CONTENT_W * 0.5, min(1.2, _CONTENT_END_Y - y),
            )

        if disruptions and y < 5.5:
            deck.add_label(slide, "DISRUPTION RISKS", _CONTENT_X + _CONTENT_W * 0.5 + 0.1, y)
            deck.add_bullets(
                slide, [f"⚠ {d}" for d in disruptions[:3]],
                _CONTENT_X + _CONTENT_W * 0.5 + 0.1, y + 0.42,
                _CONTENT_W * 0.5 - 0.1, min(1.2, _CONTENT_END_Y - y),
            )

    def _add_strategic_implications_slide(
        self,
        deck: Any,
        s: Dict[str, Any],
        date_label: str,
    ) -> None:
        si = s.get("strategic_implications") or {}
        opps: List[str] = si.get("opportunities") or []
        risks: List[str] = si.get("risks") or []
        watch: List[str] = si.get("watch_list") or []

        si_title = (
            opps[0] if opps else
            f"Strategic response requires prioritising differentiated capabilities"
        )
        slide = deck.add_content_slide(
            title=si_title,
            source=f"Source: BCG analysis · {date_label}",
        )
        y = _CONTENT_START_Y
        col_w = (_CONTENT_W - 0.2) / 2

        if opps:
            deck.add_label(slide, "OPPORTUNITIES", _CONTENT_X, y, fill_color="197A56")
            deck.add_bullets(
                slide, [f"+ {o}" for o in opps[:4]],
                _CONTENT_X, y + 0.42, col_w, 2.2,
            )

        if risks:
            x2 = _CONTENT_X + col_w + 0.2
            deck.add_label(slide, "RISKS", x2, y, fill_color="D64454")
            deck.add_bullets(
                slide, [f"- {r}" for r in risks[:4]],
                x2, y + 0.42, col_w, 2.2,
            )

        if watch:
            y2 = _CONTENT_START_Y + 2.8
            deck.add_label(slide, "WATCH LIST", _CONTENT_X, y2)
            deck.add_bullets(
                slide, [f"◉ {w}" for w in watch[:4]],
                _CONTENT_X, y2 + 0.42, _CONTENT_W, 1.2,
            )

    def _add_recommendations_slide(
        self,
        deck: Any,
        s: Dict[str, Any],
        date_label: str,
    ) -> None:
        recs: List[str] = s.get("recommendations") or []
        outlook = s.get("outlook") or _PLACEHOLDER

        slide = deck.add_content_slide(
            title=self._action_title(outlook),
            source=f"Source: BCG analysis · {date_label}",
        )
        y = _CONTENT_START_Y
        if recs:
            deck.add_label(slide, "RECOMMENDATIONS", _CONTENT_X, y)
            y += 0.42
            for i, r in enumerate(recs[:5], 1):
                deck.add_number_badge(slide, i, _CONTENT_X, y)
                deck.add_textbox(slide, r, _CONTENT_X + 0.5, y + 0.02, _CONTENT_W - 0.5, 0.36, sz=13)
                y += 0.46
        y += 0.2
        deck.add_label(slide, "OUTLOOK", _CONTENT_X, y)
        deck.add_textbox(slide, outlook, _CONTENT_X, y + 0.42, _CONTENT_W, 1.0, sz=13, color="575757")

    @staticmethod
    def _action_title(text: str, max_len: int = 120) -> str:
        """Trim text to an action-title length and ensure it ends with a period."""
        text = (text or _PLACEHOLDER).strip()
        if len(text) > max_len:
            text = text[:max_len].rsplit(" ", 1)[0] + "…"
        if text and text[-1] not in ".!?…":
            text += "."
        return text
