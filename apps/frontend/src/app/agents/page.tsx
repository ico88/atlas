"use client";

import { useEffect, useState } from "react";
import { NodeAgents, fetchAgents } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function AgentsPage() {
  const { t, tv } = useI18n();
  const [nodes, setNodes] = useState<NodeAgents[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchAgents();
        setNodes(res.nodes);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("common.failed"));
      } finally {
        setLoading(false);
      }
    })();
  }, [t]);

  const statusDot = (state: string) => {
    if (state === "UP") return "🟢";
    return "🔴";
  };

  const agentStatusColor = (status: string) => {
    if (status === "running") return "var(--ok)";
    if (status === "idle") return "var(--muted)";
    return "var(--bad)";
  };

  return (
    <div>
      <h1 className="page-title">{t("nav.agents")}</h1>
      <p className="page-subtitle">{t("agents.subtitle")}</p>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">{t("common.loading")}</p>}

      <div className="cards">
        {nodes.map((node) => (
          <div className="card" key={node.id}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ fontSize: 18 }}>{statusDot(node.state)}</span>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, textTransform: "none" }}>
                {node.id}
              </h3>
              <span className="pill" style={{ marginLeft: "auto", fontSize: 11 }}>
                {tv(node.state)}
              </span>
            </div>

            {node.agents.length === 0 ? (
              <p className="muted" style={{ fontSize: 12, margin: 0 }}>{t("agents.none")}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {node.agents.map((agent, i) => (
                  <div
                    key={i}
                    style={{
                      padding: "10px",
                      background: "var(--panel-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                      <span
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          background: agentStatusColor(agent.status),
                        }}
                      />
                      <strong style={{ color: "var(--text)" }}>{agent.name}</strong>
                      <span
                        style={{
                          marginLeft: "auto",
                          fontSize: 10,
                          color: agentStatusColor(agent.status),
                          fontWeight: 600,
                        }}
                      >
                        {tv(agent.status)}
                      </span>
                    </div>
                    <div style={{ color: "var(--muted)", fontSize: 11 }}>{agent.task}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {nodes.length === 0 && !loading && (
        <p className="muted" style={{ textAlign: "center", padding: "40px 20px" }}>
          {t("agents.noNodes")}
        </p>
      )}
    </div>
  );
}
