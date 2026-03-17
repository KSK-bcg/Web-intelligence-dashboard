# Competitive Intelligence Platform v2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FilingsCrawler, EarningsCrawler, FinancialAgent, SynthesisAgent, and PPTXAgent to turn the web intelligence agent into a full competitive research platform that outputs a 5-slide BCG-style PowerPoint.

**Architecture:** Two new crawlers (SEC filings + earnings transcripts) feed two new analyzers (financial extraction + cross-source synthesis), which feed a new PPTXAgent that renders a BCG-style 5-slide deck. The orchestrator gains four new goal types (`financial`, `market_intel`, `synthesis`, `board_deck`). All existing v1 behavior is unchanged.

**Tech Stack:** Python 3.9.6, python-pptx>=0.6.21, matplotlib>=3.8, firecrawl-py v4, anthropic SDK, SQLModel, FastAPI, Next.js 14. Use `Optional[X]`, `List[X]`, `Dict[X,Y]` from `typing` — never `X | None` or `list[x]` syntax.

---

## Chunk 1: Foundation — Exceptions, Store, Requirements

### Task 1: New Exceptions + Requirements

**Files:**
- Modify: `agent/exceptions.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add 5 new exception classes to `agent/exceptions.py`**

Append after the existing exception classes:

```python
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
```

- [ ] **Step 2: Add python-pptx and matplotlib to requirements.txt**

Append to requirements.txt under `# Export (v2 ready)`:

```
python-pptx>=0.6.21
matplotlib>=3.8
```

- [ ] **Step 3: Install new dependencies**

```bash
cd ~/projects/web-intelligence-agent
source .venv/bin/activate
pip install "python-pptx>=0.6.21" "matplotlib>=3.8"
```

Expected: Successfully installed python-pptx-X.X matplotlib-X.X

- [ ] **Step 4: Verify imports work**

```bash
python -c "from pptx import Presentation; import matplotlib; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agent/exceptions.py requirements.txt
git commit -m "feat(v2): add FilingsFetchError, EarningsFetchError, FinancialExtractionError, PPTXRenderError exceptions; add python-pptx + matplotlib deps"
```

---

### Task 2: FinancialRecord in SQLite Store

**Files:**
- Modify: `agent/store.py`
- Create: `tests/test_financial_store.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_financial_store.py
import pytest
from agent.store import Store


def test_save_and_retrieve_financial_record():
    store = Store(db_path=":memory:")
    store.init_db()
    run_id = store.create_run(goal="test", target="epic")

    store.save_financial(run_id=run_id, financial={
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
    })

    records = store.list_financials(run_id=run_id)
    assert len(records) == 1
    assert records[0].company == "Epic Systems"
    assert records[0].revenue_usd_millions == 4000.0
    assert records[0].gross_margin_pct == 72.0
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
source .venv/bin/activate
pytest tests/test_financial_store.py -v
```

Expected: FAIL with `AttributeError: 'Store' object has no attribute 'save_financial'`

- [ ] **Step 3: Add FinancialRecord model and methods to `agent/store.py`**

Add after existing imports at top of store.py:
```python
from uuid import uuid4
```

