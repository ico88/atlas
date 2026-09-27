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
  runSelfReview,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const SEV_CLASS: Record<string, string> = {
  critical: "bad",
  high: "bad",
  medium: "warn",
  low: "ok",
};

export default function MaintenancePage() {
  const { t, tv } = useI18n();
  const [issues, setIssues] = useState<MaintenanceIssue[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<MaintenanceIssue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [i, a] = await Promise.all([fetchIssues(), fetchApprovals()]);
      setIssues(i.items);
      setApprovals(a.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  }, [t]);

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
      setError(err instanceof Error ? err.message : t("common.failed"));
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
      <h1 className="page-title">{t("nav.maintenance")}</h1>
      <p className="page-subtitle">
        {t("mnt.subtitle")}
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>
            <strong>{t("mnt.selfReview")}</strong>
            <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
              {t("mnt.selfReviewHelp")}
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
                const r = await runSelfReview();
                setNote(
                  t("mnt.scanned", { files: r.scanned, findings: r.findings, issues: r.new_issues }),
                );
                await load();
              } catch (err) {
                setError(err instanceof Error ? err.message : t("common.failed"));
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("mnt.scanNow")}
          </button>
        </div>
        {note && (
          <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
            {note}
          </p>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      <div className="chat-layout">
        <div className="convo-list">
          <div className="muted" style={{ padding: "6px 10px", fontSize: 12 }}>
            {t("mnt.issues", { n: issues.length })}
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
            <p className="muted">{t("mnt.select")}</p>
          ) : (
            <div>
              <div className="status-row">
                <strong>{selected.title}</strong>
                <span className="pill">{tv(selected.status)}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("mnt.service")}</span>
                <span>{selected.service ?? "—"}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("mnt.severity")}</span>
                <span>{tv(selected.severity)}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("mnt.occurrences")}</span>
                <span className="pill">{selected.occurrences}</span>
              </div>

              <div style={{ display: "flex", gap: 8, margin: "14px 0" }}>
                <button
                  className="btn secondary"
                  disabled={busy}
                  onClick={() => act(() => analyzeIssue(selected.id), selected.id)}
                >
                  {t("mnt.analyze")}
                </button>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => act(() => createFix(selected.id), selected.id)}
                >
                  {t("mnt.createFix")}
                </button>
              </div>

              {(selected.runs ?? []).map((r) => (
                <div className="card" key={r.id} style={{ marginBottom: 10 }}>
                  <div className="status-row">
                    <span className="muted">{t("mnt.run")}</span>
                    <span className="pill">{tv(r.status)}</span>
                  </div>
                  {r.branch && (
                    <div className="status-row">
                      <span className="muted">{t("mnt.branch")}</span>
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
                        {t("mnt.applyFix")}
                      </button>
                      <p className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                        {t("mnt.applyHelp")}
                      </p>
                    </div>
                  )}
                  {r.status === "PR_OPENED" && (
                    <div className="status-row">
                      <span className="muted">{t("v.applied")}</span>
                      <span className="pill">{t("v.pr_opened")}</span>
                    </div>
                  )}
                </div>
              ))}

              {(() => {
                const pending = pendingFor(selected);
                if (!pending) return null;
                return (
                  <div className="card" style={{ borderColor: "var(--accent)" }}>
                    <h3>{t("mnt.approvalRequired")}</h3>
                    <p className="muted">{pending.reason}</p>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() => act(() => approveApproval(pending.id), selected.id)}
                      >
                        {t("common.approve")}
                      </button>
                      <button
                        className="btn secondary"
                        disabled={busy}
                        onClick={() => act(() => rejectApproval(pending.id), selected.id)}
                      >
                        {t("common.reject")}
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
