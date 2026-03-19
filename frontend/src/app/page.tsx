// frontend/src/app/page.tsx
"use client";
import { useState, useEffect } from "react";
import {
  listRuns,
  startRun,
  clarifyGoal,
  refineGoal,
  reviseRun,
  getReportUrl,
  getDeckUrl,
  Run,
  ClarifyResult,
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
    listRuns()
      .then(setRuns)
      .catch(() =>
        setError(
          "Backend offline — run: uvicorn api.server:app --host 127.0.0.1 --port 8000"
        )
      );
  }, []);

  async function handleSubmitGoal() {
    if (!goal.trim()) return;
    setError(null);
    setPhase("clarifying");
    setClarification(null);
    try {
      const result = await clarifyGoal(goal);
      if (result.questions.length === 0) {
        // Specific enough — go straight to run
        await executeRun(goal);
      } else {
        setClarification(result);
        setAnswers(Object.fromEntries(result.questions.map((q) => [q, ""])));
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
          <h1 className="text-2xl font-semibold tracking-tight">
            Web Intelligence Agent
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Multi-source research → BCG PowerPoint. LinkedIn · Filings · Web.
          </p>
        </div>

        {/* ── Input phase ── */}
        {(phase === "input" || phase === "done") && (
          <div className="mb-8">
            <label className="block text-sm text-slate-400 mb-2">
              Research Goal
            </label>
            <div className="flex gap-3">
              <input
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmitGoal()}
                placeholder='e.g. "Map Roche IT leadership and pull their 2024 financials"'
                className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-sm
                           focus:outline-none focus:border-blue-500 placeholder-slate-600"
              />
              <button
                onClick={handleSubmitGoal}
                disabled={!goal.trim()}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700
                           disabled:text-slate-500 rounded-lg text-sm font-medium transition-colors"
              >
                Research
              </button>
            </div>
            {error && <p className="mt-2 text-red-400 text-sm">{error}</p>}
          </div>
        )}

        {/* ── Clarifying — loading ── */}
        {phase === "clarifying" && !clarification && (
          <div className="mb-8 text-slate-400 text-sm animate-pulse">
            Analyzing your goal…
          </div>
        )}

        {/* ── Clarifying — questions ── */}
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
                    onChange={(e) =>
                      setAnswers((a) => ({ ...a, [q]: e.target.value }))
                    }
                    onKeyDown={(e) =>
                      e.key === "Enter" &&
                      i === clarification.questions.length - 1 &&
                      handleSubmitAnswers()
                    }
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
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
              >
                Run Research
              </button>
              <button
                onClick={() => executeRun(goal)}
                className="px-4 py-2.5 text-slate-400 hover:text-slate-200 text-sm transition-colors"
              >
                Skip, use original goal
              </button>
            </div>
            {error && <p className="mt-3 text-red-400 text-sm">{error}</p>}
          </div>
        )}

        {/* ── Running ── */}
        {phase === "running" && (
          <div className="mb-8 bg-slate-800 border border-slate-700 rounded-xl p-6">
            <div className="flex items-center gap-3">
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <p className="text-slate-300 text-sm">
                Researching across all sources in parallel…
              </p>
            </div>
            <p className="text-slate-500 text-xs mt-2 ml-5">
              LinkedIn crawls can take 2–5 minutes. Deck will open automatically.
            </p>
          </div>
        )}

        {/* ── Run History ── */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xs text-slate-500 uppercase tracking-wider">
            Run History
          </h2>
          <button
            onClick={() => listRuns().then(setRuns).catch(() => {})}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
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
                className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden"
              >
                {/* Run row */}
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{run.goal}</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {run.id} ·{" "}
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
                        className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                      >
                        Report →
                      </a>
                      {run.pptx_available && (
                        <a
                          href={getDeckUrl(run.id)}
                          download
                          className="text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-500 transition-colors"
                        >
                          ↓ Deck
                        </a>
                      )}
                      <button
                        onClick={() =>
                          setReviseTarget(
                            reviseTarget === run.id ? null : run.id
                          )
                        }
                        className="text-xs px-2 py-1 rounded border border-slate-600 text-slate-400
                                   hover:text-slate-200 hover:border-slate-500 transition-colors"
                      >
                        {reviseTarget === run.id ? "Cancel" : "Revise"}
                      </button>
                    </div>
                  )}
                </div>

                {/* Revision panel */}
                {reviseTarget === run.id && (
                  <div className="border-t border-slate-700 px-4 py-3 bg-slate-800/50">
                    <label className="block text-xs text-slate-400 mb-1">
                      Revision instructions — deck updates in-place, no duplicate file created
                    </label>
                    <div className="flex gap-2">
                      <input
                        value={revisionNotes}
                        onChange={(e) => setRevisionNotes(e.target.value)}
                        onKeyDown={(e) =>
                          e.key === "Enter" && handleRevise(run.id)
                        }
                        placeholder='e.g. "Add a slide on competitive moats, use Q4 2024 data"'
                        className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-xs
                                   focus:outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => handleRevise(run.id)}
                        disabled={!revisionNotes.trim()}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700
                                   disabled:text-slate-500 rounded text-xs transition-colors"
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

        {/* New research CTA */}
        {phase === "done" && (
          <button
            onClick={reset}
            className="mt-6 text-sm text-slate-400 hover:text-slate-200 underline underline-offset-2 transition-colors"
          >
            + New research
          </button>
        )}
      </div>
    </main>
  );
}