Add the model class after `ChangeEvent`:
```python
class FinancialRecord(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4())[:8], primary_key=True)
    run_id: str = Field(index=True)
    company: str
    period: str
    revenue_usd_millions: Optional[float] = None
    revenue_yoy_growth_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    ebitda_usd_millions: Optional[float] = None
    rd_spend_pct_revenue: Optional[float] = None
    capex_pct_revenue: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

Add `FinancialRecord` to the `SQLModel.metadata.create_all` call in `init_db()`. Then add methods:

```python
def save_financial(self, run_id: str, financial: dict) -> "FinancialRecord":
    metrics = financial.get("metrics", {})
    record = FinancialRecord(
        run_id=run_id,
        company=financial.get("company", ""),
        period=financial.get("period", ""),
        revenue_usd_millions=metrics.get("revenue_usd_millions"),
        revenue_yoy_growth_pct=metrics.get("revenue_yoy_growth_pct"),
        gross_margin_pct=metrics.get("gross_margin_pct"),
        operating_margin_pct=metrics.get("operating_margin_pct"),
        net_margin_pct=metrics.get("net_margin_pct"),
        ebitda_usd_millions=metrics.get("ebitda_usd_millions"),
        rd_spend_pct_revenue=metrics.get("rd_spend_pct_revenue"),
        capex_pct_revenue=metrics.get("capex_pct_revenue"),
    )
    with Session(self.engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record

def list_financials(self, run_id: str) -> List["FinancialRecord"]:
    with Session(self.engine) as session:
        return list(session.exec(
            select(FinancialRecord).where(FinancialRecord.run_id == run_id)
        ))
```

- [ ] **Step 4: Run test — verify PASS**

```bash
pytest tests/test_financial_store.py -v
```

Expected: PASS

- [ ] **Step 5: Run full suite — no regressions**

```bash
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
```

Expected: All existing tests + new test pass.

- [ ] **Step 6: Commit**

```bash
git add agent/store.py tests/test_financial_store.py
git commit -m "feat(v2): add FinancialRecord model + save_financial/list_financials to Store"
```

---

## Chunk 2: Crawlers — FilingsCrawler + EarningsCrawler

### Task 3: FilingsCrawler

**Files:**
- Create: `agent/crawlers/filings.py`
- Create: `tests/test_filings_crawler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_filings_crawler.py
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_fc_client():
    client = MagicMock()
    result = MagicMock()
    result.markdown = "# Epic Systems Annual Report FY2023\n\nRevenue: $4.0B\nGross margin: 72%"
    result.metadata = {"title": "Epic 10-K 2023", "sourceURL": "https://sec.gov/epic-10k"}
    client.scrape.return_value = result
    search_result = MagicMock()
    search_result.data = [MagicMock(url="https://sec.gov/epic-10k", title="Epic 10-K 2023")]
    client.search.return_value = search_result
    return client


@pytest.mark.asyncio
async def test_run_returns_filing_dicts(mock_fc_client):
    from agent.crawlers.filings import FilingsCrawler
    crawler = FilingsCrawler.__new__(FilingsCrawler)
    crawler.client = mock_fc_client
    crawler.name = "filings-crawler"
    crawler.logger = MagicMock()

    results = await crawler.run(companies=["Epic Systems"])
    assert len(results) >= 1
    assert results[0]["source"] == "filing"
    assert results[0]["company"] == "Epic Systems"
    assert "raw_text" in results[0]


@pytest.mark.asyncio
async def test_run_returns_empty_list_on_fetch_error():
    from agent.crawlers.filings import FilingsCrawler
    from agent.exceptions import FilingsFetchError
    crawler = FilingsCrawler.__new__(FilingsCrawler)
    crawler.name = "filings-crawler"
    crawler.logger = MagicMock()
    crawler.client = MagicMock()
    crawler.client.search.side_effect = Exception("Network error")

    # Should not raise — logs and returns empty
    results = await crawler.run(companies=["Epic Systems"])
    assert results == []


def test_rate_limit_delay_constant():
    from agent.crawlers.filings import FilingsCrawler
    assert FilingsCrawler.DELAY_SECONDS == 2.0
    assert FilingsCrawler.MAX_FILINGS == 5
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
pytest tests/test_filings_crawler.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent.crawlers.filings'`

- [ ] **Step 3: Implement `agent/crawlers/filings.py`**

```python
# agent/crawlers/filings.py
"""
FilingsCrawler — crawls public financial filings (10-K, annual reports).
Sources: SEC EDGAR full-text search → Firecrawl scrape of filing URL.
Rate limiting: 2s delay, max 5 filings per run.
"""
import asyncio
import logging
import os
from typing import List, Optional

import firecrawl

from agent.base_agent import BaseAgent
from agent.exceptions import FilingsFetchError

logger = logging.getLogger(__name__)


class FilingsCrawler(BaseAgent):
    DELAY_SECONDS = 2.0
    MAX_FILINGS = 5

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(name="filings-crawler")
        key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            raise FilingsFetchError("FIRECRAWL_API_KEY not set in .env")
        self.client = firecrawl.FirecrawlApp(api_key=key)

    async def run(
        self,
        companies: List[str],
        filing_types: Optional[List[str]] = None,
    ) -> List[dict]:
        """Crawl filings for a list of companies. Returns list of filing dicts."""
        if filing_types is None:
            filing_types = ["10-K", "annual report"]

        results = []
        count = 0
        for company in companies:
            if count >= self.MAX_FILINGS:
                break
            try:
                filing = await self._fetch_filing(company, filing_types)
                if filing:
                    results.append(filing)
                    count += 1
            except Exception as e:
                logger.warning("Could not fetch filing for %s: %s", company, e)
            await asyncio.sleep(self.DELAY_SECONDS)
        return results

    async def _fetch_filing(self, company: str, filing_types: List[str]) -> Optional[dict]:
        """Search for and scrape one filing for a company."""
        query = f"{company} {filing_types[0]} annual report financial results"
        try:
            search_result = self.client.search(query, params={"limit": 3})
        except Exception as e:
            raise FilingsFetchError(f"Search failed for {company}: {e}") from e

        items = search_result.data if hasattr(search_result, "data") else []
        for item in items:
            url = getattr(item, "url", None) or item.get("url", "") if isinstance(item, dict) else ""
            if not url:
                continue
            try:
                scraped = self.client.scrape(url)
                raw_text = scraped.markdown if hasattr(scraped, "markdown") else ""
                if not raw_text or len(raw_text) < 200:
                    continue
                metadata = scraped.metadata if hasattr(scraped, "metadata") else {}
                title = (
                    getattr(metadata, "title", None)
                    or (metadata.get("title") if isinstance(metadata, dict) else None)
                    or f"{company} Filing"
                )
                return {
                    "company": company,
                    "filing_type": filing_types[0],
                    "period": self._extract_period(raw_text),
                    "source_url": url,
                    "raw_text": raw_text[:50000],  # cap at 50k chars
                    "title": title,
                    "source": "filing",
                }
            except Exception as e:
                logger.debug("Scrape failed for %s: %s", url, e)
                continue
        return None

    def _extract_period(self, text: str) -> str:
        """Best-effort period extraction from filing text."""
        import re
        match = re.search(r"(?:fiscal year|FY|year ended)[^\d]*(\d{4})", text, re.IGNORECASE)
        if match:
            return f"FY{match.group(1)}"
        match = re.search(r"\b(20\d{2})\b", text)
        return f"FY{match.group(1)}" if match else "FY_UNKNOWN"
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
pytest tests/test_filings_crawler.py -v
```

Expected: 3/3 PASS

- [ ] **Step 5: Commit**

```bash
git add agent/crawlers/filings.py tests/test_filings_crawler.py
git commit -m "feat(v2): FilingsCrawler — SEC/IR filing search + scrape via Firecrawl"
```

---

### Task 4: EarningsCrawler

**Files:**
- Create: `agent/crawlers/earnings.py`
- Create: `tests/test_earnings_crawler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_earnings_crawler.py
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_fc_client():
    client = MagicMock()
    search_result = MagicMock()
    item1 = MagicMock()
    item1.url = "https://fool.com/earnings/epic-q4-2023"
    item1.title = "Epic Q4 2023 Earnings Call Transcript"
    item2 = MagicMock()
    item2.url = "https://seekingalpha.com/epic-analysis"
    item2.title = "Epic Systems: Strong Growth Continues"
    search_result.data = [item1, item2]
    client.search.return_value = search_result

    scrape_result = MagicMock()
    scrape_result.markdown = "# Epic Q4 2023\n\nCEO: Revenue grew 8% YoY..."
    scrape_result.metadata = {"title": "Epic Q4 Transcript", "sourceURL": "https://fool.com/epic"}
    client.scrape.return_value = scrape_result
    return client


@pytest.mark.asyncio
async def test_run_returns_earnings_dicts(mock_fc_client):
    from agent.crawlers.earnings import EarningsCrawler
    crawler = EarningsCrawler.__new__(EarningsCrawler)
    crawler.client = mock_fc_client
    crawler.name = "earnings-crawler"
    crawler.logger = MagicMock()

    results = await crawler.run(query="Epic Systems health IT", max_results=5)
    assert len(results) >= 1
    assert results[0]["source"] == "earnings"
    assert "body" in results[0]
    assert "title" in results[0]


@pytest.mark.asyncio
async def test_run_respects_max_results(mock_fc_client):
    from agent.crawlers.earnings import EarningsCrawler
    crawler = EarningsCrawler.__new__(EarningsCrawler)
    crawler.client = mock_fc_client
    crawler.name = "earnings-crawler"
    crawler.logger = MagicMock()

    results = await crawler.run(query="health IT market", max_results=1)
    assert len(results) <= 1


def test_rate_limit_constants():
    from agent.crawlers.earnings import EarningsCrawler
    assert EarningsCrawler.DELAY_SECONDS == 1.5
    assert EarningsCrawler.MAX_RESULTS == 15
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
pytest tests/test_earnings_crawler.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `agent/crawlers/earnings.py`**

```python
# agent/crawlers/earnings.py
"""
EarningsCrawler — crawls earnings transcripts, analyst reports, news.
Sources: Firecrawl search → scrape top results.
Rate limiting: 1.5s delay, max 15 results per run.
"""
import asyncio
import logging
import os
from typing import List, Optional

import firecrawl

from agent.base_agent import BaseAgent
from agent.exceptions import EarningsFetchError

logger = logging.getLogger(__name__)

_TRANSCRIPT_SIGNALS = ["transcript", "earnings call", "q1 ", "q2 ", "q3 ", "q4 ", "annual report"]
_ANALYST_SIGNALS = ["analysis", "outlook", "forecast", "rating", "target price"]


def _classify_source_type(title: str) -> str:
    t = title.lower()
    if any(s in t for s in _TRANSCRIPT_SIGNALS):
        return "earnings_transcript"
    if any(s in t for s in _ANALYST_SIGNALS):
        return "analyst_report"
    return "news"


class EarningsCrawler(BaseAgent):
    DELAY_SECONDS = 1.5
    MAX_RESULTS = 15

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(name="earnings-crawler")
        key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            raise EarningsFetchError("FIRECRAWL_API_KEY not set in .env")
        self.client = firecrawl.FirecrawlApp(api_key=key)

    async def run(
        self,
        query: str,
        company_name: Optional[str] = None,
        max_results: int = 10,
    ) -> List[dict]:
        """Search and scrape earnings/analyst content for a query."""
        max_results = min(max_results, self.MAX_RESULTS)
        results = []

        try:
            search_result = self.client.search(query, params={"limit": max_results})
        except Exception as e:
            logger.warning("EarningsCrawler search failed for '%s': %s", query, e)
            return []

        items = search_result.data if hasattr(search_result, "data") else []
        for item in items[:max_results]:
            url = getattr(item, "url", None) or ""
            title = getattr(item, "title", None) or "Untitled"
            if not url:
                continue
            try:
                scraped = self.client.scrape(url)
                body = scraped.markdown if hasattr(scraped, "markdown") else ""
                if not body or len(body) < 100:
                    continue
                results.append({
                    "title": title,
                    "body": body[:30000],
                    "source_url": url,
                    "source_type": _classify_source_type(title),
                    "company": company_name or "",
                    "date": "",
                    "source": "earnings",
                })
            except Exception as e:
                logger.debug("Scrape failed for %s: %s", url, e)
            await asyncio.sleep(self.DELAY_SECONDS)

        return results
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
pytest tests/test_earnings_crawler.py -v
```

Expected: 3/3 PASS

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add agent/crawlers/earnings.py tests/test_earnings_crawler.py
git commit -m "feat(v2): EarningsCrawler — earnings transcripts + analyst coverage via Firecrawl search"
```

---

## Chunk 3: Analyzers — FinancialAgent + SynthesisAgent

### Task 5: FinancialAgent

**Files:**
- Create: `agent/analyzers/financial.py`
- Create: `tests/test_financial_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_financial_agent.py
import pytest
from unittest.mock import MagicMock, patch


MOCK_FILING = {
    "company": "Epic Systems",
    "filing_type": "10-K",
    "period": "FY2023",
    "source_url": "https://sec.gov/epic",
    "raw_text": "Revenue was $4.0 billion in fiscal 2023, up 8% from prior year. Gross margin 72%.",
    "source": "filing",
}

MOCK_EARNINGS = {
    "title": "Epic Q4",
    "body": "Strong quarter",
    "source": "earnings",  # should be skipped by FinancialAgent
}

MOCK_CLAUDE_RESPONSE = """{
  "company": "Epic Systems",
  "period": "FY2023",
  "metrics": {
    "revenue_usd_millions": 4000.0,
    "revenue_yoy_growth_pct": 8.0,
    "gross_margin_pct": 72.0,
    "operating_margin_pct": null,
    "net_margin_pct": null,
    "ebitda_usd_millions": null,
    "rd_spend_pct_revenue": null,
    "capex_pct_revenue": null
  },
  "key_risks": ["Competition from Oracle"],
  "confidence": "medium"
}"""


@pytest.mark.asyncio
async def test_extracts_metrics_from_filing():
    with patch("agent.analyzers.financial.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=MOCK_CLAUDE_RESPONSE)]
        mock_client.messages.create.return_value = mock_msg

        from agent.analyzers.financial import FinancialAgent
        agent = FinancialAgent()
        result = await agent.run([MOCK_FILING])

    assert len(result) == 1
    assert result[0]["company"] == "Epic Systems"
    assert result[0]["metrics"]["revenue_usd_millions"] == 4000.0
    assert result[0]["confidence"] == "medium"


@pytest.mark.asyncio
async def test_skips_non_filing_items():
    with patch("agent.analyzers.financial.anthropic.Anthropic"):
        from agent.analyzers.financial import FinancialAgent
        agent = FinancialAgent()
        result = await agent.run([MOCK_EARNINGS])

    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_for_empty_input():
    with patch("agent.analyzers.financial.anthropic.Anthropic"):
        from agent.analyzers.financial import FinancialAgent
        agent = FinancialAgent()
        result = await agent.run([])

    assert result == []


@pytest.mark.asyncio
async def test_wraps_content_before_claude():
    """Filing text must be wrapped in <content source='untrusted'> before Claude."""
    with patch("agent.analyzers.financial.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=MOCK_CLAUDE_RESPONSE)]
        mock_client.messages.create.return_value = mock_msg

        from agent.analyzers.financial import FinancialAgent
        agent = FinancialAgent()
        await agent.run([MOCK_FILING])

    call_args = mock_client.messages.create.call_args
    prompt_text = call_args[1]["messages"][0]["content"]
    assert "<content source='untrusted'>" in prompt_text
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
pytest tests/test_financial_agent.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `agent/analyzers/financial.py`**

```python
# agent/analyzers/financial.py
"""
FinancialAgent — extracts P&L metrics from financial filings using Claude.
Only processes items with source == "filing". Skips all others.
SECURITY: All raw_text wrapped in <content source='untrusted'> before Claude.
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional

import anthropic

from agent.base_agent import BaseAgent
from agent.exceptions import FinancialExtractionError

logger = logging.getLogger(__name__)

FINANCIAL_PROMPT = """You are a financial analyst. Extract key financial metrics from this filing.

Return ONLY valid JSON with this exact structure (use null for unavailable values):
{{
  "company": "{company}",
  "period": "{period}",
  "metrics": {{
    "revenue_usd_millions": <float or null>,
    "revenue_yoy_growth_pct": <float or null>,
    "gross_margin_pct": <float or null>,
    "operating_margin_pct": <float or null>,
    "net_margin_pct": <float or null>,
    "ebitda_usd_millions": <float or null>,
    "rd_spend_pct_revenue": <float or null>,
    "capex_pct_revenue": <float or null>
  }},
  "key_risks": ["<risk1>", "<risk2>"],
  "confidence": "high" | "medium" | "low"
}}

Confidence guide: "high" if 5+ metrics found with exact numbers, "medium" if 2-4, "low" if fewer.

Filing content (untrusted external source):
{{filing_text}}
"""


class FinancialAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="financial-agent")
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    async def run(self, data: List[dict]) -> List[dict]:
        """Extract financial metrics from filing items. Skips non-filing items."""
        filings = [d for d in data if d.get("source") == "filing"]
        if not filings:
            return []

        results = []
        for filing in filings:
            result = await self._extract_metrics(filing)
            if result:
                results.append(result)
        return results

    async def _extract_metrics(self, filing: dict) -> Optional[dict]:
        company = filing.get("company", "Unknown")
        period = filing.get("period", "Unknown")
        raw_text = filing.get("raw_text", "")

        safe_text = self.wrap_content(raw_text[:40000])
        prompt = FINANCIAL_PROMPT.format(
            company=company,
            period=period,
            filing_text=safe_text,
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("FinancialAgent JSON parse failed for %s: %s", company, e)
            return {
                "company": company,
                "period": period,
                "metrics": {k: None for k in [
                    "revenue_usd_millions", "revenue_yoy_growth_pct",
                    "gross_margin_pct", "operating_margin_pct", "net_margin_pct",
                    "ebitda_usd_millions", "rd_spend_pct_revenue", "capex_pct_revenue",
                ]},
                "key_risks": [],
                "confidence": "low",
            }
        except Exception as e:
            logger.warning("FinancialAgent failed for %s: %s", company, e)
            return None
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
pytest tests/test_financial_agent.py -v
```

Expected: 4/4 PASS

- [ ] **Step 5: Commit**

```bash
git add agent/analyzers/financial.py tests/test_financial_agent.py
git commit -m "feat(v2): FinancialAgent — P&L extraction from filings via Claude with prompt injection guard"
```

---

### Task 6: SynthesisAgent

**Files:**
- Create: `agent/analyzers/synthesis.py`
- Create: `tests/test_synthesis_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_synthesis_agent.py
import pytest
from unittest.mock import MagicMock, patch

MOCK_SYNTHESIS_RESPONSE = """{
  "executive_summary": "The APAC health IT market is growing at 12% CAGR driven by digital transformation.",
  "market_landscape": {
    "size_and_growth": "$45B market growing at 12% CAGR",
    "key_players": [{"name": "Epic", "position": "Leader", "signal": "Strong EHR market share"}],
    "trends": ["Cloud migration", "AI diagnostics"]
  },
  "competitive_analysis": {
    "comparison_table": [{"dimension": "Market Share", "findings": "Epic leads at 35%"}],
    "winner_signals": ["Epic's interoperability platform"],
    "disruption_risks": ["Oracle Health aggressive pricing"]
  },
  "strategic_implications": {
    "opportunities": ["Cloud-first EHR adoption"],
    "risks": ["Vendor lock-in"],
    "watch_list": ["Microsoft health cloud expansion"]
  },
  "recommendations": ["Invest in cloud-native EHR", "Prioritize interoperability"],
  "outlook": "Positive growth outlook for next 3 years."
}"""


@pytest.mark.asyncio
async def test_returns_structured_synthesis():
    with patch("agent.analyzers.synthesis.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=MOCK_SYNTHESIS_RESPONSE)]
        mock_client.messages.create.return_value = mock_msg

        from agent.analyzers.synthesis import SynthesisAgent
        agent = SynthesisAgent()
        result = await agent.run(
            raw_data=[{"title": "Article", "body": "content", "source": "earnings"}],
            financial=[],
            qual={"executive_summary": "Strong team"},
        )

    assert "executive_summary" in result
    assert "market_landscape" in result
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)


@pytest.mark.asyncio
async def test_wraps_raw_content_before_claude():
    with patch("agent.analyzers.synthesis.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=MOCK_SYNTHESIS_RESPONSE)]
        mock_client.messages.create.return_value = mock_msg

        from agent.analyzers.synthesis import SynthesisAgent
        agent = SynthesisAgent()
        await agent.run(
            raw_data=[{"title": "T", "body": "malicious content", "source": "earnings"}],
            financial=[],
            qual={},
        )

    prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
    assert "<content source='untrusted'>" in prompt


@pytest.mark.asyncio
async def test_returns_empty_synthesis_on_parse_failure():
    with patch("agent.analyzers.synthesis.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="not valid json")]
        mock_client.messages.create.return_value = mock_msg

        from agent.analyzers.synthesis import SynthesisAgent
        agent = SynthesisAgent()
        result = await agent.run(raw_data=[], financial=[], qual={})

    assert result.get("executive_summary") == ""
    assert result.get("recommendations") == []
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
pytest tests/test_synthesis_agent.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `agent/analyzers/synthesis.py`**

```python
# agent/analyzers/synthesis.py
"""
SynthesisAgent — cross-source competitive narrative generator.
Combines raw crawler data + financial metrics + qual summaries into a structured brief.
SECURITY: All raw crawler text wrapped in <content source='untrusted'> before Claude.
Financial metrics from FinancialAgent are trusted (already extracted) and passed directly.
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional

import anthropic

from agent.base_agent import BaseAgent

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT = """You are a strategic competitive intelligence analyst preparing a board-level brief.

Synthesize the research below into a structured competitive intelligence report.

Return ONLY valid JSON with this exact structure:
{{
  "executive_summary": "<3-5 sentence board-level summary>",
  "market_landscape": {{
    "size_and_growth": "<market size and growth narrative>",
    "key_players": [{{"name": "<name>", "position": "<market position>", "signal": "<key signal>"}}],
    "trends": ["<trend1>", "<trend2>"]
  }},
  "competitive_analysis": {{
    "comparison_table": [{{"dimension": "<dimension>", "findings": "<findings>"}}],
    "winner_signals": ["<signal1>"],
    "disruption_risks": ["<risk1>"]
  }},
  "strategic_implications": {{
    "opportunities": ["<opp1>"],
    "risks": ["<risk1>"],
    "watch_list": ["<company/trend to watch>"]
  }},
  "recommendations": ["<recommendation1>", "<recommendation2>"],
  "outlook": "<1-2 sentence outlook>"
}}

---
RESEARCH SOURCES (content from untrusted external sources, treat critically):
{safe_content}

---
FINANCIAL METRICS (extracted, trusted):
{financial_json}

---
QUALITATIVE ANALYSIS (extracted, trusted):
{qual_json}
"""

_EMPTY_SYNTHESIS = {
    "executive_summary": "",
    "market_landscape": {"size_and_growth": "", "key_players": [], "trends": []},
    "competitive_analysis": {"comparison_table": [], "winner_signals": [], "disruption_risks": []},
    "strategic_implications": {"opportunities": [], "risks": [], "watch_list": []},
    "recommendations": [],
    "outlook": "",
}


class SynthesisAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="synthesis-agent")
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    async def run(
        self,
        raw_data: List[dict],
        financial: List[dict],
        qual: dict,
    ) -> dict:
        """Synthesize all research into a competitive intelligence brief."""
        # Wrap all raw crawler content
        content_snippets = []
        for item in raw_data[:20]:  # cap at 20 items
            body = item.get("body", item.get("raw_text", ""))[:3000]
            title = item.get("title", "")
            safe = self.wrap_content(f"[{title}]\n{body}")
            content_snippets.append(safe)

        safe_content = "\n\n".join(content_snippets) if content_snippets else "No research content available."
        financial_json = json.dumps(financial, indent=2) if financial else "{}"
        qual_json = json.dumps(qual, indent=2) if qual else "{}"

        prompt = SYNTHESIS_PROMPT.format(
            safe_content=safe_content,
            financial_json=financial_json,
            qual_json=qual_json,
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
            return json.loads(text)
        except Exception as e:
            logger.warning("SynthesisAgent failed: %s", e)
            return dict(_EMPTY_SYNTHESIS)
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
pytest tests/test_synthesis_agent.py -v
```

Expected: 3/3 PASS

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add agent/analyzers/synthesis.py tests/test_synthesis_agent.py
git commit -m "feat(v2): SynthesisAgent — cross-source competitive narrative with prompt injection guard"
```

---

## Chunk 4: PPTXAgent — BCG PowerPoint Generator

### Task 7: PPTXAgent

**Files:**
- Create: `agent/analyzers/pptx_agent.py`
- Create: `tests/test_pptx_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pptx_agent.py
import os
import pytest
import tempfile
from pptx import Presentation


MOCK_SYNTHESIS = {
    "executive_summary": "The APAC health IT market is growing strongly.",
    "market_landscape": {
        "size_and_growth": "$45B market at 12% CAGR",
        "key_players": [{"name": "Epic", "position": "Leader", "signal": "35% share"}],
        "trends": ["Cloud migration", "AI diagnostics"],
    },
    "competitive_analysis": {
        "comparison_table": [{"dimension": "Market Share", "findings": "Epic 35%, Cerner 20%"}],
        "winner_signals": ["Epic interoperability"],
        "disruption_risks": ["Oracle pricing"],
    },
    "strategic_implications": {
        "opportunities": ["Cloud-native EHR"],
        "risks": ["Vendor lock-in"],
        "watch_list": ["Microsoft health cloud"],
    },
    "recommendations": ["Invest in cloud EHR", "Prioritize interoperability"],
    "outlook": "Positive 3-year outlook.",
}


def test_render_produces_pptx_file():
    from agent.analyzers.pptx_agent import PPTXAgent
    agent = PPTXAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = agent.render(MOCK_SYNTHESIS, run_id="test-001", output_dir=tmpdir)
        assert os.path.exists(path)
        assert path.endswith(".pptx")


def test_pptx_has_five_slides():
    from agent.analyzers.pptx_agent import PPTXAgent
    agent = PPTXAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = agent.render(MOCK_SYNTHESIS, run_id="test-001", output_dir=tmpdir)
        prs = Presentation(path)
        assert len(prs.slides) == 5


def test_slide_titles_present():
    from agent.analyzers.pptx_agent import PPTXAgent
    agent = PPTXAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = agent.render(MOCK_SYNTHESIS, run_id="test-001", output_dir=tmpdir)
        prs = Presentation(path)
        titles = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame and shape.shape_type == 13:  # title placeholder
                    titles.append(shape.text)
                elif hasattr(shape, "text") and shape.text:
                    titles.append(shape.text)
        # At least one slide has recognizable title content
        all_text = " ".join(titles).lower()
        assert any(word in all_text for word in ["summary", "market", "competitive", "strategic", "recommendation"])


def test_render_handles_missing_synthesis_fields():
    """PPTXAgent must not raise when synthesis fields are absent."""
    from agent.analyzers.pptx_agent import PPTXAgent
    agent = PPTXAgent()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Minimal synthesis — missing most fields
        path = agent.render({"executive_summary": "Brief summary."}, run_id="test-002", output_dir=tmpdir)
        prs = Presentation(path)
        assert len(prs.slides) == 5  # all 5 slides render, some with placeholder text
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
pytest tests/test_pptx_agent.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `agent/analyzers/pptx_agent.py`**

```python
# agent/analyzers/pptx_agent.py
"""
PPTXAgent — generates a 5-slide BCG-style PowerPoint from SynthesisAgent output.

BCG layout conventions:
  - Widescreen 13.33" x 7.5"
  - Navy header bar (#0C2040), full width, 1.3" tall
  - White title text, bold, 28pt, left-aligned (action-oriented "so what" framing)
  - Category label: light blue (#7DD3FC), 10pt uppercase
  - Body: white background, 12pt left-aligned bullets
  - Footer: source + date + page number, 8pt gray (#94A3B8)
  - Accent: #0EA5E9 blue for callout boxes

Missing data: renders placeholder text rather than raising.
"""
import logging
import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt, Emu

from agent.base_agent import BaseAgent
from agent.exceptions import PPTXRenderError

logger = logging.getLogger(__name__)

# BCG color palette
NAVY = RGBColor(0x0C, 0x20, 0x40)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_BLUE = RGBColor(0x7D, 0xD3, 0xFC)
ACCENT_BLUE = RGBColor(0x0E, 0xA5, 0xE9)
BODY_GRAY = RGBColor(0x1E, 0x29, 0x3B)
FOOTER_GRAY = RGBColor(0x94, 0xA3, 0xB8)
LIGHT_BG = RGBColor(0xF8, 0xFA, 0xFC)

# Slide dimensions (widescreen)
SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)
HEADER_H = Inches(1.3)
FOOTER_H = Inches(0.35)
MARGIN = Inches(0.5)
BODY_TOP = HEADER_H + Inches(0.2)
BODY_H = SLIDE_H - HEADER_H - FOOTER_H - Inches(0.3)
BODY_W = SLIDE_W - MARGIN * 2

