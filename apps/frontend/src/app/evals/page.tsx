"use client";

import { useCallback, useEffect, useState } from "react";
import {
  EvalRun,
  EvalSuite,
  addEvalCase,
  createEvalSuite,
  fetchEvalRuns,
  fetchEvalSuites,
  runEvalSuite,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function pct(v?: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

export default function EvalsPage() {
  const { t } = useI18n();
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [selected, setSelected] = useState<EvalSuite | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [name, setName] = useState("");
  const [caseInput, setCaseInput] = useState("");
  const [caseExpected, setCaseExpected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSuites((await fetchEvalSuites()).items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const openSuite = useCallback(async (s: EvalSuite) => {
    setSelected(s);
    try {
      setRuns((await fetchEvalRuns(s.id)).items);
    } catch {
      setRuns([]);
    }
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    const s = await createEvalSuite(name.trim());
    setName("");
    await load();
    await openSuite(s);
  };

  const addCase = async () => {
    if (!selected || !caseInput.trim()) return;
    const expected = caseExpected.split(",").map((x) => x.trim()).filter(Boolean);
    await addEvalCase(selected.id, {
      input: caseInput.trim(),
      expected_substrings: expected.length ? expected : undefined,
    });
    setCaseInput("");
    setCaseExpected("");
  };

  const run = async (isBaseline: boolean) => {
    if (!selected) return;
    setBusy(true);
    try {
      await runEvalSuite(selected.id, isBaseline);
      setRuns((await fetchEvalRuns(selected.id)).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("nav.evals")}</h1>
      <p className="page-subtitle">
        {t("ev.subtitle")}
      </p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={name}
            placeholder={t("ev.namePh")}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={create} disabled={!name.trim()}>
            {t("ev.create")}
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {suites.length === 0 && <p className="muted">{t("ev.none")}</p>}
          {suites.map((s) => (
            <div
              key={s.id}
              className={`convo-item ${selected?.id === s.id ? "active" : ""}`}
              onClick={() => openSuite(s)}
            >
              {s.name}
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">{t("ev.select")}</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>{selected.name}</h3>

              <div className="card" style={{ background: "var(--panel-2)", marginBottom: 12 }}>
                <strong>{t("ev.addCase")}</strong>
                <input
                  value={caseInput}
                  placeholder={t("ev.inputPh")}
                  onChange={(e) => setCaseInput(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8, margin: "8px 0" }}
                />
                <input
                  value={caseExpected}
                  placeholder={t("ev.expectedPh")}
                  onChange={(e) => setCaseExpected(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8 }}
                />
                <button className="btn secondary" style={{ marginTop: 8 }} onClick={addCase} disabled={!caseInput.trim()}>
                  {t("ev.addCaseBtn")}
                </button>
              </div>

              <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                <button className="btn" onClick={() => run(false)} disabled={busy}>
                  {busy ? t("imp.running") : t("q.run")}
                </button>
                <button className="btn secondary" onClick={() => run(true)} disabled={busy}>
                  {t("ev.runBaseline")}
                </button>
              </div>

              <h3 style={{ fontSize: 14 }}>{t("ev.runs")}</h3>
              {runs.length === 0 ? (
                <p className="muted">{t("ev.noRuns")}</p>
              ) : (
                <div className="card" style={{ overflowX: "auto" }}>
                  <table className="data" style={{ width: "100%" }}>
                    <thead>
                      <tr>
                        <th>{t("ev.when")}</th>
                        <th>{t("res.model")}</th>
                        <th>{t("ev.pass")}</th>
                        <th>{t("imp.quality")}</th>
                        <th>{t("imp.safety")}</th>
                        <th>{t("ev.latency")}</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((r) => (
                        <tr key={r.id}>
                          <td>{new Date(r.created_at).toLocaleTimeString()}</td>
                          <td>{r.model || r.provider || "—"}</td>
                          <td>{pct(r.metrics?.pass_rate)}</td>
                          <td>{pct(r.metrics?.avg_quality)}</td>
                          <td>{pct(r.metrics?.avg_safety)}</td>
                          <td>{r.metrics?.avg_latency_ms != null ? `${r.metrics.avg_latency_ms} ms` : "—"}</td>
                          <td>{r.is_baseline ? `⭐ ${t("ev.baseline")}` : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
