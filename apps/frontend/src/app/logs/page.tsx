"use client";

import { useCallback, useEffect, useState } from "react";
import { LogEntry, fetchLogs } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function LogsPage() {
  const { t } = useI18n();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const limit = 50;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchLogs(filter || undefined, limit, offset);
      setLogs(res.items);
      setTotal(res.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load logs");
    } finally {
      setLoading(false);
    }
  }, [filter, offset, limit]);

  useEffect(() => {
    load();
  }, [load]);

  const levelColors: Record<string, string> = {
    INFO: "var(--ok)",
    WARN: "var(--warn)",
    ERROR: "var(--bad)",
  };

  return (
    <div>
      <h1 className="page-title">Logs</h1>
      <p className="page-subtitle">Control plane activity & system events</p>

      {error && <p className="error">{error}</p>}

      {/* Filter bar */}
      <div className="card" style={{ marginBottom: 16, display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="text"
          placeholder="Filter by message or level (e.g. 'error', 'deepseek')…"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setOffset(0);
          }}
          style={{ flex: 1, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--panel)", color: "var(--text)", fontSize: 14 }}
        />
        <button className="btn secondary" onClick={() => load()} disabled={loading} style={{ fontSize: 13, padding: "8px 14px" }}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Logs table */}
      <table className="data" style={{ marginBottom: 16 }}>
        <thead>
          <tr>
            <th style={{ width: "160px" }}>Timestamp</th>
            <th style={{ width: "60px" }}>Level</th>
            <th style={{ width: "100px" }}>Source</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log, i) => (
            <tr key={i}>
              <td>
                <span className="mono" style={{ fontSize: 11 }}>
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
              </td>
              <td>
                <span style={{ fontWeight: 600, color: levelColors[log.level] || "var(--text)" }}>
                  {log.level}
                </span>
              </td>
              <td>
                <span className="mono" style={{ fontSize: 12 }}>
                  {log.source}
                </span>
              </td>
              <td style={{ color: "var(--text)" }}>{log.message}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {logs.length === 0 && !loading && (
        <p className="muted" style={{ textAlign: "center", padding: "20px" }}>
          No logs found
        </p>
      )}

      {/* Pagination */}
      {total > 0 && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, color: "var(--muted)" }}>
          <span>
            Showing {offset + 1}–{Math.min(offset + limit, total)} of {total}
          </span>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              className="btn secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
              style={{ padding: "6px 10px", fontSize: 12 }}
            >
              ← Previous
            </button>
            <button
              className="btn secondary"
              disabled={offset + limit >= total}
              onClick={() => setOffset(offset + limit)}
              style={{ padding: "6px 10px", fontSize: 12 }}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
