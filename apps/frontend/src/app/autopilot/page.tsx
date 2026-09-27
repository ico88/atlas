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
  proposePatch,
  rejectApproval,
  startCanary,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

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

function timeAgo(iso: string | null, t: (k: string, v?: Record<string, number>) => string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return t("common.justNow");
  if (mins < 60) return t("common.agoM", { n: mins });
  const h = Math.round(mins / 60);
  if (h < 24) return t("common.agoH", { n: h });
  return t("common.agoD", { n: Math.round(h / 24) });
}

export default function AutopilotPage() {
  const { t, tv } = useI18n();
  const [data, setData] = useState<AutopilotSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await fetchAutopilot());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  const act = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await fn();
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : t("common.failed"));
      } finally {
        setBusy(false);
      }
    },
    [load, t],
  );

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const a = data?.automation;
  const loops = a
    ? [
        { on: a.auto_propose, label: t("ap.loop.propose"), freq: t("ap.every", { n: hours(a.propose_interval_s) }) },
        { on: a.auto_experiment, label: t("ap.loop.experiment"), freq: t("ap.onProposal") },
        { on: a.self_review, label: t("ap.loop.review"), freq: t("ap.every", { n: hours(a.self_review_interval_s) }) },
        { on: a.auto_fix, label: t("ap.loop.fix"), freq: t("ap.onIssue") },
      ]
    : [];

  return (
    <div>
      <h1 className="page-title">{t("nav.autopilot")}</h1>
      <p className="page-subtitle">{t("ap.subtitle")}</p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}
      {!data ? (
        <p className="muted">{t("common.loading")}</p>
      ) : (
        <>
          {/* What needs you */}
          <div className="admin-grid" style={{ marginBottom: 16 }}>
            <Link href="/improvements" className="admin-card">
              <div className="stat-value">{data.pending.approvals}</div>
              <div className="stat-label">{t("ap.awaiting")}</div>
            </Link>
            <Link href="/improvements" className="admin-card">
              <div className="stat-value">{data.pending.canary_awaiting_eval}</div>
              <div className="stat-label">{t("ap.canaryEval")}</div>
            </Link>
            <Link href="/maintenance" className="admin-card">
              <div className="stat-value">{data.pending.open_issues}</div>
              <div className="stat-label">{t("ap.openIssues")}</div>
            </Link>
          </div>

          {/* Decisions waiting for you — act right here, no page-hopping */}
          <div className="card" style={{ marginBottom: 16 }}>
            <strong>{t("ap.decisions")}</strong>
            {data.actions.length === 0 ? (
              <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
                {t("ap.nothing")}
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
                            {t("common.approve")}
                          </button>
                          <button
                            className="btn secondary"
                            disabled={busy}
                            onClick={() => act(() => rejectApproval(it.approval_id!))}
                          >
                            {t("common.reject")}
                          </button>
                        </>
                      )}
                      {it.action === "evaluate_canary" && it.proposal_id && (
                        <button
                          className="btn"
                          disabled={busy}
                          title={t("ap.evaluateHint")}
                          onClick={() => act(() => evaluateCanary(it.proposal_id!))}
                        >
                          {t("ap.evaluate")}
                        </button>
                      )}
                      {it.action === "rollout" && it.proposal_id && (
                        <>
                          <button
                            className="btn"
                            disabled={busy}
                            title={t("ap.canaryHint")}
                            onClick={() => act(() => startCanary(it.proposal_id!))}
                          >
                            {t("ap.startCanary")}
                          </button>
                          <button
                            className="btn secondary"
                            disabled={busy}
                            onClick={() => act(() => applyProposal(it.proposal_id!))}
                          >
                            {t("ap.apply")}
                          </button>
                        </>
                      )}
                      {it.action === "review_code" && it.issue_id && (
                        <>
                          <button
                            className="btn"
                            disabled={busy}
                            title={t("ap.genFixHint")}
                            onClick={() => act(() => proposePatch(it.issue_id!))}
                          >
                            {t("ap.genFix")}
                          </button>
                          <Link
                            href="/maintenance"
                            className="btn secondary"
                            style={{ padding: "4px 10px", fontSize: 12 }}
                          >
                            {t("ap.review")}
                          </Link>
                          <button
                            className="btn secondary"
                            disabled={busy}
                            title={t("ap.dismissHint")}
                            onClick={() => act(() => dismissIssue(it.issue_id!))}
                          >
                            {t("common.dismiss")}
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
            <strong>{t("ap.automations")}</strong>
            <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
              {loops.map((l) => (
                <div key={l.label} className="status-row">
                  <span>
                    <span className={l.on ? "dot ok" : "dot"} /> {l.label}
                  </span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {l.on ? l.freq : t("ap.off")}
                  </span>
                </div>
              ))}
            </div>
            <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              {t("ap.counts", {
                issues: data.counts.self_review_issues,
                proposals: data.counts.proposals,
                jobs: data.counts.finetune_jobs,
              })}
            </p>
          </div>

          {/* Activity feed */}
          <div className="card">
            <strong>{t("ap.activity")}</strong>
            {data.activity.length === 0 ? (
              <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
                {t("ap.noActivity")}
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
                    <span className={statusClass(item.status)}>{tv(item.status)}</span>
                    <span className="muted activity-when">{timeAgo(item.when, t)}</span>
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