PLACEHOLDER = "Insufficient data for this section — expand research scope."


def _rgb(r: int, g: int, b: int) -> RGBColor:
    return RGBColor(r, g, b)


class PPTXAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="pptx-agent")

    def render(self, synthesis: dict, run_id: str, output_dir: str = "output") -> str:
        """Render a 5-slide BCG PowerPoint. Returns path to saved .pptx file."""
        try:
            prs = Presentation()
            prs.slide_width = SLIDE_W
            prs.slide_height = SLIDE_H

            today = date.today().strftime("%B %Y")

            self._slide_executive_summary(prs, synthesis, today)
            self._slide_market_landscape(prs, synthesis, today)
            self._slide_competitive_analysis(prs, synthesis, today)
            self._slide_strategic_implications(prs, synthesis, today)
            self._slide_recommendations(prs, synthesis, today)

            out_dir = Path(output_dir) / run_id
            out_dir.mkdir(parents=True, exist_ok=True)
            path = str(out_dir / "board-deck.pptx")
            prs.save(path)
            logger.info("Board deck saved: %s", path)
            return path
        except Exception as e:
            raise PPTXRenderError(f"PPTX render failed: {e}") from e

    # ── Slide builders ────────────────────────────────────────────────────────

    def _slide_executive_summary(self, prs: Presentation, s: dict, today: str):
        slide = self._blank_slide(prs)
        self._add_header(slide, "EXECUTIVE SUMMARY", "Key findings from competitive research")
        summary = s.get("executive_summary") or PLACEHOLDER
        bullets = [summary]
        # Add top 2 recommendations as preview bullets
        for rec in (s.get("recommendations") or [])[:2]:
            bullets.append(f"→ {rec}")
        self._add_bullets(slide, bullets, top=BODY_TOP, bold_first=True)
        self._add_footer(slide, today, 1)

    def _slide_market_landscape(self, prs: Presentation, s: dict, today: str):
        slide = self._blank_slide(prs)
        self._add_header(slide, "MARKET LANDSCAPE", "Size, growth, and key players")
        ml = s.get("market_landscape") or {}
        bullets = []
        size = ml.get("size_and_growth") or PLACEHOLDER
        bullets.append(size)
        for p in (ml.get("key_players") or [])[:4]:
            name = p.get("name", "")
            pos = p.get("position", "")
            sig = p.get("signal", "")
            bullets.append(f"• {name} — {pos}: {sig}")
        for t in (ml.get("trends") or [])[:3]:
            bullets.append(f"▸ Trend: {t}")
        self._add_bullets(slide, bullets or [PLACEHOLDER], top=BODY_TOP, bold_first=True)
        self._add_footer(slide, today, 2)

    def _slide_competitive_analysis(self, prs: Presentation, s: dict, today: str):
        slide = self._blank_slide(prs)
        self._add_header(slide, "COMPETITIVE ANALYSIS", "Player comparison and positioning")
        ca = s.get("competitive_analysis") or {}
        bullets = []
        for row in (ca.get("comparison_table") or [])[:5]:
            dim = row.get("dimension", "")
            findings = row.get("findings", "")
            bullets.append(f"• {dim}: {findings}")
        for sig in (ca.get("winner_signals") or [])[:2]:
            bullets.append(f"✓ {sig}")
        for risk in (ca.get("disruption_risks") or [])[:2]:
            bullets.append(f"⚠ {risk}")
        self._add_bullets(slide, bullets or [PLACEHOLDER], top=BODY_TOP)
        self._add_footer(slide, today, 3)

    def _slide_strategic_implications(self, prs: Presentation, s: dict, today: str):
        slide = self._blank_slide(prs)
        self._add_header(slide, "STRATEGIC IMPLICATIONS", "Opportunities, risks, and watch list")
        si = s.get("strategic_implications") or {}
        col_w = (SLIDE_W - MARGIN * 3) / 2

        # Left column: opportunities
        opp_bullets = [f"+ {o}" for o in (si.get("opportunities") or [])[:4]] or [PLACEHOLDER]
        self._add_text_box(
            slide, "OPPORTUNITIES", opp_bullets,
            left=MARGIN, top=BODY_TOP, width=col_w, height=BODY_H,
            header_color=ACCENT_BLUE,
        )
        # Right column: risks
        risk_bullets = [f"− {r}" for r in (si.get("risks") or [])[:4]] or [PLACEHOLDER]
        self._add_text_box(
            slide, "RISKS & WATCH LIST", risk_bullets + [f"👁 {w}" for w in (si.get("watch_list") or [])[:2]],
            left=MARGIN * 2 + col_w, top=BODY_TOP, width=col_w, height=BODY_H,
            header_color=_rgb(0xEF, 0x44, 0x44),
        )
        self._add_footer(slide, today, 4)

    def _slide_recommendations(self, prs: Presentation, s: dict, today: str):
        slide = self._blank_slide(prs)
        self._add_header(slide, "RECOMMENDATIONS & OUTLOOK", "Actions and forward view")
        recs = s.get("recommendations") or []
        outlook = s.get("outlook") or ""
        bullets = [f"{i+1}. {r}" for i, r in enumerate(recs[:5])]
        if outlook:
            bullets.append("")
            bullets.append(f"Outlook: {outlook}")
        self._add_bullets(slide, bullets or [PLACEHOLDER], top=BODY_TOP)
        self._add_footer(slide, today, 5)

    # ── Layout helpers ────────────────────────────────────────────────────────

    def _blank_slide(self, prs: Presentation):
        blank_layout = prs.slide_layouts[6]  # completely blank
        return prs.slides.add_slide(blank_layout)

    def _add_header(self, slide, category: str, title: str):
        """Navy header bar with category label + title."""
        from pptx.util import Inches, Pt
        # Navy rectangle
        bg = slide.shapes.add_shape(
            1,  # MSO_SHAPE_TYPE.RECTANGLE
            0, 0, SLIDE_W, HEADER_H,
        )
        bg.fill.solid()
        bg.fill.fore_color.rgb = NAVY
        bg.line.fill.background()

        # Category label (light blue, uppercase, small)
        cat_box = slide.shapes.add_textbox(MARGIN, Inches(0.15), SLIDE_W - MARGIN * 2, Inches(0.3))
        tf = cat_box.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = category
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = LIGHT_BLUE

        # Title (white, bold, larger)
        title_box = slide.shapes.add_textbox(MARGIN, Inches(0.5), SLIDE_W - MARGIN * 2, Inches(0.7))
        tf2 = title_box.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        run2 = p2.add_run()
        run2.text = title
        run2.font.size = Pt(22)
        run2.font.bold = True
        run2.font.color.rgb = WHITE

    def _add_bullets(
        self, slide, bullets: List[str],
        top: Emu, bold_first: bool = False,
        left: Optional[Emu] = None,
        width: Optional[Emu] = None,
    ):
        l = left if left is not None else MARGIN
        w = width if width is not None else BODY_W
        box = slide.shapes.add_textbox(l, top, w, BODY_H)
        tf = box.text_frame
        tf.word_wrap = True
        for i, bullet in enumerate(bullets):
            if i == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            p.space_after = Pt(4)
            run = p.add_run()
            run.text = bullet
            run.font.size = Pt(13)
            run.font.color.rgb = BODY_GRAY
            if bold_first and i == 0:
                run.font.bold = True
                run.font.size = Pt(14)

    def _add_text_box(
        self, slide, header: str, bullets: List[str],
        left: Emu, top: Emu, width: Emu, height: Emu,
        header_color: RGBColor,
    ):
        # Colored header strip
        hdr = slide.shapes.add_shape(1, left, top, width, Inches(0.35))
        hdr.fill.solid()
        hdr.fill.fore_color.rgb = header_color
        hdr.line.fill.background()

        hdr_box = slide.shapes.add_textbox(left + Inches(0.1), top + Inches(0.05), width - Inches(0.2), Inches(0.3))
        tf = hdr_box.text_frame
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = header
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = WHITE

        # Bullets below header
        content_top = top + Inches(0.4)
        content_h = height - Inches(0.4)
        box = slide.shapes.add_textbox(left + Inches(0.1), content_top, width - Inches(0.2), content_h)
        tf2 = box.text_frame
        tf2.word_wrap = True
        for i, b in enumerate(bullets):
            p2 = tf2.paragraphs[0] if i == 0 else tf2.add_paragraph()
            p2.space_after = Pt(5)
            run2 = p2.add_run()
            run2.text = b
            run2.font.size = Pt(12)
            run2.font.color.rgb = BODY_GRAY

    def _add_footer(self, slide, date_str: str, page_num: int):
        footer_top = SLIDE_H - FOOTER_H
        box = slide.shapes.add_textbox(MARGIN, footer_top, SLIDE_W - MARGIN * 2, FOOTER_H)
        tf = box.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        run = p.add_run()
        run.text = f"Web Intelligence Agent  ·  {date_str}  ·  {page_num} / 5"
        run.font.size = Pt(8)
        run.font.color.rgb = FOOTER_GRAY

        # Footer line
        line = slide.shapes.add_shape(1, 0, footer_top - Inches(0.02), SLIDE_W, Inches(0.02))
        line.fill.solid()
        line.fill.fore_color.rgb = _rgb(0xE2, 0xE8, 0xF0)
        line.line.fill.background()
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
pytest tests/test_pptx_agent.py -v
```

Expected: 4/4 PASS

- [ ] **Step 5: Commit**

```bash
git add agent/analyzers/pptx_agent.py tests/test_pptx_agent.py
git commit -m "feat(v2): PPTXAgent — 5-slide BCG PowerPoint generator (navy header, action titles, evidence bullets)"
```

---

## Chunk 5: Orchestrator + API + Frontend Wiring

### Task 8: Orchestrator Expansion

**Files:**
- Modify: `agent/orchestrator.py`
- Create: `tests/test_orchestrator_v2.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_orchestrator_v2.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_board_deck_goal_triggers_pptx():
    """board_deck goal should produce a pptx_path in the result."""
    with patch("agent.orchestrator.anthropic.Anthropic") as mock_anthropic, \
         patch("agent.orchestrator.FilingsCrawler") as mock_filings, \
         patch("agent.orchestrator.EarningsCrawler") as mock_earnings, \
         patch("agent.orchestrator.FinancialAgent") as mock_financial, \
         patch("agent.orchestrator.SynthesisAgent") as mock_synthesis, \
         patch("agent.orchestrator.QualAgent") as mock_qual, \
         patch("agent.orchestrator.VizAgent") as mock_viz, \
         patch("agent.orchestrator.PPTXAgent") as mock_pptx:

        # Setup Claude classification response
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        classify_msg = MagicMock()
        classify_msg.content = [MagicMock(text='{"source_type": "board_deck", "target": "apac-health-it", "companies": ["Epic"], "sector": "health IT", "region": "APAC", "max_profiles": 0}')]
        mock_client.messages.create.return_value = classify_msg

        # Setup crawlers
        mock_filings.return_value.run = AsyncMock(return_value=[{"source": "filing", "company": "Epic", "raw_text": "revenue", "period": "FY2023", "filing_type": "10-K", "source_url": "http://x"}])
        mock_earnings.return_value.run = AsyncMock(return_value=[{"source": "earnings", "body": "text", "title": "T", "source_url": "http://y", "source_type": "news", "company": "Epic", "date": ""}])

        # Setup analyzers
        mock_financial.return_value.run = AsyncMock(return_value=[{"company": "Epic", "period": "FY2023", "metrics": {}, "key_risks": [], "confidence": "low"}])
        mock_qual.return_value.run = AsyncMock(return_value={"executive_summary": "summary", "key_themes": [], "technology_signals": [], "people_insights": []})
        mock_synthesis.return_value.run = AsyncMock(return_value={"executive_summary": "summary", "market_landscape": {}, "competitive_analysis": {}, "strategic_implications": {}, "recommendations": [], "outlook": ""})
        mock_viz.return_value.render.return_value = "<html></html>"
        mock_viz.return_value.save.return_value = "output/test/report.html"
        mock_pptx.return_value.render.return_value = "output/test/board-deck.pptx"

        from agent.orchestrator import Orchestrator
        orch = Orchestrator(db_path=":memory:", output_dir="/tmp/test-output")
        result = await orch.run(goal="Board deck on APAC health IT")

    assert "pptx_path" in result
    assert result["pptx_path"] == "output/test/board-deck.pptx"


