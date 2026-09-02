"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ModelInfo,
  fetchHardware,
  fetchModels,
  refreshModels,
} from "@/lib/api";

export default function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [hardware, setHardware] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, hw] = await Promise.all([fetchModels(), fetchHardware()]);
      setModels(m.items);
      setHardware(hw);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ color: "var(--muted)" }}>Registered models</h3>
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
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td>{m.provider}</td>
                  <td>{m.family ?? "—"}</td>
                  <td>{m.context_length ?? "—"}</td>
                  <td>
                    <span className={`dot ${m.available ? "ok" : "bad"}`} />{" "}
                    {m.available ? "yes" : "no"}
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
