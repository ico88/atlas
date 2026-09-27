"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FineTuneDataset,
  FineTuneExample,
  FineTuneJob,
  FineTuneReadiness,
  addFtExample,
  adoptFtJob,
  createFtDataset,
  createFtJob,
  curateFtDataset,
  fetchFtDatasets,
  fetchFtExamples,
  fetchFtJobs,
  fetchFtReadiness,
  setFtExampleIncluded,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function jobBadge(status: string): string {
  if (status === "COMPLETED") return "queue-badge active";
  if (status === "FAILED" || status === "CANCELLED") return "queue-badge";
  return "queue-badge idle";
}

export default function FineTunePage() {
  const { t, tv } = useI18n();
  const [readiness, setReadiness] = useState<FineTuneReadiness | null>(null);
  const [datasets, setDatasets] = useState<FineTuneDataset[]>([]);
  const [selected, setSelected] = useState<FineTuneDataset | null>(null);
  const [examples, setExamples] = useState<FineTuneExample[]>([]);
  const [jobs, setJobs] = useState<FineTuneJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [dsName, setDsName] = useState("");
  const [baseModel, setBaseModel] = useState("");
  const [exPrompt, setExPrompt] = useState("");
  const [exResponse, setExResponse] = useState("");

  const loadTop = useCallback(async () => {
    try {
      const [r, d] = await Promise.all([fetchFtReadiness(), fetchFtDatasets()]);
      setReadiness(r);
      setDatasets(d.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  const loadDetail = useCallback(async (id: string) => {
    const [ex, jb] = await Promise.all([fetchFtExamples(id), fetchFtJobs(id)]);
    setExamples(ex.items);
    setJobs(jb.items);
  }, []);

  useEffect(() => {
    loadTop();
  }, [loadTop]);

  useEffect(() => {
    if (selected) loadDetail(selected.id).catch(() => undefined);
  }, [selected, loadDetail]);

  // Poll while a job is training so its status + metrics update on their own.
  useEffect(() => {
    if (!selected) return;
    const running = jobs.some((j) => ["QUEUED", "RUNNING"].includes(j.status));
    if (!running) return;
    const id = setInterval(() => loadDetail(selected.id).catch(() => undefined), 3000);
    return () => clearInterval(id);
  }, [jobs, selected, loadDetail]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await fn();
      await loadTop();
      if (selected) await loadDetail(selected.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const included = examples.filter((e) => e.included).length;
  const enoughData = readiness ? included >= readiness.recommended_min_examples : false;

  return (
    <div>
      <h1 className="page-title">{t("ft.title")}</h1>
      <p className="page-subtitle">
        {t("ft.subtitle")}
      </p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}
      {note && (
        <p className="muted" style={{ fontSize: 13 }}>
          {note}
        </p>
      )}

      {readiness && (
        <div className="card" style={{ marginBottom: 16 }}>
          <strong>{t("ft.readiness")}</strong>
          <div className="status-row" style={{ marginTop: 6 }}>
            <span className="muted">{t("ft.gpuNode")}</span>
            <span className={readiness.gpu_node_available ? "queue-badge active" : "queue-badge"}>
              {readiness.gpu_node_available
                ? `✓ ${readiness.gpu_node_names.join(", ")}`
                : t("ft.noneOnline")}
            </span>
          </div>
          <div className="status-row">
            <span className="muted">{t("ft.positive")}</span>
            <span>{readiness.positive_feedback}</span>
          </div>
          {!readiness.gpu_node_available && (
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              {t("ft.needGpu")} <code>gpu</code>{t("ft.needGpu2")}
            </p>
          )}
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>{t("ft.newDataset")}</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <input
            value={dsName}
            placeholder={t("ft.namePh")}
            onChange={(e) => setDsName(e.target.value)}
            style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={baseModel}
            placeholder={t("ft.basePh")}
            onChange={(e) => setBaseModel(e.target.value)}
            style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
          />
          <button
            className="btn"
            disabled={!dsName.trim() || busy}
            onClick={() =>
              act(async () => {
                const d = await createFtDataset({
                  name: dsName.trim(),
                  base_model: baseModel.trim() || undefined,
                });
                setDsName("");
                setBaseModel("");
                setSelected(d);
              })
            }
          >
            {t("common.create")}
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {datasets.length === 0 && <p className="muted">{t("ft.none")}</p>}
          {datasets.map((d) => (
            <div
              key={d.id}
              className={`convo-item ${selected?.id === d.id ? "active" : ""}`}
              onClick={() => setSelected(d)}
              title={d.name}
            >
              {d.name}
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">{t("ft.select")}</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>{selected.name}</h3>
              <div className="status-row">
                <span className="muted">{t("ft.base")}</span>
                <span>{selected.base_model || t("ft.currentDefault")}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("ft.included")}</span>
                <span className={enoughData ? "queue-badge active" : "queue-badge idle"}>
                  {included}
                  {readiness ? ` / ${t("ft.recommended", { n: readiness.recommended_min_examples })}` : ""}
                </span>
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
                <button
                  className="btn"
                  disabled={busy}
                  title={t("ft.harvestHint")}
                  onClick={() =>
                    act(async () => {
                      const r = await curateFtDataset(selected.id);
                      setNote(
                        r.added > 0
                          ? t("ft.added", { n: r.added })
                          : t("ft.nothingToHarvest"),
                      );
                    })
                  }
                >
                  {t("ft.harvest")}
                </button>
                <button
                  className="btn"
                  disabled={busy || included === 0}
                  title={
                    readiness?.gpu_node_available
                      ? t("ft.trainHint")
                      : t("ft.trainNoGpu")
                  }
                  onClick={() =>
                    act(async () => {
                      await createFtJob({ dataset_id: selected.id });
                      setNote(t("ft.dispatched"));
                    })
                  }
                >
                  {t("ft.train")}
                </button>
              </div>

              {jobs.length > 0 && (
                <div className="card" style={{ background: "var(--panel-2)", margin: "10px 0" }}>
                  <strong>{t("ft.jobs")}</strong>
                  <table className="data" style={{ width: "100%", marginTop: 6 }}>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id}>
                          <td>{j.adapter_name}</td>
                          <td>
                            <span className={jobBadge(j.status)}>{tv(j.status)}</span>
                          </td>
                          <td>{t("ft.examplesShort", { n: j.example_count })}</td>
                          <td>
                            {j.metrics?.final_loss != null
                              ? t("ft.loss", { n: String(j.metrics.final_loss) })
                              : j.error
                                ? <span className="muted" title={j.error}>{t("v.error")}</span>
                                : "—"}
                          </td>
                          <td>
                            {j.status === "COMPLETED" && (
                              <button
                                className="btn secondary"
                                disabled={busy}
                                title={t("ft.adoptHint")}
                                onClick={() =>
                                  act(async () => {
                                    await adoptFtJob(j.id);
                                    setNote(
                                      t("ft.adopted"),
                                    );
                                  })
                                }
                              >
                                {t("ft.adopt")} →
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <details style={{ margin: "10px 0" }}>
                <summary style={{ cursor: "pointer" }}>{t("ft.addByHand")}</summary>
                <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                  <textarea
                    value={exPrompt}
                    placeholder={t("ft.promptPh")}
                    onChange={(e) => setExPrompt(e.target.value)}
                    rows={2}
                    style={{ padding: "8px 10px", borderRadius: 8 }}
                  />
                  <textarea
                    value={exResponse}
                    placeholder={t("ft.responsePh")}
                    onChange={(e) => setExResponse(e.target.value)}
                    rows={3}
                    style={{ padding: "8px 10px", borderRadius: 8 }}
                  />
                  <button
                    className="btn"
                    disabled={busy || !exPrompt.trim() || !exResponse.trim()}
                    onClick={() =>
                      act(async () => {
                        await addFtExample(selected.id, {
                          prompt: exPrompt.trim(),
                          response: exResponse.trim(),
                        });
                        setExPrompt("");
                        setExResponse("");
                      })
                    }
                  >
                    {t("ft.addExample")}
                  </button>
                </div>
              </details>

              <strong>{t("ft.examples", { n: examples.length })}</strong>
              {examples.length === 0 && (
                <p className="muted" style={{ fontSize: 13 }}>
                  {t("ft.noExamples")}
                </p>
              )}
              <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                {examples.map((ex) => (
                  <div
                    key={ex.id}
                    className="card"
                    style={{ opacity: ex.included ? 1 : 0.5, padding: 10 }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                      <span className="muted" style={{ fontSize: 12 }}>
                        {tv(ex.source)}
                      </span>
                      <label style={{ fontSize: 12, display: "flex", gap: 4, alignItems: "center" }}>
                        <input
                          type="checkbox"
                          checked={ex.included}
                          disabled={busy}
                          onChange={(e) =>
                            act(() => setFtExampleIncluded(ex.id, e.target.checked))
                          }
                        />
                        {t("ft.include")}
                      </label>
                    </div>
                    <div style={{ fontSize: 13, marginTop: 4 }}>
                      <strong>{t("ft.q")}:</strong> {ex.prompt}
                    </div>
                    <div style={{ fontSize: 13, marginTop: 2 }}>
                      <strong>{t("ft.a")}:</strong> {ex.response}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
