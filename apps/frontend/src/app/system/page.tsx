"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ClusterStatus,
  ComponentStatus,
  SystemMetrics,
  SystemMonitor as SystemMonitorData,
  SystemStatus,
  fetchCluster,
  fetchSystemMetrics,
  fetchSystemMonitor,
  fetchSystemStatus,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function gb(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function dur(seconds: number | null, day: string): string {
  if (seconds == null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d > 0 ? `${d}${day} ${h}h ${m}m` : h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/** One labelled metric with a thin lime bar and a monospace value. */
function Gauge({
  label,
  value,
  percent,
}: {
  label: string;
  value: string;
  percent: number | null | undefined;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div className="status-row" style={{ marginBottom: 4 }}>
        <span className="muted" style={{ fontSize: 12, letterSpacing: 0.5 }}>
          {label}
        </span>
        <span className="metric" style={{ fontSize: 13 }}>
          {value}
        </span>
      </div>
      {percent != null && (
        <div className="progress-bar" aria-hidden>
          <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
        </div>
      )}
    </div>
  );
}

function SystemMonitorCard() {
  const { t } = useI18n();
  const [m, setM] = useState<SystemMonitorData | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const data = await fetchSystemMonitor();
        if (live) {
          setM(data);
          setErr(false);
        }
      } catch {
        if (live) setErr(true);
      }
    };
    load();
    const id = setInterval(load, 2000); // SPEC §11: ~2s refresh
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);

  if (err && !m) return <p className="muted">{t("sys.unavailable")}</p>;
  if (!m) return <p className="muted">{t("common.loading")}</p>;

  const load = m.cpu.load_average;
  return (
    <div className="card" style={{ gridColumn: "1 / -1" }}>
      <h3>{t("sys.monitor")}</h3>
      <div className="stat-grid">
        <div>
          <Gauge
            label="CPU"
            value={m.cpu.percent == null ? "—" : `${m.cpu.percent}%`}
            percent={m.cpu.percent}
          />
          <div className="muted" style={{ fontSize: 11 }}>
            {t("sys.cores", { n: m.cpu.cores ?? "—" })} ·{" "}
            <span className="metric">
              {load ? load.map((x) => x.toFixed(2)).join(" ") : "—"}
            </span>{" "}
            {t("sys.load")}
          </div>
        </div>
        <Gauge
          label="RAM"
          value={`${gb(m.memory.used)} / ${gb(m.memory.total)}`}
          percent={m.memory.percent}
        />
        <Gauge
          label={t("sys.swap")}
          value={m.swap.total ? `${gb(m.swap.used)} / ${gb(m.swap.total)}` : "—"}
          percent={m.swap.percent}
        />
        <Gauge
          label={t("sys.storage", { path: m.storage.path })}
          value={`${gb(m.storage.used)} / ${gb(m.storage.total)}`}
          percent={m.storage.percent}
        />
        <div className="status-row">
          <span className="muted" style={{ fontSize: 12 }}>{t("sys.uptime")}</span>
          <span className="metric" style={{ fontSize: 13 }}>{dur(m.uptime_seconds, t("common.dayShort"))}</span>
        </div>
        <div className="status-row">
          <span className="muted" style={{ fontSize: 12 }}>{t("sys.cpuTemp")}</span>
          <span className="metric" style={{ fontSize: 13 }}>
            {m.cpu_temperature == null ? "—" : `${m.cpu_temperature} °C`}
          </span>
        </div>
      </div>
      {m.gpu.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {m.gpu.map((g, i) => (
            <div className="status-row" key={i}>
              <span className="muted" style={{ fontSize: 12 }}>GPU · {g.name ?? "—"}</span>
              <span className="metric" style={{ fontSize: 13 }}>
                {g.temperature != null ? `${g.temperature} °C` : "—"}
                {g.vram_total != null ? ` · ${g.vram_total} MB` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusDot({ status }: { status: ComponentStatus["status"] }) {
  return <span className={`dot ${status === "healthy" ? "ok" : "bad"}`} />;
}

export default function SystemStatusPage() {
  const { t, tv } = useI18n();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [cluster, setCluster] = useState<ClusterStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, m, c] = await Promise.all([
        fetchSystemStatus(),
        fetchSystemMetrics(),
        fetchCluster(),
      ]);
      setStatus(s);
      setMetrics(m);
      setCluster(c);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div>
      <h1 className="page-title">{t("nav.system")}</h1>
      <p className="page-subtitle">
        {t("sys.subtitle")}
      </p>

      {error && <p className="error">{t("common.backendError", { error })}</p>}

      <div className="cards">
        <SystemMonitorCard />
        <div className="card">
          <h3>{t("sys.components")}</h3>
          {!status && !error && <p className="muted">{t("common.loading")}</p>}
          {status &&
            status.components.map((c) => (
              <div className="status-row" key={c.name}>
                <span style={{ textTransform: "capitalize" }}>{c.name}</span>
                <span className="badge">
                  {typeof c.latency_ms === "number" && (
                    <span className="muted">{c.latency_ms} ms</span>
                  )}
                  <StatusDot status={c.status} />
                  {tv(c.status)}
                </span>
              </div>
            ))}
        </div>

        <div className="card">
          <h3>{t("sys.overview")}</h3>
          {status && (
            <>
              <div className="status-row">
                <span>{t("sys.overall")}</span>
                <span className="badge">
                  <span
                    className={`dot ${
                      status.status === "healthy" ? "ok" : "warn"
                    }`}
                  />
                  {tv(status.status)}
                </span>
              </div>
              <div className="status-row">
                <span>{t("sys.version")}</span>
                <span className="pill">{status.version}</span>
              </div>
              <div className="status-row">
                <span>{t("sys.environment")}</span>
                <span className="pill">{status.environment}</span>
              </div>
            </>
          )}
        </div>

        <div className="card">
          <h3>{t("nav.tasks")}</h3>
          {metrics && Object.keys(metrics.tasks_by_status).length === 0 && (
            <p className="muted">{t("sys.noTasks")}</p>
          )}
          {metrics &&
            Object.entries(metrics.tasks_by_status).map(([k, v]) => (
              <div className="status-row" key={k}>
                <span>{tv(k)}</span>
                <span className="pill">{v}</span>
              </div>
            ))}
          {metrics && (
            <div className="status-row">
              <span>{t("dash.nodesOnline")}</span>
              <span className="pill">{metrics.nodes_online}</span>
            </div>
          )}
          {metrics && (
            <div className="status-row">
              <span>{t("dash.approvals")}</span>
              <span className="pill">{metrics.approvals_pending}</span>
            </div>
          )}
        </div>

        <div className="card">
          <h3>{t("sys.cluster")}</h3>
          {cluster && (
            <>
              <div className="status-row">
                <span>{t("sys.mode")}</span>
                <span className="pill">
                  {cluster.ha_enabled ? t("sys.ha") : t("sys.single")}
                </span>
              </div>
              <div className="status-row">
                <span>{t("sys.thisInstance")}</span>
                <span className="badge">
                  {cluster.instance_id}
                  {cluster.is_leader && (
                    <span className="queue-badge active" style={{ marginLeft: 6 }}>
                      {t("sys.leader")}
                    </span>
                  )}
                </span>
              </div>
              {cluster.members.map((m) => (
                <div className="status-row" key={m.id}>
                  <span>{m.id}{m.self ? ` (${t("sys.you")})` : ""}</span>
                  <span className={`queue-badge ${m.leader ? "active" : "idle"}`}>
                    {m.leader ? t("sys.leader") : t("sys.follower")}
                  </span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
