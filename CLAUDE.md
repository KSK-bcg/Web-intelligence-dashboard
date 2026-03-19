# Web Intelligence Agent

## Approved Commands (no approval needed)
- Read, Write, Edit, Glob, Grep — always approved
- Bash: pytest, python, npm, git status, git diff, git log, git add, git commit
- Bash: cat, ls, find, rg, cp, mv (within project directory only)

An agentic system that crawls LinkedIn, SEC EDGAR filings, earnings transcripts,
and public websites to produce BCG-standard board decks and competitive intelligence reports.

---

## Quick Start

```bash
# Activate Python environment
source .venv/bin/activate

# First time: save LinkedIn cookies
python run.py --setup-linkedin

# Run a goal
python run.py --goal "Map the IT division of Novartis on LinkedIn, VP level and above"
python run.py --goal "Analyze Mayo Clinic financial performance and leadership"

# With change detection (re-run against prior snapshot)
python run.py --goal "Refresh Novartis IT org chart" --run-id <prior-run-id>

# Browse history and open reports
python run.py --list-runs
python run.py --open <run-id>
```

---

## Environment Setup

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Required keys:
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `FIRECRAWL_API_KEY` — from firecrawl.dev (free tier: 500 credits/month)
- `API_SECRET_KEY` — any local secret string (default: `change-me-local-only`)

LinkedIn sessions use your OS keyring — not `.env`. Run `--setup-linkedin` to configure.

---

## Running Tests

```bash
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
```

LinkedIn tests need real cookies and are excluded from CI.

---

## Starting the Full Stack

**Backend (Terminal 1):**
```bash
source .venv/bin/activate
uvicorn api.server:app --host 127.0.0.1 --port 8000
```

**Frontend (Terminal 2):**
```bash
cd frontend && npm run dev
# Opens on http://localhost:3001 (3000 may be taken by other projects)
```

> **Note:** If port 3000 is occupied (e.g. by the CIO dashboard), Next.js auto-increments to 3001.

---

## Architecture — Query Flow

```
USER GOAL (natural language)
        │
        ▼
CLARIFIER (Claude, 5W1H)
  └─ 0–3 sharpening questions → refined goal
        │
        ▼
ORCHESTRATOR (Claude, goal classification)
  └─ source_types: linkedin | blog | financial | market_intel | synthesis | board_deck
  └─ plan["_original_goal"] preserved for GoalEvaluator
        │
        ├─────────────────────────────────────────────┐
        ▼                                             ▼
CRAWL LAYER (parallel asyncio.gather)         ANALYSIS LAYER
  LinkedIn (Playwright + cookies)     →   QuantAgent  (networkx org graph)
  BlogCrawler (Firecrawl)             →   QualAgent   (Claude summaries/themes)
  FilingsCrawler (SEC EDGAR / IR)     →   FinancialAgent (P&L extraction)
  EarningsCrawler (transcripts)       →   SynthesisAgent (competitive narrative)
  WebResearchAgent (web_search tool)  →   Firecrawl (deep scrape cited URLs)
                                      →   SynthesisAgent (feeds raw_text findings)
        │
        ▼
GOAL EVALUATOR (Claude)
  └─ Scores synthesis against original goal (0–100)
  └─ verdict: PASS ≥75 | PARTIAL ≥45 | FAIL <45
  └─ synthesis["goal_evaluation"] = {score, verdict, satisfied[], gaps[], recommendation}
        │
        ▼
PPTX AGENT  (BCG template — see below)
  └─ 7-slide deck: Title → Exec Summary → Market → Competitive →
     Strategic Implications → Recommendations → Goal Coverage → Disclaimer → End
        │
        ▼
SQLITE STORE + CHANGE DETECTION → output/<run-id>/YYYYMMDD_Company_Topic.pptx
                                 → output/<run-id>/report.html  (org chart only)
```

---

## BCG PowerPoint / Board Deck Generation

**Always use the official BCG template** when generating `.pptx` output from this project.