@pytest.mark.asyncio
async def test_blog_goal_does_not_trigger_pptx():
    """Existing blog goals must NOT produce pptx_path (backward compat)."""
    with patch("agent.orchestrator.anthropic.Anthropic") as mock_anthropic, \
         patch("agent.orchestrator.BlogCrawler") as mock_blog, \
         patch("agent.orchestrator.QualAgent") as mock_qual, \
         patch("agent.orchestrator.QuantAgent") as mock_quant, \
         patch("agent.orchestrator.VizAgent") as mock_viz:

        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        classify_msg = MagicMock()
        classify_msg.content = [MagicMock(text='{"source_type": "blog", "target": "martinfowler", "url": "https://martinfowler.com", "max_profiles": 0}')]
        mock_client.messages.create.return_value = classify_msg

        mock_blog.return_value.run = AsyncMock(return_value=[{"source": "blog", "body": "article content", "title": "T", "source_url": "http://x"}])
        mock_qual.return_value.run = AsyncMock(return_value={"executive_summary": "s", "key_themes": [], "technology_signals": [], "people_insights": []})
        mock_quant.return_value.run = AsyncMock(return_value={"graph": {}, "stats": {}})
        mock_viz.return_value.render.return_value = "<html></html>"
        mock_viz.return_value.save.return_value = "output/test/report.html"

        from agent.orchestrator import Orchestrator
        orch = Orchestrator(db_path=":memory:", output_dir="/tmp/test-output")
        result = await orch.run(goal="Summarize https://martinfowler.com")

    assert "pptx_path" not in result or result.get("pptx_path") is None
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
pytest tests/test_orchestrator_v2.py -v
```

Expected: FAIL (imports missing)

- [ ] **Step 3: Update `agent/orchestrator.py`**

Add new imports at the top:
```python
from agent.crawlers.filings import FilingsCrawler
from agent.crawlers.earnings import EarningsCrawler
from agent.analyzers.financial import FinancialAgent
from agent.analyzers.synthesis import SynthesisAgent
from agent.analyzers.pptx_agent import PPTXAgent
```

Replace the `CLASSIFY_PROMPT` constant with the expanded version:
```python
CLASSIFY_PROMPT = """Classify this research goal and extract key parameters.

Goal: {goal}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "source_type": "linkedin",
  "analysis_type": "org_chart",
  "target": "slug-for-storage",
  "company_name": "Company Name",
  "companies": ["Company A", "Company B"],
  "sector": "health IT",
  "region": "APAC",
  "department_filter": null,
  "url": null,
  "max_profiles": 30
}}

source_type options:
- "linkedin": goal is about LinkedIn org structure, people, executives
- "blog": goal is about summarizing a blog, website, or articles (provide url)
- "financial": goal is about P&L, revenue, margins, financial analysis of companies
- "market_intel": goal is about market landscape, industry trends, market sizing
- "synthesis": goal is about competitive analysis comparing multiple companies
- "board_deck": goal explicitly requests a board presentation, deck, or comprehensive report

For financial/market_intel/synthesis/board_deck: populate companies[] with any named companies.
For blog: set url to the target URL.
For linkedin: set company_name and max_profiles.
"""
```

Replace the `_crawl` method with the expanded version:
```python
async def _crawl(self, plan: dict) -> list:
    source_type = plan.get("source_type", "linkedin")
    if source_type == "linkedin":
        crawler = LinkedInCrawler(max_profiles=int(plan.get("max_profiles") or 30))
        return await crawler.run(
            company_name=plan.get("company_name", ""),
            department_filter=plan.get("department_filter"),
        )
    elif source_type == "blog":
        crawler = BlogCrawler()
        return await crawler.run(url=plan.get("url", ""), max_pages=20)
    elif source_type == "financial":
        companies = plan.get("companies") or [plan.get("company_name", "")]
        return await FilingsCrawler().run(companies=[c for c in companies if c])
    elif source_type in ("market_intel", "synthesis", "board_deck"):
        companies = plan.get("companies") or []
        target = plan.get("target", "")
        filings = await FilingsCrawler().run(companies=companies) if companies else []
        earnings = await EarningsCrawler().run(
            query=f"{target} {plan.get('sector', '')} {plan.get('region', '')}".strip(),
            max_results=10,
        )
        return filings + earnings
    else:
        # fallback: treat as blog
        crawler = BlogCrawler()
        return await crawler.run(url=plan.get("url", ""), max_pages=20)
