# agent/orchestrator.py
"""
Goal Orchestrator — decomposes NL goals into crawl + analyze pipelines.

Flow:
  User goal -> Claude classifies -> selects crawl + analysis agents -> runs pipeline

Multi-source: _classify_goal returns source_types (list); _crawl fans out in parallel
via asyncio.gather and merges all results before analysis.
"""
import asyncio
import json
import logging
import os
import re
from typing import Optional, List

import anthropic

from agent.crawlers.linkedin import LinkedInCrawler
from agent.crawlers.blog import BlogCrawler
from agent.crawlers.filings import FilingsCrawler
from agent.crawlers.earnings import EarningsCrawler
from agent.analyzers.quant import QuantAgent
from agent.analyzers.qual import QualAgent
from agent.analyzers.viz import VizAgent
from agent.analyzers.financial import FinancialAgent
from agent.analyzers.synthesis import SynthesisAgent
from agent.analyzers.pptx_agent import PPTXAgent
from agent.normalizer import Normalizer
from agent.store import Store

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Classify this research goal and extract key parameters.

Goal: {goal}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "source_types": ["linkedin"],
  "target": "company-slug-for-storage",
  "company_name": "Company Name",
  "department_filter": "IT",
  "url": null,
  "max_profiles": 30,
  "companies": [],
  "sector": null,
  "region": null
}}

Rules for source_types (MUST be a JSON array — include ALL that apply):
- LinkedIn org structure / people → include "linkedin"
- Blog or website URL → include "blog"
- Financial filings / P&L / earnings → include "financial"
- Market landscape / industry intelligence → include "market_intel"
- Competitive analysis across companies → include "synthesis"
- Board deck / presentation explicitly requested → include "board_deck"
- Multi-faceted goals (e.g. org chart + financials) → include ALL matching types

For financial/market_intel/synthesis/board_deck: populate "sector" (e.g. "health IT") and "region" (e.g. "APAC") if mentioned.
"""

BOARD_DECK_TYPES = {"board_deck", "market_intel", "synthesis", "financial"}


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

        if run_id_hint:
            run_id = run_id_hint
            existing = self.store.get_run(run_id)
            if not existing:
                raise ValueError(f"run_id_hint '{run_id_hint}' not found in store")
        else:
            run_id = self.store.create_run(goal=goal, target=target)

        try:
            source_types = plan.get("source_types") or ["linkedin"]

            # Step 1: Fan-out crawl in parallel across all source types
            raw_data = await self._crawl(plan)

            # Step 2: Route to pipeline
            use_board_deck = bool(BOARD_DECK_TYPES.intersection(set(source_types)))
            has_people_source = bool({"linkedin", "blog"}.intersection(set(source_types)))

            if use_board_deck:
                pipeline_result = await self._run_board_deck_pipeline(
                    plan, raw_data, run_id, include_people=has_people_source
                )
                self.store.complete_run(run_id)
                pptx_path = pipeline_result.get("pptx_path")
                if pptx_path:
                    self.store.update_pptx_path(run_id, pptx_path)
                logger.info("Pipeline complete. PPTX: %s", pptx_path)
                return {
                    "run_id": run_id,
                    "report_path": None,
                    "pptx_path": pptx_path,
                    "pptx_available": bool(pptx_path),
                    "changes": [],
                    "people_count": len([d for d in raw_data if "name" in d]),
                    "synthesis": pipeline_result.get("synthesis"),
                }
            else:
                # LinkedIn / blog pipeline → HTML org chart report
                people = self.normalizer.normalize(raw_data)
                for person in people:
                    self.store.save_person(run_id=run_id, person={
                        k: person.get(k) for k in
                        ["linkedin_id", "name", "title", "department", "confidence"]
                        if person.get(k)
                    })

                quant_result = await QuantAgent().run(people=people)
                qual_result = await QualAgent().run(people=people)

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
                    "pptx_path": None,
                    "pptx_available": False,
                    "changes": changes_dicts,
                    "people_count": len(people),
                }
        except Exception:
            self.store.fail_run(run_id)
            raise

    async def _run_board_deck_pipeline(
        self, plan: dict, raw_data: list, run_id: str, include_people: bool = False
    ) -> dict:
        """Run full board deck pipeline: qual + financial + synthesis + pptx."""
        people_data = [d for d in raw_data if "name" in d] if include_people else []
        qual_result = await QualAgent().run(people=people_data)

        filing_items = [d for d in raw_data if d.get("source") == "filing"]
        if filing_items:
            financial_results = await FinancialAgent().run(raw_data)
            for fr in financial_results:
                self.store.save_financial(run_id=run_id, financial=fr)
        else:
            financial_results = []

        synthesis = await SynthesisAgent().run(
            raw_data=raw_data,
            financial=financial_results,
            qual=qual_result,
        )

        pptx_path = await PPTXAgent().render(synthesis, run_id)
        return {
            "synthesis": synthesis,
            "pptx_path": pptx_path,
            "financial_results": financial_results,
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
            text = re.sub(r'```(?:json)?\s*', '', text).strip().rstrip('`')
            data = json.loads(text)
            # Back-compat: old single source_type → list
            if "source_type" in data and "source_types" not in data:
                data["source_types"] = [data["source_type"]]
            elif "source_types" not in data:
                data["source_types"] = ["linkedin"]
            return data
        except Exception as e:
            logger.warning("Goal classification failed (%s), defaulting to LinkedIn", e)
            return {
                "source_types": ["linkedin"],
                "analysis_type": "org_chart",
                "target": goal.lower().replace(" ", "-")[:20],
                "company_name": goal,
                "department_filter": None,
                "url": None,
                "max_profiles": 30,
            }

    async def _crawl(self, plan: dict) -> list:
        """Fan out to all source_types in parallel, merge results."""
        source_types = plan.get("source_types") or ["linkedin"]
        tasks = [self._crawl_one(st, plan) for st in source_types]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged = []
        for st, result in zip(source_types, results):
            if isinstance(result, Exception):
                logger.warning("Crawler %s failed: %s", st, result)
            else:
                merged.extend(result)
        return merged

    async def _crawl_one(self, source_type: str, plan: dict) -> list:
        """Run a single crawler by source_type."""
        if source_type == "linkedin":
            crawler = LinkedInCrawler(max_profiles=int(plan.get("max_profiles") or 30))
            return await crawler.run(
                company_name=plan.get("company_name", ""),
                department_filter=plan.get("department_filter"),
            )
        elif source_type == "blog":
            return await BlogCrawler().run(url=plan.get("url", ""), max_pages=20)
        elif source_type == "financial":
            companies = plan.get("companies") or [plan.get("company_name", "")]
            return await FilingsCrawler().run(companies=companies)
        elif source_type in ("market_intel", "synthesis", "board_deck"):
            companies = plan.get("companies") or []
            target_query = plan.get("target") or plan.get("sector") or ""
            filings = []
            if companies:
                try:
                    filings = await FilingsCrawler().run(companies=companies)
                except Exception as e:
                    logger.warning("FilingsCrawler failed: %s", e)
            try:
                earnings = await EarningsCrawler().run(
                    query=target_query,
                    companies=companies,
                    max_results=10,
                )
            except Exception as e:
                logger.warning("EarningsCrawler failed: %s", e)
                earnings = []
            return filings + earnings
        else:
            return await BlogCrawler().run(url=plan.get("url", ""), max_pages=20)
