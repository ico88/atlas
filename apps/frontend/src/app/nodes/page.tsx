"use client";

import { useCallback, useEffect, useState } from "react";
import NodeWizard from "@/components/NodeWizard";
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
import { useI18n } from "@/lib/i18n";

function capList(caps?: Record<string, unknown> | null): string {
  if (!caps) return "—";
  const active = Object.entries(caps)
    .filter(([, v]) => Boolean(v))
    .map(([k]) => k);
  return active.length ? active.join(", ") : "—";
}

function relativeTime(iso: string | null | undefined, t: (k: string, v?: Record<string, number>) => string): string {
  if (!iso) return t("common.never");
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return t("common.agoS", { n: secs });
  if (secs < 3600) return t("common.agoM", { n: Math.round(secs / 60) });
  return t("common.agoH", { n: Math.round(secs / 3600) });
}

export default function NodesPage() {
  const { t, tv } = useI18n();
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
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  }, [t]);

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
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  const act = async (fn: (id: string) => Promise<unknown>, id: string) => {
    try {
      const r = (await fn(id)) as { token?: string; node_id?: string };
      if (r && r.token && r.node_id) setMintedToken({ node: r.node_id, token: r.token });
      await loadEnrollments();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("nav.nodes")}</h1>
      <p className="page-subtitle">{t("nodes.subtitle")}</p>

      {error && <p className="error">{t("common.backendError", { error })}</p>}

      <NodeWizard />

      {data && (
        <p className="muted" style={{ marginBottom: 16 }}>
          {t("nodes.onlineCount", { online: data.online, total: data.total })}
        </p>
      )}

      {data && data.items.length === 0 && !error && (
        <div className="card">
          <p className="muted">
            {t("nodes.empty1")} <code>./infrastructure/scripts/install.sh --role node</code>{" "}
            {t("nodes.empty2")} <code>docker compose -f docker-compose.node.yml up -d</code>.
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
                {node.online ? t("common.online") : t("common.offline")}
              </span>
            </div>
            <div className="status-row">
              <span className="muted">{t("nodes.nodeId")}</span>
              <span className="pill">{node.node_id}</span>
            </div>
            <div className="status-row">
              <span className="muted">{t("nodes.host")}</span>
              <span>{node.hostname || "—"}</span>
            </div>
            <div className="status-row">
              <span className="muted">{t("nodes.capabilities")}</span>
              <span>{capList(node.capabilities)}</span>
            </div>
            <div className="status-row">
              <span className="muted">{t("nodes.lastHeartbeat")}</span>
              <span>{relativeTime(node.last_heartbeat, t)}</span>
            </div>
          </div>
        ))}
      </div>

      <ZeroTierCard />

      <h2 className="page-title" style={{ fontSize: 20, marginTop: 28 }}>
        {t("nodes.enrollment")}
      </h2>
      <p className="page-subtitle">
        {t("nodes.enrollmentHelp")} <code>ATLAS_NODE_ENROLLMENT_REQUIRED=true</code>.
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={newNodeId}
            placeholder={t("nodes.nodeIdPh")}
            onChange={(e) => setNewNodeId(e.target.value)}
            style={{ flex: "1 1 180px", padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={newLabel}
            placeholder={t("nodes.labelPh")}
            onChange={(e) => setNewLabel(e.target.value)}
            style={{ flex: "1 1 140px", padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={invite} disabled={!newNodeId.trim()}>
            {t("nodes.invite")}
          </button>
        </div>
        {mintedToken && (
          <div className="card" style={{ marginTop: 10 }}>
            <p className="muted" style={{ fontSize: 12 }}>
              {t("nodes.tokenFor")} <strong>{mintedToken.node}</strong> — {t("nodes.tokenOnce")}{" "}
              <code>ATLAS_NODE_TOKEN</code>.
            </p>
            <pre style={{ overflow: "auto" }}>{mintedToken.token}</pre>
            <button className="btn secondary" onClick={() => setMintedToken(null)}>
              {t("common.dismiss")}
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
                  {tv(e.status)}
                </span>
              </div>
              <div className="status-row">
                <span className="muted">{t("nodes.nodeId")}</span>
                <span className="pill">{e.node_id}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("nodes.token")}</span>
                <span>{e.token_prefix}…</span>
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                {e.status !== "APPROVED" && (
                  <button className="btn" onClick={() => act(approveEnrollment, e.id)}>
                    {t("common.approve")}
                  </button>
                )}
                {e.status === "PENDING" && (
                  <button className="btn secondary" onClick={() => act(rejectEnrollment, e.id)}>
                    {t("common.reject")}
                  </button>
                )}
                {e.status === "APPROVED" && (
                  <button className="btn secondary" onClick={() => act(revokeEnrollment, e.id)}>
                    {t("common.revoke")}
                  </button>
                )}
                <button className="btn secondary" onClick={() => act(rotateEnrollment, e.id)}>
                  {t("nodes.rotate")}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