```

Replace the analysis pipeline section in `run()` (inside the try block, after normalization):
```python
        source_type = plan.get("source_type", "linkedin")

        # Step 3: Analyze
        qual_result = await QualAgent().run(people=people)

        if source_type in ("financial", "market_intel", "synthesis", "board_deck"):
            # v2: financial + synthesis pipeline
            financial_result = await FinancialAgent().run(raw_data) if any(
                d.get("source") == "filing" for d in raw_data
            ) else []
            synthesis_result = await SynthesisAgent().run(
                raw_data=raw_data,
                financial=financial_result,
                qual=qual_result,
            )
            # Persist financial records
            for fin in financial_result:
                self.store.save_financial(run_id=run_id, financial=fin)
        else:
            financial_result = []
            synthesis_result = {}

        quant_result = await QuantAgent().run(people=people)
```

Add PPTX generation after viz rendering (still inside try block):
```python
        # Step 5b: PPTX (board_deck goals only)
        pptx_path = None
        if source_type == "board_deck" and synthesis_result:
            try:
                pptx_path = PPTXAgent().render(
                    synthesis_result,
                    run_id=run_id,
                    output_dir=self.output_dir,
                )
            except Exception as e:
                logger.warning("PPTX render failed (HTML report still available): %s", e)
```

Add `pptx_path` to the return dict:
```python
        return {
            "run_id": run_id,
            "report_path": report_path,
            "pptx_path": pptx_path,
            "changes": changes_dicts,
            "people_count": len(people),
        }
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
pytest tests/test_orchestrator_v2.py -v
```

Expected: 2/2 PASS

- [ ] **Step 5: Run full suite — no regressions**

```bash
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add agent/orchestrator.py tests/test_orchestrator_v2.py
git commit -m "feat(v2): expand orchestrator — financial/market_intel/synthesis/board_deck goal types + PPTXAgent wiring"
```

---

### Task 9: API + Frontend

**Files:**
- Modify: `api/server.py`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add deck download endpoint to `api/server.py`**

Add after the existing `/report/{run_id}` endpoint:

```python
@app.get("/report/{run_id}/deck")
def get_deck(run_id: str, _: None = Depends(verify_api_key_query)):
    path = Path(f"output/{run_id}/board-deck.pptx")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Deck not found: {run_id}")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"board-deck-{run_id}.pptx",
    )
