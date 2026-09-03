"use client";

import { useCallback, useEffect, useState } from "react";
import {
  NodeMetric,
  OllamaPerfRow,
  fetchNodeMetrics,
  fetchOllamaPerf,
} from "@/lib/api";

function relativeTime(iso?: string | null): string {
  if (!iso) return "never";
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  return `${Math.round(secs / 3600)}h ago`;
}

export default function ResourcesPage() {
  const [nodes, setNodes] = useState<NodeMetric[]>([]);
  const [perf, setPerf] = useState<OllamaPerfRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([fetchNodeMetrics(), fetchOllamaPerf()]);
      setNodes(m);
      setPerf(p.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load metrics");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div>
      <h1 className="page-title">Resources</h1>
      <p className="page-subtitle">
        Node telemetry from heartbeats and Ollama latency (ROADMAP PR 12).
      </p>

      {error && <p className="error">Error: {error}</p>}

      <h2 className="page-title" style={{ fontSize: 20 }}>Nodes</h2>
      {nodes.length === 0 ? (
        <p className="muted">No telemetry yet — nodes report on heartbeat.</p>
      ) : (
        <div className="cards">
          {nodes.map((m) => (
            <div className="card" key={m.id}>
              <div className="status-row">
                <strong>{m.node_id}</strong>
                <span className="muted">{relativeTime(m.created_at)}</span>
              </div>
              <div className="status-row">
                <span className="muted">Load (1m)</span>
                <span>{m.load1 ?? "—"}</span>
              </div>
              <div className="status-row">
                <span className="muted">Free RAM</span>
                <span>{m.ram_free_mb != null ? `${m.ram_free_mb} MB` : "—"}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 className="page-title" style={{ fontSize: 20, marginTop: 28 }}>
        Ollama performance
      </h2>
      {perf.length === 0 ? (
        <p className="muted">No inference recorded yet.</p>
      ) : (
        <div className="card" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--muted)" }}>
                <th style={{ padding: "6px 8px" }}>Provider</th>
                <th style={{ padding: "6px 8px" }}>Model</th>
                <th style={{ padding: "6px 8px" }}>Calls</th>
                <th style={{ padding: "6px 8px" }}>Avg ms</th>
                <th style={{ padding: "6px 8px" }}>Min</th>
                <th style={{ padding: "6px 8px" }}>Max</th>
              </tr>
            </thead>
            <tbody>
              {perf.map((r, i) => (
                <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "6px 8px" }}>{r.provider ?? "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{r.model ?? "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{r.count}</td>
                  <td style={{ padding: "6px 8px" }}>{r.avg_latency_ms ?? "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{r.min_latency_ms ?? "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{r.max_latency_ms ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
