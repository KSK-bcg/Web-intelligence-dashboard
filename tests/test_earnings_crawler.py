import pytest
from unittest.mock import MagicMock, patch


def make_search_result(url: str, title: str = "", markdown: str = ""):
    r = MagicMock()
    r.url = url
    r.title = title
    r.markdown = markdown
    return r


@pytest.fixture
def mock_app():
    with patch("agent.crawlers.earnings.FirecrawlApp") as MockApp:
        instance = MockApp.return_value
        instance.search.return_value = [
            make_search_result(
                "https://fool.com/earnings/epic-q4-2023-call",
                title="Epic Systems Q4 2023 Earnings Call Transcript",
                markdown="Revenue grew 8% in Q4 2023...",
            ),
            make_search_result(
                "https://reuters.com/epic-analyst-report",
                title="Epic Systems analyst report — price target raised",
                markdown="Analyst coverage initiation...",
            ),
        ]
        yield instance


@pytest.mark.asyncio
async def test_run_returns_earnings_items(mock_app):
    from agent.crawlers.earnings import EarningsCrawler
    with patch("agent.crawlers.earnings.FirecrawlApp", return_value=mock_app):
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"}):
            with patch("asyncio.sleep"):
                crawler = EarningsCrawler()
                crawler._app = mock_app
                results = await crawler.run(query="Epic Systems earnings 2023", companies=["Epic Systems"])

    assert len(results) == 2
    assert all(r["source"] == "earnings" for r in results)
    assert results[0]["source_type"] == "earnings_transcript"
    assert results[1]["source_type"] == "analyst_report"


@pytest.mark.asyncio
async def test_run_raises_on_search_failure():
    from agent.crawlers.earnings import EarningsCrawler
    from agent.exceptions import EarningsFetchError
    with patch("agent.crawlers.earnings.FirecrawlApp") as MockApp:
        mock_app = MockApp.return_value
        mock_app.search.side_effect = Exception("API down")
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"}):
            crawler = EarningsCrawler()
            crawler._app = mock_app
            with pytest.raises(EarningsFetchError):
                await crawler.run(query="Epic Systems earnings")


def test_classify_source_type_earnings():
    from agent.crawlers.earnings import _classify_source_type
    assert _classify_source_type("Epic Q3 2023 Earnings Call Transcript", "") == "earnings_transcript"


def test_classify_source_type_analyst():
    from agent.crawlers.earnings import _classify_source_type
    assert _classify_source_type("Epic Systems Analyst Report — price target raised", "") == "analyst_report"


def test_classify_source_type_news():
    from agent.crawlers.earnings import _classify_source_type
    assert _classify_source_type("Epic acquires startup", "https://reuters.com/epic") == "news"
