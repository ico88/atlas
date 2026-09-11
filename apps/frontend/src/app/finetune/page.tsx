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

function jobBadge(status: string): string {
  if (status === "COMPLETED") return "queue-badge active";
  if (status === "FAILED" || status === "CANCELLED") return "queue-badge";
  return "queue-badge idle";
}

export default function FineTunePage() {
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
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

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
      setError(e instanceof Error ? e.message : "action failed");
    } finally {
      setBusy(false);
    }
  };

  const included = examples.filter((e) => e.included).length;
  const enoughData = readiness ? included >= readiness.recommended_min_examples : false;

  return (
    <div>
      <h1 className="page-title">Fine-tuning (self-improvement)</h1>
      <p className="page-subtitle">
        Turn ATLAS&apos;s own <strong>good answers</strong> into a better model — locally.
        Curate a dataset from thumbs-up chat replies, train a <strong>LoRA adapter</strong> on a
        GPU node, then adopt it through the same <em>eval + canary</em> guardrails as any other
        change. Nothing is sent anywhere; the model only becomes the default if it actually wins.
      </p>

      {error && <p className="error">Error: {error}</p>}
      {note && (
        <p className="muted" style={{ fontSize: 13 }}>
          {note}
        </p>
      )}

      {readiness && (
        <div className="card" style={{ marginBottom: 16 }}>
          <strong>Readiness</strong>
          <div className="status-row" style={{ marginTop: 6 }}>
            <span className="muted">GPU training node</span>
            <span className={readiness.gpu_node_available ? "queue-badge active" : "queue-badge"}>
              {readiness.gpu_node_available
                ? `✓ ${readiness.gpu_node_names.join(", ")}`
                : "none online"}
            </span>
          </div>
          <div className="status-row">
            <span className="muted">Positive feedback available</span>
            <span>{readiness.positive_feedback}</span>
          </div>
          {!readiness.gpu_node_available && (
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              Fine-tuning trains on a real GPU. Add a node that advertises the{" "}
              <code>gpu</code> capability (e.g. the Zotac), or run a job as a dry-run to test the
              pipeline end-to-end without training.
            </p>
          )}
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>New dataset</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <input
            value={dsName}
            placeholder="Name (e.g. Good IT answers)"
            onChange={(e) => setDsName(e.target.value)}
            style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={baseModel}
            placeholder="Base model (optional, blank = default)"
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
            Create
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {datasets.length === 0 && <p className="muted">No datasets yet.</p>}
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
            <p className="muted">Select or create a dataset.</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>{selected.name}</h3>
              <div className="status-row">
                <span className="muted">Base model</span>
                <span>{selected.base_model || "current default"}</span>
              </div>
              <div className="status-row">
                <span className="muted">Included examples</span>
                <span className={enoughData ? "queue-badge active" : "queue-badge idle"}>
                  {included}
                  {readiness ? ` / ${readiness.recommended_min_examples} recommended` : ""}
                </span>
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
                <button
                  className="btn"
                  disabled={busy}
                  title="Harvest thumbs-up chat replies into this dataset"
                  onClick={() =>
                    act(async () => {
                      const r = await curateFtDataset(selected.id);
                      setNote(
                        r.added > 0
                          ? `Added ${r.added} example(s) from positive feedback.`
                          : "No new positively-rated replies to harvest yet — give 👍 to good chat answers first.",
                      );
                    })
                  }
                >
                  Harvest from feedback
                </button>
                <button
                  className="btn"
                  disabled={busy || included === 0}
                  title={
                    readiness?.gpu_node_available
                      ? "Dispatch a LoRA training job to the GPU node"
                      : "No GPU node online — the job will wait for one (or fail honestly)"
                  }
                  onClick={() =>
                    act(async () => {
                      await createFtJob({ dataset_id: selected.id });
                      setNote("Training job dispatched — it runs on a GPU node.");
                    })
                  }
                >
                  Train LoRA adapter
                </button>
              </div>

              {jobs.length > 0 && (
                <div className="card" style={{ background: "var(--panel-2)", margin: "10px 0" }}>
                  <strong>Training jobs</strong>
                  <table className="data" style={{ width: "100%", marginTop: 6 }}>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id}>
                          <td>{j.adapter_name}</td>
                          <td>
                            <span className={jobBadge(j.status)}>{j.status}</span>
                          </td>
                          <td>{j.example_count} ex.</td>
                          <td>
                            {j.metrics?.final_loss != null
                              ? `loss ${String(j.metrics.final_loss)}`
                              : j.error
                                ? <span className="muted" title={j.error}>error</span>
                                : "—"}
                          </td>
                          <td>
                            {j.status === "COMPLETED" && (
                              <button
                                className="btn secondary"
                                disabled={busy}
                                title="Propose this adapter as the new default (eval + canary gated)"
                                onClick={() =>
                                  act(async () => {
                                    await adoptFtJob(j.id);
                                    setNote(
                                      "Created an improvement proposal — review it under Improvements; it must beat the baseline and pass the canary health gate.",
                                    );
                                  })
                                }
                              >
                                Adopt →
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
                <summary style={{ cursor: "pointer" }}>Add an example by hand</summary>
                <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                  <textarea
                    value={exPrompt}
                    placeholder="Prompt (user)"
                    onChange={(e) => setExPrompt(e.target.value)}
                    rows={2}
                    style={{ padding: "8px 10px", borderRadius: 8 }}
                  />
                  <textarea
                    value={exResponse}
                    placeholder="Ideal response (assistant)"
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
                    Add example
                  </button>
                </div>
              </details>

              <strong>Examples ({examples.length})</strong>
              {examples.length === 0 && (
                <p className="muted" style={{ fontSize: 13 }}>
                  None yet — harvest from feedback or add one by hand.
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
                        {ex.source}
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
                        include
                      </label>
                    </div>
                    <div style={{ fontSize: 13, marginTop: 4 }}>
                      <strong>Q:</strong> {ex.prompt}
                    </div>
                    <div style={{ fontSize: 13, marginTop: 2 }}>
                      <strong>A:</strong> {ex.response}
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
