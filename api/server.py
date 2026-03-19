# api/server.py
"""
FastAPI backend — binds to localhost only.
Endpoints: /health, /clarify, /refine, /run, /revise, /runs, /report/{run_id}

SECURITY: Bound to 127.0.0.1 only. API key auth on all endpoints.
NOTE: /run blocks until complete (SSE streaming is a future enhancement).
"""
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.orchestrator import Orchestrator
from agent.store import Store
from agent.exceptions import WebIntelligenceError

logger = logging.getLogger(__name__)

app = FastAPI(title="Web Intelligence Agent API", docs_url=None, redoc_url=None)

_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(WebIntelligenceError)
async def intelligence_error_handler(request: Request, exc: WebIntelligenceError):
    logger.error("WebIntelligenceError: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def verify_api_key(x_api_key: str = Header(...)):
    expected = os.environ.get("API_SECRET_KEY", "change-me-local-only")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def verify_api_key_query(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, alias="x-api-key"),
):
    key = x_api_key or api_key
    expected = os.environ.get("API_SECRET_KEY", "change-me-local-only")
    if key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Request models ────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    goal: str
    run_id: Optional[str] = None


class ClarifyRequest(BaseModel):
    goal: str


class RefineRequest(BaseModel):
    goal: str
    answers: dict  # {question: answer}


class ReviseRequest(BaseModel):
    run_id: str
    revision_notes: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/clarify")
async def clarify_goal(req: ClarifyRequest, _: str = Depends(verify_api_key)):
    """Ask 1-3 sharpening questions for a goal using the 5W1H framework.
    Returns empty questions list if goal is already specific enough.
    """
    from agent.clarifier import Clarifier
    result = Clarifier().clarify(req.goal)
    return {
        "questions": result.get("questions", []),
        "refined_context": result.get("refined_context", {}),
    }


@app.post("/refine")
async def refine_goal(req: RefineRequest, _: str = Depends(verify_api_key)):
    """Convert an original goal + Q&A answers into a single refined goal string."""
    from agent.clarifier import Clarifier
    refined = Clarifier().build_refined_goal(req.goal, req.answers)
    return {"refined_goal": refined}


@app.post("/run")
async def start_run(req: RunRequest, _: str = Depends(verify_api_key)):
    """Start a new intelligence gathering run. Blocks until complete.
    Supports multi-source goals (LinkedIn + financials + blog in parallel).
    """
    orch = Orchestrator()
    result = await orch.run(goal=req.goal, run_id_hint=req.run_id)
    run_id = result.get("run_id", "")
    # pptx_path is the named stable path; check it directly
    pptx_path = result.get("pptx_path")
    result["pptx_available"] = bool(pptx_path and Path(pptx_path).exists())
    return result


@app.post("/revise")
async def revise_run(req: ReviseRequest, _: str = Depends(verify_api_key)):
    """Re-run synthesis + PPTX with revision notes, overwriting the existing deck in-place."""
    store = Store()
    store.init_db()
    run = store.get_run(req.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "complete":
        raise HTTPException(status_code=400, detail="Run not complete — cannot revise")

    # Append revision instructions to the original goal and re-run
    revised_goal = f"{run.goal}\n\nRevision instructions: {req.revision_notes}"
    orch = Orchestrator()
    result = await orch.run(goal=revised_goal, run_id_hint=req.run_id)
    pptx_path = result.get("pptx_path")
    result["pptx_available"] = bool(pptx_path and Path(pptx_path).exists())
    return result


@app.get("/runs")
def list_runs(_: str = Depends(verify_api_key)):
    store = Store()
    store.init_db()
    runs = store.list_runs()
    return [
        {
            "id": r.id,
            "goal": r.goal,
            "target": r.target,
            "status": r.status,
            "created_at": str(r.created_at),
            "pptx_available": bool(r.pptx_path and Path(r.pptx_path).exists()),
            "pptx_path": r.pptx_path,
        }
        for r in runs
    ]


@app.get("/report/{run_id}")
def get_report(run_id: str, _: None = Depends(verify_api_key_query)):
    path = Path(f"output/{run_id}/report.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {run_id}")
    return FileResponse(path, media_type="text/html")


@app.get("/report/{run_id}/deck")
def get_deck(run_id: str, _: None = Depends(verify_api_key_query)):
    """Serve the PPTX deck. Uses the stable named path stored on the run record."""
    store = Store()
    store.init_db()
    run = store.get_run(run_id)

    # Prefer named path from store; fall back to legacy run-id path
    if run and run.pptx_path and Path(run.pptx_path).exists():
        path = Path(run.pptx_path)
        filename = path.name
    else:
        # Legacy fallback for runs created before named output
        path = Path(f"output/{run_id}/board-deck.pptx")
        filename = f"board-deck-{run_id}.pptx"

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Deck not found for run: {run_id}")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )
