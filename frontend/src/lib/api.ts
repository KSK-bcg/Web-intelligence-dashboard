// frontend/src/lib/api.ts
const API_BASE = "http://localhost:8000";
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

export interface RunResult {
  run_id: string;
  report_path: string;
  pptx_path?: string | null;
  pptx_available?: boolean;
  people_count: number;
  changes: Array<{
    change_type: string;
    person_name: string;
    from_value?: string;
    to_value?: string;
  }>;
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
  const res = await fetch(`${API_BASE}/runs`, { headers });
  if (!res.ok) await apiError(res, `Failed to fetch runs: ${res.status}`);
  return res.json();
}

export async function startRun(goal: string, runId?: string): Promise<RunResult> {
  const res = await fetch(`${API_BASE}/run`, {
    method: "POST",
    headers,
    body: JSON.stringify({ goal, run_id: runId }),
  });
  if (!res.ok) await apiError(res, `Run failed: ${res.status}`);
  return res.json();
}

export function getReportUrl(runId: string): string {
  return `${API_BASE}/report/${runId}?x-api-key=${API_KEY}`;
}

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
  });
  if (!res.ok) await apiError(res, `Refine failed: ${res.status}`);
  const data = await res.json();
  return data.refined_goal;
}

export async function reviseRun(
  runId: string,
  revisionNotes: string
): Promise<RunResult> {
  const res = await fetch(`${API_BASE}/revise`, {
    method: "POST",
    headers,
    body: JSON.stringify({ run_id: runId, revision_notes: revisionNotes }),
  });
  if (!res.ok) await apiError(res, `Revise failed: ${res.status}`);
  return res.json();
}
