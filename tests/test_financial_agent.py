import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


FILING_ITEM = {
    "company": "Epic Systems",
    "period": "FY2023",
    "source_url": "https://epic.com/ar2023",
    "raw_text": "Epic annual report FY2023. Revenue $4B. Gross margin 72%.",
    "source": "filing",
}

EARNINGS_ITEM = {
    "title": "Epic Q4 2023 Earnings Call",
    "body": "We reported strong Q4 results...",
    "source_url": "https://fool.com/epic-q4",
    "source_type": "earnings_transcript",
    "company": "Epic Systems",
    "date": "2024-01-15",
    "source": "earnings",
}

GOOD_RESPONSE = {
    "company": "Epic Systems",
    "period": "FY2023",
    "metrics": {
        "revenue_usd_millions": 4000.0,
        "revenue_yoy_growth_pct": 8.5,
        "gross_margin_pct": 72.0,
        "operating_margin_pct": 25.0,
        "net_margin_pct": 18.0,
        "ebitda_usd_millions": 1100.0,
        "rd_spend_pct_revenue": 15.0,
        "capex_pct_revenue": 4.0,
    },
    "key_risks": ["Competition from Oracle Health"],
    "confidence": "high",
}


def make_response(text: str):
    content = MagicMock()
    content.text = text
    resp = MagicMock()
    resp.content = [content]
    return resp


@pytest.fixture
def mock_anthropic():
    with patch("agent.analyzers.financial.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = make_response(json.dumps(GOOD_RESPONSE))
        yield instance


@pytest.mark.asyncio
async def test_run_processes_filing_items(mock_anthropic):
    from agent.analyzers.financial import FinancialAgent
    with patch("agent.analyzers.financial.Anthropic", return_value=mock_anthropic):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = FinancialAgent()
            agent._client = mock_anthropic
            results = await agent.run([FILING_ITEM, EARNINGS_ITEM])

    # Only filing item processed
    assert len(results) == 1
    assert results[0]["company"] == "Epic Systems"
    assert results[0]["metrics"]["revenue_usd_millions"] == 4000.0
    assert results[0]["confidence"] == "high"


@pytest.mark.asyncio
async def test_run_skips_non_filing_items():
    from agent.analyzers.financial import FinancialAgent
    with patch("agent.analyzers.financial.Anthropic") as MockClient:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = FinancialAgent()
            results = await agent.run([EARNINGS_ITEM])

    assert results == []


@pytest.mark.asyncio
async def test_run_returns_low_confidence_on_bad_json(mock_anthropic):
    from agent.analyzers.financial import FinancialAgent
    mock_anthropic.messages.create.return_value = make_response("NOT VALID JSON {{{")
    with patch("agent.analyzers.financial.Anthropic", return_value=mock_anthropic):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = FinancialAgent()
            agent._client = mock_anthropic
            results = await agent.run([FILING_ITEM])

    assert len(results) == 1
    assert results[0]["confidence"] == "low"
    assert results[0]["metrics"]["revenue_usd_millions"] is None


@pytest.mark.asyncio
async def test_run_returns_low_confidence_on_api_error(mock_anthropic):
    from agent.analyzers.financial import FinancialAgent
    mock_anthropic.messages.create.side_effect = Exception("API timeout")
    with patch("agent.analyzers.financial.Anthropic", return_value=mock_anthropic):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            agent = FinancialAgent()
            agent._client = mock_anthropic
            results = await agent.run([FILING_ITEM])

    assert len(results) == 1
    assert results[0]["confidence"] == "low"
