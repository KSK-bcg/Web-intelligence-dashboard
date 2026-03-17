import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def make_search_result(url: str):
    r = MagicMock()
    r.url = url
    return r


def make_scrape_result(markdown: str):
    r = MagicMock()
    r.markdown = markdown
    return r


SAMPLE_TEXT = """
Epic Systems Annual Report 2023
Fiscal year ended December 31, 2023.
Revenue for FY2023 was $4.0 billion, up 8% year-over-year.
"""


@pytest.fixture
def mock_app():
    with patch("agent.crawlers.filings.FirecrawlApp") as MockApp:
        instance = MockApp.return_value
        instance.search.return_value = [make_search_result("https://epic.com/annual-report")]
        instance.scrape.return_value = make_scrape_result(SAMPLE_TEXT)
        yield instance


@pytest.mark.asyncio
async def test_run_returns_filing_items(mock_app):
    from agent.crawlers.filings import FilingsCrawler
    with patch("agent.crawlers.filings.FirecrawlApp", return_value=mock_app):
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"}):
            with patch("asyncio.sleep"):
                crawler = FilingsCrawler()
                crawler._app = mock_app
                results = await crawler.run(companies=["Epic Systems"])

    assert len(results) >= 1
    assert results[0]["source"] == "filing"
    assert results[0]["company"] == "Epic Systems"
    assert results[0]["raw_text"] == SAMPLE_TEXT


@pytest.mark.asyncio
async def test_run_skips_failed_company(mock_app):
    from agent.crawlers.filings import FilingsCrawler
    from agent.exceptions import FilingsFetchError

    mock_app.search.side_effect = Exception("Network error")
    with patch("agent.crawlers.filings.FirecrawlApp", return_value=mock_app):
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"}):
            with patch("asyncio.sleep"):
                crawler = FilingsCrawler()
                crawler._app = mock_app
                results = await crawler.run(companies=["FailCo"])

    assert results == []


@pytest.mark.asyncio
async def test_extract_period_fy2023():
    from agent.crawlers.filings import FilingsCrawler
    with patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"}):
        with patch("agent.crawlers.filings.FirecrawlApp"):
            crawler = FilingsCrawler()
    period = crawler._extract_period("Annual Report 2023\nFY2023 results")
    assert period == "FY2023"