```

Also update the `/runs` response to include `pptx_available`:
```python
return [
    {
        "id": r.id,
        "goal": r.goal,
        "target": r.target,
        "status": r.status,
        "created_at": str(r.created_at),
        "pptx_available": Path(f"output/{r.id}/board-deck.pptx").exists(),
    }
    for r in runs
]
```

- [ ] **Step 2: Update `frontend/src/lib/api.ts`**

Add `pptx_available` to the `Run` interface and `getDeckUrl` function:

```typescript
export interface Run {
  id: string;
  goal: string;
  target: string;
  status: string;
  created_at: string;
  pptx_available?: boolean;
}

export function getDeckUrl(runId: string): string {
  return `${API_BASE}/report/${runId}/deck?x-api-key=${API_KEY}`;
}
```

Also update `RunResult` to include `pptx_path`:
```typescript
export interface RunResult {
  run_id: string;
  report_path: string;
  pptx_path?: string | null;
  people_count: number;
  changes: Array<{
    change_type: string;
    person_name: string;
    from_value?: string;
    to_value?: string;
  }>;
}
```

- [ ] **Step 3: Update `frontend/src/app/page.tsx`**

Import `getDeckUrl`:
```typescript
import { listRuns, startRun, getReportUrl, getDeckUrl, Run } from "@/lib/api";
```

In `handleRun`, after opening the report, also open the deck if available:
```typescript
    try {
      const result = await startRun(goal);
      window.open(getReportUrl(result.run_id), "_blank");
      if (result.pptx_path) {
        // Small delay so browser doesn't block two popups
        setTimeout(() => window.open(getDeckUrl(result.run_id), "_blank"), 500);
      }
      const updated = await listRuns();
      setRuns(updated);
      setGoal("");
    }
