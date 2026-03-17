# Competitive Intelligence Platform — Design Spec
**Date:** 2026-03-17
**Status:** Draft
**Builds on:** `docs/superpowers/specs/2026-03-16-web-intelligence-agent-design.md`

---

## 1. Problem & Goal

Extend the Web Intelligence Agent into a standalone competitive research platform. A user types a natural language goal; the agent researches public sources, synthesizes findings, and produces a **5-slide BCG-style PowerPoint** plus an HTML report — with no manual copy-paste.

**Primary use case:** "Generate a board deck on the APAC health IT market landscape for Synapxe's CIO"

**Secondary use cases:**
- Financial intelligence on public companies from SEC filings
- Competitive analysis across multiple players (Epic vs Cerner)
- Market & industry synthesis from earnings transcripts + analyst coverage

---

## 2. Scope

### In scope (v2)
- **D: Multi-Source Synthesis** — cross-source competitive narrative from multiple crawlers
- **E: Market & Industry Intelligence** — filings, earnings transcripts, analyst reports, news

### Explicitly out of scope
- cio-dashboard integration (separate project, no coupling)
- LinkedIn org crawling changes (v1 feature, unchanged)
- Scheduled/cron re-crawling
- Authenticated paywalled sources

---

## 3. New Goal Types

The orchestrator's `_classify_goal` prompt gains three new `source_type` values:

| source_type | Example goal | Crawlers used | Analyzers used |
|---|---|---|---|
| `market_intel` | "Market landscape of APAC health IT" | EarningsCrawler + BlogCrawler | FinancialAgent + SynthesisAgent |
| `financial` | "P&L analysis of Epic Systems" | FilingsCrawler | FinancialAgent |
| `board_deck` | "Board deck on cloud adoption in Singapore gov tech" | FilingsCrawler + EarningsCrawler + BlogCrawler | FinancialAgent + SynthesisAgent |
| `synthesis` | "Competitive analysis of Epic vs Cerner" | EarningsCrawler + BlogCrawler | SynthesisAgent |

Existing `linkedin` and `blog` source types unchanged.

---

## 4. New Components

### 4.1 FilingsCrawler (`agent/crawlers/filings.py`)

Crawls public financial filings using Firecrawl.

**Inputs:** `company_name`, `ticker` (optional), `filing_types` (default: `["10-K", "annual-report"]`)

**Data sources (in priority order):**
1. SEC EDGAR full-text search: `https://efts.sec.gov/LATEST/search-index?q="{company}"&dateRange=custom&startdt={year}-01-01&forms=10-K`
2. Company IR page: discovered via `{company_name} investor relations annual report site:*.com`
3. Firecrawl scrape of the discovered URL

**Output schema:**
```python
{
    "company": str,
    "filing_type": str,          # "10-K", "annual-report"
    "period": str,               # "FY2024", "FY2023"
    "source_url": str,
    "raw_text": str,             # full markdown from Firecrawl
    "source": "filing"
}
```

**Rate limiting:** 2s delay between requests. Max 5 filings per run.

---

### 4.2 EarningsCrawler (`agent/crawlers/earnings.py`)

Crawls earnings call transcripts and analyst/news coverage via Firecrawl.

**Inputs:** `company_name`, `query` (e.g. "APAC health IT market"), `max_results` (default: 10)

**Rate limiting:** 1.5s delay between requests. Max 15 results per run.

**Data sources:**
- Earnings transcripts: Motley Fool, Seeking Alpha (public pages), company IR
- News/analyst: search via Firecrawl `/search` endpoint
- Fallback: BlogCrawler for general news

**Output schema:**
```python
{
    "title": str,
    "body": str,                 # markdown content
    "source_url": str,
    "source_type": str,          # "earnings_transcript", "analyst_report", "news"
    "company": str,
    "date": str,                 # ISO date if extractable
    "source": "earnings"
}
```

---

### 4.3 FinancialAgent (`agent/analyzers/financial.py`)

Extracts structured financial metrics from raw filing/earnings text using Claude.

**Input:** list of raw document dicts from FilingsCrawler and/or EarningsCrawler. FinancialAgent filters to only process items where `source == "filing"` and skips earnings/news items.

**Claude prompt extracts:**
- Revenue (TTM, YoY growth %)
- Gross margin, operating margin, net margin
- EBITDA
- R&D spend as % of revenue
- Capex vs opex split
- Key risks (from risk factors section)

