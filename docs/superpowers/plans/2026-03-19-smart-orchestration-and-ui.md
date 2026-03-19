# Smart Orchestration + Persistent UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add goal clarification dialogue, parallel multi-source crawling, smart PPTX naming with in-place revision, and upgrade the local frontend into a full conversational agent interface.

**Architecture:** A new `Clarifier` agent uses Claude + a 5W1H research framework to ask 1–3 sharpening questions before any crawl starts; the `Orchestrator` now classifies goals into *multiple* `source_types` and fans out crawlers in parallel via `asyncio.gather`; all outputs land in a flat `output/` folder named `{company}-{topic}-{YYYYMMDD}.pptx` and revisions overwrite in-place; the existing Next.js frontend is upgraded with a multi-step clarification flow and revision panel.

**Tech Stack:** Python 3.11, FastAPI, anthropic SDK, python-pptx, SQLModel/SQLite, Next.js 14, TypeScript, Tailwind CSS

---

## Chunk 1: Goal Clarifier + API endpoint

### Task 1: Goal Clarifier agent (`agent/clarifier.py`)

**Files:**
- Create: `agent/clarifier.py`
- Create: `tests/test_clarifier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_clarifier.py
import pytest
from unittest.mock import patch, MagicMock
from agent.clarifier import Clarifier

def _mock_response(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg

def test_clarify_returns_questions():
    c = Clarifier()
    with patch.object(c.client.messages, "create", return_value=_mock_response(
        '{"questions": ["Which specific department?", "VP-level and above only?"], "refined_context": {"company": "Roche", "scope": "IT"}}'
    )):
        result = c.clarify("Map Roche IT")
    assert len(result["questions"]) == 2
    assert "company" in result["refined_context"]

def test_clarify_returns_empty_when_goal_is_specific():
    c = Clarifier()
    with patch.object(c.client.messages, "create", return_value=_mock_response(
        '{"questions": [], "refined_context": {"company": "Roche", "scope": "IT", "level": "VP+"}}'
    )):
        result = c.clarify("Map the IT division of Roche on LinkedIn, VP level and above")
    assert result["questions"] == []

def test_build_refined_goal():
    c = Clarifier()
    goal = "Map Roche IT"
    answers = {"Which department?": "IT", "Level?": "VP and above"}
    refined = c.build_refined_goal(goal, answers)
    assert "Roche" in refined
    assert "VP" in refined
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/srikumarkrishna/projects/web-intelligence-agent && source .venv/bin/activate && pytest tests/test_clarifier.py -v 2>&1 | head -30
```

Expected: `ERROR` — module not found.

- [ ] **Step 3: Implement `agent/clarifier.py`**

```python
# agent/clarifier.py
"""
Goal Clarifier — uses 5W1H research framework to ask sharpening questions
before the orchestrator runs, producing a tighter goal context.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List

import anthropic

logger = logging.getLogger(__name__)

_CLARIFY_PROMPT = """You are a research scoping expert. A user has submitted a research goal.
Apply the 5W1H framework (Who, What, When, Where, Why, How) to identify the 1-3 most
important ambiguities that, if resolved, would significantly improve result quality.

If the goal is already specific and unambiguous, return zero questions.

Goal: {goal}

Return ONLY valid JSON:
{{
  "questions": ["question1", "question2"],
  "refined_context": {{
    "company": "extracted company name or null",
    "scope": "department/topic extracted or null",
    "level": "seniority filter extracted or null",
    "time_horizon": "time period if relevant or null",
    "output_preference": "deck | report | both or null"
  }}
}}
"""

_REFINE_PROMPT = """A user submitted this research goal: {goal}

They answered these clarifying questions:
{qa_pairs}

Rewrite the goal as a single, precise, actionable research instruction that incorporates
all the answers. Be specific. Include company name, department, seniority level, and any
other constraints that were clarified. Return only the refined goal string, no explanation.
"""


class Clarifier:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    def clarify(self, goal: str) -> Dict[str, Any]:
        """Return questions + extracted context for a goal."""
        prompt = _CLARIFY_PROMPT.format(goal=goal)
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
            return json.loads(text)
        except Exception as e:
            logger.warning("Clarifier failed (%s), returning empty", e)
            return {"questions": [], "refined_context": {}}

    def build_refined_goal(self, goal: str, answers: Dict[str, str]) -> str:
        """Produce a tightened goal string from original goal + Q&A answers."""
        if not answers:
            return goal
        qa_pairs = "\n".join(f"Q: {q}\nA: {a}" for q, a in answers.items())
        prompt = _REFINE_PROMPT.format(goal=goal, qa_pairs=qa_pairs)
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning("build_refined_goal failed (%s), returning original", e)
            return goal
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_clarifier.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/clarifier.py tests/test_clarifier.py
git commit -m "feat: add Goal Clarifier with 5W1H research sharpening"
```