```

Add "Download Deck" button in the run history list item, next to "Open Report →":
```tsx
                {run.status === "complete" && run.pptx_available && (
                  <a
                    href={getDeckUrl(run.id)}
                    className="text-xs text-emerald-400 hover:text-emerald-300 ml-3 shrink-0"
                  >
                    ↓ Deck
                  </a>
                )}
```

Update the loading message to mention the deck:
```tsx
            <p className="mt-2 text-slate-400 text-sm">
              ⏳ Running… Board deck goals take 3–8 minutes. Report + PPTX will open automatically.
            </p>
```

- [ ] **Step 4: Restart servers and verify build**

```bash
# Verify Next.js still builds
cd ~/projects/web-intelligence-agent/frontend && npm run build 2>&1 | tail -5
```

Expected: `✓ Compiled successfully`

- [ ] **Step 5: Run full test suite**

```bash
cd ~/projects/web-intelligence-agent
source .venv/bin/activate
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
cd ~/projects/web-intelligence-agent
git add api/server.py frontend/src/app/page.tsx frontend/src/lib/api.ts
git commit -m "feat(v2): API deck endpoint + frontend Download Deck button + pptx_available in run history"
```

---

### Task 10: End-to-End Smoke Test

**Files:**
- Modify: `tests/test_integration_smoke.py`

- [ ] **Step 1: Add v2 smoke tests**

Add to the existing `tests/test_integration_smoke.py`:

```python
def test_filings_crawler_imports():
    from agent.crawlers.filings import FilingsCrawler
    assert FilingsCrawler.DELAY_SECONDS == 2.0
    assert FilingsCrawler.MAX_FILINGS == 5


