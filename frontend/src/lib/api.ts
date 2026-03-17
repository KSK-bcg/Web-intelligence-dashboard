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
}

export interface RunResult {
  run_id: string;
  report_path: string;
  people_count: number;
  changes: Array<{
    change_type: string;
    person_name: string;
    from_value?: string;
    to_value?: string;
  }>;
}

async function apiError(res: Response, fallback: string): Promise<never> {
  try {
    const body = await res.json();
    throw new Error(body.detail ?? fallback);
  } catch {
    throw new Error(fallback);
  }
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
