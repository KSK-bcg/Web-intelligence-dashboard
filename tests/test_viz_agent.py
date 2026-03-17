import pytest
from agent.analyzers.viz import VizAgent

SAMPLE_GRAPH = {
    "nodes": [
        {"linkedin_id": "cio1", "name": "Alice", "title": "CIO", "department": "IT Leadership",
         "confidence": "high", "reports_to": None},
        {"linkedin_id": "vp1", "name": "Bob", "title": "VP Cloud", "department": "Cloud",
         "confidence": "high", "reports_to": "cio1"},
        {"linkedin_id": "dir1", "name": "Carol", "title": "Director Security", "department": "Security",
         "confidence": "medium", "reports_to": "cio1"},
    ],
    "edges": [("cio1", "vp1"), ("cio1", "dir1")],
}

SAMPLE_QUAL = {
    "executive_summary": "A cloud-first IT team.",
    "key_themes": ["cloud", "security"],
    "technology_signals": ["AWS", "Azure"],
    "people_insights": [],
}

SAMPLE_STATS = {
    "total_people": 3,
    "departments": {"IT Leadership": 1, "Cloud": 1, "Security": 1},
    "org_depth": 1,
}

@pytest.fixture
def agent():
    return VizAgent()

def test_render_returns_html_string(agent):
    html = agent.render(graph=SAMPLE_GRAPH, qual=SAMPLE_QUAL, stats=SAMPLE_STATS, run_id="test-001")
    assert isinstance(html, str)
    assert "<html" in html.lower()

def test_render_includes_all_names(agent):
    html = agent.render(graph=SAMPLE_GRAPH, qual=SAMPLE_QUAL, stats=SAMPLE_STATS, run_id="test-001")
    assert "Alice" in html
    assert "Bob" in html
    assert "Carol" in html

def test_render_includes_d3_script(agent):
    html = agent.render(graph=SAMPLE_GRAPH, qual=SAMPLE_QUAL, stats=SAMPLE_STATS, run_id="test-001")
    assert "d3" in html.lower()

def test_render_includes_confidence_indicators(agent):
    html = agent.render(graph=SAMPLE_GRAPH, qual=SAMPLE_QUAL, stats=SAMPLE_STATS, run_id="test-001")
    assert "medium" in html.lower() or "confidence" in html.lower()
