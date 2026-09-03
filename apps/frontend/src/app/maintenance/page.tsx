"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Approval,
  MaintenanceIssue,
  analyzeIssue,
  applyFix,
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
        <strong>Semi-automatic:</strong> a new issue is analysed and a fix is
        prepared &amp; validated in a real, isolated <strong>sandbox</strong> on its
        own (this page refreshes as it progresses) — you are left with just{" "}
        <em>Approve</em> then <em>Apply</em>. Only after you approve does it open
        the PR — never touching <code>main</code>, never merging. Git actions are
        guard-railed and audited (dry-run unless GitHub is explicitly enabled).
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
                      <span className="muted">Sandbox</span>
                      <span>{r.tests_summary}</span>
                    </div>
                  )}
                  {r.status === "APPROVED" && (
                    <div style={{ marginTop: 10 }}>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() => act(() => applyFix(selected.id), selected.id)}
                      >
                        Apply approved fix (open PR)
                      </button>
                      <p className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                        Governed action: opens the PR via the configured provider
                        (dry-run unless GitHub is enabled). Never pushes to a
                        protected branch or merges.
                      </p>
                    </div>
                  )}
                  {r.status === "PR_OPENED" && (
                    <div className="status-row">
                      <span className="muted">Applied</span>
                      <span className="pill">PR opened</span>
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
