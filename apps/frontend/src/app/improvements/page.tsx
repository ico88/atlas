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
import { useI18n } from "@/lib/i18n";

function pct(v?: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function verdictClass(v?: string | null): string {
  if (v === "improvement") return "queue-badge active";
  if (v === "regression") return "queue-badge";
  return "queue-badge idle";
}

export default function ImprovementsPage() {
  const { t, tv } = useI18n();
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
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

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
      setError(e instanceof Error ? e.message : t("common.failed"));
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
      <h1 className="page-title">{t("nav.improvements")}</h1>
      <p className="page-subtitle">{t("imp.subtitle")}</p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>
            <strong>{t("imp.letPropose")}</strong>
            <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
              {t("imp.letProposeHelp")}
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
                    ? t("imp.created", { n: res.total })
                    : t("imp.nothingToPropose"),
                );
                await load();
              } catch (e) {
                setError(e instanceof Error ? e.message : t("common.failed"));
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("imp.generate")}
          </button>
        </div>
        {note && (
          <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
            {note}
          </p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>{t("imp.new")}</strong>
        <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
          <input
            value={title}
            placeholder={t("imp.titlePh")}
            onChange={(e) => setTitle(e.target.value)}
            style={{ padding: "8px 10px", borderRadius: 8 }}
          />
          <select
            value={suiteId}
            onChange={(e) => setSuiteId(e.target.value)}
            className="model-select"
            style={{ maxWidth: "none", width: "100%" }}
          >
            <option value="">{t("imp.suitePh")}</option>
            {suites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              value={baseline}
              placeholder={t("imp.baselinePh")}
              onChange={(e) => setBaseline(e.target.value)}
              style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
            />
            <input
              value={candidate}
              placeholder={t("imp.candidatePh")}
              onChange={(e) => setCandidate(e.target.value)}
              style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
            />
          </div>
          <button className="btn" onClick={create} disabled={!title.trim() || busy}>
            {t("imp.create")}
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {proposals.length === 0 && <p className="muted">{t("imp.none")}</p>}
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
            <p className="muted">{t("imp.select")}</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>{selected.title}</h3>
              <div className="status-row">
                <span className="muted">{t("common.status")}</span>
                <span className="pill">{tv(selected.status)}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("imp.candidate")}</span>
                <span>
                  {selected.candidate_model || "—"}
                  {selected.baseline_model ? ` vs ${selected.baseline_model}` : ` ${t("imp.vsDefault")}`}
                </span>
              </div>
              {selected.recommendation && (
                <div className="status-row">
                  <span className="muted">{t("imp.verdict")}</span>
                  <span className={verdictClass(selected.recommendation)}>
                    {tv(selected.recommendation)}
                  </span>
                </div>
              )}

              {selected.comparison?.deltas && (
                <div className="card" style={{ background: "var(--panel-2)", margin: "10px 0" }}>
                  <strong>{t("imp.deltas")}</strong>
                  <table className="data" style={{ width: "100%", marginTop: 6 }}>
                    <tbody>
                      <tr>
                        <td>{t("imp.passRate")}</td>
                        <td>{deltas.pass_rate == null ? "—" : pct(deltas.pass_rate)}</td>
                      </tr>
                      <tr>
                        <td>{t("imp.quality")}</td>
                        <td>{deltas.avg_quality == null ? "—" : pct(deltas.avg_quality)}</td>
                      </tr>
                      <tr>
                        <td>{t("imp.safety")}</td>
                        <td>{deltas.avg_safety == null ? "—" : pct(deltas.avg_safety)}</td>
                      </tr>
                      <tr>
                        <td>{t("imp.p95")}</td>
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
                    title={selected.suite_id ? "" : t("imp.attachSuite")}
                    onClick={() => act(() => experimentProposal(selected.id))}
                  >
                    {busy ? t("imp.running") : t("imp.run")}
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
                        {t("common.approve")}
                      </button>
                      <button
                        className="btn secondary"
                        disabled={busy}
                        onClick={() =>
                          act(() => rejectApproval(pendingApprovalFor(selected.id)!.id))
                        }
                      >
                        {t("common.reject")}
                      </button>
                    </>
                  )}

                {selected.status === "APPROVED" && (
                  <>
                    <button
                      className="btn"
                      disabled={busy}
                      title={t("ap.canaryHint")}
                      onClick={() => act(() => startCanary(selected.id))}
                    >
                      {t("ap.startCanary")}
                    </button>
                    <button
                      className="btn secondary"
                      disabled={busy}
                      onClick={() => act(() => applyProposal(selected.id))}
                    >
                      {t("imp.applyDirect")}
                    </button>
                  </>
                )}

                {selected.status === "CANARY" && (
                  <button
                    className="btn"
                    disabled={busy}
                    title={t("ap.evaluateHint")}
                    onClick={() => act(() => evaluateCanary(selected.id))}
                  >
                    {t("imp.evaluate")}
                  </button>
                )}

                {selected.status === "APPLIED" && (
                  <span className="queue-badge active">✓ {t("v.applied")}</span>
                )}
                {selected.status === "ROLLED_BACK" && (
                  <span className="queue-badge">↩ {t("v.rolled_back")}</span>
                )}
              </div>

              {selected.status === "CANARY" && (
                <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                  🐤 {t("imp.canaryLive")}
                </p>
              )}
              {selected.comparison?.canary?.reason && (
                <p className="muted" style={{ marginTop: 4, fontSize: 12 }}>
                  {t("imp.healthGate")}: {String(selected.comparison.canary.reason)}
                </p>
              )}

              {selected.status === "EXPERIMENTED" && !pendingApprovalFor(selected.id) && (
                <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                  {t("imp.awaitingHuman")}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
