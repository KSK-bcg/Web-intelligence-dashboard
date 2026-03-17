import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_fc_client():
    client = MagicMock()
    # v4 API: scrape() returns an object with .markdown and .metadata
    scrape_result = MagicMock()
    scrape_result.markdown = "# Post Title\n\nBody content here."
    scrape_result.metadata = {"title": "Post Title", "description": "A description"}
    client.scrape.return_value = scrape_result
    return client


def test_fail_fast_on_bad_auth():
    """BlogCrawler.__init__ calls verify_auth(), which must raise on bad key."""
    with patch("agent.crawlers.blog.firecrawl") as mock_fc:
        mock_fc.FirecrawlApp.return_value.scrape.side_effect = Exception("Unauthorized")
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
    # v4 API: crawl() returns an object with .data list of scrape result objects
    item1 = MagicMock()
    item1.markdown = "# Article 1"
    item1.metadata = {"title": "Article 1", "sourceURL": "https://ex.com/1"}
    item2 = MagicMock()
    item2.markdown = "# Article 2"
    item2.metadata = {"title": "Article 2", "sourceURL": "https://ex.com/2"}
    crawl_result = MagicMock()
    crawl_result.data = [item1, item2]
    mock_fc_client.crawl.return_value = crawl_result

    from agent.crawlers.blog import BlogCrawler
    crawler = BlogCrawler.__new__(BlogCrawler)
    crawler.client = mock_fc_client
    crawler.name = "blog-crawler"
    crawler.logger = MagicMock()
    results = await crawler.run(url="https://ex.com/blog", max_pages=5)
    assert len(results) == 2
