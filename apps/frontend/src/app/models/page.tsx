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

// Curated open models that run locally via Ollama, far better than llama3.2:1b.
// Sizes are approximate download sizes; on a CPU-only host smaller = faster.
const RECOMMENDED: { name: string; size: string; note: string; tier: string }[] = [
  { name: "qwen2.5:3b", size: "~2 GB", note: "★ Recommended — great in Italian, 3B", tier: "balanced" },
  { name: "llama3.2:3b", size: "~2 GB", note: "Fast and solid, 3B", tier: "fast" },
  { name: "gemma2:2b", size: "~1.6 GB", note: "Very fast, 2B", tier: "fast" },
  { name: "phi3.5", size: "~2.2 GB", note: "Strong reasoning for its size, 3.8B", tier: "balanced" },
  { name: "qwen2.5:7b", size: "~4.7 GB", note: "Best quality, slower on CPU, 7B", tier: "quality" },
  { name: "mistral:7b", size: "~4.1 GB", note: "Solid generalist, 7B", tier: "quality" },
];

export default function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [hardware, setHardware] = useState<Record<string, unknown> | null>(null);
  const [defaultModel, setDefault] = useState("");
  const [pullName, setPullName] = useState("");
  const [pulls, setPulls] = useState<Record<string, { state: string; status?: string; completed?: number; total?: number }>>({});
  const [wantDefault, setWantDefault] = useState<string[]>([]);
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
        // A "download & use" finished -> make it the default, then stop wanting it.
        for (const name of wantDefault) {
          if (st[name]?.state === "done") {
            try {
              const r = await setDefaultModel(name);
              setDefault(r.default_model);
            } catch {
              /* ignore */
            }
            setWantDefault((w) => w.filter((n) => n !== name));
          }
        }
        if (Object.values(st).every((p) => p.state === "done" || p.state === "error")) {
          load();
        }
      } catch {
        /* ignore */
      }
    }, 1500);
    return () => clearInterval(id);
  }, [pulls, load, wantDefault]);

  const makeDefault = async (name: string) => {
    try {
      const r = await setDefaultModel(name);
      setDefault(r.default_model);
    } catch (err) {
      setError(err instanceof Error ? err.message : "set default failed");
    }
  };

  const pull = async (name: string, asDefault = false) => {
    const clean = name.trim();
    if (!clean) return;
    try {
      await pullModel(clean);
      setPulls((p) => ({ ...p, [clean]: { state: "starting", status: "queued" } }));
      if (asDefault) setWantDefault((w) => (w.includes(clean) ? w : [...w, clean]));
    } catch (err) {
      setError(err instanceof Error ? err.message : "pull failed");
    }
  };

  const doPull = async () => {
    await pull(pullName);
    setPullName("");
  };

  const isPulling = (name: string) =>
    pulls[name]?.state === "pulling" || pulls[name]?.state === "starting";

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
        <h3 style={{ marginTop: 0 }}>Recommended models</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          Better open models than <code>llama3.2:1b</code> that still run locally via
          Ollama. On a CPU-only host, smaller = faster; 7B gives the best quality but
          is slower.
        </p>
        <div className="rec-grid">
          {RECOMMENDED.map((r) => {
            const installed = models.some((m) => m.name === r.name && m.available);
            const pulling = isPulling(r.name);
            return (
              <div key={r.name} className={`rec-card tier-${r.tier}`}>
                <div className="rec-head">
                  <strong>{r.name}</strong>
                  <span className="pill">{r.size}</span>
                </div>
                <div className="muted" style={{ fontSize: 12, margin: "4px 0 10px" }}>
                  {r.note}
                </div>
                {installed ? (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span className="queue-badge active">installed</span>
                    {r.name !== defaultModel && (
                      <button className="btn secondary" onClick={() => makeDefault(r.name)}>
                        Use as default
                      </button>
                    )}
                    {r.name === defaultModel && <span className="pill">⭐ default</span>}
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button className="btn" disabled={pulling} onClick={() => pull(r.name, true)}>
                      {pulling ? "Downloading…" : "Download & use"}
                    </button>
                    <button
                      className="btn secondary"
                      disabled={pulling}
                      onClick={() => pull(r.name, false)}
                    >
                      Download
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Download any model</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          Pull any Ollama model by name (e.g. <code>qwen2.5:3b</code>, <code>gemma2:2b</code>).
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
