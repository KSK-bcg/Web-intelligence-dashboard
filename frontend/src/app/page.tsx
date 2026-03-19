// frontend/src/app/page.tsx
"use client";
import { useState, useEffect, useRef } from "react";
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

const SOURCE_INDICATORS = [
  { id: "linkedin", label: "LinkedIn", color: "#4A9EE8", glowColor: "rgba(74,158,232,0.4)" },
  { id: "filings", label: "SEC Filings", color: "#E8A045", glowColor: "rgba(232,160,69,0.4)" },
  { id: "web", label: "Open Web", color: "#00C896", glowColor: "rgba(0,200,150,0.4)" },
];

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, { color: string; bg: string; border: string; label: string }> = {
    complete: {
      color: "#00C896",
      bg: "rgba(0,200,150,0.08)",
      border: "rgba(0,200,150,0.25)",
      label: "COMPLETE",
    },
    running: {
      color: "#E8A045",
      bg: "rgba(232,160,69,0.08)",
      border: "rgba(232,160,69,0.25)",
      label: "RUNNING",
    },
    failed: {
      color: "#E85454",
      bg: "rgba(232,84,84,0.08)",
      border: "rgba(232,84,84,0.25)",
      label: "FAILED",
    },
  };
  const s = styles[status] ?? {
    color: "#7A90A8",
    bg: "rgba(122,144,168,0.08)",
    border: "rgba(122,144,168,0.2)",
    label: status.toUpperCase(),
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        color: s.color,
        background: s.bg,
        border: `1px solid ${s.border}`,
        fontSize: "9px",
        fontFamily: "var(--font-geist-mono)",
        padding: "2px 7px",
        borderRadius: "4px",
        letterSpacing: "0.1em",
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      <span
        style={{
          width: "4px",
          height: "4px",
          borderRadius: "50%",
          background: s.color,
          display: "inline-block",
          animation: status === "running" ? "pulse-dot 1s ease-in-out infinite" : "none",
        }}
      />
      {s.label}
    </span>
  );
}

function SkeletonRow() {
  return (
    <div
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: "12px",
        padding: "16px 20px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
        <div className="skeleton-shimmer" style={{ height: "18px", width: "70px", borderRadius: "4px" }} />
        <div className="skeleton-shimmer" style={{ height: "12px", width: "60px", borderRadius: "4px" }} />
      </div>
      <div className="skeleton-shimmer" style={{ height: "14px", width: "75%", borderRadius: "4px" }} />
    </div>
  );
}

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [goal, setGoal] = useState("");
  const [phase, setPhase] = useState<Phase>("input");
  const [clarification, setClarification] = useState<ClarifyResult | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [reviseTarget, setReviseTarget] = useState<string | null>(null);
  const [revisionNotes, setRevisionNotes] = useState("");
  const [isLoadingRuns, setIsLoadingRuns] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setIsLoadingRuns(true);
    listRuns()
      .then(setRuns)
      .catch(() =>
        setError("Backend offline — run: uvicorn api.server:app --host 127.0.0.1 --port 8000")
      )
      .finally(() => setIsLoadingRuns(false));
  }, []);

  async function handleSubmitGoal() {
    if (!goal.trim()) return;
    setError(null);
    setPhase("clarifying");
    setClarification(null);
    try {
      const result = await clarifyGoal(goal);
      if (result.questions.length === 0) {
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

  function refreshRuns() {
    setIsLoadingRuns(true);
    listRuns()
      .then(setRuns)
      .catch(() => {})
      .finally(() => setIsLoadingRuns(false));
  }

  function reset() {
    setGoal("");
    setPhase("input");
    setClarification(null);
    setAnswers({});
    setError(null);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  const isInputActive = phase === "input" || phase === "done";
  const isProcessing = phase === "clarifying" || phase === "running";
  const canSubmit = goal.trim().length > 0 && isInputActive;

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "var(--bg-base)",
        position: "relative",
        overflowX: "hidden",
      }}
    >
      {/* Atmospheric background layers */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          background:
            "radial-gradient(ellipse 90% 55% at 50% -5%, rgba(232,160,69,0.055) 0%, transparent 65%)",
          zIndex: 0,
        }}
      />
      <div
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.025) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
          zIndex: 0,
        }}
      />

      <div
        style={{
          maxWidth: "700px",
          margin: "0 auto",
          padding: "clamp(40px, 8vw, 72px) 20px 80px",
          position: "relative",
          zIndex: 1,
        }}
      >
        {/* ── Header ── */}
        <header style={{ marginBottom: "52px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              marginBottom: "14px",
            }}
          >
            <div
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: "#E8A045",
                boxShadow: "0 0 10px #E8A045, 0 0 20px rgba(232,160,69,0.3)",
                animation: "pulse-dot 3s ease-in-out infinite",
              }}
            />
            <span
              style={{
                fontFamily: "var(--font-geist-mono)",
                fontSize: "10px",
                color: "#E8A045",
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                opacity: 0.8,
              }}
            >
              Intelligence Platform
            </span>
          </div>
          <h1
            style={{
              fontFamily: "var(--font-display), 'DM Serif Display', Georgia, serif",
              fontSize: "clamp(28px, 5.5vw, 42px)",
              fontWeight: 400,
              letterSpacing: "-0.025em",
              color: "var(--text-primary)",
              margin: "0 0 10px",
              lineHeight: 1.12,
            }}
          >
            What do you want
            <br />
            to research?
          </h1>
          <p
            style={{
              color: "var(--text-dim)",
              fontSize: "12px",
              fontFamily: "var(--font-geist-mono)",
              letterSpacing: "0.04em",
              margin: 0,
            }}
          >
            LinkedIn · SEC Filings · Open Web{" "}
            <span style={{ color: "var(--border-bright)", margin: "0 4px" }}>→</span>
            BCG PowerPoint
          </p>
        </header>

        {/* ── Goal Input ── */}
        <div style={{ marginBottom: "36px" }}>
          <label
            style={{
              display: "block",
              fontSize: "10px",
              color: "var(--text-dim)",
              fontFamily: "var(--font-geist-mono)",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              marginBottom: "10px",
            }}
          >
            Research Goal
          </label>
          <div style={{ display: "flex", gap: "10px", alignItems: "stretch" }}>
            <input
              ref={inputRef}
              value={goal}
              onChange={(e) => (isInputActive ? setGoal(e.target.value) : undefined)}
              onKeyDown={(e) => isInputActive && e.key === "Enter" && handleSubmitGoal()}
              readOnly={isProcessing}
              placeholder='e.g. "Map Roche IT leadership and pull their 2024 financials"'
              style={{
                flex: 1,
                padding: "14px 18px",
                background: isProcessing
                  ? "rgba(13,19,32,0.6)"
                  : "var(--bg-surface)",
                border: `1px solid ${isProcessing ? "var(--border)" : "#1E2D45"}`,
                borderRadius: "10px",
                color: isProcessing ? "var(--text-dim)" : "var(--text-primary)",
                fontSize: "14px",
                fontFamily: "var(--font-geist-sans)",
                outline: "none",
                cursor: isProcessing ? "default" : "text",
                transition: "border-color 0.2s, box-shadow 0.2s",
              }}
              onFocus={(e) => {
                if (!isProcessing) {
                  e.currentTarget.style.borderColor = "rgba(232,160,69,0.5)";
                  e.currentTarget.style.boxShadow =
                    "0 0 0 3px rgba(232,160,69,0.08), inset 0 1px 3px rgba(0,0,0,0.3)";
                }
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = isProcessing
                  ? "var(--border)"
                  : "#1E2D45";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
            <button
              onClick={handleSubmitGoal}
              disabled={!canSubmit}
              style={{
                padding: "14px 22px",
                background: canSubmit ? "#E8A045" : "var(--bg-surface)",
                border: `1px solid ${canSubmit ? "#E8A045" : "var(--border)"}`,
                borderRadius: "10px",
                color: canSubmit ? "#070B12" : "var(--text-dim)",
                fontSize: "12px",
                fontWeight: 700,
                fontFamily: "var(--font-geist-mono)",
                letterSpacing: "0.06em",
                cursor: canSubmit ? "pointer" : "not-allowed",
                whiteSpace: "nowrap",
                transition: "background 0.2s, color 0.2s, border-color 0.2s, transform 0.15s, box-shadow 0.15s",
                boxShadow: canSubmit
                  ? "0 2px 12px rgba(232,160,69,0.2)"
                  : "none",
              }}
              onMouseEnter={(e) => {
                if (canSubmit) {
                  e.currentTarget.style.transform = "translateY(-1px)";
                  e.currentTarget.style.boxShadow = "0 4px 18px rgba(232,160,69,0.35)";
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.boxShadow = canSubmit
                  ? "0 2px 12px rgba(232,160,69,0.2)"
                  : "none";
              }}
              onMouseDown={(e) => {
                if (canSubmit) e.currentTarget.style.transform = "translateY(0)";
              }}
            >
              {isProcessing ? "···" : "Research →"}
            </button>
          </div>
          {error && (
            <p
              style={{
                marginTop: "10px",
                color: "#E85454",
                fontSize: "12px",
                fontFamily: "var(--font-geist-mono)",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <span>⚠</span> {error}
            </p>
          )}
        </div>

        {/* ── Clarifying — spinner ── */}
        {phase === "clarifying" && !clarification && (
          <div
            className="animate-fade-slide"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "12px",
              padding: "20px 24px",
              marginBottom: "24px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <div style={{ display: "flex", gap: "4px" }}>
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    style={{
                      width: "5px",
                      height: "5px",
                      borderRadius: "50%",
                      background: "#E8A045",
                      animation: `pulse-dot 1.1s ease-in-out ${i * 0.18}s infinite`,
                    }}
                  />
                ))}
              </div>
              <span
                style={{
                  fontSize: "12px",
                  color: "var(--text-secondary)",
                  fontFamily: "var(--font-geist-mono)",
                }}
              >
                Analyzing goal…
              </span>
            </div>
            <p
              style={{
                marginTop: "10px",
                marginLeft: "29px",
                fontSize: "11px",
                color: "var(--text-dim)",
                fontFamily: "var(--font-geist-mono)",
                fontStyle: "italic",
              }}
            >
              &ldquo;{goal}&rdquo;
            </p>
          </div>
        )}

        {/* ── Clarifying — questions ── */}
        {phase === "clarifying" && clarification && (
          <div
            className="animate-fade-slide"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid rgba(232,160,69,0.2)",
              borderRadius: "12px",
              padding: "24px",
              marginBottom: "24px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                marginBottom: "20px",
              }}
            >
              <span
                style={{
                  fontSize: "10px",
                  color: "#E8A045",
                  fontFamily: "var(--font-geist-mono)",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                }}
              >
                ◈ Clarifying questions
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {clarification.questions.map((q, i) => (
                <div key={i}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "13px",
                      color: "#B8C8D8",
                      marginBottom: "7px",
                      lineHeight: 1.4,
                    }}
                  >
                    {q}
                  </label>
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
                    placeholder="Your answer…"
                    style={{
                      width: "100%",
                      padding: "10px 14px",
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border)",
                      borderRadius: "8px",
                      color: "var(--text-primary)",
                      fontSize: "13px",
                      fontFamily: "var(--font-geist-sans)",
                      outline: "none",
                      boxSizing: "border-box",
                      transition: "border-color 0.2s",
                    }}
                    onFocus={(e) => {
                      e.currentTarget.style.borderColor = "rgba(232,160,69,0.4)";
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.borderColor = "var(--border)";
                    }}
                  />
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: "10px", marginTop: "20px" }}>
              <button
                onClick={handleSubmitAnswers}
                style={{
                  padding: "10px 20px",
                  background: "#E8A045",
                  border: "none",
                  borderRadius: "8px",
                  color: "#070B12",
                  fontSize: "12px",
                  fontWeight: 700,
                  fontFamily: "var(--font-geist-mono)",
                  letterSpacing: "0.05em",
                  cursor: "pointer",
                  transition: "opacity 0.15s, transform 0.15s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = "0.9";
                  e.currentTarget.style.transform = "translateY(-1px)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = "1";
                  e.currentTarget.style.transform = "translateY(0)";
                }}
              >
                Run Research →
              </button>
              <button
                onClick={() => executeRun(goal)}
                style={{
                  padding: "10px 16px",
                  background: "transparent",
                  border: "none",
                  color: "var(--text-dim)",
                  fontSize: "12px",
                  fontFamily: "var(--font-geist-mono)",
                  cursor: "pointer",
                  transition: "color 0.15s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "var(--text-secondary)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "var(--text-dim)";
                }}
              >
                Skip →
              </button>
            </div>
            {error && (
              <p
                style={{
                  marginTop: "12px",
                  color: "#E85454",
                  fontSize: "12px",
                  fontFamily: "var(--font-geist-mono)",
                }}
              >
                ⚠ {error}
              </p>
            )}
          </div>
        )}

        {/* ── Running — source stream indicators ── */}
        {phase === "running" && (
          <div
            className="animate-fade-slide"
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "12px",
              padding: "24px",
              marginBottom: "24px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                marginBottom: "20px",
              }}
            >
              <div
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: "#E8A045",
                  boxShadow: "0 0 8px #E8A045",
                  animation: "pulse-dot 0.9s ease-in-out infinite",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontSize: "13px",
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-geist-mono)",
                }}
              >
                Crawling all sources in parallel…
              </span>
            </div>

            {/* Source stream badges */}
            <div
              style={{
                display: "flex",
                gap: "10px",
                flexWrap: "wrap",
                marginBottom: "18px",
              }}
            >
              {SOURCE_INDICATORS.map((src, i) => (
                <div
                  key={src.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    padding: "9px 14px",
                    background: `rgba(${src.color === "#4A9EE8" ? "74,158,232" : src.color === "#E8A045" ? "232,160,69" : "0,200,150"}, 0.07)`,
                    border: `1px solid ${src.color}35`,
                    borderRadius: "8px",
                    animation: `fadeSlideIn 0.4s ease ${i * 0.12}s both`,
                  }}
                >
                  <div
                    style={{
                      width: "6px",
                      height: "6px",
                      borderRadius: "50%",
                      background: src.color,
                      boxShadow: `0 0 8px ${src.glowColor}`,
                      animation: `pulse-dot 1.4s ease-in-out ${i * 0.35}s infinite`,
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      fontSize: "11px",
                      color: src.color,
                      fontFamily: "var(--font-geist-mono)",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {src.label}
                  </span>
                  <span
                    style={{
                      fontSize: "9px",
                      color: `${src.color}70`,
                      fontFamily: "var(--font-geist-mono)",
                      letterSpacing: "0.08em",
                    }}
                  >
                    ACTIVE
                  </span>
                </div>
              ))}
            </div>

            <div
              style={{
                padding: "10px 14px",
                background: "var(--bg-elevated)",
                borderRadius: "6px",
                borderLeft: "2px solid var(--border-bright)",
              }}
            >
              <p
                style={{
                  fontSize: "11px",
                  color: "var(--text-dim)",
                  fontFamily: "var(--font-geist-mono)",
                  margin: 0,
                  lineHeight: 1.6,
                }}
              >
                LinkedIn crawls may take 2–5 min.
                <br />
                The deck will open automatically when ready.
              </p>
            </div>
          </div>
        )}

        {/* ── Run History ── */}
        <div style={{ marginTop: "44px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "14px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div
                style={{
                  width: "1px",
                  height: "12px",
                  background: "var(--border-bright)",
                }}
              />
              <span
                style={{
                  fontSize: "10px",
                  color: "var(--text-secondary)",
                  fontFamily: "var(--font-geist-mono)",
                  letterSpacing: "0.14em",
                  textTransform: "uppercase",
                }}
              >
                Intelligence Runs
              </span>
              {!isLoadingRuns && runs.length > 0 && (
                <span
                  style={{
                    fontSize: "9px",
                    color: "var(--text-dim)",
                    fontFamily: "var(--font-geist-mono)",
                    background: "var(--bg-elevated)",
                    border: "1px solid var(--border)",
                    borderRadius: "10px",
                    padding: "1px 7px",
                  }}
                >
                  {runs.length}
                </span>
              )}
            </div>
            <button
              onClick={refreshRuns}
              style={{
                fontSize: "11px",
                color: "var(--text-dim)",
                background: "none",
                border: "none",
                fontFamily: "var(--font-geist-mono)",
                cursor: "pointer",
                transition: "color 0.15s",
                padding: "4px 0",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = "var(--text-primary)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = "var(--text-dim)";
              }}
            >
              ↺ Refresh
            </button>
          </div>

          {/* Skeleton */}
          {isLoadingRuns && (
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </div>
          )}

          {/* Empty state */}
          {!isLoadingRuns && runs.length === 0 && (
            <div
              className="animate-fade-slide"
              style={{
                padding: "48px 24px",
                textAlign: "center",
                border: "1px dashed var(--border)",
                borderRadius: "12px",
                background: "rgba(13,19,32,0.4)",
              }}
            >
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  margin: "0 auto 14px",
                  borderRadius: "50%",
                  border: "1px solid var(--border)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--text-dim)",
                  fontSize: "16px",
                }}
              >
                ◎
              </div>
              <p
                style={{
                  fontSize: "13px",
                  color: "var(--text-dim)",
                  fontFamily: "var(--font-geist-mono)",
                  margin: "0 0 4px",
                }}
              >
                No intelligence runs yet.
              </p>
              <p
                style={{
                  fontSize: "11px",
                  color: "var(--border-bright)",
                  fontFamily: "var(--font-geist-mono)",
                  margin: 0,
                }}
              >
                Enter a research goal above to begin your first run.
              </p>
            </div>
          )}

          {/* Run list */}
          {!isLoadingRuns && runs.length > 0 && (
            <div
              className="animate-fade-slide"
              style={{ display: "flex", flexDirection: "column", gap: "8px" }}
            >
              {runs.map((run) => (
                <div
                  key={run.id}
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "12px",
                    overflow: "hidden",
                    transition: "border-color 0.2s",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "var(--border-bright)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--border)";
                  }}
                >
                  {/* Run card row */}
                  <div
                    style={{
                      padding: "15px 20px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "14px",
                    }}
                  >
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                          marginBottom: "5px",
                          flexWrap: "wrap",
                        }}
                      >
                        <StatusBadge status={run.status} />
                        <span
                          style={{
                            fontSize: "10px",
                            color: "var(--text-dim)",
                            fontFamily: "var(--font-geist-mono)",
                            letterSpacing: "0.05em",
                          }}
                        >
                          {run.id}
                        </span>
                      </div>
                      <p
                        style={{
                          fontSize: "13px",
                          color: "#C0D2E4",
                          margin: 0,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          lineHeight: 1.4,
                        }}
                        title={run.goal}
                      >
                        {run.goal}
                      </p>
                    </div>

                    {run.status === "complete" && (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          flexShrink: 0,
                        }}
                      >
                        <a
                          href={getReportUrl(run.id)}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            fontSize: "11px",
                            color: "#00C896",
                            textDecoration: "none",
                            fontFamily: "var(--font-geist-mono)",
                            letterSpacing: "0.03em",
                            transition: "opacity 0.15s",
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.opacity = "0.7";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.opacity = "1";
                          }}
                        >
                          Report →
                        </a>
                        {run.pptx_available && (
                          <a
                            href={getDeckUrl(run.id)}
                            download
                            style={{
                              fontSize: "11px",
                              padding: "4px 10px",
                              background: "rgba(232,160,69,0.1)",
                              border: "1px solid rgba(232,160,69,0.25)",
                              borderRadius: "6px",
                              color: "#E8A045",
                              textDecoration: "none",
                              fontFamily: "var(--font-geist-mono)",
                              transition: "background 0.15s",
                              whiteSpace: "nowrap",
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background =
                                "rgba(232,160,69,0.2)";
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background =
                                "rgba(232,160,69,0.1)";
                            }}
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
                          style={{
                            fontSize: "11px",
                            padding: "4px 10px",
                            background: "transparent",
                            border: "1px solid var(--border)",
                            borderRadius: "6px",
                            color:
                              reviseTarget === run.id
                                ? "var(--text-primary)"
                                : "var(--text-dim)",
                            fontFamily: "var(--font-geist-mono)",
                            cursor: "pointer",
                            transition: "color 0.15s, border-color 0.15s",
                            whiteSpace: "nowrap",
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.borderColor =
                              "var(--border-bright)";
                            e.currentTarget.style.color = "var(--text-primary)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.borderColor = "var(--border)";
                            if (reviseTarget !== run.id) {
                              e.currentTarget.style.color = "var(--text-dim)";
                            }
                          }}
                        >
                          {reviseTarget === run.id ? "✕ Cancel" : "Revise"}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Revision panel */}
                  {reviseTarget === run.id && (
                    <div
                      className="animate-fade-slide"
                      style={{
                        borderTop: "1px solid var(--border)",
                        padding: "16px 20px",
                        background: "#0A1018",
                      }}
                    >
                      <label
                        style={{
                          display: "block",
                          fontSize: "10px",
                          color: "var(--text-dim)",
                          fontFamily: "var(--font-geist-mono)",
                          letterSpacing: "0.1em",
                          textTransform: "uppercase",
                          marginBottom: "10px",
                        }}
                      >
                        Revision Instructions
                      </label>
                      <div style={{ display: "flex", gap: "8px" }}>
                        <input
                          value={revisionNotes}
                          onChange={(e) => setRevisionNotes(e.target.value)}
                          onKeyDown={(e) =>
                            e.key === "Enter" && handleRevise(run.id)
                          }
                          placeholder='e.g. "Add a slide on competitive moats, use Q4 2024 data"'
                          style={{
                            flex: 1,
                            padding: "9px 13px",
                            background: "var(--bg-elevated)",
                            border: "1px solid var(--border)",
                            borderRadius: "7px",
                            color: "var(--text-primary)",
                            fontSize: "12px",
                            fontFamily: "var(--font-geist-sans)",
                            outline: "none",
                            transition: "border-color 0.2s",
                          }}
                          onFocus={(e) => {
                            e.currentTarget.style.borderColor =
                              "rgba(232,160,69,0.4)";
                          }}
                          onBlur={(e) => {
                            e.currentTarget.style.borderColor = "var(--border)";
                          }}
                        />
                        <button
                          onClick={() => handleRevise(run.id)}
                          disabled={!revisionNotes.trim()}
                          style={{
                            padding: "9px 16px",
                            background: revisionNotes.trim()
                              ? "#E8A045"
                              : "var(--bg-elevated)",
                            border: `1px solid ${
                              revisionNotes.trim()
                                ? "#E8A045"
                                : "var(--border)"
                            }`,
                            borderRadius: "7px",
                            color: revisionNotes.trim()
                              ? "#070B12"
                              : "var(--text-dim)",
                            fontSize: "12px",
                            fontFamily: "var(--font-geist-mono)",
                            cursor: revisionNotes.trim()
                              ? "pointer"
                              : "not-allowed",
                            transition:
                              "background 0.2s, color 0.2s, border-color 0.2s",
                            whiteSpace: "nowrap",
                          }}
                        >
                          Apply →
                        </button>
                      </div>
                      <p
                        style={{
                          marginTop: "8px",
                          fontSize: "10px",
                          color: "var(--text-dim)",
                          fontFamily: "var(--font-geist-mono)",
                        }}
                      >
                        Deck updates in-place — no duplicate file created
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* New research CTA */}
        {phase === "done" && (
          <button
            onClick={reset}
            style={{
              marginTop: "24px",
              fontSize: "12px",
              color: "var(--text-dim)",
              background: "none",
              border: "none",
              fontFamily: "var(--font-geist-mono)",
              cursor: "pointer",
              textDecoration: "underline",
              textUnderlineOffset: "3px",
              transition: "color 0.15s",
              letterSpacing: "0.04em",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "var(--text-primary)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "var(--text-dim)";
            }}
          >
            + New research
          </button>
        )}
      </div>
    </main>
  );
}