def test_earnings_crawler_imports():
    from agent.crawlers.earnings import EarningsCrawler
    assert EarningsCrawler.DELAY_SECONDS == 1.5
    assert EarningsCrawler.MAX_RESULTS == 15


def test_financial_agent_imports():
    from agent.analyzers.financial import FinancialAgent
    agent = FinancialAgent.__new__(FinancialAgent)
    assert hasattr(agent, "wrap_content")


def test_synthesis_agent_imports():
    from agent.analyzers.synthesis import SynthesisAgent
    assert SynthesisAgent is not None


def test_pptx_agent_produces_file():
    """Full PPTXAgent render smoke test — no mocks."""
    import tempfile
    from pptx import Presentation
    from agent.analyzers.pptx_agent import PPTXAgent

    agent = PPTXAgent()
    synthesis = {
        "executive_summary": "APAC health IT market growing at 12% CAGR.",
        "market_landscape": {
            "size_and_growth": "$45B market",
            "key_players": [{"name": "Epic", "position": "Leader", "signal": "35% EHR share"}],
            "trends": ["Cloud migration"],
        },
        "competitive_analysis": {
            "comparison_table": [{"dimension": "Market Share", "findings": "Epic leads"}],
            "winner_signals": ["Strong interoperability"],
            "disruption_risks": ["Oracle pricing pressure"],
        },
        "strategic_implications": {
            "opportunities": ["Cloud-native EHR adoption"],
            "risks": ["Vendor lock-in"],
            "watch_list": ["Microsoft health cloud"],
        },
        "recommendations": ["Invest in cloud EHR", "Build interoperability layer"],
        "outlook": "Positive 3-year outlook for cloud-native health IT.",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        path = agent.render(synthesis, run_id="smoke-test-001", output_dir=tmpdir)
        prs = Presentation(path)
        assert len(prs.slides) == 5
        print(f"\n✅ Board deck: {path}")


def test_store_financial_record():
    from agent.store import Store
    store = Store(db_path=":memory:")
    store.init_db()
    run_id = store.create_run(goal="test", target="epic")
    store.save_financial(run_id=run_id, financial={
        "company": "Epic",
        "period": "FY2023",
        "metrics": {"revenue_usd_millions": 4000.0},
        "key_risks": [],
        "confidence": "high",
    })
    records = store.list_financials(run_id=run_id)
    assert len(records) == 1
    assert records[0].revenue_usd_millions == 4000.0
```

- [ ] **Step 2: Run full suite including new smoke tests**

```bash
source .venv/bin/activate
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py -s
```

Expected: All pass. The `test_pptx_agent_produces_file` test will print the deck path.

- [ ] **Step 3: Final commit**

```bash
git add tests/test_integration_smoke.py
git commit -m "test(v2): integration smoke tests for all v2 components — FilingsCrawler, EarningsCrawler, FinancialAgent, SynthesisAgent, PPTXAgent"
```

---

## Final Verification

After all tasks complete, verify the full stack works:

```bash
# 1. Tests
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
# Expected: All pass

# 2. CLI help shows new goal types
source .venv/bin/activate
python run.py --help

# 3. Quick board deck test (uses real APIs)
python run.py --goal "Board deck on APAC health IT market landscape for Synapxe CIO"
# Expected: report.html opens in browser + board-deck.pptx saved to output/<run-id>/

# 4. Frontend build
cd frontend && npm run build
# Expected: ✓ Compiled successfully
```

The `board-deck.pptx` will be at:
```
output/<run-id>/board-deck.pptx
```

Open it in PowerPoint, Keynote, or Google Slides.
