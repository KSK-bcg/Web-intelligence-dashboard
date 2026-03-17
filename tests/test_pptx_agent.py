import shutil
import pytest
from pathlib import Path


FULL_SYNTHESIS = {
    "executive_summary": "The APAC health IT market is growing rapidly at 12% CAGR.",
    "market_landscape": {
        "size_and_growth": "$50B market, 12% CAGR through 2028",
        "key_players": [
            {"name": "Epic Systems", "position": "Market leader", "signal": "Strong revenue growth"},
        ],
        "trends": ["Cloud adoption", "AI-driven diagnostics"],
    },
    "competitive_analysis": {
        "comparison_table": [
            {"dimension": "Revenue", "findings": "Epic leads at $4B annually"},
        ],
        "winner_signals": ["R&D investment above industry average"],
        "disruption_risks": ["Hyperscaler entry (AWS HealthLake)"],
    },
    "strategic_implications": {
        "opportunities": ["APAC cloud migration wave"],
        "risks": ["Regulatory fragmentation across ASEAN"],
        "watch_list": ["Oracle Health APAC expansion"],
    },
    "recommendations": [
        "Invest in cloud-native EHR integrations",
        "Establish Singapore as APAC HQ",
    ],
    "outlook": "Sustained double-digit growth expected through 2026.",
}

EMPTY_SYNTHESIS = {
    "executive_summary": "",
    "market_landscape": {"size_and_growth": "", "key_players": [], "trends": []},
    "competitive_analysis": {"comparison_table": [], "winner_signals": [], "disruption_risks": []},
    "strategic_implications": {"opportunities": [], "risks": [], "watch_list": []},
    "recommendations": [],
    "outlook": "",
}


@pytest.mark.asyncio
async def test_render_creates_pptx():
    """render() returns a path ending in board-deck.pptx."""
    from agent.analyzers.pptx_agent import PPTXAgent

    agent = PPTXAgent()
    result = await agent.render(FULL_SYNTHESIS, "pytest-pptx-test")

    try:
        assert "board-deck.pptx" in result
        assert Path(result).exists()
    finally:
        shutil.rmtree("output/pytest-pptx-test", ignore_errors=True)


@pytest.mark.asyncio
async def test_render_handles_empty_synthesis():
    """PPTXAgent never raises on empty/missing synthesis data."""
    from agent.analyzers.pptx_agent import PPTXAgent

    agent = PPTXAgent()
    result = await agent.render(EMPTY_SYNTHESIS, "pytest-pptx-empty")

    try:
        assert result.endswith("board-deck.pptx")
        assert Path(result).exists()
    finally:
        shutil.rmtree("output/pytest-pptx-empty", ignore_errors=True)


@pytest.mark.asyncio
async def test_render_produces_5_slides():
    """Verify output has exactly 5 slides."""
    from agent.analyzers.pptx_agent import PPTXAgent
    from pptx import Presentation

    agent = PPTXAgent()
    result = await agent.render(FULL_SYNTHESIS, "pytest-pptx-slides")

    try:
        prs = Presentation(result)
        assert len(prs.slides) == 5
    finally:
        shutil.rmtree("output/pytest-pptx-slides", ignore_errors=True)


@pytest.mark.asyncio
async def test_render_none_values_dont_raise():
    """PPTXAgent handles None values at every key gracefully."""
    from agent.analyzers.pptx_agent import PPTXAgent

    none_synthesis = {
        "executive_summary": None,
        "market_landscape": None,
        "competitive_analysis": None,
        "strategic_implications": None,
        "recommendations": None,
        "outlook": None,
    }
    agent = PPTXAgent()
    result = await agent.render(none_synthesis, "pytest-pptx-none")

    try:
        assert result.endswith("board-deck.pptx")
    finally:
        shutil.rmtree("output/pytest-pptx-none", ignore_errors=True)
