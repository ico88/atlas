"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ComplianceReport,
  SystemMetrics,
  SystemStatus,
  fetchCompliance,
  fetchDefaultModel,
  fetchSystemMetrics,
  fetchSystemStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="stat">
      <div className={`stat-value ${tone ?? ""}`}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

const LINKS: { href: string; key: string }[] = [
  { href: "/", key: "nav.chat" },
  { href: "/queries", key: "nav.queries" },
  { href: "/nodes", key: "nav.nodes" },
  { href: "/fleet", key: "nav.fleet" },
  { href: "/compliance", key: "nav.compliance" },
  { href: "/models", key: "nav.models" },
  { href: "/maintenance", key: "nav.maintenance" },
  { href: "/improvements", key: "nav.improvements" },
  { href: "/reviews", key: "nav.reviews" },
  { href: "/knowledge", key: "nav.knowledge" },
  { href: "/evals", key: "nav.evals" },
  { href: "/settings", key: "nav.settings" },
];

export default function DashboardPage() {
  const { t } = useI18n();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [compliance, setCompliance] = useState<ComplianceReport | null>(null);
  const [model, setModel] = useState<string>("");

  const load = useCallback(async () => {
    const [s, m, c, d] = await Promise.allSettled([
      fetchSystemStatus(),
      fetchSystemMetrics(),
      fetchCompliance(),
      fetchDefaultModel(),
    ]);
    if (s.status === "fulfilled") setStatus(s.value);
    if (m.status === "fulfilled") setMetrics(m.value);
    if (c.status === "fulfilled") setCompliance(c.value);
    if (d.status === "fulfilled") setModel(d.value.default_model || "");
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const running = metrics?.tasks_by_status?.["RUNNING"] ?? 0;
  const queued = metrics?.tasks_by_status?.["QUEUED"] ?? 0;
  const compliancePct =
    compliance && typeof compliance.summary["compliance_pct"] === "number"
      ? `${Math.round((compliance.summary["compliance_pct"] as number) * 100)}%`
      : "—";
  const healthy = status?.status === "healthy";

  return (
    <div>
      <h1 className="page-title">{t("nav.dashboard")}</h1>
      <p className="page-subtitle">{t("dash.subtitle")}</p>

      <div className="stat-grid">
        <Stat
          label={t("dash.health")}
          value={status ? (healthy ? t("dash.healthy") : t("dash.degraded")) : "—"}
          tone={status ? (healthy ? "ok" : "warn") : ""}
        />
        <Stat
          label={t("dash.nodesOnline")}
          value={metrics ? `${metrics.nodes_online}/${metrics.nodes_total}` : "—"}
        />
        <Stat label={t("dash.compliance")} value={compliancePct} />
        <Stat label={t("dash.tasksRunning")} value={String(running)} />
        <Stat label={t("dash.tasksQueued")} value={String(queued)} />
        <Stat
          label={t("dash.approvals")}
          value={String(metrics?.approvals_pending ?? 0)}
          tone={metrics && metrics.approvals_pending > 0 ? "warn" : ""}
        />
      </div>

      <div className="cards" style={{ marginTop: 20 }}>
        <div className="card">
          <h3>{t("dash.system")}</h3>
          {status ? (
            status.components.map((c) => (
              <div key={c.name} className="status-row">
                <span className="muted">{c.name}</span>
                <span className="badge">
                  <span className={`dot ${c.status === "healthy" ? "ok" : "bad"}`} />
                  {c.status}
                </span>
              </div>
            ))
          ) : (
            <p className="muted">{t("common.loading")}</p>
          )}
          <div className="status-row">
            <span className="muted">{t("dash.model")}</span>
            <span className="pill">{model || t("chat.auto")}</span>
          </div>
        </div>

        <div className="card">
          <h3>{t("dash.quickLinks")}</h3>
          <div className="quick-links">
            {LINKS.map((l) => (
              <Link key={l.href} href={l.href} className="quick-link">
                {t(l.key)}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
