"use client";

import { useEffect, useState } from "react";
import { fetchSystemStatus, SystemStatus } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const QUICK_ACTIONS = [
  { icon: "🌐", cmd: "/web", label: "Web Search", desc: "answer using web search" },
  { icon: "💾", cmd: "/remember", label: "Remember", desc: "save a memory" },
  { icon: "🔍", cmd: "/recall", label: "Recall", desc: "find saved memories" },
  { icon: "🤖", cmd: "/model", label: "Model", desc: "pick the AI model" },
  { icon: "🖥", cmd: "/status", label: "Status", desc: "system health" },
  { icon: "🛰", cmd: "/nodes", label: "Nodes", desc: "list infrastructure" },
];

export default function AlmaWelcome() {
  const { t } = useI18n();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const s = await fetchSystemStatus();
        setStatus(s);
      } catch {
        /* backend starting */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const statusDot = status?.status === "healthy" ? "🟢" : "🟡";

  return (
    <div className="alma-welcome">
      <div className="welcome-header">
        <h1 style={{ margin: "0 0 8px", fontSize: 32, fontWeight: 800 }}>ALMA</h1>
        <p style={{ margin: 0, color: "var(--muted)", fontSize: 14 }}>
          Local AI assistant on ATLAS
        </p>
      </div>

      {/* Status pill */}
      {!loading && status && (
        <div className="welcome-status">
          <span>{statusDot}</span>
          <span className="status-text">
            {status.status === "healthy" ? "All systems healthy" : "Degraded service"}
          </span>
          <span className="status-version">{status.version}</span>
        </div>
      )}

      {/* Quick actions grid */}
      <div className="welcome-actions">
        <p style={{ margin: "18px 0 10px", fontSize: 12, textTransform: "uppercase", color: "var(--muted)", letterSpacing: "0.5px", fontWeight: 600 }}>
          Quick Start
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 8 }}>
          {QUICK_ACTIONS.map((a) => (
            <button
              key={a.cmd}
              className="action-card"
              onClick={() => {
                const input = document.querySelector(".composer input") as HTMLInputElement;
                if (input) {
                  input.value = a.cmd + " ";
                  input.focus();
                }
              }}
            >
              <div style={{ fontSize: 20, marginBottom: 4 }}>{a.icon}</div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 2 }}>
                {a.label}
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>{a.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Suggestions / help text */}
      <div className="welcome-help">
        <p style={{ margin: "18px 0 10px", fontSize: 12, textTransform: "uppercase", color: "var(--muted)", letterSpacing: "0.5px", fontWeight: 600 }}>
          Commands
        </p>
        <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--text)" }}>
          <div>
            <strong>/web</strong> · answer using web search with cites
          </div>
          <div>
            <strong>/remember</strong> · save a note to your memory
          </div>
          <div>
            <strong>/recall</strong> · find memories related to your query
          </div>
          <div>
            <strong>/model</strong> · pick an AI model or list available
          </div>
          <div>
            <strong>/status</strong> · check system + runtime health
          </div>
          <div>
            <strong>/nodes</strong> · list infrastructure nodes
          </div>
          <div>
            <strong>/task</strong> · create a task
          </div>
          <div>
            <strong>/help</strong> · show full help
          </div>
        </div>
      </div>
    </div>
  );
}
