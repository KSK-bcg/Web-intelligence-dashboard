import json
import pytest
from unittest.mock import MagicMock, patch


SAMPLE_DATA = [
    {
        "company": "Epic Systems",
        "filing_type": "10-K",
        "period": "FY2023",
        "source_url": "https://epic.com/ar",
        "raw_text": "Epic revenue $4B in FY2023, up 8% YoY.",
        "source": "filing",
    },
    {
        "title": "APAC Health IT Market 2024",
        "body": "The APAC health IT market is growing at 12% CAGR.",
        "source_url": "https://reuters.com/apac-health-it",
        "source_type": "news",
        "company": "Market",
        "date": "2024-01-01",
        "source": "earnings",
    },
]

GOOD_SYNTHESIS = {
    "executive_summary": "The APAC health IT market is growing rapidly.",
    "market_landscape": {
        "size_and_growth": "$50B market growing at 12% CAGR",
        "key_players": [{"name": "Epic", "position": "Leader", "signal": "Revenue growth"}],
        "trends": ["Cloud adoption", "AI integration"],
    },
    "competitive_analysis": {
        "comparison_table": [{"dimension": "Revenue", "findings": "Epic leads at $4B"}],
        "winner_signals": ["Strong R&D investment"],
        "disruption_risks": ["New entrants from hyperscalers"],
    },
    "strategic_implications": {
        "opportunities": ["APAC expansion"],
        "risks": ["Regulatory complexity"],
        "watch_list": ["Oracle Health"],
    },
    "recommendations": ["Invest in cloud-native stack", "Partner with local vendors"],
    "outlook": "Continued growth expected through 2025.",
}


def make_response(text: str):
    content = MagicMock()
    content.text = text
    resp = MagicMock()
    resp.content = [content]
    return resp


@pytest.mark.asyncio
async def test_run_returns_synthesis():
    from agent.analyzers.synthesis import SynthesisAgent
    with patch("agent.analyzers.synthesis.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = make_response(json.dumps(GOOD_SYNTHESIS))
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = SynthesisAgent()
            agent._client = instance
            result = await agent.run(raw_data=SAMPLE_DATA)

    assert result["executive_summary"] == "The APAC health IT market is growing rapidly."
    assert len(result["recommendations"]) == 2


@pytest.mark.asyncio
async def test_run_returns_empty_on_bad_json():
    from agent.analyzers.synthesis import SynthesisAgent, _EMPTY_SYNTHESIS
    with patch("agent.analyzers.synthesis.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = make_response("NOT JSON {{{")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = SynthesisAgent()
            agent._client = instance
            result = await agent.run(raw_data=SAMPLE_DATA)

    assert result["executive_summary"] == ""
    assert result["recommendations"] == []


@pytest.mark.asyncio
async def test_run_returns_empty_on_api_error():
    from agent.analyzers.synthesis import SynthesisAgent, _EMPTY_SYNTHESIS
    with patch("agent.analyzers.synthesis.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.side_effect = Exception("API timeout")
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = SynthesisAgent()
            agent._client = instance
            result = await agent.run(raw_data=SAMPLE_DATA)

    assert result == _EMPTY_SYNTHESIS


@pytest.mark.asyncio
async def test_run_wraps_raw_text_in_untrusted_tags():
    """Verify prompt injection guard — raw text must appear inside untrusted tags."""
    from agent.analyzers.synthesis import SynthesisAgent
    with patch("agent.analyzers.synthesis.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = make_response(json.dumps(GOOD_SYNTHESIS))
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = SynthesisAgent()
            agent._client = instance
            await agent.run(raw_data=SAMPLE_DATA)

    call_args = instance.messages.create.call_args
    prompt_text = call_args[1]["messages"][0]["content"]
    assert "<content source='untrusted'" in prompt_text
    assert "Epic revenue $4B" in prompt_text
