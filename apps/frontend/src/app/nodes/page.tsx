"use client";

import { useCallback, useEffect, useState } from "react";
import ZeroTierCard from "@/components/ZeroTierCard";
import {
  Enrollment,
  Node,
  NodeList,
  approveEnrollment,
  createEnrollment,
  fetchEnrollments,
  fetchNodes,
  rejectEnrollment,
  revokeEnrollment,
  rotateEnrollment,
} from "@/lib/api";

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
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [newNodeId, setNewNodeId] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [mintedToken, setMintedToken] = useState<{ node: string; token: string } | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await fetchNodes());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load nodes");
    }
  }, []);

  const loadEnrollments = useCallback(async () => {
    try {
      setEnrollments((await fetchEnrollments()).items);
    } catch {
      /* endpoint always present; ignore transient errors */
    }
  }, []);

  useEffect(() => {
    load();
    loadEnrollments();
    const id = setInterval(() => {
      load();
      loadEnrollments();
    }, 5000);
    return () => clearInterval(id);
  }, [load, loadEnrollments]);

  const invite = async () => {
    if (!newNodeId.trim()) return;
    try {
      const res = await createEnrollment({
        node_id: newNodeId.trim(),
        label: newLabel.trim() || undefined,
      });
      setMintedToken({ node: res.node_id, token: res.token });
      setNewNodeId("");
      setNewLabel("");
      await loadEnrollments();
    } catch (e) {
      setError(e instanceof Error ? e.message : "invite failed");
    }
  };

  const act = async (fn: (id: string) => Promise<unknown>, id: string) => {
    try {
      const r = (await fn(id)) as { token?: string; node_id?: string };
      if (r && r.token && r.node_id) setMintedToken({ node: r.node_id, token: r.token });
      await loadEnrollments();
    } catch (e) {
      setError(e instanceof Error ? e.message : "action failed");
    }
  };

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

      <ZeroTierCard />

      <h2 className="page-title" style={{ fontSize: 20, marginTop: 28 }}>
        Enrollment
      </h2>
      <p className="page-subtitle">
        Per-node credentials with an approval gate (ROADMAP PR 6). Enforced only
        when <code>ATLAS_NODE_ENROLLMENT_REQUIRED=true</code>.
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={newNodeId}
            placeholder="node id (e.g. worker-2)"
            onChange={(e) => setNewNodeId(e.target.value)}
            style={{ flex: "1 1 180px", padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={newLabel}
            placeholder="label (optional)"
            onChange={(e) => setNewLabel(e.target.value)}
            style={{ flex: "1 1 140px", padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={invite} disabled={!newNodeId.trim()}>
            Invite
          </button>
        </div>
        {mintedToken && (
          <div className="card" style={{ marginTop: 10 }}>
            <p className="muted" style={{ fontSize: 12 }}>
              One-time token for <strong>{mintedToken.node}</strong> — copy it now,
              it is not shown again. Set it as <code>ATLAS_NODE_TOKEN</code> on the node.
            </p>
            <pre style={{ overflow: "auto" }}>{mintedToken.token}</pre>
            <button className="btn secondary" onClick={() => setMintedToken(null)}>
              Dismiss
            </button>
          </div>
        )}
      </div>

      {enrollments.length > 0 && (
        <div className="cards">
          {enrollments.map((e) => (
            <div className="card" key={e.id}>
              <div className="status-row">
                <strong>{e.label || e.node_id}</strong>
                <span className={`queue-badge ${e.status === "APPROVED" ? "active" : "idle"}`}>
                  {e.status}
                </span>
              </div>
              <div className="status-row">
                <span className="muted">Node id</span>
                <span className="pill">{e.node_id}</span>
              </div>
              <div className="status-row">
                <span className="muted">Token</span>
                <span>{e.token_prefix}…</span>
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                {e.status !== "APPROVED" && (
                  <button className="btn" onClick={() => act(approveEnrollment, e.id)}>
                    Approve
                  </button>
                )}
                {e.status === "PENDING" && (
                  <button className="btn secondary" onClick={() => act(rejectEnrollment, e.id)}>
                    Reject
                  </button>
                )}
                {e.status === "APPROVED" && (
                  <button className="btn secondary" onClick={() => act(revokeEnrollment, e.id)}>
                    Revoke
                  </button>
                )}
                <button className="btn secondary" onClick={() => act(rotateEnrollment, e.id)}>
                  Rotate
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
