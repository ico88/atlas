"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Approval,
  EvalSuite,
  ImprovementProposal,
  applyProposal,
  approveApproval,
  autoPropose,
  createProposal,
  evaluateCanary,
  experimentProposal,
  fetchApprovals,
  fetchEvalSuites,
  fetchProposals,
  rejectApproval,
  startCanary,
} from "@/lib/api";

function pct(v?: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function verdictClass(v?: string | null): string {
  if (v === "improvement") return "queue-badge active";
  if (v === "regression") return "queue-badge";
  return "queue-badge idle";
}

export default function ImprovementsPage() {
  const [proposals, setProposals] = useState<ImprovementProposal[]>([]);
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<ImprovementProposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // new-proposal form
  const [title, setTitle] = useState("");
  const [suiteId, setSuiteId] = useState("");
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");

  const load = useCallback(async () => {
    try {
      const [p, s, a] = await Promise.all([
        fetchProposals(),
        fetchEvalSuites(),
        fetchApprovals(),
      ]);
      setProposals(p.items);
      setSuites(s.items);
      setApprovals(a.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh while an experiment is running in the background (DRAFT), so the
  // verdict + approval gate appear on their own.
  useEffect(() => {
    const running = proposals.some((p) => p.status === "DRAFT");
    if (!running) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [proposals, load]);

  // Keep the selected proposal in sync with the freshest list data.
  useEffect(() => {
    if (selected) {
      const fresh = proposals.find((p) => p.id === selected.id);
      if (fresh && fresh !== selected) setSelected(fresh);
    }
  }, [proposals, selected]);

  const pendingApprovalFor = (id: string) =>
    approvals.find(
      (a) =>
        a.subject_type === "improvement_proposal" &&
        a.subject_id === id &&
        a.status === "PENDING",
    );

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "action failed");
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!title.trim()) return;
    await act(async () => {
      const p = await createProposal({
        title: title.trim(),
        suite_id: suiteId || undefined,
        baseline_model: baseline.trim() || undefined,
        candidate_model: candidate.trim() || undefined,
      });
      setTitle("");
      setBaseline("");
      setCandidate("");
      setSelected(p);
    });
  };

  const deltas = selected?.comparison?.deltas ?? {};

  return (
    <div>
      <h1 className="page-title">Continuous Improvement</h1>
      <p className="page-subtitle">
        <strong>Semi-automatic:</strong> create a proposal and the{" "}
        <strong>experiment</strong> (candidate vs baseline on an eval suite) runs
        by itself — this page refreshes until a verdict and an approval gate
        appear. You are left with just <em>Approve</em> then <em>Apply</em>
        (ROADMAP PR 18). Safety is the overriding signal: a candidate that lowers
        safety is always a regression.
      </p>

      {error && <p className="error">Error: {error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>
            <strong>Let ATLAS propose</strong>
            <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
              generates a proposal for each available model vs the current default,
              then experiments them automatically
            </span>
          </span>
          <button
            className="btn"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              setNote(null);
              try {
                const res = await autoPropose();
                setNote(
                  res.total > 0
                    ? `Created ${res.total} proposal(s); the experiment runs automatically.`
                    : "Nothing to propose yet — you need at least two models (download another on the Models page). A starter eval suite was created for you.",
                );
                await load();
              } catch (e) {
                setError(e instanceof Error ? e.message : "auto-propose failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Generate proposals now
          </button>
        </div>
        {note && (
          <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
            {note}
          </p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>New proposal</strong>
        <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
          <input
            value={title}
            placeholder="Title (e.g. Adopt llama3.2:3b as default)"
            onChange={(e) => setTitle(e.target.value)}
            style={{ padding: "8px 10px", borderRadius: 8 }}
          />
          <select
            value={suiteId}
            onChange={(e) => setSuiteId(e.target.value)}
            className="model-select"
            style={{ maxWidth: "none", width: "100%" }}
          >
            <option value="">Eval suite (required to experiment)…</option>
            {suites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              value={baseline}
              placeholder="Baseline model (blank = current default)"
              onChange={(e) => setBaseline(e.target.value)}
              style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
            />
            <input
              value={candidate}
              placeholder="Candidate model"
              onChange={(e) => setCandidate(e.target.value)}
              style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
            />
          </div>
          <button className="btn" onClick={create} disabled={!title.trim() || busy}>
            Create proposal
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {proposals.length === 0 && <p className="muted">No proposals yet.</p>}
          {proposals.map((p) => (
            <div
              key={p.id}
              className={`convo-item ${selected?.id === p.id ? "active" : ""}`}
              onClick={() => setSelected(p)}
              title={p.title}
            >
              {p.title}
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">Select a proposal.</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>{selected.title}</h3>
              <div className="status-row">
                <span className="muted">Status</span>
                <span className="pill">{selected.status}</span>
              </div>
              <div className="status-row">
                <span className="muted">Candidate</span>
                <span>
                  {selected.candidate_model || "—"}
                  {selected.baseline_model ? ` vs ${selected.baseline_model}` : " vs current default"}
                </span>
              </div>
              {selected.recommendation && (
                <div className="status-row">
                  <span className="muted">Verdict</span>
                  <span className={verdictClass(selected.recommendation)}>
                    {selected.recommendation}
                  </span>
                </div>
              )}

              {selected.comparison?.deltas && (
                <div className="card" style={{ background: "var(--panel-2)", margin: "10px 0" }}>
                  <strong>Metric deltas (candidate − baseline)</strong>
                  <table className="data" style={{ width: "100%", marginTop: 6 }}>
                    <tbody>
                      <tr>
                        <td>Pass rate</td>
                        <td>{deltas.pass_rate == null ? "—" : pct(deltas.pass_rate)}</td>
                      </tr>
                      <tr>
                        <td>Quality</td>
                        <td>{deltas.avg_quality == null ? "—" : pct(deltas.avg_quality)}</td>
                      </tr>
                      <tr>
                        <td>Safety</td>
                        <td>{deltas.avg_safety == null ? "—" : pct(deltas.avg_safety)}</td>
                      </tr>
                      <tr>
                        <td>p95 latency</td>
                        <td>{deltas.p95_latency_ms == null ? "—" : `${deltas.p95_latency_ms} ms`}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                {(selected.status === "DRAFT" || selected.status === "EXPERIMENTED") && (
                  <button
                    className="btn"
                    disabled={busy || !selected.suite_id}
                    title={selected.suite_id ? "" : "Attach an eval suite first"}
                    onClick={() => act(() => experimentProposal(selected.id))}
                  >
                    {busy ? "Running…" : "Run experiment"}
                  </button>
                )}

                {selected.status === "EXPERIMENTED" &&
                  pendingApprovalFor(selected.id) && (
                    <>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          act(() => approveApproval(pendingApprovalFor(selected.id)!.id))
                        }
                      >
                        Approve
                      </button>
                      <button
                        className="btn secondary"
                        disabled={busy}
                        onClick={() =>
                          act(() => rejectApproval(pendingApprovalFor(selected.id)!.id))
                        }
                      >
                        Reject
                      </button>
                    </>
                  )}

                {selected.status === "APPROVED" && (
                  <>
                    <button
                      className="btn"
                      disabled={busy}
                      title="Roll out to a watched canary, then promote or auto-rollback"
                      onClick={() => act(() => startCanary(selected.id))}
                    >
                      Start canary
                    </button>
                    <button
                      className="btn secondary"
                      disabled={busy}
                      onClick={() => act(() => applyProposal(selected.id))}
                    >
                      Apply directly
                    </button>
                  </>
                )}

                {selected.status === "CANARY" && (
                  <button
                    className="btn"
                    disabled={busy}
                    title="Run the health gate: promote if healthy, else auto-rollback"
                    onClick={() => act(() => evaluateCanary(selected.id))}
                  >
                    Evaluate canary (health gate)
                  </button>
                )}

                {selected.status === "APPLIED" && (
                  <span className="queue-badge active">✓ applied</span>
                )}
                {selected.status === "ROLLED_BACK" && (
                  <span className="queue-badge">↩ rolled back</span>
                )}
              </div>

              {selected.status === "CANARY" && (
                <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                  🐤 Canary live — the candidate is active. Evaluate to promote it or
                  automatically roll back on a regression.
                </p>
              )}
              {selected.comparison?.canary?.reason && (
                <p className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                  Health gate: {String(selected.comparison.canary.reason)}
                </p>
              )}

              {selected.status === "EXPERIMENTED" && !pendingApprovalFor(selected.id) && (
                <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                  Awaiting a human approval decision.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
