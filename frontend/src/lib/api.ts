// frontend/src/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "change-me-local-only";

const headers: Record<string, string> = {
  "x-api-key": API_KEY,
  "Content-Type": "application/json",
};

export interface Run {
  id: string;
  goal: string;
  target: string;
  status: string;
  created_at: string;
  pptx_available?: boolean;
}

export interface RunQueued {
  run_id: string;
  status: "queued";
}

export interface RunResult {
  run_id: string;
  report_path?: string | null;
  pptx_path?: string | null;
  pptx_available?: boolean;
  people_count?: number;
  goal_evaluation?: { score: number; verdict: string } | null;
}

export interface ProgressEvent {
  type: "progress" | "done" | "error";
  message: string;
  result?: RunResult;
}

async function apiError(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const body = await res.json();
    if (body.detail) detail = String(body.detail);
  } catch {
    // JSON parse failed — use fallback
  }
  throw new Error(detail);
}

export async function listRuns(): Promise<Run[]> {
  const res = await fetch(`${API_BASE}/runs`, {
    headers,
    signal: AbortSignal.timeout(10000),
  });
  if (!res.ok) await apiError(res, `Failed to fetch runs: ${res.status}`);
  return res.json();
}

/** POST /run — returns immediately with run_id. Pipeline runs in background. */
export async function startRun(goal: string, runId?: string): Promise<RunQueued> {
  const res = await fetch(`${API_BASE}/run`, {
    method: "POST",
    headers,
    body: JSON.stringify({ goal, run_id: runId }),
    signal: AbortSignal.timeout(60000),
  });
  if (!res.ok) await apiError(res, `Run failed: ${res.status}`);
  return res.json();
}

/** POST /revise — returns immediately with run_id. Revision runs in background. */
export async function startRevision(runId: string, revisionNotes: string): Promise<RunQueued> {
  const res = await fetch(`${API_BASE}/revise`, {
    method: "POST",
    headers,
    body: JSON.stringify({ run_id: runId, revision_notes: revisionNotes }),
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) await apiError(res, `Revise failed: ${res.status}`);
  return res.json();
}

/**
 * Subscribe to SSE progress stream for a run.
 * Calls onProgress for each event, onDone on completion, onError on failure.
 * Returns a cleanup function to close the stream.
 */
export function subscribeToRun(
  runId: string,
  callbacks: {
    onProgress: (message: string) => void;
    onDone: (result: RunResult) => void;
    onError: (message: string) => void;
  }
): () => void {
  const streamUrl = `${API_BASE}/run/${runId}/stream?api_key=${encodeURIComponent(API_KEY)}`;
  let es: EventSource;
  let closed = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECTS = 10;

  function connect() {
    es = new EventSource(streamUrl);

    es.onmessage = (event) => {
      reconnectAttempts = 0; // reset on successful message
      try {
        const data: ProgressEvent = JSON.parse(event.data);
        if (data.type === "progress") {
          callbacks.onProgress(data.message);
        } else if (data.type === "done") {
          closed = true;
          es.close();
          callbacks.onDone(data.result || { run_id: runId });
        } else if (data.type === "error") {
          closed = true;
          es.close();
          callbacks.onError(data.message);
        }
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      es.close();
      if (closed) return;
      if (reconnectAttempts >= MAX_RECONNECTS) {
        callbacks.onError("Lost connection to research stream after multiple retries — check server logs");
        return;
      }
      reconnectAttempts++;
      const delay = Math.min(2000 * reconnectAttempts, 15000);
      callbacks.onProgress(`⟳ Connection dropped — reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttempts}/${MAX_RECONNECTS})...`);
      reconnectTimer = setTimeout(connect, delay);
    };
  }

  connect();

  return () => {
    closed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    es.close();
  };
}

/** Download the PPTX deck via fetch (header auth) and trigger browser download. */
export async function downloadDeck(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/report/${runId}/deck`, { headers });
  if (!res.ok) await apiError(res, `Deck not available: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `research-deck-${runId}.pptx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function getReportUrl(runId: string): string {
  return `${API_BASE}/report/${runId}?x-api-key=${API_KEY}`;
}

// Keep for backward compat but prefer downloadDeck()
export function getDeckUrl(runId: string): string {
  return `${API_BASE}/report/${runId}/deck?x-api-key=${API_KEY}`;
}

export interface ClarifyResult {
  questions: string[];
  refined_context: Record<string, string | null>;
}

export async function clarifyGoal(goal: string): Promise<ClarifyResult> {
  const res = await fetch(`${API_BASE}/clarify`, {
    method: "POST",
    headers,
    body: JSON.stringify({ goal }),
    signal: AbortSignal.timeout(30000),
  });
  if (!res.ok) await apiError(res, `Clarify failed: ${res.status}`);
  return res.json();
}

export async function refineGoal(
  goal: string,
  answers: Record<string, string>
): Promise<string> {
  const res = await fetch(`${API_BASE}/refine`, {
    method: "POST",
    headers,
    body: JSON.stringify({ goal, answers }),
    signal: AbortSignal.timeout(30000),
  });
  if (!res.ok) await apiError(res, `Refine failed: ${res.status}`);
  const data = await res.json();
  return data.refined_goal;
}
