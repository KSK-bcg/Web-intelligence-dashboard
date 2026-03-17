class WebIntelligenceError(Exception):
    """Base exception for all agent errors."""

# --- LinkedIn ---
class LinkedInAuthExpiredError(WebIntelligenceError):
    """Session cookies are expired or invalid."""

class LinkedInCaptchaError(WebIntelligenceError):
    """CAPTCHA triggered during LinkedIn traversal."""

class LinkedInRateLimitError(WebIntelligenceError):
    """LinkedIn rate limit (429) hit."""

class ProfileNotFoundError(WebIntelligenceError):
    """LinkedIn profile does not exist or is private."""

# --- Firecrawl ---
class FirecrawlAuthError(WebIntelligenceError):
    """Firecrawl API key is invalid or missing."""

class FirecrawlRateLimitError(WebIntelligenceError):
    """Firecrawl rate limit exceeded."""

class FirecrawlBlockedError(WebIntelligenceError):
    """Target site is blocking Firecrawl."""

class FirecrawlFetchError(WebIntelligenceError):
    """URL unreachable or returned error."""

# --- Claude / Agent ---
class AgentResponseParseError(WebIntelligenceError):
    """Claude response could not be parsed as expected JSON."""

class AgentRefusalError(WebIntelligenceError):
    """Claude refused to process the content."""

class AgentEmptyResponseError(WebIntelligenceError):
    """Claude returned an empty response."""

class ConfidenceBelowThresholdError(WebIntelligenceError):
    """Analysis confidence is too low to be useful."""

# --- Data / Graph ---
class OrgGraphCycleError(WebIntelligenceError):
    """Cycle detected in reporting chain graph."""

class InsufficientDataError(WebIntelligenceError):
    """Not enough data to produce meaningful output."""

class DeduplicationConflictError(WebIntelligenceError):
    """Cannot resolve entity deduplication conflict."""

class DataSchemaError(WebIntelligenceError):
    """Crawled data does not match expected schema."""

# --- Storage ---
class DatabaseLockError(WebIntelligenceError):
    """SQLite database is locked by another process."""

class StorageCapacityError(WebIntelligenceError):
    """Disk is full or storage quota exceeded."""

# v2: Competitive Intelligence
class FilingsFetchError(WebIntelligenceError):
    """Failed to fetch financial filing from SEC EDGAR or IR page."""
    pass

class FilingsParseError(WebIntelligenceError):
    """Failed to parse filing content into structured data."""
    pass

class EarningsFetchError(WebIntelligenceError):
    """Failed to fetch earnings transcript or analyst content."""
    pass

class FinancialExtractionError(WebIntelligenceError):
    """Claude failed to extract financial metrics from filing text."""
    pass

class PPTXRenderError(WebIntelligenceError):
    """Failed to render the BCG PowerPoint deck."""
    pass
