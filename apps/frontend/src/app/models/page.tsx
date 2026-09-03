"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ModelInfo,
  deleteModel,
  fetchDefaultModel,
  fetchHardware,
  fetchModels,
  fetchPullStatus,
  pullModel,
  refreshModels,
  setDefaultModel,
} from "@/lib/api";

export default function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [hardware, setHardware] = useState<Record<string, unknown> | null>(null);
  const [defaultModel, setDefault] = useState("");
  const [pullName, setPullName] = useState("");
  const [pulls, setPulls] = useState<Record<string, { state: string; status?: string; completed?: number; total?: number }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, hw, def] = await Promise.all([
        fetchModels(),
        fetchHardware(),
        fetchDefaultModel(),
      ]);
      setModels(m.items);
      setHardware(hw);
      setDefault(def.default_model || "");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll pull progress while any download is active.
  useEffect(() => {
    const active = Object.values(pulls).some((p) => p.state === "pulling" || p.state === "starting");
    if (!active) return;
    const id = setInterval(async () => {
      try {
        const st = (await fetchPullStatus()).items;
        setPulls(st);
        if (Object.values(st).every((p) => p.state === "done" || p.state === "error")) {
          load();
        }
      } catch {
        /* ignore */
      }
    }, 1500);
    return () => clearInterval(id);
  }, [pulls, load]);

  const makeDefault = async (name: string) => {
    try {
      const r = await setDefaultModel(name);
      setDefault(r.default_model);
    } catch (err) {
      setError(err instanceof Error ? err.message : "set default failed");
    }
  };

  const doPull = async () => {
    if (!pullName.trim()) return;
    try {
      await pullModel(pullName.trim());
      setPulls((p) => ({ ...p, [pullName.trim()]: { state: "starting", status: "queued" } }));
      setPullName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "pull failed");
    }
  };

  const doDelete = async (name: string) => {
    if (!confirm(`Delete model ${name}?`)) return;
    try {
      const m = await deleteModel(name);
      setModels(m.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "delete failed");
    }
  };

  const doRefresh = async () => {
    setBusy(true);
    try {
      const m = await refreshModels();
      setModels(m.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  };

  const hw = hardware ?? {};

  function gpuSummary(gpu: unknown): string {
    if (!gpu || typeof gpu !== "object") return "none";
    const g = gpu as { count?: number; devices?: Array<{ name?: string; vendor?: string }> };
    if (!g.count) return "none";
    const first = g.devices?.[0];
    const label = first?.name || first?.vendor || "GPU";
    return g.count > 1 ? `${label} (+${g.count - 1})` : label;
  }

  return (
    <div>
      <h1 className="page-title">Models</h1>
      <p className="page-subtitle">
        Model registry and host hardware scan (spec §16 M2).
      </p>

      {error && <p className="error">{error}</p>}

      <div className="cards" style={{ marginBottom: 20 }}>
        <div className="card">
          <h3>Host hardware</h3>
          <div className="status-row">
            <span className="muted">Platform</span>
            <span>
              {String(hw.platform ?? "—")} {String(hw.arch ?? "")}
            </span>
          </div>
          <div className="status-row">
            <span className="muted">CPU cores</span>
            <span className="pill">{String(hw.cpu_cores ?? "—")}</span>
          </div>
          <div className="status-row">
            <span className="muted">RAM total</span>
            <span className="pill">
              {hw.ram_total_mb ? `${hw.ram_total_mb} MB` : "—"}
            </span>
          </div>
          <div className="status-row">
            <span className="muted">GPU</span>
            <span>{gpuSummary(hw.gpu)}</span>
          </div>
          <div className="status-row">
            <span className="muted">Ollama backend</span>
            <span className="pill">{String(hw.recommended_ollama_backend ?? "—")}</span>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Download a model</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          Pull an Ollama model by name (e.g. <code>llama3.2:1b</code>, <code>qwen2.5:0.5b</code>).
          Small models are much faster on CPU.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={pullName}
            placeholder="model:tag"
            onChange={(e) => setPullName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doPull()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={doPull} disabled={!pullName.trim()}>
            Download
          </button>
        </div>
        {Object.entries(pulls).map(([name, p]) => (
          <div key={name} className="queue-item" style={{ marginTop: 8 }}>
            <strong>{name}</strong>{" "}
            <span className="meta">
              {p.state}
              {p.status ? ` · ${p.status}` : ""}
              {p.completed && p.total
                ? ` · ${Math.round((p.completed / p.total) * 100)}%`
                : ""}
            </span>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ color: "var(--muted)" }}>
          Registered models{" "}
          {defaultModel && <span className="pill">default: {defaultModel}</span>}
        </h3>
        <button className="btn secondary" onClick={doRefresh} disabled={busy}>
          {busy ? "Refreshing…" : "Refresh from providers"}
        </button>
      </div>

      <div className="card" style={{ marginTop: 10, overflowX: "auto" }}>
        {models.length === 0 ? (
          <p className="muted">
            No models yet. Click “Refresh from providers” to discover them.
          </p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>Provider</th>
                <th>Family</th>
                <th>Context</th>
                <th>Available</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>
                    {m.name === defaultModel ? "⭐ " : ""}
                    {m.name}
                  </td>
                  <td>{m.provider}</td>
                  <td>{m.family ?? "—"}</td>
                  <td>{m.context_length ?? "—"}</td>
                  <td>
                    <span className={`dot ${m.available ? "ok" : "bad"}`} />{" "}
                    {m.available ? "yes" : "no"}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      {m.name !== defaultModel && (
                        <button className="btn secondary" onClick={() => makeDefault(m.name)}>
                          Set default
                        </button>
                      )}
                      {m.provider === "ollama" && (
                        <button className="btn secondary" onClick={() => doDelete(m.name)}>
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
