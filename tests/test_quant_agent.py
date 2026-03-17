import pytest
from unittest.mock import MagicMock, patch

SAMPLE_PEOPLE = [
    {"linkedin_id": "cio1", "name": "Alice CIO", "title": "CIO", "department": "IT Leadership", "confidence": "high"},
    {"linkedin_id": "vp1", "name": "Bob VP", "title": "VP of Cloud", "department": "Cloud", "confidence": "high"},
    {"linkedin_id": "dir1", "name": "Carol Dir", "title": "Director of Security", "department": "Security", "confidence": "high"},
    {"linkedin_id": "vp2", "name": "Dave VP", "title": "VP of Applications", "department": "Applications", "confidence": "high"},
]

@pytest.fixture
def agent():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"hierarchy": [{"linkedin_id": "cio1", "reports_to": null}, {"linkedin_id": "vp1", "reports_to": "cio1"}, {"linkedin_id": "dir1", "reports_to": "cio1"}, {"linkedin_id": "vp2", "reports_to": "cio1"}]}')]
    )
    with patch("agent.analyzers.quant.anthropic.Anthropic", return_value=mock_client):
        from agent.analyzers.quant import QuantAgent
        return QuantAgent()

@pytest.mark.asyncio
async def test_builds_org_graph(agent):
    result = await agent.run(people=SAMPLE_PEOPLE)
    assert "graph" in result
    assert "nodes" in result["graph"]
    assert len(result["graph"]["nodes"]) == 4

@pytest.mark.asyncio
async def test_detects_cycle_in_graph(agent):
    import networkx as nx
    from agent.exceptions import OrgGraphCycleError
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "a")  # cycle
    with pytest.raises(OrgGraphCycleError):
        agent._validate_graph(g)

@pytest.mark.asyncio
async def test_raises_insufficient_data_with_too_few_people(agent):
    from agent.exceptions import InsufficientDataError
    with pytest.raises(InsufficientDataError):
        await agent.run(people=[SAMPLE_PEOPLE[0]])

def test_validate_dag_passes_for_valid_tree(agent):
    import networkx as nx
    g = nx.DiGraph()
    g.add_edge("cio", "vp1")
    g.add_edge("cio", "vp2")
    agent._validate_graph(g)  # Should not raise
