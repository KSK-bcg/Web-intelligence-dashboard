# Web Intelligence Agent — Design Spec
**Date:** 2026-03-16
**Status:** Approved
**Mode reviewed:** SCOPE EXPANSION (CEO/plan review)

---

## 1. Problem & Goal

Manual research on LinkedIn (org structures, executive profiles, IT divisions) takes hours of copy-pasting. This agent automates authenticated web traversal to produce org charts, visualizations, and qualitative summaries — on demand, with change detection across runs.

**Primary use case:** Map the IT division org structure of a pharma company using LinkedIn → high-confidence, interactive org chart.

**Secondary use cases:** Blog/article summarization, quantitative analysis of web data, any site where the user has an authenticated account.

---

## 2. Architecture: Two-Layer Agentic System

```
USER GOAL (natural language)
        │
        ▼
┌──────────────────────────────────────────┐
│  LAYER 0: GOAL ORCHESTRATOR              │
│  Claude claude-sonnet-4-6 + Sequential Thinking MCP  │
│  • Parse NL goal → task classification   │
│  • Select & sequence sub-agents (tools)  │
│  • Merge results, generate final output  │
└──────────┬───────────┬───────────────────┘
           │           │           │
           ▼           ▼           ▼
┌──────────────────────────────────────────┐
│  LAYER 1: CRAWL SUB-AGENTS (site-aware)  │
├─────────────┬────────────┬───────────────┤
│ LinkedIn    │ Blog/News  │ Generic Web   │
│ Agent       │ Agent      │ Agent         │
│ Playwright  │ Firecrawl  │ Firecrawl +   │
│ + cookies   │ API        │ Playwright    │
│ Rate limit  │ Schema ext │ fallback      │
│ CAPTCHA hdl │            │ Auth forms    │
└──────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│  LAYER 1.5: DATA NORMALIZATION           │
│  • Raw → canonical Person/Org/Article    │
│  • Entity dedup (name variants)          │
│  • Confidence scoring per field          │
│  • Persist to SQLite + diff prior runs   │
│  • Emit change events                    │
└──────────┬───────────┬───────────────────┘
           │           │           │
           ▼           ▼           ▼
┌──────────────────────────────────────────┐
│  LAYER 2: ANALYSIS SUB-AGENTS (task-aware│
├─────────────┬────────────┬───────────────┤
│ Quant Agent │ Qual Agent │ Viz Agent     │
│ Org graph   │ Exec bios  │ D3 org chart  │
│ Reporting   │ Theme ext  │ Recharts      │
│ chains      │ Sentiment  │ Export engine │
│ Dept counts │ Narrative  │ PDF/SVG/HTML  │
└──────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│  LAYER 3: OUTPUT + INTELLIGENCE STORE    │
│  Report Generator + SQLite store         │
│  Run history, change log, entity registry│
└──────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Component | Technology | Rationale |
|---|---|---|
| Backend orchestrator | Python 3.11+ | Best AI/automation ecosystem |
| LinkedIn crawl | Playwright + session cookies | Auth required; only viable approach |
| Public site crawl | Firecrawl API | Managed JS rendering, no browser overhead |
| Agent SDK | Anthropic Claude SDK (Python) | Tool-calling pattern; claude-sonnet-4-6 |
| Reasoning | Sequential Thinking MCP | Complex multi-step goal decomposition |
| Graph analysis | networkx | Org tree construction + cycle detection |
| Data store | SQLite via SQLModel | Single-user, no server, run history |
| Backend API | FastAPI (localhost only) | Frontend bridge via SSE for progress |
| Frontend | Next.js 14 + TypeScript | Matches existing cio-dashboard stack |
| Org chart UI | D3.js | Interactive tree with drill-down |
| Charts | Recharts | Reuse from cio-dashboard |
| Export | python-pptx, weasyprint | PPT + PDF output |

---

## 4. Agent Invocation Interface

The primary interface is a **Python CLI**:

```bash
# Map an org chart
python run.py --goal "Map the IT division of Novartis on LinkedIn, focus on VP level and above"

# Summarize a blog
python run.py --goal "Summarize the last 10 posts from https://example.com/blog"

# Re-run with change detection
python run.py --goal "Refresh Novartis IT org chart" --run-id novartis-it-001

# List prior runs
python run.py --list-runs