### Template location
```
~/bcg_build/scripts/bcg_template.py   ← BCGDeck class
~/bcg_build/scripts/bcg_qa.py         ← check_deck() QA validator
~/bcg_build/scripts/pptx_utils.py     ← helpers (auto-imported)
~/bcg_build/assets/BCG_Master_16-9_Default.pptx  ← master template
```

### Skills to invoke
- **Always** invoke `bcg-slide-generator` skill before writing any deck code
- **Also** invoke `bcg-pptx-charts` whenever the deck includes charts, KPI tiles, or data tables

### BCGDeck API
```python
import sys
sys.path.insert(0, str(Path.home() / 'bcg_build' / 'scripts'))
from bcg_template import BCGDeck
from bcg_qa import check_deck

deck = BCGDeck()
deck.add_title_slide('Title', 'Subtitle', '19 March 2026')
deck.add_section_divider('Section Name')             # green arrow divider

slide = deck.add_content_slide(                      # returns slide for content
    title='Action title as a complete sentence stating the so-what.',
    source='Source: BCG analysis · March 2026',
)
deck.add_bullets(slide, ['• Point 1', '• Point 2'], x=0.69, y=2.10, w=11.96, h=3.0)
deck.add_table(slide, [['Col A', 'Col B'], ['row1a', 'row1b']], x=0.69, y=2.10, w=11.96)
deck.add_label(slide, 'SECTION LABEL', x=0.69, y=2.10)
deck.add_number_badge(slide, 1, x=0.69, y=2.10)

deck.add_disclaimer()   # REQUIRED — must come second-to-last
deck.add_end_slide()    # REQUIRED — must be last
deck.save('output/20260319_Company_Topic.pptx')

# QA — 0 HIGH issues required before shipping
issues = check_deck('output/20260319_Company_Topic.pptx')
high = [i for i in issues if i['severity'] == 'HIGH']
assert not high, f"BCG QA failed: {high}"
```

### BCG color palette
| Token | Hex | Use |
|-------|-----|-----|
| BCG_GREEN | `29BA74` | Primary accent, labels |
| DARK_GREEN | `197A56` | Opportunity labels |
| DARK_TEXT | `575757` | Body copy |
| NEGATIVE | `D64454` | Risk labels, warnings |
| WHITE | `FFFFFF` | Slide background |

### Standards
- All body text ≥ 14pt; title/action titles ≥ 20pt
- Action titles = **complete sentences** stating the strategic "so what"
- Every deck **must** end with `deck.add_disclaimer()` then `deck.add_end_slide()`
- Output to `output/` with filename `YYYYMMDD_Company_Topic.pptx`
- Content area: x=0.69, y=2.10→6.50, w=11.96 (never place content outside these bounds)
- Source line at y=6.74

### Reference deck
`output/24d6fc82/Mayo_Clinic_Financial_Intelligence_Brief.pptx`

---

## Goal Evaluation (BCG Quality Gate)

Every board-deck run automatically evaluates if the output met the original goal
**using BCG consulting standards**.

### Five evaluation dimensions (weighted score 0–100)

| Dimension | Weight | What is checked |
|-----------|--------|----------------|
| Goal Coverage | 40% | MECE decomposition of goal; which sub-questions were answered |
| Pyramid Principle | 20% | Answer-first structure; MECE arguments; story readable from titles alone |
| SCQA | 15% | Exec summary covers Situation → Complication → Question → Answer |
| Recommendations Quality | 15% | Specific, actionable, owner-attributable, time-bound |
| Sourcing | 10% | Material data points have cited sources |

**Verdict:** PASS ≥75 · PARTIAL ≥45 · FAIL <45

