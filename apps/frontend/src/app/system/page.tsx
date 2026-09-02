"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ComponentStatus,
  SystemMetrics,
  SystemStatus,
  fetchSystemMetrics,
  fetchSystemStatus,
} from "@/lib/api";

function StatusDot({ status }: { status: ComponentStatus["status"] }) {
  return <span className={`dot ${status === "healthy" ? "ok" : "bad"}`} />;
}

export default function SystemStatusPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([
        fetchSystemStatus(),
        fetchSystemMetrics(),
      ]);
      setStatus(s);
      setMetrics(m);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div>
      <h1 className="page-title">System Status</h1>
      <p className="page-subtitle">
        Live health of the ATLAS control plane and its dependencies.
      </p>

      {error && <p className="error">Unable to reach backend: {error}</p>}

      <div className="cards">
        <div className="card">
          <h3>Components</h3>
          {!status && !error && <p className="muted">Loading…</p>}
          {status &&
            status.components.map((c) => (
              <div className="status-row" key={c.name}>
                <span style={{ textTransform: "capitalize" }}>{c.name}</span>
                <span className="badge">
                  {typeof c.latency_ms === "number" && (
                    <span className="muted">{c.latency_ms} ms</span>
                  )}
                  <StatusDot status={c.status} />
                  {c.status}
                </span>
              </div>
            ))}
        </div>

        <div className="card">
          <h3>Overview</h3>
          {status && (
            <>
              <div className="status-row">
                <span>Overall</span>
                <span className="badge">
                  <span
                    className={`dot ${
                      status.status === "healthy" ? "ok" : "warn"
                    }`}
                  />
                  {status.status}
                </span>
              </div>
              <div className="status-row">
                <span>Version</span>
                <span className="pill">{status.version}</span>
              </div>
              <div className="status-row">
                <span>Environment</span>
                <span className="pill">{status.environment}</span>
              </div>
            </>
          )}
        </div>

        <div className="card">
          <h3>Tasks</h3>
          {metrics && Object.keys(metrics.tasks_by_status).length === 0 && (
            <p className="muted">No tasks yet.</p>
          )}
          {metrics &&
            Object.entries(metrics.tasks_by_status).map(([k, v]) => (
              <div className="status-row" key={k}>
                <span>{k}</span>
                <span className="pill">{v}</span>
              </div>
            ))}
          {metrics && (
            <div className="status-row">
              <span>Nodes online</span>
              <span className="pill">{metrics.nodes_online}</span>
            </div>
          )}
          {metrics && (
            <div className="status-row">
              <span>Approvals pending</span>
              <span className="pill">{metrics.approvals_pending}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
