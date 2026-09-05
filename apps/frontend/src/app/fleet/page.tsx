"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Deployment,
  DeploymentSummary,
  advanceDeployment,
  createDeployment,
  fetchDeployment,
  fetchDeployments,
} from "@/lib/api";

function statusClass(s: string): string {
  if (s === "COMPLETED" || s === "HEALTHY") return "queue-badge active";
  if (s === "ROLLED_BACK" || s === "FAILED" || s === "INCOMPATIBLE") return "queue-badge";
  return "queue-badge idle";
}

export default function FleetPage() {
  const [items, setItems] = useState<DeploymentSummary[]>([]);
  const [selected, setSelected] = useState<Deployment | null>(null);
  const [version, setVersion] = useState("");
  const [canary, setCanary] = useState(1);
  const [minCompat, setMinCompat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems((await fetchDeployments()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh the selected deployment while it is in flight.
  useEffect(() => {
    if (!selected || ["COMPLETED", "ROLLED_BACK", "FAILED"].includes(selected.status)) return;
    const id = setInterval(async () => {
      try {
        setSelected(await fetchDeployment(selected.id));
      } catch {
        /* transient */
      }
    }, 2500);
    return () => clearInterval(id);
  }, [selected]);

  const create = async () => {
    if (!version.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const d = await createDeployment({
        target_version: version.trim(),
        canary_count: canary,
        min_compatible: minCompat.trim() || undefined,
      });
      setSelected(d);
      setVersion("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "create failed");
    } finally {
      setBusy(false);
    }
  };

  const advance = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      setSelected(await advanceDeployment(selected.id));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "advance failed");
    } finally {
      setBusy(false);
    }
  };

  const wave = (w: string) => (selected?.targets ?? []).filter((t) => t.wave === w);

  return (
    <div>
      <h1 className="page-title">Fleet Update</h1>
      <p className="page-subtitle">
        Roll a version out to the node fleet safely (ROADMAP PR 21/22): a{" "}
        <strong>canary</strong> wave first, a <strong>health gate</strong> before promoting
        the rest, then a rolling wave — with automatic <strong>rollback</strong> on failure.
        Offline nodes are skipped; nodes below the compatibility floor are skipped with a
        reason. Nodes apply their <code>desired_version</code> and report back.
      </p>

      {error && <p className="error">Error: {error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>New deployment</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <input
            value={version}
            placeholder="Target version (e.g. 1.4.0)"
            onChange={(e) => setVersion(e.target.value)}
            style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
          />
          <label className="muted" style={{ fontSize: 13 }}>
            Canary{" "}
            <input
              type="number"
              min={0}
              value={canary}
              onChange={(e) => setCanary(Math.max(0, Number(e.target.value)))}
              style={{ width: 60, padding: "6px 8px", borderRadius: 8 }}
            />
          </label>
          <input
            value={minCompat}
            placeholder="Min compatible (optional)"
            onChange={(e) => setMinCompat(e.target.value)}
            style={{ flex: "1 1 160px", padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={create} disabled={busy || !version.trim()}>
            Start rollout
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {items.length === 0 && <p className="muted">No deployments yet.</p>}
          {items.map((d) => (
            <div
              key={d.id}
              className={`convo-item ${selected?.id === d.id ? "active" : ""}`}
              onClick={async () => setSelected(await fetchDeployment(d.id))}
            >
              <span className="convo-title">{d.target_version}</span>
              <span className={statusClass(d.status)}>{d.status}</span>
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">Select or start a deployment.</p>
          ) : (
            <div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <span className={statusClass(selected.status)}>{selected.status}</span>
                <span className="pill">→ {selected.target_version}</span>
                {selected.previous_version && (
                  <span className="muted">from {selected.previous_version}</span>
                )}
                {["CANARY", "ROLLING"].includes(selected.status) && (
                  <button
                    className="btn"
                    style={{ marginLeft: "auto" }}
                    disabled={busy}
                    onClick={advance}
                  >
                    Advance / health-gate
                  </button>
                )}
              </div>

              {["canary", "rollout"].map((w) => {
                const ts = wave(w);
                if (ts.length === 0) return null;
                return (
                  <div key={w} style={{ marginTop: 14 }}>
                    <h3 style={{ fontSize: 14, textTransform: "capitalize" }}>{w} wave</h3>
                    <div className="card" style={{ overflowX: "auto" }}>
                      <table className="data">
                        <thead>
                          <tr>
                            <th>Node</th>
                            <th>From</th>
                            <th>Status</th>
                            <th>Detail</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ts.map((t) => (
                            <tr key={t.id}>
                              <td>{t.node_ref}</td>
                              <td>{t.from_version ?? "—"}</td>
                              <td>
                                <span className={statusClass(t.status)}>{t.status}</span>
                              </td>
                              <td className="muted">{t.detail ?? ""}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
