import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-fc-key")

@pytest.mark.asyncio
async def test_orchestrator_runs_linkedin_pipeline(mock_env, tmp_path):
    with patch("agent.orchestrator.LinkedInCrawler") as mock_li, \
         patch("agent.orchestrator.BlogCrawler") as mock_blog, \
         patch("agent.orchestrator.QuantAgent") as mock_quant, \
         patch("agent.orchestrator.QualAgent") as mock_qual, \
         patch("agent.orchestrator.VizAgent") as mock_viz, \
         patch("agent.orchestrator.Normalizer") as mock_norm, \
         patch("agent.orchestrator.Store") as mock_store, \
         patch("agent.orchestrator.anthropic.Anthropic") as mock_anthropic:

        # Mock Claude goal classification response
        mock_anthropic.return_value.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"source_type": "linkedin", "analysis_type": "org_chart", "target": "roche-it", "company_name": "Roche", "department_filter": "IT", "url": null, "max_profiles": 10}')]
        )

        mock_li.return_value.run = AsyncMock(return_value=[
            {"linkedin_id": "p1", "name": "Alice", "title": "CIO", "source": "linkedin", "about": ""},
            {"linkedin_id": "p2", "name": "Bob", "title": "VP Cloud", "source": "linkedin", "about": ""},
            {"linkedin_id": "p3", "name": "Carol", "title": "Director IT", "source": "linkedin", "about": ""},
        ])
        mock_norm.return_value.normalize.return_value = [
            {"linkedin_id": "p1", "name": "Alice", "title": "CIO", "department": "IT Leadership", "confidence": "high"},
            {"linkedin_id": "p2", "name": "Bob", "title": "VP Cloud", "department": "Cloud", "confidence": "high"},
            {"linkedin_id": "p3", "name": "Carol", "title": "Director IT", "department": "IT", "confidence": "high"},
        ]
        mock_quant.return_value.run = AsyncMock(return_value={
            "graph": {"nodes": [], "edges": []}, "stats": {"total_people": 3, "departments": {}, "org_depth": 1}
        })
        mock_qual.return_value.run = AsyncMock(return_value={
            "executive_summary": "Test", "key_themes": [], "technology_signals": [], "people_insights": []
        })
        mock_viz.return_value.render.return_value = "<html>test</html>"
        mock_viz.return_value.save.return_value = str(tmp_path / "report.html")
        mock_store.return_value.create_run.return_value = "run-001"
        mock_store.return_value.diff_runs.return_value = []
        mock_store.return_value.get_latest_run_for_target.return_value = None
        mock_store.return_value.get_run.return_value = MagicMock(id="run-001")

        from agent.orchestrator import Orchestrator
        orch = Orchestrator(output_dir=str(tmp_path))
        result = await orch.run(goal="Map IT division of Roche on LinkedIn")
        assert "report_path" in result
        assert result["run_id"] == "run-001"
