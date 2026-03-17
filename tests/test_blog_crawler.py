import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_fc_client():
    client = MagicMock()
    client.scrape_url.return_value = {
        "markdown": "# Post Title\n\nBody content here.",
        "metadata": {"title": "Post Title", "description": "A description"},
    }
    return client


def test_fail_fast_on_bad_auth():
    """BlogCrawler.__init__ calls verify_auth(), which must raise on bad key."""
    with patch("agent.crawlers.blog.firecrawl") as mock_fc:
        mock_fc.FirecrawlApp.return_value.scrape_url.side_effect = Exception("Unauthorized")
        with pytest.raises(Exception):  # FirecrawlAuthError
            from agent.crawlers.blog import BlogCrawler
            BlogCrawler(api_key="bad-key")


@pytest.mark.asyncio
async def test_scrape_returns_article_dict(mock_fc_client):
    from agent.crawlers.blog import BlogCrawler
    crawler = BlogCrawler.__new__(BlogCrawler)
    crawler.client = mock_fc_client
    crawler.name = "blog-crawler"
    crawler.logger = MagicMock()
    result = await crawler._scrape_url("https://example.com/post-1")
    assert result["title"] == "Post Title"
    assert "body" in result
    assert result["source_url"] == "https://example.com/post-1"


@pytest.mark.asyncio
async def test_crawl_site_returns_multiple_articles(mock_fc_client):
    mock_fc_client.crawl_url.return_value = {
        "data": [
            {"markdown": "# Article 1", "metadata": {"title": "Article 1", "sourceURL": "https://ex.com/1"}},
            {"markdown": "# Article 2", "metadata": {"title": "Article 2", "sourceURL": "https://ex.com/2"}},
        ]
    }
    from agent.crawlers.blog import BlogCrawler
    crawler = BlogCrawler.__new__(BlogCrawler)
    crawler.client = mock_fc_client
    crawler.name = "blog-crawler"
    crawler.logger = MagicMock()
    results = await crawler.run(url="https://ex.com/blog", max_pages=5)
    assert len(results) == 2