# View output in browser
python run.py --open novartis-it-001
```

Output: a self-contained `output/<run-id>/report.html` opened in browser, plus SQLite snapshot.

---

## 5. Project Structure

```
web-intelligence-agent/
├── run.py                      # CLI entry point
├── .env                        # API keys (gitignored)
├── requirements.txt
├── agent/
│   ├── orchestrator.py         # Goal Orchestrator (Claude + tools)
│   ├── base_agent.py           # BaseAgent with retry/backoff/logging
│   ├── crawlers/
│   │   ├── linkedin.py         # Playwright + session cookie auth
│   │   ├── blog.py             # Firecrawl API
│   │   └── generic.py          # Firecrawl + Playwright fallback
│   ├── analyzers/
│   │   ├── quant.py            # Org graph, counts, charts
│   │   ├── qual.py             # Summarization, themes, sentiment
│   │   └── viz.py              # D3 org chart, export engine
│   ├── normalizer.py           # Raw → canonical schema + dedup
│   └── store.py                # SQLite via SQLModel, change detection
├── api/
│   └── server.py               # FastAPI (localhost:8000, SSE progress)
├── frontend/                   # Next.js 14 dashboard
│   └── src/
│       ├── app/
│       ├── components/
│       │   ├── OrgChart.tsx    # D3.js interactive org chart
│       │   └── RunHistory.tsx
│       └── lib/
├── output/                     # Generated reports (gitignored)
├── tests/
│   ├── test_normalizer.py
│   ├── test_quant_agent.py
│   ├── test_org_graph.py       # Cycle detection, disconnected graph
│   └── fixtures/               # VCR cassettes for LinkedIn mocks
└── docs/
    └── superpowers/specs/      # This file
```

---

## 6. Critical Implementation Requirements

### 6.1 Prompt Injection Guard
All crawled content MUST be wrapped before passing to Claude:
```python
safe_content = f"<content source='untrusted'>{scraped_text}</content>"
# Never: f"Analyze this: {scraped_text}"
```

### 6.2 Org Graph Cycle Detection
Before rendering any org chart:
```python
import networkx as nx
if not nx.is_directed_acyclic_graph(org_graph):
    raise OrgGraphCycleError("Cycle detected in reporting chain")
```

### 6.3 Session Cookie Security
- Store LinkedIn cookies in OS keyring (`keyring` lib), not `.env`
- Never log cookie values
- Cookies are user-scoped: tool explicitly refuses bulk scraping (>50 profiles/run)

### 6.4 Firecrawl Auth Fail-Fast
```python
# At startup, before any crawl:
if not firecrawl_client.test_auth():
    raise FirecrawlAuthError("Invalid API key — set FIRECRAWL_API_KEY in .env")
```

### 6.5 Rate Limiting (LinkedIn)
- Random delay between 2.0–4.5 seconds per page
- Max 50 profiles per run (hard limit)
- Exponential backoff on 429: `2^n` seconds, max 5 retries
- CAPTCHA detection → pause + notify user (no auto-solve)

---

## 7. Change Detection (built into v1)

On each re-run against the same target:
1. Load prior SQLite snapshot
2. Diff: new people, departed people, title changes
3. Emit structured change log:
```json
{"type": "promotion", "person": "Jane Smith", "from": "Director", "to": "VP", "detected": "2026-03-16"}
{"type": "new_hire", "person": "Alex Chen", "title": "Head of Cloud", "detected": "2026-03-16"}
```
4. Surface in report as "Changes since last run" section

---

## 8. Error & Rescue Map (critical paths)

| Error | Action | User sees |
|---|---|---|
| `LinkedInAuthExpiredError` | Pause, prompt re-auth | "Session expired — re-login" |
| `LinkedInCaptchaError` | Pause + screenshot + alert | "CAPTCHA hit — manual action needed" |
| `LinkedInRateLimitError` | Exponential backoff | Silent (progress indicator) |
| `FirecrawlAuthError` | Fail fast at startup | "Invalid Firecrawl API key" |
| `OrgGraphCycleError` | Halt, log full graph | "Cycle in org chart — partial output" |
| `AgentRefusalError` | Log + use raw data only | "AI analysis unavailable for X" |
| `InsufficientDataError` | Surface partial chart | "Partial data — expand search depth" |

---

## 9. TODOS (deferred to v2+)

| Item | Priority | Effort |
|---|---|---|
| Confidence scoring UI (node-level HIGH/MED/LOW) | P1 | M |
| Tech stack inference from job postings | P2 | L |
| 'Your network' LinkedIn connection overlay | P2 | M |
| PowerPoint export (python-pptx) | P3 | M |

---

## 10. Out of Scope (v1)

- Scheduled/cron-based re-crawling (manual re-run only)
- Multi-user / shared intelligence store
- Cloud deployment (local-only)
- LinkedIn API (official) — too limited for org chart use case
- CRM integration