---

### Task 2: Add `POST /clarify` to API

**Files:**
- Modify: `api/server.py`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add Pydantic model + endpoint to `api/server.py`**

After the existing `RunRequest` class, add:

```python
class ClarifyRequest(BaseModel):
    goal: str

class ClarifyResponse(BaseModel):
    questions: list[str]
    refined_context: dict

@app.post("/clarify", response_model=ClarifyResponse)
async def clarify_goal(req: ClarifyRequest, _: str = Depends(verify_api_key)):
    """Ask clarifying questions for a goal before running."""
    from agent.clarifier import Clarifier
    result = Clarifier().clarify(req.goal)
    return ClarifyResponse(
        questions=result.get("questions", []),
        refined_context=result.get("refined_context", {}),
    )
```

Also add `RefineRequest` and `/refine` to convert answers → refined goal:

```python
class RefineRequest(BaseModel):
    goal: str
    answers: dict[str, str]  # {question: answer}

@app.post("/refine")
async def refine_goal(req: RefineRequest, _: str = Depends(verify_api_key)):
    from agent.clarifier import Clarifier
    refined = Clarifier().build_refined_goal(req.goal, req.answers)
    return {"refined_goal": refined}
```

- [ ] **Step 2: Add `clarifyGoal` + `refineGoal` to `frontend/src/lib/api.ts`**

```typescript
export interface ClarifyResult {
  questions: string[];
  refined_context: Record<string, string | null>;
}

export async function clarifyGoal(goal: string): Promise<ClarifyResult> {
  const res = await fetch(`${API_BASE}/clarify`, {
    method: "POST", headers,
    body: JSON.stringify({ goal }),
  });
  if (!res.ok) await apiError(res, `Clarify failed: ${res.status}`);
  return res.json();
}

export async function refineGoal(goal: string, answers: Record<string, string>): Promise<string> {
  const res = await fetch(`${API_BASE}/refine`, {
    method: "POST", headers,
    body: JSON.stringify({ goal, answers }),
  });
  if (!res.ok) await apiError(res, `Refine failed: ${res.status}`);
  const data = await res.json();
  return data.refined_goal;
}
```

- [ ] **Step 3: Smoke-test the endpoint manually**

```bash
source .venv/bin/activate && uvicorn api.server:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s -X POST http://localhost:8000/clarify \
  -H "x-api-key: change-me-local-only" \
  -H "Content-Type: application/json" \
  -d '{"goal": "Map Roche IT"}' | python -m json.tool
kill %1
```
Expected: JSON with `questions` array.

- [ ] **Step 4: Commit**

```bash
git add api/server.py frontend/src/lib/api.ts
git commit -m "feat: add /clarify and /refine API endpoints"
```

---

## Chunk 2: Multi-source parallel orchestration

### Task 3: Multi-source classifier + parallel crawler

**Files:**
- Modify: `agent/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_orchestrator.py`:

