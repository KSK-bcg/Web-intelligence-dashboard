# agent/analyzers/viz.py
"""
Viz Agent — renders interactive D3.js org chart as a self-contained HTML file.
"""
import json
import logging
import os
from pathlib import Path
from string import Template
from typing import List, Optional

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "org_chart.html"


class VizAgent:
    """Renders org chart data into a self-contained interactive HTML report."""

    def render(
        self,
        graph: dict,
        qual: dict,
        stats: dict,
        run_id: str,
        changes: Optional[List[dict]] = None,
    ) -> str:
        template_src = TEMPLATE_PATH.read_text()
        template = Template(template_src)
        return template.safe_substitute(
            RUN_ID=run_id,
            GRAPH_DATA=json.dumps(graph),
            QUAL_DATA=json.dumps(qual),
            STATS_DATA=json.dumps(stats),
            CHANGES_DATA=json.dumps(changes or []),
        )

    def save(self, html: str, run_id: str, output_dir: str = "output") -> str:
        run_dir = os.path.join(output_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)
        path = os.path.join(run_dir, "report.html")
        with open(path, "w") as f:
            f.write(html)
        logger.info("Report saved to %s", path)
        return path
