"use client";

import { useCallback, useEffect, useState } from "react";
import {
  NodeMetric,
  OllamaPerfRow,
  fetchNodeMetrics,
  fetchOllamaPerf,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function relativeTime(iso: string | null | undefined, t: (k: string, v?: Record<string, number>) => string): string {
  if (!iso) return t("common.never");
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return t("common.agoS", { n: secs });
  if (secs < 3600) return t("common.agoM", { n: Math.round(secs / 60) });
  return t("common.agoH", { n: Math.round(secs / 3600) });
}

export default function ResourcesPage() {
  const { t } = useI18n();
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
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div>
      <h1 className="page-title">{t("nav.resources")}</h1>
      <p className="page-subtitle">
        {t("res.subtitle")}
      </p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      <h2 className="page-title" style={{ fontSize: 20 }}>{t("nav.nodes")}</h2>
      {nodes.length === 0 ? (
        <p className="muted">{t("res.none")}</p>
      ) : (
        <div className="cards">
          {nodes.map((m) => (
            <div className="card" key={m.id}>
              <div className="status-row">
                <strong>{m.node_id}</strong>
                <span className="muted">{relativeTime(m.created_at, t)}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("res.load")}</span>
                <span>{m.load1 ?? "—"}</span>
              </div>
              <div className="status-row">
                <span className="muted">{t("res.freeRam")}</span>
                <span>{m.ram_free_mb != null ? `${m.ram_free_mb} MB` : "—"}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <h2 className="page-title" style={{ fontSize: 20, marginTop: 28 }}>
        {t("res.perf")}
      </h2>
      {perf.length === 0 ? (
        <p className="muted">{t("res.noPerf")}</p>
      ) : (
        <div className="card" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--muted)" }}>
                <th style={{ padding: "6px 8px" }}>{t("models.provider")}</th>
                <th style={{ padding: "6px 8px" }}>{t("res.model")}</th>
                <th style={{ padding: "6px 8px" }}>{t("res.calls")}</th>
                <th style={{ padding: "6px 8px" }}>{t("res.avg")}</th>
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