```python
def test_classify_returns_multiple_source_types():
    """Multi-faceted goal should return multiple source_types."""
    orch = Orchestrator.__new__(Orchestrator)
    # Mock Claude returning multi-source JSON
    import types
    orch.client = types.SimpleNamespace()
    mock_msg = types.SimpleNamespace(content=[types.SimpleNamespace(
        text='{"source_types": ["linkedin", "financial"], "target": "roche", '
             '"company_name": "Roche", "department_filter": "IT", "url": null, '
             '"max_profiles": 30, "companies": ["Roche"], "sector": "pharma", "region": null}'
    )])
    orch.client.messages = types.SimpleNamespace(create=lambda **kw: mock_msg)
    plan = orch._classify_goal("Map Roche IT org and pull financials")
    assert "linkedin" in plan["source_types"]
    assert "financial" in plan["source_types"]
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_orchestrator.py::test_classify_returns_multiple_source_types -v
```
Expected: FAIL (KeyError or AttributeError)

- [ ] **Step 3: Update `CLASSIFY_PROMPT` in `agent/orchestrator.py`**

Replace the `CLASSIFY_PROMPT` constant entirely:

```python
CLASSIFY_PROMPT = """Classify this research goal and extract key parameters.

Goal: {goal}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "source_types": ["linkedin"],
  "target": "company-slug-for-storage",
  "company_name": "Company Name",
  "department_filter": "IT",
  "url": null,
  "max_profiles": 30,
  "companies": [],
  "sector": null,
  "region": null
}}

Rules for source_types (can be a list with multiple values):
- LinkedIn org structure → include "linkedin"
- Blog or website URL → include "blog"
- Financial filings / P&L → include "financial"
- Market landscape / industry → include "market_intel"
- Competitive analysis → include "synthesis"
- Board deck / presentation explicitly requested → include "board_deck"
- If the goal spans multiple domains (e.g. org chart + financials), include ALL that apply.

For financial/market_intel/synthesis/board_deck: populate "sector" and "region" if mentioned.
"""
```

- [ ] **Step 4: Update `_classify_goal` fallback to use `source_types` list**

In the `except` block of `_classify_goal`, change:
```python
# OLD
return {
    "source_type": "linkedin",
    ...
}
# NEW
return {
    "source_types": ["linkedin"],
    "analysis_type": "org_chart",
    "target": goal.lower().replace(" ", "-")[:20],
    "company_name": goal,
    "department_filter": None,
    "url": None,
    "max_profiles": 30,
}
```

Also update the JSON parse to ensure `source_types` always exists:
```python
data = json.loads(text)
# back-compat: old single source_type → list
if "source_type" in data and "source_types" not in data:
    data["source_types"] = [data["source_type"]]
elif "source_types" not in data:
    data["source_types"] = ["linkedin"]
return data
```

- [ ] **Step 5: Replace `_crawl` with parallel fan-out**

Replace `_crawl` method entirely:

```python
async def _crawl(self, plan: dict) -> list:
    """Fan out to all source_types in parallel, merge results."""
    import asyncio
    source_types = plan.get("source_types") or [plan.get("source_type", "linkedin")]
    tasks = [self._crawl_one(st, plan) for st in source_types]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = []
    for st, result in zip(source_types, results):
        if isinstance(result, Exception):
            logger.warning("Crawler %s failed: %s", st, result)
        else:
            merged.extend(result)
    return merged

async def _crawl_one(self, source_type: str, plan: dict) -> list:
    """Run a single crawler by source_type."""
    if source_type == "linkedin":
        crawler = LinkedInCrawler(max_profiles=int(plan.get("max_profiles") or 30))
        return await crawler.run(
            company_name=plan.get("company_name", ""),
            department_filter=plan.get("department_filter"),
        )
    elif source_type == "blog":
        return await BlogCrawler().run(url=plan.get("url", ""), max_pages=20)
    elif source_type == "financial":
        companies = plan.get("companies") or [plan.get("company_name", "")]
        return await FilingsCrawler().run(companies=companies)
    elif source_type in ("market_intel", "synthesis", "board_deck"):
        companies = plan.get("companies") or []
        target_query = plan.get("target") or plan.get("sector") or ""
        filings = []
        if companies:
            try:
                filings = await FilingsCrawler().run(companies=companies)
            except Exception as e:
                logger.warning("FilingsCrawler failed: %s", e)
        try:
            earnings = await EarningsCrawler().run(
                query=target_query, companies=companies, max_results=10,
            )
        except Exception as e:
            logger.warning("EarningsCrawler failed: %s", e)
            earnings = []
        return filings + earnings
    else:
        return await BlogCrawler().run(url=plan.get("url", ""), max_pages=20)
```