**Output schema:**
```python
{
    "company": str,
    "period": str,
    "metrics": {
        "revenue_usd_millions": float | None,
        "revenue_yoy_growth_pct": float | None,
        "gross_margin_pct": float | None,
        "operating_margin_pct": float | None,
        "net_margin_pct": float | None,
        "ebitda_usd_millions": float | None,
        "rd_spend_pct_revenue": float | None,
        "capex_pct_revenue": float | None,
    },
    "key_risks": [str],
    "confidence": "high" | "medium" | "low"
}
```

**Security:** All raw filing text wrapped in `<content source='untrusted'>` before Claude.

**Error handling:** `InsufficientDataError` if no financials extractable. Returns `confidence: "low"` with partial data rather than failing.

---

### 4.4 SynthesisAgent (`agent/analyzers/synthesis.py`)

Produces a cross-source competitive narrative from all collected data.

**Input:** combined output from all crawlers + analyzers for a run

**Security:** All raw text fields from crawlers wrapped in `<content source='untrusted'>` before Claude. Financial metrics (already extracted by FinancialAgent) are trusted internal data and passed directly.

**Claude produces:**
```python
{
    "executive_summary": str,        # 3-5 sentence board-level summary
    "market_landscape": {
        "size_and_growth": str,
        "key_players": [{"name": str, "position": str, "signal": str}],
        "trends": [str]
    },
    "competitive_analysis": {
        "comparison_table": [{"dimension": str, "findings": str}],
        "winner_signals": [str],
        "disruption_risks": [str]
    },
    "strategic_implications": {
        "opportunities": [str],
        "risks": [str],
        "watch_list": [str]
    },
    "recommendations": [str],
    "outlook": str
}
```

---

### 4.5 PPTXAgent (`agent/analyzers/pptx_agent.py`)

Generates a 5-slide BCG-style PowerPoint from synthesis output.

**BCG layout conventions:**
- Slide dimensions: 13.33" × 7.5" (widescreen)
- Header bar: full-width navy rectangle (`#0C2040`), 1.3" tall
- Title: white, bold, 28pt, left-aligned, action-oriented ("so what" framing)
- Category label: `#7dd3fc` (light blue), 10pt uppercase, top-left of header
- Body: white background, left-aligned evidence bullets, 12pt
- Charts: embedded as PNG images (matplotlib)
- Footer: source list + date + slide number, 8pt `#94a3b8`
- Accent color: `#0ea5e9` (blue) for highlights, callout boxes

**5 slides:**

| # | Title | Content |
|---|---|---|
| 1 | Executive Summary | 3-5 key findings as bold bullets + 1-sentence "so what" |
| 2 | Market Landscape | Market size/growth narrative + key players table |
| 3 | Competitive Analysis | Player comparison table + positioning signals |
| 4 | Strategic Implications | Opportunities vs risks (two-column layout) |
| 5 | Recommendations & Outlook | Numbered recommendations + outlook statement |

**Missing data handling:** Each slide checks for required SynthesisAgent keys before rendering. If a section is absent or empty, the slide renders a placeholder: "Insufficient data for this section — expand research scope." PPTXAgent never raises on missing fields; it degrades gracefully per slide.

**Library:** `python-pptx`

**Output:** `output/<run-id>/board-deck.pptx` + `output/<run-id>/report.html` (both generated per run)

---

## 5. Orchestrator Changes (`agent/orchestrator.py`)

### 5.1 Expanded classify prompt

```
New source_type values: "market_intel", "financial", "board_deck", "synthesis"
New fields: "companies": ["Company A", "Company B"], "sector": "health IT", "region": "APAC"
```

### 5.2 Expanded `_crawl()` dispatch

```python
elif source_type == "financial":
    return await FilingsCrawler().run(companies=plan["companies"])
elif source_type in ("market_intel", "synthesis", "board_deck"):
    filings = await FilingsCrawler().run(companies=plan.get("companies", []))
    earnings = await EarningsCrawler().run(query=plan["target"], max_results=10)
    return filings + earnings
```

### 5.3 Expanded analysis pipeline

