# agent/orchestrator.py
"""
Goal Orchestrator — decomposes NL goals into crawl + analyze pipelines.

Flow:
  User goal -> Claude classifies -> selects crawl + analysis agents -> runs pipeline
"""
import json
import logging
import os
import re
from typing import Optional, List

import anthropic

from agent.crawlers.linkedin import LinkedInCrawler
from agent.crawlers.blog import BlogCrawler
from agent.analyzers.quant import QuantAgent
from agent.analyzers.qual import QualAgent
from agent.analyzers.viz import VizAgent
from agent.normalizer import Normalizer
from agent.store import Store

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Classify this research goal and extract key parameters.

Goal: {goal}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "source_type": "linkedin",
  "analysis_type": "org_chart",
  "target": "company-slug-for-storage",
  "company_name": "Company Name",
  "department_filter": "IT",
  "url": null,
  "max_profiles": 30
}}

If the goal is about a blog or website, set source_type to "blog" and url to the URL.
If it is about LinkedIn org structure, set source_type to "linkedin".
"""


class Orchestrator:
    def __init__(self, db_path: str = "intelligence.db", output_dir: str = "output"):
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.store = Store(db_path=db_path)
        self.store.init_db()
        self.normalizer = Normalizer()
        self.output_dir = output_dir

    async def run(self, goal: str, run_id_hint: Optional[str] = None) -> dict:
        """Execute the full pipeline for a goal."""
        logger.info("Starting pipeline for goal: %s", goal)
        plan = self._classify_goal(goal)
        logger.info("Classified: %s", plan)

        target = plan.get("target") or "unknown"

        # Use existing run_id for re-runs (enables change detection diff).
        # Create a new run_id only when no hint is provided.
        if run_id_hint:
            run_id = run_id_hint
            existing = self.store.get_run(run_id)
            if not existing:
                raise ValueError(f"run_id_hint '{run_id_hint}' not found in store")
        else:
            run_id = self.store.create_run(goal=goal, target=target)

        # Step 1: Crawl
        raw_data = await self._crawl(plan)

        # Step 2: Normalize
        people = self.normalizer.normalize(raw_data)
        for person in people:
            self.store.save_person(run_id=run_id, person={
                k: person.get(k) for k in
                ["linkedin_id", "name", "title", "department", "confidence"]
                if person.get(k)
            })

        # Step 3: Analyze
        quant_result = await QuantAgent().run(people=people)
        qual_result = await QualAgent().run(people=people)

        # Step 4: Change detection
        prior_run = self.store.get_latest_run_for_target(target, exclude_run_id=run_id)
        changes_dicts: List[dict] = []
        if prior_run:
            changes = self.store.diff_runs(prior_run_id=prior_run.id, current_run_id=run_id)
            changes_dicts = [
                {
                    "change_type": c.change_type,
                    "person_name": c.person_name,
                    "from_value": c.from_value,
                    "to_value": c.to_value,
                }
                for c in changes
            ]

        # Step 5: Render
        viz = VizAgent()
        html = viz.render(
            graph=quant_result["graph"],
            qual=qual_result,
            stats=quant_result["stats"],
            run_id=run_id,
            changes=changes_dicts,
        )
        report_path = viz.save(html, run_id=run_id, output_dir=self.output_dir)

        self.store.complete_run(run_id)
        logger.info("Pipeline complete. Report: %s", report_path)

        return {
            "run_id": run_id,
            "report_path": report_path,
            "changes": changes_dicts,
            "people_count": len(people),
        }

    def _classify_goal(self, goal: str) -> dict:
        prompt = CLASSIFY_PROMPT.format(goal=goal)
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            # Strip markdown code fences if present
            text = re.sub(r'```(?:json)?\s*', '', text).strip().rstrip('`')
            return json.loads(text)
        except Exception as e:
            logger.warning("Goal classification failed (%s), defaulting to LinkedIn", e)
            return {
                "source_type": "linkedin",
                "analysis_type": "org_chart",
                "target": goal.lower().replace(" ", "-")[:20],
                "company_name": goal,
                "department_filter": None,
                "url": None,
                "max_profiles": 30,
            }

    async def _crawl(self, plan: dict) -> list:
        source_type = plan.get("source_type", "linkedin")
        if source_type == "linkedin":
            crawler = LinkedInCrawler(max_profiles=int(plan.get("max_profiles") or 30))
            return await crawler.run(
                company_name=plan.get("company_name", ""),
                department_filter=plan.get("department_filter"),
            )
        else:
            crawler = BlogCrawler()
            return await crawler.run(url=plan.get("url", ""), max_pages=20)
