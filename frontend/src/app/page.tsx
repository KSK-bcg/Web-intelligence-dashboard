// frontend/src/app/page.tsx
"use client";
import { useState, useEffect } from "react";
import { listRuns, startRun, getReportUrl, getDeckUrl, Run } from "@/lib/api";

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch(() => setError("API offline — start backend: uvicorn api.server:app --host 127.0.0.1 --port 8000"));
  }, []);

  async function handleRun() {
    if (!goal.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await startRun(goal);
      window.open(getReportUrl(result.run_id), "_blank");
      if (result.pptx_available || result.pptx_path) {
        window.open(getDeckUrl(result.run_id), "_blank");
      }
      const updated = await listRuns();
      setRuns(updated);
      setGoal("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-900 text-slate-100 p-8">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-semibold mb-1">Web Intelligence Agent</h1>
        <p className="text-slate-400 text-sm mb-8">
          Crawl LinkedIn and blogs. Build org charts, summaries, and visualizations.
        </p>

        <div className="mb-8">
          <label className="block text-sm text-slate-400 mb-2">Research Goal</label>
          <div className="flex gap-3">
            <input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRun()}
              placeholder='e.g. "Map IT division of Novartis on LinkedIn, VP level and above"'
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm
                         focus:outline-none focus:border-blue-500 placeholder-slate-600"
            />
            <button
              onClick={handleRun}
              disabled={loading || !goal.trim()}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700
                         disabled:text-slate-500 rounded-lg text-sm font-medium"
            >
              {loading ? "Running…" : "Run"}
            </button>
          </div>
          {error && <p className="mt-2 text-red-400 text-sm">{error}</p>}
          {loading && (
            <p className="mt-2 text-slate-400 text-sm">
              ⏳ Running… LinkedIn crawls can take 2–5 minutes. Report will open automatically.
            </p>
          )}
        </div>

        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm text-slate-400 uppercase tracking-wider">Run History</h2>
          <button
            onClick={() => listRuns().then(setRuns).catch(() => {})}
            className="text-xs text-slate-500 hover:text-slate-300"
          >
            Refresh
          </button>
        </div>

        {runs.length === 0 ? (
          <p className="text-slate-600 text-sm">
            No runs yet. Enter a goal above to get started.
          </p>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between bg-slate-800 rounded-lg px-4 py-3 border border-slate-700"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{run.goal}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {run.id} · {run.target} ·{" "}
                    <span
                      className={
                        run.status === "complete"
                          ? "text-green-400"
                          : run.status === "failed"
                          ? "text-red-400"
                          : "text-yellow-400"
                      }
                    >
                      {run.status}
                    </span>
                  </p>
                </div>
                {run.status === "complete" && (
                  <div className="flex items-center gap-2 ml-4 shrink-0">
                    <a
                      href={getReportUrl(run.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      Open Report →
                    </a>
                    {run.pptx_available && (
                      <a
                        href={getDeckUrl(run.id)}
                        className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-500"
                        download
                      >
                        ↓ Deck
                      </a>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="mt-12 pt-8 border-t border-slate-800">
          <h2 className="text-sm text-slate-400 uppercase tracking-wider mb-3">Quick Start</h2>
          <div className="bg-slate-800 rounded-lg p-4 font-mono text-xs text-slate-300 space-y-1">
            <p><span className="text-slate-500"># Setup (once)</span></p>
            <p>python run.py --setup-linkedin</p>
            <p className="mt-2"><span className="text-slate-500"># LinkedIn org chart</span></p>
            <p>python run.py --goal &quot;Map IT division of Roche on LinkedIn&quot;</p>
            <p className="mt-2"><span className="text-slate-500"># Blog summarization</span></p>
            <p>python run.py --goal &quot;Summarize https://martinfowler.com/articles&quot;</p>
          </div>
        </div>
      </div>
    </main>
  );
}
