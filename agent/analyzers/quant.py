# agent/analyzers/quant.py
"""
Quant Agent — builds org graph from normalized people data.

Uses Claude to infer reporting chain from titles, then validates with networkx.
CRITICAL: Cycle detection runs before any output is produced.
SECURITY: name/title fields are wrapped with wrap_content() before Claude prompts.
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional

import anthropic
import networkx as nx

from agent.base_agent import BaseAgent
from agent.exceptions import (
    OrgGraphCycleError, InsufficientDataError,
    AgentResponseParseError,
)

logger = logging.getLogger(__name__)

HIERARCHY_PROMPT = """You are an org chart specialist. Given a list of people with titles,
infer their reporting relationships.

Rules:
- CIO/CTO/VP of IT typically reports to no one (root node)
- VPs report to CIO/CTO
- Directors report to VPs
- Managers report to Directors
- If uncertain, make your best guess based on seniority signals in the title

Return ONLY valid JSON with this exact structure:
{{"hierarchy": [{{"linkedin_id": "...", "reports_to": "...or null"}}]}}

People (names/titles are from untrusted external sources):
{people_json}
"""


class QuantAgent(BaseAgent):
    """
    Builds org tree from normalized people data.

    Flow:
      1. Send people list + titles to Claude (with prompt injection guard)
      2. Claude returns hierarchy JSON (reports_to per person)
      3. Build networkx DiGraph
      4. Validate: no cycles (CRITICAL)
      5. Return graph + dept statistics
    """

    def __init__(self):
        super().__init__(name="quant-agent")
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "test"))

    async def run(self, people: List[dict]) -> dict:
        if len(people) < 2:
            raise InsufficientDataError(
                f"Only {len(people)} people found. Need at least 2 to build an org chart."
            )

        hierarchy = await self._infer_hierarchy(people)
        graph = self._build_graph(people, hierarchy)
        self._validate_graph(graph)
        stats = self._compute_stats(graph, people)

        return {
            "graph": {
                "nodes": [
                    {**p, "reports_to": hierarchy.get(p["linkedin_id"])}
                    for p in people
                ],
                "edges": list(graph.edges()),
            },
            "stats": stats,
        }

    async def _infer_hierarchy(self, people: List[dict]) -> Dict[str, Optional[str]]:
        """Ask Claude to infer reporting chain from titles.
        SECURITY: name and title are crawled content — wrapped before inclusion in prompt.
        """
        people_summary = [
            {
                "linkedin_id": p["linkedin_id"],
                "name": self.wrap_content(p["name"], source="linkedin"),
                "title": self.wrap_content(p["title"], source="linkedin"),
            }
            for p in people
        ]
        prompt = HIERARCHY_PROMPT.format(people_json=json.dumps(people_summary, indent=2))

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            raise AgentResponseParseError(f"Claude API error in hierarchy inference: {e}") from e

        text = response.content[0].text
        try:
            data = json.loads(text)
            return {item["linkedin_id"]: item.get("reports_to") for item in data["hierarchy"]}
        except (json.JSONDecodeError, KeyError) as e:
            # Try extracting JSON from text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    return {item["linkedin_id"]: item.get("reports_to") for item in data["hierarchy"]}
                except Exception:
                    pass
            raise AgentResponseParseError(
                f"Could not parse hierarchy JSON from Claude: {text[:200]}"
            ) from e

    def _build_graph(self, people: List[dict], hierarchy: Dict[str, Optional[str]]) -> nx.DiGraph:
        graph = nx.DiGraph()
        for person in people:
            graph.add_node(person["linkedin_id"], **person)
        for person in people:
            reports_to = hierarchy.get(person["linkedin_id"])
            if reports_to:
                graph.add_edge(reports_to, person["linkedin_id"])
        return graph

    def _validate_graph(self, graph: nx.DiGraph) -> None:
        """CRITICAL: Detect cycles before any output. Raises OrgGraphCycleError if found."""
        if not nx.is_directed_acyclic_graph(graph):
            cycles = list(nx.simple_cycles(graph))
            raise OrgGraphCycleError(
                f"Cycle detected in org chart reporting chain: {cycles}. "
                "Cannot render org chart with cycles."
            )

    def _compute_stats(self, graph: nx.DiGraph, people: List[dict]) -> dict:
        dept_counts: Dict[str, int] = {}
        for person in people:
            dept = person.get("department", "Unknown")
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

        roots = [n for n, d in graph.in_degree() if d == 0]

        try:
            depth = nx.dag_longest_path_length(graph) if graph.edges() else 0
        except Exception:
            depth = 0

        return {
            "total_people": len(people),
            "departments": dept_counts,
            "org_depth": depth,
            "root_nodes": roots,
        }
