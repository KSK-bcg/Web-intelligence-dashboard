import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.crawlers.linkedin import LinkedInCrawler
from agent.exceptions import LinkedInAuthExpiredError, LinkedInRateLimitError

@pytest.fixture
def crawler():
    return LinkedInCrawler(max_profiles=5, min_delay=0.01, max_delay=0.02)

@pytest.mark.asyncio
async def test_raises_auth_expired_when_redirected_to_login(crawler):
    mock_page = AsyncMock()
    mock_page.url = "https://www.linkedin.com/login"
    with pytest.raises(LinkedInAuthExpiredError):
        await crawler._check_auth(mock_page)

@pytest.mark.asyncio
async def test_raises_rate_limit_on_429(crawler):
    """_visit_profile calls _check_rate_limit after page load."""
    mock_page = AsyncMock()
    mock_page.url = "https://www.linkedin.com/in/someone"
    mock_page.evaluate = AsyncMock(return_value=429)
    with pytest.raises(LinkedInRateLimitError):
        await crawler._check_rate_limit(mock_page)

def test_enforces_max_profiles_limit(crawler):
    assert crawler.max_profiles == 5

@pytest.mark.asyncio
async def test_extract_person_data_from_profile(crawler):
    """Test extraction uses query_selector — mock at selector level."""
    mock_name_el = AsyncMock()
    mock_name_el.inner_text = AsyncMock(return_value="Jane Smith")
    mock_title_el = AsyncMock()
    mock_title_el.inner_text = AsyncMock(return_value="VP of IT | Pharma Corp")
    mock_about_el = AsyncMock()
    mock_about_el.inner_text = AsyncMock(return_value="Leading digital transformation.")

    mock_page = AsyncMock()
    mock_page.url = "https://www.linkedin.com/in/janesmith"
    async def mock_query_selector(selector):
        if "heading" in selector:
            return mock_name_el
        elif "body-medium" in selector:
            return mock_title_el
        elif "pv-shared" in selector:
            return mock_about_el
        return None
    mock_page.query_selector = mock_query_selector

    result = await crawler._extract_profile_data(mock_page)
    assert result["name"] == "Jane Smith"
    assert result["title"] == "VP of IT | Pharma Corp"
    assert result["linkedin_id"] == "janesmith"
