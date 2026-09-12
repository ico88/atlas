"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  AutopilotSummary,
  applyProposal,
  approveApproval,
  dismissIssue,
  evaluateCanary,
  fetchAutopilot,
  rejectApproval,
  startCanary,
} from "@/lib/api";

function hours(seconds: number): string {
  if (seconds >= 3600) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 60)}m`;
}

function statusClass(status: string): string {
  const s = status.toUpperCase();
  if (["APPLIED", "COMPLETED", "IMPROVEMENT", "RESOLVED"].includes(s)) return "queue-badge active";
  if (["ROLLED_BACK", "FAILED", "REGRESSION", "REJECTED"].includes(s)) return "queue-badge";
  return "queue-badge idle";
}

const KIND_ICON: Record<string, string> = {
  proposal: "🔬",
  "self-review": "🔍",
  maintenance: "🔧",
  finetune: "🎓",
};

const KIND_HREF: Record<string, string> = {
  proposal: "/improvements",
  "self-review": "/maintenance",
  maintenance: "/maintenance",
  finetune: "/finetune",
};

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export default function AutopilotPage() {
  const [data, setData] = useState<AutopilotSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await fetchAutopilot());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
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
    },
    [load],
  );

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const a = data?.automation;
  const loops = a
    ? [
        { on: a.auto_propose, label: "Proposes model improvements", freq: hours(a.propose_interval_s) },
        { on: a.auto_experiment, label: "Runs A/B experiments", freq: "on new proposal" },
        { on: a.self_review, label: "Reviews its own code", freq: hours(a.self_review_interval_s) },
        { on: a.auto_fix, label: "Prepares sandbox-validated fixes", freq: "on new issue" },
      ]
    : [];

  return (
    <div>
      <h1 className="page-title">Autopilot</h1>
      <p className="page-subtitle">
        What ATLAS is doing on its own — proposing model &amp; code improvements, running
        experiments, and self-reviewing. Everything here is <strong>propose-only</strong>: the
        irreversible step (apply / merge) always waits for you.
      </p>

      {error && <p className="error">Error: {error}</p>}
      {!data ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          {/* What needs you */}
          <div className="admin-grid" style={{ marginBottom: 16 }}>
            <Link href="/improvements" className="admin-card">
              <div className="stat-value">{data.pending.approvals}</div>
              <div className="stat-label">awaiting your approval</div>
            </Link>
            <Link href="/improvements" className="admin-card">
              <div className="stat-value">{data.pending.canary_awaiting_eval}</div>
              <div className="stat-label">canary to evaluate</div>
            </Link>
            <Link href="/maintenance" className="admin-card">
              <div className="stat-value">{data.pending.open_issues}</div>
              <div className="stat-label">open code issues</div>
            </Link>
          </div>

          {/* Decisions waiting for you — act right here, no page-hopping */}
          <div className="card" style={{ marginBottom: 16 }}>
            <strong>Decisions waiting for you</strong>
            {data.actions.length === 0 ? (
              <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
                Nothing to decide — ATLAS is caught up.
              </p>
            ) : (
              <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                {data.actions.map((it) => (
                  <div key={it.id} className="action-row">
                    <span className="activity-icon">
                      {it.kind === "code" ? "🔧" : it.kind === "canary" ? "🐤" : "🔬"}
                    </span>
                    <span className="action-body">
                      <span className="action-title" title={it.title}>
                        {it.title}
                      </span>
                      <span className="muted" style={{ fontSize: 11 }}>
                        {it.detail}
                      </span>
                    </span>
                    <span className="action-buttons">
                      {it.action === "decide" && it.approval_id && (
                        <>
                          <button
                            className="btn"
                            disabled={busy}
                            onClick={() => act(() => approveApproval(it.approval_id!))}
                          >
                            Approve
                          </button>
                          <button
                            className="btn secondary"
                            disabled={busy}
                            onClick={() => act(() => rejectApproval(it.approval_id!))}
                          >
                            Reject
                          </button>
                        </>
                      )}
                      {it.action === "evaluate_canary" && it.proposal_id && (
                        <button
                          className="btn"
                          disabled={busy}
                          title="Run the health gate: promote if healthy, else auto-rollback"
                          onClick={() => act(() => evaluateCanary(it.proposal_id!))}
                        >
                          Evaluate canary
                        </button>
                      )}
                      {it.action === "rollout" && it.proposal_id && (
                        <>
                          <button
                            className="btn"
                            disabled={busy}
                            title="Roll out to a watched canary, then promote or auto-rollback"
                            onClick={() => act(() => startCanary(it.proposal_id!))}
                          >
                            Start canary
                          </button>
                          <button
                            className="btn secondary"
                            disabled={busy}
                            onClick={() => act(() => applyProposal(it.proposal_id!))}
                          >
                            Apply
                          </button>
                        </>
                      )}
                      {it.action === "review_code" && it.issue_id && (
                        <>
                          <Link
                            href="/maintenance"
                            className="btn"
                            style={{ padding: "4px 10px", fontSize: 12 }}
                          >
                            Review
                          </Link>
                          <button
                            className="btn secondary"
                            disabled={busy}
                            title="Ignore this code finding"
                            onClick={() => act(() => dismissIssue(it.issue_id!))}
                          >
                            Dismiss
                          </button>
                        </>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Loops running */}
          <div className="card" style={{ marginBottom: 16 }}>
            <strong>Automations running</strong>
            <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
              {loops.map((l) => (
                <div key={l.label} className="status-row">
                  <span>
                    <span className={l.on ? "dot ok" : "dot"} /> {l.label}
                  </span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {l.on ? `every ${l.freq}` : "off"}
                  </span>
                </div>
              ))}
            </div>
            <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              {data.counts.self_review_issues} code finding(s) · {data.counts.proposals} proposal(s)
              · {data.counts.finetune_jobs} fine-tune job(s)
            </p>
          </div>

          {/* Activity feed */}
          <div className="card">
            <strong>Recent activity</strong>
            {data.activity.length === 0 ? (
              <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
                Nothing yet — automations run on a timer; give 👍/👎 in chat and download a second
                model to give ATLAS something to work with.
              </p>
            ) : (
              <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
                {data.activity.map((item, i) => (
                  <Link
                    key={i}
                    href={KIND_HREF[item.kind] ?? "/"}
                    className="activity-row"
                  >
                    <span className="activity-icon">{KIND_ICON[item.kind] ?? "•"}</span>
                    <span className="activity-title" title={item.title}>
                      {item.title}
                    </span>
                    <span className={statusClass(item.status)}>{item.status}</span>
                    <span className="muted activity-when">{timeAgo(item.when)}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
