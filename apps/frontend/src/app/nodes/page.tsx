"use client";

import { useCallback, useEffect, useState } from "react";
import { Node, NodeList, fetchNodes } from "@/lib/api";

function capList(caps?: Record<string, unknown> | null): string {
  if (!caps) return "—";
  const active = Object.entries(caps)
    .filter(([, v]) => Boolean(v))
    .map(([k]) => k);
  return active.length ? active.join(", ") : "—";
}

function relativeTime(iso?: string | null): string {
  if (!iso) return "never";
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
  return `${Math.round(secs / 3600)}h ago`;
}

export default function NodesPage() {
  const [data, setData] = useState<NodeList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await fetchNodes());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load nodes");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div>
      <h1 className="page-title">Nodes</h1>
      <p className="page-subtitle">
        Registered worker nodes and their live heartbeat status (spec §8).
      </p>

      {error && <p className="error">Unable to reach backend: {error}</p>}

      {data && (
        <p className="muted" style={{ marginBottom: 16 }}>
          {data.online} of {data.total} node{data.total === 1 ? "" : "s"} online
        </p>
      )}

      {data && data.items.length === 0 && !error && (
        <div className="card">
          <p className="muted">
            No nodes registered yet. Install a node with{" "}
            <code>./infrastructure/scripts/install.sh --role node</code> and start
            it with <code>docker compose -f docker-compose.node.yml up -d</code>.
          </p>
        </div>
      )}

      <div className="cards">
        {data?.items.map((node: Node) => (
          <div className="card" key={node.id}>
            <div className="status-row">
              <strong>{node.label || node.node_id}</strong>
              <span className="badge">
                <span className={`dot ${node.online ? "ok" : "bad"}`} />
                {node.online ? "online" : "offline"}
              </span>
            </div>
            <div className="status-row">
              <span className="muted">Node id</span>
              <span className="pill">{node.node_id}</span>
            </div>
            <div className="status-row">
              <span className="muted">Host</span>
              <span>{node.hostname || "—"}</span>
            </div>
            <div className="status-row">
              <span className="muted">Capabilities</span>
              <span>{capList(node.capabilities)}</span>
            </div>
            <div className="status-row">
              <span className="muted">Last heartbeat</span>
              <span>{relativeTime(node.last_heartbeat)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
