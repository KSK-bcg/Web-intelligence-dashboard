# api/server.py
"""
FastAPI backend — binds to localhost only.
Provides: /health, /run, /runs, /report/{run_id} endpoints.

SECURITY: Bound to 127.0.0.1 only. API key auth on all endpoints.
NOTE: SSE progress streaming is a v2 feature. sse_starlette is in requirements
but not wired here — the /run endpoint blocks until complete.
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


class RunRequest(BaseModel):
    goal: str
    run_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
async def start_run(req: RunRequest, _: str = Depends(verify_api_key)):
    """Start a new intelligence gathering run. Returns result when complete.
    NOTE: Long-running (LinkedIn runs can take 2-5 min). SSE streaming is v2.
    """
    orch = Orchestrator()
    result = await orch.run(goal=req.goal, run_id_hint=req.run_id)
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
        }
        for r in runs
    ]


def verify_api_key_query(
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, alias="x-api-key"),
):
    key = x_api_key or api_key
    expected = os.environ.get("API_SECRET_KEY", "change-me-local-only")
    if key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/report/{run_id}")
def get_report(run_id: str, _: None = Depends(verify_api_key_query)):
    path = Path(f"output/{run_id}/report.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {run_id}")
    return FileResponse(path, media_type="text/html")