- [ ] **Step 6: Update pipeline routing in `run()` to use `source_types` list**

In `run()`, change the routing logic:

```python
source_types = plan.get("source_types") or [plan.get("source_type", "linkedin")]

BOARD_DECK_TYPES = {"board_deck", "market_intel", "synthesis", "financial"}
use_board_deck_pipeline = bool(BOARD_DECK_TYPES.intersection(set(source_types)))
has_linkedin = "linkedin" in source_types
has_blog = "blog" in source_types

if use_board_deck_pipeline:
    # Board deck pipeline handles financial/synthesis/market_intel
    # If linkedin is also requested, run QuantAgent+QualAgent on people too
    people_data = [d for d in raw_data if d.get("source") == "linkedin" or "name" in d]
    pipeline_result = await self._run_board_deck_pipeline(plan, raw_data, run_id)
    self.store.complete_run(run_id)
    return {
        "run_id": run_id,
        "report_path": None,
        "pptx_path": pipeline_result.get("pptx_path"),
        "changes": [],
        "people_count": len(people_data),
        "synthesis": pipeline_result.get("synthesis"),
    }
elif has_linkedin or has_blog:
    # Original org chart / blog pipeline
    people = self.normalizer.normalize(raw_data)
    ... # existing code unchanged
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/test_orchestrator.py -v
```
Expected: all pass (including new test).

- [ ] **Step 8: Commit**

```bash
git add agent/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: multi-source parallel crawl with asyncio.gather"
```

---

## Chunk 3: Smart output naming + in-place revision

### Task 4: Named PPTX output + revision support

**Files:**
- Modify: `agent/analyzers/pptx_agent.py`
- Modify: `agent/store.py`
- Modify: `api/server.py`
- Create: `tests/test_pptx_naming.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pptx_naming.py
from agent.analyzers.pptx_agent import build_output_path
import re

def test_build_output_path_basic():
    path = build_output_path("Roche", "IT Org Chart", "2026-03-19")
    assert path.endswith(".pptx")
    assert "roche" in path.lower()
    assert "it-org-chart" in path.lower()
    assert "2026-03-19" in path

def test_build_output_path_sanitizes_special_chars():
    path = build_output_path("J&J / Pharma", "R&D Overview", "2026-03-19")
    assert "/" not in path
    assert "&" not in path

def test_build_output_path_same_company_same_name():
    p1 = build_output_path("Roche", "IT Org", "2026-03-19")
    p2 = build_output_path("Roche", "IT Org", "2026-03-19")
    assert p1 == p2  # same → same file (revision overwrites)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pptx_naming.py -v
```
Expected: FAIL (ImportError)

- [ ] **Step 3: Add `build_output_path` to `agent/analyzers/pptx_agent.py`**

Add near the top (after imports):

```python
import re as _re
from pathlib import Path as _Path

def build_output_path(company: str, topic: str, date_str: str, output_dir: str = "output") -> str:
    """Build a stable, human-readable PPTX path.
    Same company + topic + date always returns the same path (enables in-place revision).
    """
    def slugify(s: str) -> str:
        s = s.lower().strip()
        s = _re.sub(r"[^\w\s-]", "", s)
        s = _re.sub(r"[\s_]+", "-", s)
        return s[:40].strip("-")

    filename = f"{slugify(company)}-{slugify(topic)}-{date_str}.pptx"
    _Path(output_dir).mkdir(parents=True, exist_ok=True)
    return str(_Path(output_dir) / filename)
```

