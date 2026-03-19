# api/server.py
"""
FastAPI backend — binds to localhost only.
Endpoints: /health, /clarify, /refine, /run, /run/{id}/stream, /revise, /runs, /report/{run_id}

SECURITY: Bound to 127.0.0.1 only. API key auth on all endpoints (header only).
P1: /run is non-blocking — returns run_id immediately, pipeline runs in background.
P8: /run/{run_id}/stream streams SSE progress events to the frontend.
"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.orchestrator import Orchestrator
from agent.store import Store
from agent.exceptions import WebIntelligenceError

logger = logging.getLogger(__name__)

app = FastAPI(title="Web Intelligence Agent API", docs_url=None, redoc_url=None)

_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003,http://localhost:3004,http://localhost:3005",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── SSE event queues (run_id → asyncio.Queue) ─────────────────────────────────
# Each queue holds dicts: {"type": "progress"|"done"|"error", "message": "..."}
_run_queues: dict[str, asyncio.Queue] = {}
_cancel_events: dict[str, asyncio.Event] = {}
_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,16}$")


# ── Error handlers ────────────────────────────────────────────────────────────

@app.exception_handler(WebIntelligenceError)
async def intelligence_error_handler(request: Request, exc: WebIntelligenceError):
    logger.error("WebIntelligenceError: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_api_key(x_api_key: str = Header(...)):
    expected = os.environ.get("API_SECRET_KEY", "change-me-local-only")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def verify_api_key_header(x_api_key: Optional[str] = Header(None)):
    """Header-only API key verification (no query param to avoid log exposure)."""
    expected = os.environ.get("API_SECRET_KEY", "change-me-local-only")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _validate_run_id(run_id: str) -> str:
    """Validate run_id to prevent path traversal. Raises 400 on invalid."""
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")
    return run_id


# ── Request models ────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    goal: str
    run_id: Optional[str] = None


class ClarifyRequest(BaseModel):
    goal: str


class RefineRequest(BaseModel):
    goal: str
    answers: dict


class ReviseRequest(BaseModel):
    run_id: str
    revision_notes: str


# ── Background pipeline ───────────────────────────────────────────────────────

async def _run_pipeline(run_id: str, goal: str, run_id_hint: Optional[str] = None):
    """
    Runs the full intelligence pipeline in the background.
    Pushes SSE events to _run_queues[run_id] throughout.
    """
    queue = _run_queues.setdefault(run_id, asyncio.Queue())
    cancel_event = asyncio.Event()
    _cancel_events[run_id] = cancel_event
    store = Store()
    store.init_db()

    async def progress(event: dict):
        await queue.put(event)

    try:
        await progress({"type": "progress", "message": "🔍 Classifying goal and planning research..."})
        orch = Orchestrator()
        result = await orch.run(
            goal=goal,
            run_id_hint=run_id_hint,
            progress_callback=progress,
        )
        pptx_path = result.get("pptx_path")
        result["pptx_available"] = bool(pptx_path and Path(pptx_path).exists())

        await progress({
            "type": "done",
            "message": "✅ Research complete",
            "result": {
                "run_id": result.get("run_id", run_id),
                "pptx_available": result["pptx_available"],
                "pptx_path": pptx_path,
                "people_count": result.get("people_count", 0),
                "goal_evaluation": result.get("goal_evaluation"),
            },
        })
    except WebIntelligenceError as e:
        logger.error("Pipeline WebIntelligenceError for run %s: %s", run_id, e)
        store.fail_run(run_id)
        await progress({"type": "error", "message": str(e)})
    except Exception as e:
        logger.exception("Pipeline error for run %s", run_id)
        store.fail_run(run_id)
        await progress({"type": "error", "message": "Research pipeline failed — check server logs"})
    finally:
        # Keep queue alive for 5 minutes so late SSE subscribers can still read
        await asyncio.sleep(300)
        _run_queues.pop(run_id, None)
        _cancel_events.pop(run_id, None)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/clarify")
async def clarify_goal(req: ClarifyRequest, _: str = Depends(verify_api_key)):
    from agent.clarifier import Clarifier
    result = Clarifier().clarify(req.goal)
    return {
        "questions": result.get("questions", []),
        "refined_context": result.get("refined_context", {}),
    }


@app.post("/refine")
async def refine_goal(req: RefineRequest, _: str = Depends(verify_api_key)):
    from agent.clarifier import Clarifier
    refined = Clarifier().build_refined_goal(req.goal, req.answers)
    return {"refined_goal": refined}


@app.post("/run")
async def start_run(
    req: RunRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
):
    """
    Start a new intelligence run. Returns immediately with run_id.
    Pipeline executes in background — subscribe to /run/{run_id}/stream for progress.
    """
    store = Store()
    store.init_db()

    # Validate run_id_hint if provided
    if req.run_id:
        _validate_run_id(req.run_id)
        run = store.get_run(req.run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"run_id '{req.run_id}' not found")
        run_id = req.run_id
    else:
        run_id = store.create_run(goal=req.goal, target="pending")

    # Pre-create the queue so the SSE subscriber can connect before the task starts
    _run_queues[run_id] = asyncio.Queue()

    background_tasks.add_task(_run_pipeline, run_id, req.goal, req.run_id)

    return {"run_id": run_id, "status": "queued"}


@app.get("/run/{run_id}/stream")
async def stream_run(
    run_id: str,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = None,  # query param — browser EventSource can't set headers
):
    """
    SSE stream for a run's progress. Events:
      {"type": "progress", "message": "..."}
      {"type": "done",     "message": "...", "result": {...}}
      {"type": "error",    "message": "..."}
    Note: accepts api_key as query param for browser EventSource compatibility (localhost only).
    """
    _validate_run_id(run_id)
    expected = os.environ.get("API_SECRET_KEY", "change-me-local-only")
    if (x_api_key or api_key) != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # If the run already completed (no queue), check the store and return synthetic done/error
    queue = _run_queues.get(run_id)
    if queue is None:
        store = Store()
        store.init_db()
        run = store.get_run(run_id)

        async def completed_generator():
            if run and run.status == "complete":
                yield {
                    "data": json.dumps({
                        "type": "done",
                        "message": "✅ Research complete",
                        "result": {
                            "run_id": run_id,
                            "pptx_available": bool(run.pptx_path and Path(run.pptx_path).exists()),
                        },
                    })
                }
            else:
                yield {"data": json.dumps({"type": "error", "message": "Run not found or already completed"})}

        return EventSourceResponse(completed_generator())

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {"data": json.dumps(event)}
                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                # Send keepalive comment
                yield {"comment": "keepalive"}

    return EventSourceResponse(event_generator())


@app.post("/run/{run_id}/cancel")
async def cancel_run(run_id: str, _: str = Depends(verify_api_key)):
    """Cancel a running pipeline. Marks run as failed and pushes cancel event to SSE stream."""
    _validate_run_id(run_id)
    store = Store()
    store.init_db()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Signal cancellation to any waiting pipeline
    event = _cancel_events.get(run_id)
    if event:
        event.set()

    # Push cancel event to SSE queue so frontend knows immediately
    queue = _run_queues.get(run_id)
    if queue:
        await queue.put({"type": "error", "message": "⛔ Run cancelled by user"})

    store.fail_run(run_id)
    return {"run_id": run_id, "status": "cancelled"}


@app.post("/revise")
async def revise_run(
    req: ReviseRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(verify_api_key),
):
    """Re-run synthesis + PPTX with revision notes (non-blocking)."""
    _validate_run_id(req.run_id)
    store = Store()
    store.init_db()
    run = store.get_run(req.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "complete":
        raise HTTPException(status_code=400, detail="Run not complete — cannot revise")

    revised_goal = f"{run.goal}\n\nRevision instructions: {req.revision_notes}"
    _run_queues[req.run_id] = asyncio.Queue()
    background_tasks.add_task(_run_pipeline, req.run_id, revised_goal, req.run_id)

    return {"run_id": req.run_id, "status": "queued"}


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
def get_report(run_id: str, _: None = Depends(verify_api_key_header)):
    _validate_run_id(run_id)
    path = Path(f"output/{run_id}/report.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {run_id}")
    return FileResponse(path, media_type="text/html")


@app.get("/report/{run_id}/deck")
def get_deck(run_id: str, _: None = Depends(verify_api_key_header)):
    """Serve the PPTX deck. Header-only auth (no query param to avoid log exposure)."""
    _validate_run_id(run_id)
    store = Store()
    store.init_db()
    run = store.get_run(run_id)

    if run and run.pptx_path and Path(run.pptx_path).exists():
        path = Path(run.pptx_path)
        filename = path.name
    else:
        path = Path(f"output/{run_id}/board-deck.pptx")
        filename = f"board-deck-{run_id}.pptx"

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Deck not found for run: {run_id}")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )
