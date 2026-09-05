"use client";

import { useCallback, useEffect, useState } from "react";
import Markdown from "@/components/Markdown";
import { Review, ReviewSummary, fetchReview, fetchReviews, runReview } from "@/lib/api";

function decisionClass(d: string): string {
  if (d === "accept") return "queue-badge active";
  if (d === "revise") return "queue-badge idle";
  return "queue-badge";
}

function sevColor(sev: string): string {
  if (sev === "severe" || sev === "major") return "var(--bad)";
  if (sev === "minor") return "var(--warn)";
  return "var(--muted)";
}

export default function ReviewsPage() {
  const [items, setItems] = useState<ReviewSummary[]>([]);
  const [selected, setSelected] = useState<Review | null>(null);
  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState("");
  const [rounds, setRounds] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems((await fetchReviews()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const references = refs
        .split("\n")
        .flatMap((l) => l.split(","))
        .map((s) => s.trim())
        .filter(Boolean);
      const review = await runReview({
        prompt: prompt.trim(),
        references: references.length ? references : undefined,
        max_rounds: rounds,
      });
      setSelected(review);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "review failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">Critical Review</h1>
      <p className="page-subtitle">
        A proposer answers, then a <strong>critic</strong> finds flaws, a{" "}
        <strong>verifier</strong> checks claims against your reference facts, and a{" "}
        <strong>judge</strong> scores &amp; decides — across several rounds, keeping the
        best by adaptive consensus (ROADMAP PR 19).
      </p>

      {error && <p className="error">Error: {error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "grid", gap: 8 }}>
          <textarea
            value={prompt}
            placeholder="Question / prompt to review…"
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            style={{ padding: "8px 10px", borderRadius: 8, resize: "vertical" }}
          />
          <textarea
            value={refs}
            placeholder="Reference facts the answer should contain (one per line or comma-separated) — optional"
            onChange={(e) => setRefs(e.target.value)}
            rows={2}
            style={{ padding: "8px 10px", borderRadius: 8, resize: "vertical" }}
          />
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <label className="muted" style={{ fontSize: 13 }}>
              Max rounds{" "}
              <input
                type="number"
                min={1}
                max={8}
                value={rounds}
                onChange={(e) => setRounds(Math.max(1, Math.min(8, Number(e.target.value))))}
                style={{ width: 60, padding: "6px 8px", borderRadius: 8 }}
              />
            </label>
            <button className="btn" onClick={run} disabled={busy || !prompt.trim()}>
              {busy ? "Reviewing…" : "Run review"}
            </button>
          </div>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {items.length === 0 && <p className="muted">No reviews yet.</p>}
          {items.map((r) => (
            <div
              key={r.id}
              className={`convo-item ${selected?.id === r.id ? "active" : ""}`}
              onClick={async () => setSelected(await fetchReview(r.id))}
              title={r.prompt}
            >
              <span className="convo-title">{r.prompt}</span>
              <span className={decisionClass(r.decision)}>{Math.round(r.best_score * 100)}%</span>
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">Run a review or select one.</p>
          ) : (
            <div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <span className={decisionClass(selected.decision)}>{selected.decision}</span>
                <span className="pill">score {Math.round(selected.best_score * 100)}%</span>
                <span className="muted">
                  {selected.round_count} round(s) · agreement{" "}
                  {selected.consensus ? Math.round(selected.consensus.agreement * 100) : 0}% ·{" "}
                  {selected.provider} · {selected.model}
                </span>
              </div>

              <h3 style={{ fontSize: 14, marginTop: 14 }}>Best answer</h3>
              <div className="card result-card" style={{ background: "var(--panel-2)" }}>
                <Markdown text={selected.best_answer || ""} />
              </div>

              <h3 style={{ fontSize: 14, marginTop: 14 }}>Rounds</h3>
              {(selected.rounds ?? []).map((rd) => (
                <div key={rd.attempt} className="card" style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <strong>#{rd.attempt}</strong>
                    <span className={decisionClass(rd.decision)}>{rd.decision}</span>
                    <span className="pill">{Math.round(rd.score * 100)}%</span>
                    {rd.verification.grounding != null && (
                      <span className="muted">
                        grounding {Math.round(rd.verification.grounding * 100)}%
                      </span>
                    )}
                  </div>
                  {rd.findings.length > 0 && (
                    <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13 }}>
                      {rd.findings.map((f, i) => (
                        <li key={i} style={{ color: sevColor(f.severity) }}>
                          [{f.severity}] {f.message}
                        </li>
                      ))}
                    </ul>
                  )}
                  {rd.verification.unsupported.length > 0 && (
                    <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                      Unsupported: {rd.verification.unsupported.join(", ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
