"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Approval,
  MaintenanceIssue,
  analyzeIssue,
  approveApproval,
  createFix,
  fetchApprovals,
  fetchIssue,
  fetchIssues,
  rejectApproval,
} from "@/lib/api";

const SEV_CLASS: Record<string, string> = {
  critical: "bad",
  high: "bad",
  medium: "warn",
  low: "ok",
};

export default function MaintenancePage() {
  const [issues, setIssues] = useState<MaintenanceIssue[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<MaintenanceIssue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [i, a] = await Promise.all([fetchIssues(), fetchApprovals()]);
      setIssues(i.items);
      setApprovals(a.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);

  const open = async (id: string) => setSelected(await fetchIssue(id));

  const act = async (fn: () => Promise<unknown>, issueId?: string) => {
    setBusy(true);
    try {
      await fn();
      await load();
      if (issueId) setSelected(await fetchIssue(issueId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const pendingFor = (issue: MaintenanceIssue): Approval | undefined => {
    const runIds = new Set((issue.runs ?? []).map((r) => r.id));
    return approvals.find(
      (a) => a.status === "PENDING" && a.subject_id && runIds.has(a.subject_id),
    );
  };

  return (
    <div>
      <h1 className="page-title">Maintenance</h1>
      <p className="page-subtitle">
        The Maintenance Agent fingerprints logs into issues, proposes a fix
        (branch → patch → tests → PR, never touching <code>main</code>), and waits
        for your approval (spec §11). Git actions are dry-run and audited.
      </p>

      {error && <p className="error">{error}</p>}

      <div className="chat-layout">
        <div className="convo-list">
          <div className="muted" style={{ padding: "6px 10px", fontSize: 12 }}>
            {issues.length} issue(s)
          </div>
          {issues.map((i) => (
            <div
              key={i.id}
              className={`convo-item ${selected?.id === i.id ? "active" : ""}`}
              onClick={() => open(i.id)}
              title={i.title}
            >
              <span className={`dot ${SEV_CLASS[i.severity] ?? "warn"}`} /> {i.title}
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 18, display: "block", overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">Select an issue to see details.</p>
          ) : (
            <div>
              <div className="status-row">
                <strong>{selected.title}</strong>
                <span className="pill">{selected.status}</span>
              </div>
              <div className="status-row">
                <span className="muted">Service</span>
                <span>{selected.service ?? "—"}</span>
              </div>
              <div className="status-row">
                <span className="muted">Severity</span>
                <span>{selected.severity}</span>
              </div>
              <div className="status-row">
                <span className="muted">Occurrences</span>
                <span className="pill">{selected.occurrences}</span>
              </div>

              <div style={{ display: "flex", gap: 8, margin: "14px 0" }}>
                <button
                  className="btn secondary"
                  disabled={busy}
                  onClick={() => act(() => analyzeIssue(selected.id), selected.id)}
                >
                  Analyze
                </button>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => act(() => createFix(selected.id), selected.id)}
                >
                  Create fix
                </button>
              </div>

              {(selected.runs ?? []).map((r) => (
                <div className="card" key={r.id} style={{ marginBottom: 10 }}>
                  <div className="status-row">
                    <span className="muted">Run</span>
                    <span className="pill">{r.status}</span>
                  </div>
                  {r.branch && (
                    <div className="status-row">
                      <span className="muted">Branch</span>
                      <span>{r.branch}</span>
                    </div>
                  )}
                  {r.pr_url && (
                    <div className="status-row">
                      <span className="muted">PR</span>
                      <span>{r.pr_url}</span>
                    </div>
                  )}
                  {r.tests_summary && (
                    <div className="status-row">
                      <span className="muted">Tests</span>
                      <span>{r.tests_summary}</span>
                    </div>
                  )}
                </div>
              ))}

              {(() => {
                const pending = pendingFor(selected);
                if (!pending) return null;
                return (
                  <div className="card" style={{ borderColor: "var(--accent)" }}>
                    <h3>Approval required</h3>
                    <p className="muted">{pending.reason}</p>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() => act(() => approveApproval(pending.id), selected.id)}
                      >
                        Approve
                      </button>
                      <button
                        className="btn secondary"
                        disabled={busy}
                        onClick={() => act(() => rejectApproval(pending.id), selected.id)}
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
