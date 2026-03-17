# Web Intelligence Agent

## Approved Commands (no approval needed)
- Read, Write, Edit, Glob, Grep — always approved
- Bash: pytest, python, npm, git status, git diff, git log, git add, git commit
- Bash: cat, ls, find, rg, cp, mv (within project directory only)

An agentic system that crawls LinkedIn and public websites to build org charts,
visualizations, and qualitative summaries.

## Quick Start

```bash
# Activate Python environment
source .venv/bin/activate

# First time: save LinkedIn cookies
python run.py --setup-linkedin

# Run a goal
python run.py --goal "Map the IT division of Novartis on LinkedIn, VP level and above"
python run.py --goal "Summarize the last 10 posts from https://martinfowler.com"

# With change detection (re-run against prior snapshot)
python run.py --goal "Refresh Novartis IT org chart" --run-id <prior-run-id>

# Browse history and open reports
python run.py --list-runs
python run.py --open <run-id>
```

## Environment Setup

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Required keys:
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `FIRECRAWL_API_KEY` — from [firecrawl.dev](https://firecrawl.dev) (free tier: 500 credits/month)
- `API_SECRET_KEY` — any local secret string (default: `change-me-local-only`)

LinkedIn sessions use your OS keyring — not `.env`. Run `--setup-linkedin` to configure.

## Running Tests

```bash
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py
```

LinkedIn tests need real cookies and are excluded from CI.

## Starting the Full Stack

**Backend (Terminal 1):**
```bash
source .venv/bin/activate
uvicorn api.server:app --host 127.0.0.1 --port 8000
```

**Frontend (Terminal 2):**
```bash
cd frontend && npm run dev
# Open http://localhost:3000
```

## Architecture

See `docs/superpowers/specs/2026-03-16-web-intelligence-agent-design.md`

```
USER GOAL (natural language)
        ↓
ORCHESTRATOR (Claude claude-sonnet-4-6 + goal classification)
        ↓
CRAWL LAYER          ANALYSIS LAYER
LinkedIn (Playwright) → Quant Agent (org graph, networkx)
Blog/News (Firecrawl) → Qual Agent (summaries, themes)
Generic Web           → Viz Agent (D3 org chart HTML)
        ↓
SQLite Store + Change Detection → HTML Report
```

## Agent Invocation Examples

```bash
# LinkedIn org chart (pharma IT division)
python run.py --goal "Map the IT division of Roche on LinkedIn"
python run.py --goal "Find VP-level and above in Novartis IT on LinkedIn"

# Blog summarization
python run.py --goal "Summarize the last 10 posts from https://engineering.atspotify.com"
python run.py --goal "What are the key themes on https://netflixtechblog.com"

# Change detection
python run.py --list-runs
python run.py --goal "Refresh Roche IT" --run-id <prior-run-id>
```

## Project Structure

```
web-intelligence-agent/
├── run.py                    ← CLI entry point
├── .env                      ← API keys (gitignored)
├── requirements.txt
├── agent/
│   ├── orchestrator.py       ← Goal Orchestrator (Claude + pipeline)
│   ├── base_agent.py         ← BaseAgent with retry/backoff
│   ├── exceptions.py         ← All named exceptions
│   ├── normalizer.py         ← Data normalization + dedup
│   ├── store.py              ← SQLite store + change detection
│   ├── crawlers/
│   │   ├── linkedin.py       ← Playwright + session cookies
│   │   ├── blog.py           ← Firecrawl API
│   │   └── generic.py        ← Firecrawl + Playwright fallback
│   ├── analyzers/
│   │   ├── quant.py          ← Org graph (networkx + Claude)
│   │   ├── qual.py           ← Summarization + themes (Claude)
│   │   └── viz.py            ← D3 org chart HTML renderer
│   └── templates/
│       └── org_chart.html    ← Interactive D3 + sidebar template
├── api/
│   └── server.py             ← FastAPI (localhost:8000)
├── frontend/                 ← Next.js 14 dashboard
└── output/                   ← Generated reports (gitignored)
```