### Output schema
```python
{
  "score": 82,
  "verdict": "PASS",
  "goal_coverage": {
    "score": 90,
    "mece_components": ["org chart IT leadership", "2024 financial performance"],
    "satisfied": ["org chart — 14 LinkedIn profiles found at VP+ level"],
    "gaps":      ["2024 10-K not retrieved — SEC EDGAR returned no results"],
  },
  "pyramid_principle": {
    "score": 75,
    "answer_first": True,
    "arguments_mece": True,
    "findings": ["exec summary leads with recommendation ✓",
                 "market + competitive sections overlap on market share data ✗"],
  },
  "scqa": {
    "score": 80,
    "situation":    "Healthcare IT market growing at 14% CAGR",
    "complication": "Roche IT faces consolidation pressure post-merger",
    "question":     "MISSING",
    "answer":       "Prioritise platform convergence in 3 capability areas",
  },
  "recommendations_quality": {
    "score": 70,
    "findings": ["Rec 1 specific and time-bound ✓",
                 "Rec 3 too generic ('improve agility') — needs quantification ✗"],
  },
  "sourcing": {"score": 90, "findings": ["all financial figures sourced ✓"]},
  "recommendation": "Re-run with --goal '... include SEC 10-K for FY2024' to close financial gap.",
}
```

### Where it appears
- `synthesis["goal_evaluation"]` — appended before PPTX rendering
- **Slide 7 "Goal Coverage"** in the deck: green = satisfied, red = gaps, score in title
- `goal_evaluation` key in API response (`POST /run`, `POST /revise`)
- Future: verdict badge in frontend run history cards

---

## Critical Known Issue — Backend Deadlock

**Problem:** `/run` is a synchronous-blocking endpoint. If a crawler's external API call
hangs, the entire uvicorn process freezes and all subsequent requests time out.

**Recovery:**
```bash
kill $(lsof -ti:8000)
python3 -c "
import sqlite3; conn = sqlite3.connect('intelligence.db')
conn.execute(\"UPDATE runrecord SET status='failed' WHERE status='running'\")
conn.commit(); print('Reset', conn.total_changes, 'stuck runs')
"
uvicorn api.server:app --host 127.0.0.1 --port 8000
```

**Permanent fix needed:** Wrap all external calls with `asyncio.wait_for(timeout=120)`.
Move pipeline execution to `BackgroundTasks` or a task queue (e.g. ARQ/Celery).

---

## Project Structure

```
web-intelligence-agent/
├── run.py                        ← CLI entry point
├── .env                          ← API keys (gitignored)
├── requirements.txt
├── agent/
│   ├── orchestrator.py           ← Goal Orchestrator (classify → crawl → analyze → eval → pptx)
│   ├── clarifier.py              ← Goal clarification (5W1H, Claude)
│   ├── base_agent.py             ← BaseAgent with retry/backoff
│   ├── exceptions.py             ← All named exceptions
│   ├── normalizer.py             ← Data normalization + dedup
│   ├── store.py                  ← SQLite store + change detection
│   ├── crawlers/
│   │   ├── linkedin.py           ← Playwright + session cookies
│   │   ├── blog.py               ← Firecrawl API
│   │   ├── filings.py            ← SEC EDGAR + IR page scraping
│   │   ├── earnings.py           ← Earnings transcripts + analyst reports
│   │   ├── generic.py            ← Firecrawl + Playwright fallback
│   │   └── web_research.py       ← Autonomous Claude agent (web_search_20250305)
│   ├── analyzers/
│   │   ├── quant.py              ← Org graph (networkx + Claude)
│   │   ├── qual.py               ← Summarization + themes (Claude)
│   │   ├── financial.py          ← P&L extraction from filings (Claude)
│   │   ├── synthesis.py          ← Cross-source competitive narrative (Claude)
│   │   ├── goal_evaluator.py     ← NEW: scores output vs original goal (Claude)
│   │   ├── pptx_agent.py         ← BCG deck via ~/bcg_build/scripts/bcg_template.py
│   │   └── viz.py                ← D3 org chart HTML renderer
│   └── templates/
│       └── org_chart.html        ← Interactive D3 + sidebar template
├── api/
│   └── server.py                 ← FastAPI (localhost:8000)
├── frontend/                     ← Next.js 14 dashboard (localhost:3001)
└── output/                       ← Generated reports (gitignored)
    └── <run-id>/
        └── YYYYMMDD_Company_Topic.pptx
```