- [ ] **Step 4: Update `PPTXAgent.render` to use named path**

In `pptx_agent.py`, find where the output path is constructed (currently uses `run_id`) and replace:

```python
# OLD (find and replace this pattern)
output_path = Path(f"output/{run_id}/board-deck.pptx")
output_path.parent.mkdir(parents=True, exist_ok=True)

# NEW
from datetime import date
company = synthesis.get("company_name") or synthesis.get("target") or "research"
topic = synthesis.get("topic") or synthesis.get("scope") or "intelligence-brief"
date_str = date.today().isoformat()
output_path_str = build_output_path(company, topic, date_str)
output_path = Path(output_path_str)
```

Also store `pptx_path` on the `RunRecord` so we can reference it later. Add field to store:

- [ ] **Step 5: Add `pptx_path` column to `RunRecord` in `agent/store.py`**

```python
class RunRecord(SQLModel, table=True):
    ...
    pptx_path: Optional[str] = None  # add this field
```

Add `update_pptx_path` method:
```python
def update_pptx_path(self, run_id: str, pptx_path: str):
    with Session(self.engine) as session:
        run = session.get(RunRecord, run_id)
        if run:
            run.pptx_path = pptx_path
            session.add(run)
            session.commit()
```

- [ ] **Step 6: Add `POST /revise` endpoint to `api/server.py`**

```python
class ReviseRequest(BaseModel):
    run_id: str
    revision_notes: str

@app.post("/revise")
async def revise_run(req: ReviseRequest, _: str = Depends(verify_api_key)):
    """Re-run synthesis+PPTX with revision notes, overwriting the existing file."""
    store = Store()
    store.init_db()
    run = store.get_run(req.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "complete":
        raise HTTPException(status_code=400, detail="Run not complete")

    orch = Orchestrator()
    # Re-run the board deck pipeline with revision notes appended to goal
    revised_goal = f"{run.goal}\n\nRevision instructions: {req.revision_notes}"
    result = await orch.run(goal=revised_goal, run_id_hint=req.run_id)
    return result
```

- [ ] **Step 7: Add `reviseRun` to `frontend/src/lib/api.ts`**

```typescript
export async function reviseRun(runId: string, revisionNotes: string): Promise<RunResult> {
  const res = await fetch(`${API_BASE}/revise`, {
    method: "POST", headers,
    body: JSON.stringify({ run_id: runId, revision_notes: revisionNotes }),
  });
  if (!res.ok) await apiError(res, `Revise failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 8: Run naming tests**

```bash
pytest tests/test_pptx_naming.py -v
```
Expected: 3 PASSED

- [ ] **Step 9: Commit**

```bash
git add agent/analyzers/pptx_agent.py agent/store.py api/server.py tests/test_pptx_naming.py frontend/src/lib/api.ts
git commit -m "feat: smart PPTX output naming + in-place revision endpoint"
```

---

## Chunk 4: Frontend — clarification flow + revision UI

### Task 5: Upgrade Next.js UI

**Files:**
- Modify: `frontend/src/app/page.tsx`

The UI has three phases:
1. **Input phase** — user types goal, clicks "Research"
2. **Clarification phase** — agent returns 0–3 questions; user answers inline; "Run" fires refined goal
3. **Results phase** — run history cards with PPTX download + "Revise" button that opens an inline notes input

- [ ] **Step 1: Replace `frontend/src/app/page.tsx` entirely**