For `board_deck` goals, run all four analyzers and pass combined output to PPTXAgent:
```python
qual_result = await QualAgent().run(data)          # themes + summaries from raw text
financial_result = await FinancialAgent().run(data) # P&L from filing items only
synthesis_result = await SynthesisAgent().run(
    raw_data=data,
    financial=financial_result,
    qual=qual_result,
)
pptx_path = await PPTXAgent().render(synthesis_result, run_id)
```
`QualAgent` runs for all new goal types (not just `linkedin`). `FinancialAgent` is skipped if no filing items in `data` — in that case `financial_result = {}` is passed to `SynthesisAgent`, which treats missing financial data as "not available" and omits financial sections from the deck.

For non-`board_deck` goals, skip PPTXAgent (backward compatible).

---

## 6. New Exceptions (`agent/exceptions.py`)

```python
class FilingsFetchError(WebIntelligenceError): pass
class FilingsParseError(WebIntelligenceError): pass
class EarningsFetchError(WebIntelligenceError): pass
class FinancialExtractionError(WebIntelligenceError): pass
class PPTXRenderError(WebIntelligenceError): pass
# InsufficientDataError already exists in v1 — reused here for FinancialAgent
```

### Error & Rescue Map (additions to v1 table)

| Error | Action | User sees |
|---|---|---|
| `FilingsFetchError` | Log + skip company, continue with others | "Could not fetch filings for {company}" |
| `FilingsParseError` | Log + return empty financials | "Filing parse failed — partial data only" |
| `EarningsFetchError` | Log + skip, use blog fallback | Silent (progress indicator) |
| `FinancialExtractionError` | Return `confidence: "low"` partial result | "Financial data may be incomplete" |
| `PPTXRenderError` | Log + skip PPTX, HTML report still generated | "Deck generation failed — HTML report available" |

---

## 7. SQLite Store Changes (`agent/store.py`)

New `FinancialRecord` model persists all 7 extracted metrics for change detection:

```python
class FinancialRecord(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4())[:8], primary_key=True)
    run_id: str
    company: str
    period: str
    revenue_usd_millions: Optional[float]
    revenue_yoy_growth_pct: Optional[float]
    gross_margin_pct: Optional[float]
    operating_margin_pct: Optional[float]
    net_margin_pct: Optional[float]
    ebitda_usd_millions: Optional[float]
    rd_spend_pct_revenue: Optional[float]
    capex_pct_revenue: Optional[float]
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## 8. API Changes (`api/server.py`)

New endpoint for PPTX download:

```python
@app.get("/report/{run_id}/deck")
def get_deck(run_id: str, _=Depends(verify_api_key_query)):
    path = Path(f"output/{run_id}/board-deck.pptx")
    if not path.exists():
        raise HTTPException(404, "Deck not found")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
```

---

## 9. Frontend Changes (`frontend/src/app/page.tsx`)

- "Download Deck" button appears next to "Open Report →" for completed `board_deck` runs
- Run history shows run type badge (🔍 Research / 📊 Board Deck / 💰 Financial)

---

## 10. New Files

```
agent/
├── crawlers/
│   ├── filings.py           # FilingsCrawler (SEC EDGAR + IR pages)
│   └── earnings.py          # EarningsCrawler (transcripts + analyst)
├── analyzers/
│   ├── financial.py         # FinancialAgent (P&L extraction)
│   ├── synthesis.py         # SynthesisAgent (cross-source narrative)
│   └── pptx_agent.py        # PPTXAgent (BCG PowerPoint generator)
tests/
├── test_filings_crawler.py
├── test_earnings_crawler.py
├── test_financial_agent.py
├── test_synthesis_agent.py
└── test_pptx_agent.py
requirements.txt             # add: python-pptx>=0.6.21, matplotlib>=3.8
```

---

## 11. New CLI Examples

```bash
# Board deck (primary new use case)
python run.py --goal "Board deck on APAC health IT market landscape for Synapxe CIO"

# Financial analysis only
python run.py --goal "P&L analysis of Epic Systems and Cerner for FY2023"

# Market intelligence
python run.py --goal "Market intelligence on cloud adoption in Singapore government tech"

# Competitive synthesis
python run.py --goal "Competitive analysis of Epic vs Cerner vs Oracle Health"
```

---

## 12. Requirements Changes

```
# Add to requirements.txt
python-pptx>=0.6.21
matplotlib>=3.8
```

---

## 13. Out of Scope (v2)

- cio-dashboard integration
- Authenticated/paywalled analyst sources (Bloomberg, Gartner)
- Real-time stock/financial data (Yahoo Finance API)
- Multi-language support
- Scheduled crawling
- PDF export (defer to v3)