```tsx
"use client";
import { useState, useEffect } from "react";
import {
  listRuns, startRun, clarifyGoal, refineGoal, reviseRun,
  getReportUrl, getDeckUrl, Run, ClarifyResult,
} from "@/lib/api";

type Phase = "input" | "clarifying" | "running" | "done";

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [goal, setGoal] = useState("");
  const [phase, setPhase] = useState<Phase>("input");
  const [clarification, setClarification] = useState<ClarifyResult | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [reviseTarget, setReviseTarget] = useState<string | null>(null);
  const [revisionNotes, setRevisionNotes] = useState("");

  useEffect(() => {
    listRuns().then(setRuns).catch(() =>
      setError("Backend offline — run: uvicorn api.server:app --host 127.0.0.1 --port 8000")
    );
  }, []);

  async function handleSubmitGoal() {
    if (!goal.trim()) return;
    setError(null);
    setPhase("clarifying");
    try {
      const result = await clarifyGoal(goal);
      if (result.questions.length === 0) {
        // No questions needed — go straight to run
        await executeRun(goal);
      } else {
        setClarification(result);
        setAnswers(Object.fromEntries(result.questions.map(q => [q, ""])));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Clarification failed");
      setPhase("input");
    }
  }

  async function handleSubmitAnswers() {
    setError(null);
    try {
      const refined = await refineGoal(goal, answers);
      await executeRun(refined);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to refine goal");
      setPhase("clarifying");
    }
  }

  async function executeRun(finalGoal: string) {
    setPhase("running");
    try {
      const result = await startRun(finalGoal);
      if (result.pptx_available || result.pptx_path) {
        window.open(getDeckUrl(result.run_id), "_blank");
      } else if (result.report_path) {
        window.open(getReportUrl(result.run_id), "_blank");
      }
      const updated = await listRuns();
      setRuns(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setPhase("done");
    }
  }

  async function handleRevise(runId: string) {
    if (!revisionNotes.trim()) return;
    setError(null);
    try {
      const result = await reviseRun(runId, revisionNotes);
      if (result.pptx_available || result.pptx_path) {
        window.open(getDeckUrl(result.run_id), "_blank");
      }
      const updated = await listRuns();
      setRuns(updated);
      setReviseTarget(null);
      setRevisionNotes("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Revision failed");
    }
  }

  function reset() {
    setGoal("");
    setPhase("input");
    setClarification(null);
    setAnswers({});
    setError(null);
  }

  return (
    <main className="min-h-screen bg-slate-900 text-slate-100 p-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold">Web Intelligence Agent</h1>
          <p className="text-slate-400 text-sm mt-1">
            Multi-source research → BCG PowerPoint. LinkedIn · Filings · Web.
          </p>
        </div>

        {/* Phase: Input */}
        {(phase === "input" || phase === "done") && (
          <div className="mb-8">
            <label className="block text-sm text-slate-400 mb-2">Research Goal</label>
            <div className="flex gap-3">
              <input
                value={goal}
                onChange={e => setGoal(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSubmitGoal()}
                placeholder='e.g. "Map Roche IT leadership and pull their 2024 financials"'
                className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm
                           focus:outline-none focus:border-blue-500 placeholder-slate-600"
              />
              <button
                onClick={handleSubmitGoal}
                disabled={!goal.trim()}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700
                           disabled:text-slate-500 rounded-lg text-sm font-medium"
              >
                Research
              </button>
            </div>
            {error && <p className="mt-2 text-red-400 text-sm">{error}</p>}
          </div>
        )}

        {/* Phase: Clarifying */}
        {phase === "clarifying" && clarification && (
          <div className="mb-8 bg-slate-800 border border-slate-700 rounded-xl p-6">
            <p className="text-sm text-slate-300 mb-4 font-medium">
              A few quick questions to sharpen your research:
            </p>
            <div className="space-y-4">
              {clarification.questions.map((q, i) => (
                <div key={i}>
                  <label className="block text-sm text-slate-300 mb-1">{q}</label>
                  <input
                    value={answers[q] ?? ""}
                    onChange={e => setAnswers(a => ({ ...a, [q]: e.target.value }))}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm
                               focus:outline-none focus:border-blue-500"
                    placeholder="Your answer…"
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={handleSubmitAnswers}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium"
              >
                Run Research
              </button>
              <button
                onClick={() => executeRun(goal)}
                className="px-4 py-2.5 text-slate-400 hover:text-slate-200 text-sm"
              >
                Skip, use original goal
              </button>
            </div>
          </div>
        )}

        {/* Phase: Clarifying — loading spinner */}
        {phase === "clarifying" && !clarification && (
          <div className="mb-8 text-slate-400 text-sm">Analyzing your goal…</div>
        )}

        {/* Phase: Running */}
        {phase === "running" && (
          <div className="mb-8 bg-slate-800 border border-slate-700 rounded-xl p-6">
            <p className="text-slate-300 text-sm">
              Running research across all sources… This can take 2–5 minutes.
            </p>
            <p className="text-slate-500 text-xs mt-2">
              Deck will open automatically when ready.
            </p>
          </div>
        )}

        {/* Run History */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xs text-slate-500 uppercase tracking-wider">Run History</h2>
          <button
            onClick={() => listRuns().then(setRuns).catch(() => {})}
            className="text-xs text-slate-500 hover:text-slate-300"
          >
            Refresh
          </button>
        </div>

        {runs.length === 0 ? (
          <p className="text-slate-600 text-sm">No runs yet. Enter a goal to get started.</p>
        ) : (
          <div className="space-y-2">
            {runs.map(run => (
              <div key={run.id} className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{run.goal}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {run.id} ·{" "}
                      <span className={
                        run.status === "complete" ? "text-green-400" :
                        run.status === "failed" ? "text-red-400" : "text-yellow-400"
                      }>{run.status}</span>
                    </p>
                  </div>
                  {run.status === "complete" && (
                    <div className="flex items-center gap-2 ml-4 shrink-0">
                      <a href={getReportUrl(run.id)} target="_blank" rel="noreferrer"
                         className="text-xs text-blue-400 hover:text-blue-300">
                        Report →
                      </a>
                      {run.pptx_available && (
                        <a href={getDeckUrl(run.id)} download
                           className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-500">
                          ↓ Deck
                        </a>
                      )}
                      <button
                        onClick={() => setReviseTarget(reviseTarget === run.id ? null : run.id)}
                        className="text-xs px-2 py-1 rounded border border-slate-600 text-slate-400 hover:text-slate-200"
                      >
                        Revise
                      </button>
                    </div>
                  )}
                </div>

                {/* Revision panel */}
                {reviseTarget === run.id && (
                  <div className="border-t border-slate-700 px-4 py-3 bg-slate-850">
                    <label className="block text-xs text-slate-400 mb-1">Revision instructions</label>
                    <div className="flex gap-2">
                      <input
                        value={revisionNotes}
                        onChange={e => setRevisionNotes(e.target.value)}
                        placeholder="e.g. Add a slide on competitive moats, use Q4 2024 data"
                        className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-xs
                                   focus:outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => handleRevise(run.id)}
                        disabled={!revisionNotes.trim()}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700
                                   disabled:text-slate-500 rounded text-xs"
                      >
                        Apply
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* New research button when done */}
        {phase === "done" && (
          <button onClick={reset}
            className="mt-6 text-sm text-slate-400 hover:text-slate-200 underline underline-offset-2">
            + New research
          </button>
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Run frontend dev server and verify UI loads**

```bash
cd /Users/srikumarkrishna/projects/web-intelligence-agent/frontend && npm run dev &
sleep 3
curl -s http://localhost:3000 | grep -c "Research Goal" || echo "check browser"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat: upgrade UI with clarification flow + revision panel"
```

---

## Chunk 5: Final wiring + smoke test

### Task 6: End-to-end smoke test

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/srikumarkrishna/projects/web-intelligence-agent && source .venv/bin/activate
pytest tests/ -v --ignore=tests/test_linkedin_crawler.py 2>&1 | tail -30
```
Expected: all pass except LinkedIn (needs real cookies).

- [ ] **Step 2: Start both servers and verify**

```bash
source .venv/bin/activate && uvicorn api.server:app --host 127.0.0.1 --port 8000 &
cd frontend && npm run dev &
sleep 3
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: smart orchestration + clarification UI — complete"
git push origin main
```
